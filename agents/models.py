"""Modèles partagés par tous les nœuds du pipeline.

`Criteria` est le miroir Python du JSONB `profile_criteria.criteria`, dont la
source de vérité côté formulaire est `web/lib/schemas/criteria.ts`. Les deux
doivent rester alignés — le test `test_criteria_matches_seed` vérifie que le
seed SQL se charge bien dans ce modèle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RemotePreference = Literal["any", "prefer_remote", "prefer_hybrid", "prefer_onsite"]
ApplyChannel = Literal["email", "form", "easy_apply", "account_required", "unknown"]


class CountryTarget(BaseModel):
    code: str  # 'FR', 'MA', 'DE'
    priority: int = 1
    cities: list[str] = Field(default_factory=list)  # vide = tout le pays


class Criteria(BaseModel):
    """Critères de matching, entièrement pilotés depuis le dashboard."""

    titles_include: list[str] = Field(default_factory=list)
    titles_exclude: list[str] = Field(default_factory=list)
    keywords_bonus: list[str] = Field(default_factory=list)
    keywords_exclude: list[str] = Field(default_factory=list)
    countries: list[CountryTarget] = Field(default_factory=list)
    languages_ok: list[str] = Field(default_factory=lambda: ["fr", "en"])
    salary_min_by_country: dict[str, float] = Field(default_factory=dict)
    remote_preference: RemotePreference = "any"
    contract_types: list[str] = Field(default_factory=lambda: ["CDI"])
    sectors: list[str] = Field(default_factory=list)
    min_score_to_keep: int = 65
    auto_send_enabled: bool = False

    def country_codes(self) -> list[str]:
        return [c.code for c in self.countries]

    def cities_for(self, code: str) -> list[str]:
        for c in self.countries:
            if c.code == code:
                return c.cities
        return []


class RawOffer(BaseModel):
    """Offre telle que renvoyée par une source, avant tout filtrage.

    Chaque source est responsable de la normalisation vers ce format — le reste
    du pipeline ne connaît jamais le format natif d'un site.
    """

    source: str
    source_offer_id: str
    country: str
    title: str
    url: str
    company: str | None = None
    city: str | None = None
    description: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_raw: str | None = None
    contract_type: str | None = None
    remote_policy: str | None = None
    posted_at: datetime | None = None
    apply_email: str | None = None
    apply_channel: ApplyChannel = "unknown"


class StoredOffer(RawOffer):
    """Offre après insertion en base : porte son uuid."""

    id: str


class MatchVerdict(BaseModel):
    """Résultat de l'étage LLM du filtre."""

    source_offer_id: str
    score: int = Field(ge=0, le=100)
    keep: bool
    reason: str
