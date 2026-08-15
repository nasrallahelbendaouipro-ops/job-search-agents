"""Étage 1 du filtre : élimination déterministe, sans appel LLM.

Ce module ne coûte rien à l'exécution et écarte typiquement la majorité des
offres récupérées. Tout ce qu'il élimine n'atteint jamais l'étage LLM — c'est
le principal levier pour tenir le budget mensuel.

Règle de conception : le pré-filtre n'écarte que sur des critères **certains**
(mot-clé d'exclusion présent, pays hors liste, salaire affiché sous le
plancher). Tout ce qui demande du jugement est laissé au LLM. Un pré-filtre
trop agressif ferait rater de bonnes offres sans qu'on puisse le voir.
"""

from __future__ import annotations

from dataclasses import dataclass

from unidecode import unidecode

from .models import Criteria, RawOffer


@dataclass
class PrefilterResult:
    kept: list[RawOffer]
    rejected: list[tuple[RawOffer, str]]  # (offre, raison lisible)


def normalize(text: str | None) -> str:
    """Minuscules sans accents, pour comparer « données » et « donnees »."""
    return unidecode(text or "").lower()


def _contains_any(haystack: str, needles: list[str]) -> str | None:
    """Renvoie le premier terme trouvé, ou None."""
    for needle in needles:
        n = normalize(needle).strip()
        if n and n in haystack:
            return needle
    return None


def apply_prefilter(
    offers: list[RawOffer], criteria: Criteria, *, known_ids: set[str] | None = None
) -> PrefilterResult:
    known_ids = known_ids or set()
    kept: list[RawOffer] = []
    rejected: list[tuple[RawOffer, str]] = []

    allowed_countries = {c.upper() for c in criteria.country_codes()}
    allowed_contracts = {normalize(c) for c in criteria.contract_types if c}

    for offer in offers:
        # Déjà traitée lors d'une exécution précédente.
        if offer.source_offer_id in known_ids:
            rejected.append((offer, "déjà vue"))
            continue

        title = normalize(offer.title)
        body = normalize(offer.description)
        haystack = f"{title} {body}"

        # 1. Intitulé disqualifiant (stage, alternance, poste de direction…).
        #    Testé sur le titre seulement : « pas d'alternance possible » dans
        #    une description ne doit pas écarter une offre en CDI.
        hit = _contains_any(title, criteria.titles_exclude)
        if hit:
            rejected.append((offer, f"intitulé exclu : « {hit} »"))
            continue

        # 2. Pays hors périmètre.
        if allowed_countries and offer.country.upper() not in allowed_countries:
            rejected.append((offer, f"pays hors périmètre : {offer.country}"))
            continue

        # 3. Ville : seulement si des villes sont explicitement listées pour ce
        #    pays. Une liste vide signifie « tout le pays ».
        cities = criteria.cities_for(offer.country.upper())
        if cities and offer.city:
            if not _contains_any(normalize(offer.city), cities):
                rejected.append((offer, f"ville hors liste : {offer.city}"))
                continue

        # 4. Type de contrat, quand la source le renseigne.
        if allowed_contracts and offer.contract_type:
            if normalize(offer.contract_type) not in allowed_contracts:
                rejected.append((offer, f"contrat non ciblé : {offer.contract_type}"))
                continue

        # 5. Technos / métiers hors profil.
        hit = _contains_any(haystack, criteria.keywords_exclude)
        if hit:
            rejected.append((offer, f"mot-clé exclu : « {hit} »"))
            continue

        # 6. Salaire : uniquement si un montant est effectivement connu.
        #    Une offre sans salaire affiché n'est jamais écartée ici — c'est le
        #    cas le plus fréquent, et l'écarter ferait perdre l'essentiel du
        #    flux.
        floor = criteria.salary_min_by_country.get(offer.country.upper())
        if floor is not None and offer.salary_max is not None:
            if offer.salary_max < floor:
                rejected.append(
                    (offer, f"salaire max {offer.salary_max:.0f} < plancher {floor:.0f}")
                )
                continue

        # 7. Aucun intitulé recherché ne correspond, ni dans le titre ni dans
        #    la description. Testé en dernier : c'est la règle la plus large,
        #    et on veut que les rejets précédents donnent une raison plus
        #    précise dans les logs.
        if criteria.titles_include and not _contains_any(haystack, criteria.titles_include):
            rejected.append((offer, "aucun intitulé ciblé trouvé"))
            continue

        kept.append(offer)

    return PrefilterResult(kept=kept, rejected=rejected)
