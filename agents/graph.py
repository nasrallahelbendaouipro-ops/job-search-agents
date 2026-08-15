"""Orchestration du pipeline nocturne avec LangGraph.

    scraper → pré-filtre → filtre LLM → rédacteur → candidature

Chaque nœud écrit son résultat en base avant de passer au suivant : si le
rédacteur échoue, les offres récupérées et filtrées restent acquises et la
prochaine exécution ne les repaiera pas.

Le dépassement de budget n'est pas une erreur du pipeline mais une fin
attendue : l'exécution se termine en `budget_exceeded` avec tout ce qui a été
produit jusque-là.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from .apply import decide
from .config import get_settings
from .db import Database
from .filter import classify
from .llm.budget import BudgetExceeded, BudgetGuard
from .models import Criteria, RawOffer, StoredOffer
from .prefilter import apply_prefilter
from .sources.base import JobSource
from .sources.france_travail import FranceTravailSource
from .writer import choose_cv, write_letter

logger = logging.getLogger(__name__)


def _keep_last(_: Any, new: Any) -> Any:
    return new


class PipelineState(TypedDict, total=False):
    run_id: str
    criteria: Criteria
    scraped: Annotated[list[RawOffer], _keep_last]
    candidates: Annotated[list[RawOffer], _keep_last]
    stored: Annotated[list[StoredOffer], _keep_last]
    matched: Annotated[list[StoredOffer], _keep_last]
    letters_generated: int
    errors: Annotated[list[dict[str, Any]], _keep_last]
    budget_exceeded: bool


def build_sources(settings) -> list[JobSource]:
    """Sources actives.

    Phase 1 : France Travail uniquement (API officielle, gratuite). Les
    scrapers Playwright s'ajouteront ici, un par un, une fois le pipeline
    stabilisé. Aucun scraper LinkedIn ou Indeed n'est prévu.
    """
    return [
        FranceTravailSource(
            settings.france_travail_client_id,
            settings.france_travail_client_secret,
        )
    ]


class Pipeline:
    def __init__(self, db: Database | None = None):
        self.settings = get_settings()
        self.db = db or Database()
        self.sources = build_sources(self.settings)
        self.budget: BudgetGuard | None = None

    # -- Nœuds ---------------------------------------------------------------

    async def node_scrape(self, state: PipelineState) -> PipelineState:
        criteria = state["criteria"]
        errors = list(state.get("errors", []))
        all_offers: list[RawOffer] = []

        for source in self.sources:
            try:
                offers = await source.fetch(criteria)
                logger.info("%s : %d offres récupérées.", source.name, len(offers))
                all_offers.extend(offers)
            except Exception as exc:  # une source morte ne tue pas le run
                logger.exception("Échec de la source %s.", source.name)
                errors.append({"stage": "scrape", "source": source.name, "error": str(exc)})

        return {"scraped": all_offers, "errors": errors}

    async def node_prefilter(self, state: PipelineState) -> PipelineState:
        criteria = state["criteria"]
        scraped = state.get("scraped", [])

        # Les identifiants déjà connus sont retirés avant tout appel LLM.
        known: set[str] = set()
        for source in self.sources:
            known |= self.db.known_source_ids(source.name)

        result = apply_prefilter(scraped, criteria, known_ids=known)
        logger.info(
            "Pré-filtre : %d offres retenues, %d écartées sans coût.",
            len(result.kept),
            len(result.rejected),
        )
        for offer, reason in result.rejected[:20]:
            logger.debug("  écartée — %s : %s", offer.title, reason)

        return {"candidates": result.kept}

    async def node_store(self, state: PipelineState) -> PipelineState:
        """Insère les offres candidates avant le filtre LLM.

        Écrire ici plutôt qu'après le filtre garantit qu'un échec du LLM ne
        fait pas re-récupérer les mêmes offres la nuit suivante.
        """
        stored = self.db.insert_offers(state.get("candidates", []), state["run_id"])
        logger.info("%d offres neuves insérées.", len(stored))
        return {"stored": stored}

    async def node_classify(self, state: PipelineState) -> PipelineState:
        assert self.budget is not None
        stored = state.get("stored", [])
        errors = list(state.get("errors", []))

        if not stored:
            return {"matched": [], "errors": errors}

        try:
            verdicts = await classify(
                stored,  # type: ignore[arg-type]
                state["criteria"],
                self.budget,
                max_offers=self.settings.max_offers_to_classify_per_run,
            )
        except BudgetExceeded as exc:
            logger.warning("Filtre interrompu : %s", exc)
            errors.append({"stage": "classify", "error": str(exc)})
            return {"matched": [], "errors": errors, "budget_exceeded": True}

        by_id = {o.source_offer_id: o for o in stored}
        matched: list[StoredOffer] = []

        for verdict in verdicts:
            offer = by_id.get(verdict.source_offer_id)
            if offer is None:
                continue
            status = "matched" if verdict.keep else "rejected"
            self.db.update_match(
                offer.id, status=status, score=verdict.score, reason=verdict.reason
            )
            if verdict.keep:
                matched.append(offer)

        # Les meilleures d'abord : si le plafond de lettres coupe la liste,
        # autant qu'il coupe les moins bonnes.
        scores = {v.source_offer_id: v.score for v in verdicts}
        matched.sort(key=lambda o: scores.get(o.source_offer_id, 0), reverse=True)

        return {"matched": matched, "errors": errors}

    async def node_write(self, state: PipelineState) -> PipelineState:
        assert self.budget is not None
        matched = state.get("matched", [])
        errors = list(state.get("errors", []))
        criteria = state["criteria"]

        if not matched:
            return {"letters_generated": 0, "errors": errors}

        limit = self.settings.max_letters_per_run
        if len(matched) > limit:
            logger.info(
                "Plafond par exécution : %d lettres sur %d offres retenues.",
                limit,
                len(matched),
            )
            matched = matched[:limit]

        cv_documents = self.db.cv_documents()
        generated = 0
        budget_hit = False

        for offer in matched:
            try:
                letter = await write_letter(offer, self.budget)
            except BudgetExceeded as exc:
                logger.warning("Rédaction interrompue : %s", exc)
                errors.append({"stage": "write", "error": str(exc)})
                budget_hit = True
                break
            except Exception as exc:
                logger.exception("Échec de rédaction pour l'offre %s.", offer.id)
                errors.append({"stage": "write", "offer_id": offer.id, "error": str(exc)})
                continue

            decision = decide(offer, criteria)
            self.db.update_apply_channel(
                offer.id, channel=decision.channel, apply_email=decision.apply_email
            )

            storage_path = self.db.upload_letter(
                filename=letter.filename, content=letter.docx
            )
            cv = choose_cv(offer, cv_documents)
            self.db.create_application(
                offer_id=offer.id,
                run_id=state["run_id"],
                status=decision.application_status,
                letter_text=letter.text,
                letter_storage_path=storage_path,
                cv_document_id=cv["id"] if cv else None,
            )
            generated += 1

        return {
            "letters_generated": generated,
            "errors": errors,
            "budget_exceeded": budget_hit or state.get("budget_exceeded", False),
        }

    # -- Assemblage ----------------------------------------------------------

    def compile(self):
        graph = StateGraph(PipelineState)
        graph.add_node("scrape", self.node_scrape)
        graph.add_node("prefilter", self.node_prefilter)
        graph.add_node("store", self.node_store)
        graph.add_node("classify", self.node_classify)
        graph.add_node("write", self.node_write)

        graph.set_entry_point("scrape")
        graph.add_edge("scrape", "prefilter")
        graph.add_edge("prefilter", "store")

        # Rien de neuf à classer : on saute directement à la fin plutôt que
        # d'ouvrir une session LLM pour zéro offre.
        graph.add_conditional_edges(
            "store",
            lambda s: "classify" if s.get("stored") else END,
            {"classify": "classify", END: END},
        )
        graph.add_conditional_edges(
            "classify",
            lambda s: END if s.get("budget_exceeded") or not s.get("matched") else "write",
            {"write": "write", END: END},
        )
        graph.add_edge("write", END)

        return graph.compile()

    # -- Exécution -----------------------------------------------------------

    async def run(self) -> dict[str, Any]:
        criteria = self.db.active_criteria()
        run_id = self.db.start_run()
        self.budget = BudgetGuard(self.db, run_id)

        logger.info("Exécution %s démarrée.", run_id)

        try:
            final = await self.compile().ainvoke(
                {"run_id": run_id, "criteria": criteria, "errors": []}
            )
        except Exception as exc:
            logger.exception("Échec du pipeline.")
            self.db.finish_run(
                run_id, "failed", errors=[{"stage": "pipeline", "error": str(exc)}]
            )
            raise

        status = "budget_exceeded" if final.get("budget_exceeded") else "succeeded"
        summary = {
            "run_id": run_id,
            "status": status,
            "offers_scraped": len(final.get("scraped", [])),
            "offers_matched": len(final.get("matched", [])),
            "letters_generated": final.get("letters_generated", 0),
            "spend_this_month_eur": round(self.budget.spent_eur, 4),
            "errors": final.get("errors", []),
        }

        self.db.finish_run(
            run_id,
            status,
            offers_scraped=summary["offers_scraped"],
            offers_matched=summary["offers_matched"],
            letters_generated=summary["letters_generated"],
            errors=summary["errors"],
        )
        logger.info("Exécution %s terminée : %s", run_id, summary)
        return summary
