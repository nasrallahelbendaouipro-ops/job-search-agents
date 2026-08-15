"""Configuration lue depuis l'environnement.

Aucun critère de matching ici : ce fichier ne porte que des secrets et des
réglages d'infrastructure. Les critères vivent en base (`profile_criteria`)
pour rester modifiables depuis le dashboard.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    owner_id: str

    # France Travail
    france_travail_client_id: str = ""
    france_travail_client_secret: str = ""

    # Rédaction des lettres
    anthropic_api_key: str = ""
    writer_model: str = "claude-haiku-4-5"

    # Filtrage low-cost (API compatible OpenAI)
    filter_provider: str = "deepseek"
    filter_api_key: str = ""
    filter_model: str = "deepseek-v4-flash"
    filter_base_url: str = "https://api.deepseek.com/v1"

    # Plafonds
    monthly_budget_eur: float = 10.0
    max_letters_per_run: int = 10
    max_offers_to_classify_per_run: int = 120

    # Sécurité interne
    internal_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
