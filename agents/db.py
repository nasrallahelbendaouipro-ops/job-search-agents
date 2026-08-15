"""Accès Supabase pour le service d'agents.

Le service utilise la clé `service_role`, qui contourne la RLS. Toutes les
requêtes filtrent donc explicitement sur `owner_id` — c'est la seule barrière
d'isolation côté Python, et elle est appliquée ici plutôt que dans chaque
appelant.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from supabase import Client, create_client

from .config import get_settings
from .models import Criteria, RawOffer, StoredOffer


class Database:
    def __init__(self, client: Client | None = None, owner_id: str | None = None):
        settings = get_settings()
        self.owner_id = owner_id or settings.owner_id
        self.client = client or create_client(
            settings.supabase_url, settings.supabase_service_role_key
        )

    # -- Critères ------------------------------------------------------------

    def active_criteria(self) -> Criteria:
        """Charge la version active des critères.

        Lève si aucune version n'est active : mieux vaut un échec explicite
        qu'un pipeline qui tourne sur des valeurs par défaut silencieuses et
        candidate à des offres hors profil.
        """
        res = (
            self.client.table("profile_criteria")
            .select("criteria")
            .eq("owner_id", self.owner_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise RuntimeError(
                "Aucune version active dans profile_criteria. "
                "Exécute supabase/seed.sql, ou active une version depuis /criteres."
            )
        return Criteria.model_validate(res.data[0]["criteria"])

    # -- Exécutions ----------------------------------------------------------

    def start_run(self) -> str:
        res = (
            self.client.table("agent_runs")
            .insert({"owner_id": self.owner_id, "status": "running"})
            .execute()
        )
        return res.data[0]["id"]

    def finish_run(
        self,
        run_id: str,
        status: str,
        *,
        offers_scraped: int = 0,
        offers_matched: int = 0,
        letters_generated: int = 0,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.client.table("agent_runs").update(
            {
                "status": status,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "offers_scraped": offers_scraped,
                "offers_matched": offers_matched,
                "letters_generated": letters_generated,
                "errors": errors or [],
            }
        ).eq("id", run_id).eq("owner_id", self.owner_id).execute()

    # -- Offres --------------------------------------------------------------

    def known_source_ids(self, source: str) -> set[str]:
        """Identifiants déjà en base pour cette source.

        Utilisé avant tout appel LLM : une offre déjà vue ne doit être ni
        re-filtrée ni re-rédigée. C'est le principal levier de coût.
        """
        res = (
            self.client.table("offers")
            .select("source_offer_id")
            .eq("owner_id", self.owner_id)
            .eq("source", source)
            .execute()
        )
        return {row["source_offer_id"] for row in res.data}

    def insert_offers(self, offers: list[RawOffer], run_id: str) -> list[StoredOffer]:
        """Insère les offres neuves et renvoie les lignes créées.

        `upsert` sur la contrainte de déduplication : si deux exécutions se
        chevauchent, la seconde ne plante pas sur un doublon.
        """
        if not offers:
            return []

        payload = []
        for offer in offers:
            row = offer.model_dump(mode="json")
            row["owner_id"] = self.owner_id
            row["run_id"] = run_id
            payload.append(row)

        res = (
            self.client.table("offers")
            .upsert(payload, on_conflict="owner_id,source,source_offer_id", ignore_duplicates=True)
            .execute()
        )
        return [StoredOffer.model_validate(row) for row in res.data]

    def update_match(self, offer_id: str, *, status: str, score: int, reason: str) -> None:
        self.client.table("offers").update(
            {"match_status": status, "match_score": score, "match_reason": reason}
        ).eq("id", offer_id).eq("owner_id", self.owner_id).execute()

    def update_apply_channel(
        self, offer_id: str, *, channel: str, apply_email: str | None
    ) -> None:
        self.client.table("offers").update(
            {"apply_channel": channel, "apply_email": apply_email}
        ).eq("id", offer_id).eq("owner_id", self.owner_id).execute()

    # -- Candidatures --------------------------------------------------------

    def create_application(
        self,
        *,
        offer_id: str,
        run_id: str,
        status: str,
        letter_text: str,
        letter_storage_path: str,
        cv_document_id: str | None,
    ) -> str:
        res = (
            self.client.table("applications")
            .upsert(
                {
                    "owner_id": self.owner_id,
                    "offer_id": offer_id,
                    "run_id": run_id,
                    "status": status,
                    "letter_text": letter_text,
                    "letter_storage_path": letter_storage_path,
                    "cv_document_id": cv_document_id,
                },
                on_conflict="offer_id",
            )
            .execute()
        )
        return res.data[0]["id"]

    # -- Documents -----------------------------------------------------------

    def cv_documents(self) -> list[dict[str, Any]]:
        res = (
            self.client.table("documents")
            .select("*")
            .eq("owner_id", self.owner_id)
            .eq("kind", "cv")
            .execute()
        )
        return res.data

    def upload_letter(self, *, filename: str, content: bytes) -> str:
        """Dépose le .docx dans le bucket `letters` et renvoie son chemin.

        Le premier segment du chemin est l'owner_id : c'est ce que les policies
        Storage vérifient pour autoriser la lecture depuis le dashboard.
        """
        path = f"{self.owner_id}/{filename}"
        self.client.storage.from_("letters").upload(
            path,
            content,
            {
                "content-type": (
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
                "upsert": "true",
            },
        )
        return path

    # -- Usage LLM -----------------------------------------------------------

    def record_usage(
        self,
        *,
        run_id: str,
        agent: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_eur: float,
    ) -> None:
        self.client.table("llm_usage").insert(
            {
                "owner_id": self.owner_id,
                "run_id": run_id,
                "agent": agent,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_eur": cost_eur,
            }
        ).execute()

    def spend_this_month_eur(self) -> float:
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        res = (
            self.client.table("llm_usage")
            .select("cost_eur")
            .eq("owner_id", self.owner_id)
            .gte("created_at", start.isoformat())
            .execute()
        )
        return sum(float(row["cost_eur"]) for row in res.data)
