"""Étage 2 du filtre : classification LLM des offres survivantes.

Les offres arrivent ici après `prefilter.apply_prefilter`, qui a déjà écarté
tout ce qui pouvait l'être sans jugement. Le LLM traite par lots pour amortir
le prompt système, qui est entièrement construit à partir du JSONB
`profile_criteria` — modifier les critères depuis le dashboard change donc le
comportement du filtre sans toucher au code.
"""

from __future__ import annotations

import json
import logging

from .llm.budget import BudgetGuard
from .llm.client import FilterLLM
from .models import Criteria, MatchVerdict, RawOffer

logger = logging.getLogger(__name__)

#: Offres par appel. Assez pour amortir le prompt système, assez peu pour que
#: le modèle garde une attention correcte sur chacune.
BATCH_SIZE = 10

#: Longueur de description envoyée au modèle. Les offres françaises tournent
#: autour de 2 000 caractères ; au-delà on paie surtout du boilerplate légal.
DESCRIPTION_CHARS = 1500


SYSTEM_PROMPT = """Tu es un assistant de recrutement qui évalue la pertinence d'offres d'emploi pour UN candidat précis.

## Profil du candidat
Nasr Allah El Bendaoui, 25 ans, basé en France.
- Master Data & IA (École Centrale de Lyon, 2025), diplôme d'ingénieur (EMSI).
- Stage Safran Aircraft Engines : Power BI, Python, LSTM.
- CDI Akkodis : MBOM/EBOM pour Alstom et Stellantis, dashboards KPI.
- Postes visés en priorité : Data Analyst, Analytics Engineer (CDI). Postes d'ingénieur industriel acceptés.
- Langues : français (natif), anglais (professionnel). Pas d'allemand courant.

## Ses critères
{criteria_block}

## Ta tâche
Pour chaque offre, attribue un score de 0 à 100 et décide si elle mérite une candidature.

Barème :
- 85-100 : correspondance forte (intitulé visé, séniorité junior/confirmée adaptée, secteur ciblé).
- 65-84  : correspondance correcte, quelques écarts acceptables.
- 40-64  : lien réel avec le profil mais écart net (séniorité, techno, secteur).
- 0-39   : hors profil.

Pénalise nettement :
- une expérience requise supérieure à 4 ans (le candidat sort d'études) ;
- une exigence d'allemand courant ;
- un poste principalement commercial, support ou de management d'équipe.

`keep` doit être true si et seulement si le score est >= {min_score}.
`reason` : une phrase en français, concrète, qui cite ce qui a décidé du score. Pas de généralités.

Réponds UNIQUEMENT avec un objet JSON de cette forme, sans texte autour :
{{"verdicts": [{{"source_offer_id": "...", "score": 0, "keep": false, "reason": "..."}}]}}
Un élément par offre reçue, dans le même ordre."""


def _criteria_block(criteria: Criteria) -> str:
    """Rend les critères sous une forme lisible par le modèle."""
    lines = [
        f"- Intitulés recherchés : {', '.join(criteria.titles_include) or 'aucun'}",
        f"- Intitulés à éviter : {', '.join(criteria.titles_exclude) or 'aucun'}",
        f"- Compétences valorisées : {', '.join(criteria.keywords_bonus) or 'aucune'}",
        f"- À proscrire : {', '.join(criteria.keywords_exclude) or 'rien'}",
        f"- Types de contrat : {', '.join(criteria.contract_types) or 'tous'}",
        f"- Secteurs visés : {', '.join(criteria.sectors) or 'tous'}",
        f"- Langues maîtrisées : {', '.join(criteria.languages_ok)}",
        f"- Préférence télétravail : {criteria.remote_preference}",
    ]

    for country in sorted(criteria.countries, key=lambda c: c.priority):
        cities = ", ".join(country.cities) if country.cities else "tout le pays"
        floor = criteria.salary_min_by_country.get(country.code)
        salary = f", salaire annuel brut minimum {floor:.0f}" if floor else ""
        lines.append(
            f"- Pays {country.code} (priorité {country.priority}) : {cities}{salary}"
        )

    return "\n".join(lines)


