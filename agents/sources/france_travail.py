"""Source France Travail — API officielle « Offres d'emploi v2 ».

Documentation : https://francetravail.io/produits-partages/catalogue/offres-emploi
Compte développeur gratuit ; il faut souscrire à l'API et récupérer un couple
client_id / client_secret.

C'est la seule source de la Phase 1 : API officielle, gratuite, sans scraping.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from ..models import Criteria, RawOffer
from .base import JobSource

logger = logging.getLogger(__name__)

TOKEN_URL = (
    "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
    "?realm=%2Fpartenaire"
)
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SCOPE = "api_offresdemploiv2 o2dsoffre"

#: L'API plafonne à 150 résultats par requête (en-tête `Range`).
PAGE_SIZE = 150
#: Nombre maximum de pages par mot-clé — garde-fou contre une requête trop large.
MAX_PAGES = 4

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


class FranceTravailSource(JobSource):
    name = "france_travail"
    country = "FR"

    def __init__(self, client_id: str, client_secret: str, *, lookback_hours: int = 26):
        self._client_id = client_id
        self._client_secret = client_secret
        # 26 h plutôt que 24 : recouvrement volontaire entre deux exécutions
        # nocturnes, pour ne pas rater une offre publiée pile à la frontière.
        # La déduplication en base absorbe le surplus.
        self._lookback_hours = lookback_hours
        self._token: str | None = None
        self._token_expiry: datetime = datetime.min.replace(tzinfo=timezone.utc)

    # -- Authentification ----------------------------------------------------

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        """Renvoie un token valide, en réutilisant celui en cache si possible."""
        now = datetime.now(timezone.utc)
        if self._token and now < self._token_expiry:
            return self._token

        res = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": SCOPE,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        res.raise_for_status()
        payload = res.json()
        self._token = payload["access_token"]
        # Marge de 60 s pour ne pas envoyer une requête avec un token qui
        # expire pendant le vol.
        self._token_expiry = now + timedelta(seconds=payload.get("expires_in", 1500) - 60)
        return self._token

    # -- Récupération --------------------------------------------------------

    async def fetch(self, criteria: Criteria) -> list[RawOffer]:
        if not self._client_id or not self._client_secret:
            logger.warning("France Travail : identifiants absents, source ignorée.")
            return []

        if "FR" not in criteria.country_codes():
            logger.info("France Travail : la France n'est pas dans les pays ciblés.")
            return []

        since = datetime.now(timezone.utc) - timedelta(hours=self._lookback_hours)
        offers: dict[str, RawOffer] = {}

        async with httpx.AsyncClient(timeout=30.0) as client:
            token = await self._access_token(client)

            # Une requête par intitulé recherché : l'API pondère mal les
            # requêtes multi-termes, et interroger terme par terme donne un
            # rappel nettement meilleur. Les doublons sont fusionnés par id.
            for keyword in criteria.titles_include:
                try:
                    found = await self._search_keyword(client, token, keyword, criteria, since)
                except httpx.HTTPStatusError as exc:
                    # Un mot-clé qui échoue ne doit pas faire tomber toute la
                    # récupération : on log et on continue avec les autres.
                    logger.warning(
                        "France Travail : échec sur « %s » (%s)", keyword, exc.response.status_code
                    )
                    continue
                for offer in found:
                    offers.setdefault(offer.source_offer_id, offer)

                # Respect du quota de l'API (limite par appelant et par seconde).
                await asyncio.sleep(0.4)

        logger.info("France Travail : %d offres uniques récupérées.", len(offers))
        return list(offers.values())

    async def _search_keyword(
        self,
        client: httpx.AsyncClient,
        token: str,
        keyword: str,
        criteria: Criteria,
        since: datetime,
    ) -> list[RawOffer]:
        params: dict[str, str] = {
            "motsCles": keyword,
            "minCreationDate": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "maxCreationDate": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sort": "1",  # tri par date de création décroissante
        }

        # L'API attend des codes : CDI -> 'CDI', CDD -> 'CDD'.
        contract_codes = [c.upper() for c in criteria.contract_types if c]
        if contract_codes:
            params["typeContrat"] = ",".join(contract_codes)

        results: list[RawOffer] = []
        for page in range(MAX_PAGES):
            start = page * PAGE_SIZE
            params["range"] = f"{start}-{start + PAGE_SIZE - 1}"

            res = await client.get(
                SEARCH_URL,
                params=params,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )

            # 204 = aucun résultat, 206 = page partielle (dernière page).
            if res.status_code == 204:
                break
            res.raise_for_status()

            batch = res.json().get("resultats", [])
            results.extend(self._to_offer(raw) for raw in batch)

            if res.status_code == 206 or len(batch) < PAGE_SIZE:
                break

        return results

    # -- Normalisation -------------------------------------------------------

    def _to_offer(self, raw: dict) -> RawOffer:
        lieu = raw.get("lieuTravail") or {}
        entreprise = raw.get("entreprise") or {}
        origine = raw.get("origineOffre") or {}
        contact = raw.get("contact") or {}
        salaire = raw.get("salaire") or {}
        description = raw.get("description") or ""

        # L'email de contact est parfois dans `contact.courriel`, parfois noyé
        # dans le texte de la description.
        email = contact.get("courriel")
        if not email:
            match = _EMAIL_RE.search(description)
            email = match.group(0) if match else None

        return RawOffer(
            source=self.name,
            source_offer_id=str(raw["id"]),
            country=self.country,
            title=raw.get("intitule") or "(sans intitulé)",
            company=entreprise.get("nom"),
            city=lieu.get("libelle"),
            url=origine.get("urlOrigine") or f"https://candidat.francetravail.fr/offres/recherche/detail/{raw['id']}",
            description=description or None,
            salary_raw=salaire.get("libelle"),
            contract_type=raw.get("typeContrat"),
            remote_policy=_remote_policy(raw),
            posted_at=_parse_date(raw.get("dateCreation")),
            apply_email=email,
            # Le canal réel est déterminé par agents/apply.py ; la source se
            # contente de signaler qu'un email est disponible.
            apply_channel="email" if email else "unknown",
        )


def _remote_policy(raw: dict) -> str | None:
    """Déduit la politique de télétravail des champs disponibles.

    L'API n'expose pas de champ dédié fiable ; on se rabat sur les libellés.
    Renvoie None quand rien n'est exploitable — mieux vaut « inconnu » qu'une
    valeur inventée qui fausserait le score.
    """
    haystack = " ".join(
        str(raw.get(field) or "") for field in ("intitule", "description")
    ).lower()

    if "100% télétravail" in haystack or "full remote" in haystack:
        return "remote"
    if "télétravail" in haystack or "hybride" in haystack:
        return "hybrid"
    return None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