def _offer_block(offer: RawOffer) -> dict:
    description = (offer.description or "")[:DESCRIPTION_CHARS]
    return {
        "source_offer_id": offer.source_offer_id,
        "titre": offer.title,
        "entreprise": offer.company,
        "ville": offer.city,
        "pays": offer.country,
        "contrat": offer.contract_type,
        "salaire": offer.salary_raw,
        "teletravail": offer.remote_policy,
        "description": description,
    }


def _parse_verdicts(payload: str, batch: list[RawOffer]) -> list[MatchVerdict]:
    """Lit la réponse du modèle, en tolérant les écarts de format.

    Une offre absente ou illisible est conservée avec un score neutre plutôt
    qu'écartée : un bug de parsing ne doit pas faire disparaître silencieusement
    une offre potentiellement bonne.
    """
    try:
        data = json.loads(payload)
        raw_verdicts = data.get("verdicts", [])
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Réponse du filtre illisible, lot conservé par défaut.")
        raw_verdicts = []

    by_id: dict[str, dict] = {
        str(v.get("source_offer_id")): v
        for v in raw_verdicts
        if isinstance(v, dict) and v.get("source_offer_id") is not None
    }

    verdicts: list[MatchVerdict] = []
    for offer in batch:
        raw = by_id.get(offer.source_offer_id)
        if raw is None:
            logger.warning(
                "Offre %s absente de la réponse du filtre — conservée pour revue.",
                offer.source_offer_id,
            )
            verdicts.append(
                MatchVerdict(
                    source_offer_id=offer.source_offer_id,
                    score=50,
                    keep=True,
                    reason="Non classée par le filtre — à revoir manuellement.",
                )
            )
            continue

        try:
            score = max(0, min(100, int(raw.get("score", 0))))
            verdicts.append(
                MatchVerdict(
                    source_offer_id=offer.source_offer_id,
                    score=score,
                    keep=bool(raw.get("keep", False)),
                    reason=str(raw.get("reason", "")).strip() or "Sans justification.",
                )
            )
        except (TypeError, ValueError):
            verdicts.append(
                MatchVerdict(
                    source_offer_id=offer.source_offer_id,
                    score=50,
                    keep=True,
                    reason="Verdict illisible — à revoir manuellement.",
                )
            )

    return verdicts


async def classify(
    offers: list[RawOffer],
    criteria: Criteria,
    budget: BudgetGuard,
    *,
    llm: FilterLLM | None = None,
    max_offers: int | None = None,
) -> list[MatchVerdict]:
    """Classe les offres par lots et renvoie un verdict par offre."""
    if not offers:
        return []

    if max_offers is not None and len(offers) > max_offers:
        logger.info(
            "Plafond par exécution : %d offres sur %d classées.", max_offers, len(offers)
        )
        offers = offers[:max_offers]

    llm = llm or FilterLLM()
    system = SYSTEM_PROMPT.format(
        criteria_block=_criteria_block(criteria),
        min_score=criteria.min_score_to_keep,
    )

    verdicts: list[MatchVerdict] = []
    for start in range(0, len(offers), BATCH_SIZE):
        batch = offers[start : start + BATCH_SIZE]
        budget.check()

        user = json.dumps(
            {"offres": [_offer_block(o) for o in batch]}, ensure_ascii=False
        )
        response = await llm.complete(system, user)
        budget.record(
            agent="filter",
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )

        verdicts.extend(_parse_verdicts(response.text, batch))

    kept = sum(1 for v in verdicts if v.keep)
    logger.info("Filtre LLM : %d offres retenues sur %d classées.", kept, len(verdicts))
    return verdicts
