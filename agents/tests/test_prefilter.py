"""Tests du pré-filtre déterministe.

Le test qui compte vraiment est `test_criteria_drive_behaviour` : il prouve
qu'aucun critère n'est codé en dur et que modifier `profile_criteria` depuis le
dashboard change bien le résultat.
"""

from __future__ import annotations

import pytest

from agents.models import Criteria, RawOffer
from agents.prefilter import apply_prefilter, normalize


def offer(**kwargs) -> RawOffer:
    defaults = dict(
        source="france_travail",
        source_offer_id="1",
        country="FR",
        title="Data Analyst",
        url="https://example.com/1",
        company="ACME",
        city="Lyon",
        description="Analyse de données, Power BI, SQL.",
        contract_type="CDI",
    )
    defaults.update(kwargs)
    return RawOffer(**defaults)


def reasons(result) -> list[str]:
    return [reason for _, reason in result.rejected]


# -- Le seed se charge bien dans le modèle Python ---------------------------


def test_seed_loads_into_criteria_model(seeded_criteria: Criteria) -> None:
    assert "data analyst" in seeded_criteria.titles_include
    assert seeded_criteria.min_score_to_keep == 65
    assert seeded_criteria.auto_send_enabled is False
    assert {c.code for c in seeded_criteria.countries} == {"FR", "MA", "DE"}


def test_auto_send_is_disabled_by_default(seeded_criteria: Criteria) -> None:
    """Garde-fou : personne ne doit livrer un seed avec l'auto-envoi actif."""
    assert seeded_criteria.auto_send_enabled is False


# -- Normalisation -----------------------------------------------------------


def test_normalize_strips_accents_and_case() -> None:
    assert normalize("Analyste de Données") == "analyste de donnees"
    assert normalize(None) == ""


# -- Règles d'exclusion ------------------------------------------------------


def test_keeps_a_matching_offer(criteria: Criteria) -> None:
    result = apply_prefilter([offer()], criteria)
    assert len(result.kept) == 1


def test_rejects_internships_and_apprenticeships(criteria: Criteria) -> None:
    offers = [
        offer(source_offer_id="a", title="Stage Data Analyst"),
        offer(source_offer_id="b", title="Alternance Analytics Engineer"),
        offer(source_offer_id="c", title="Data Analyst en apprentissage"),
    ]
    result = apply_prefilter(offers, criteria)
    assert result.kept == []
    assert all("intitulé exclu" in r for r in reasons(result))


def test_title_exclusions_ignore_the_description(criteria: Criteria) -> None:
    """« pas d'alternance possible » dans le corps ne doit rien écarter."""
    result = apply_prefilter(
        [offer(description="Poste en CDI, pas d'alternance possible.")], criteria
    )
    assert len(result.kept) == 1


def test_rejects_offers_outside_targeted_countries(criteria: Criteria) -> None:
    result = apply_prefilter([offer(country="ES")], criteria)
    assert result.kept == []
    assert "pays hors périmètre" in reasons(result)[0]


def test_rejects_cities_outside_an_explicit_list(criteria: Criteria) -> None:
    # Le Maroc liste des villes précises dans le seed.
    result = apply_prefilter(
        [offer(country="MA", city="Agadir"), offer(source_offer_id="2", country="MA", city="Casablanca")],
        criteria,
    )
    assert len(result.kept) == 1
    assert result.kept[0].city == "Casablanca"


def test_empty_city_list_means_whole_country(criteria: Criteria) -> None:
    # La France a une liste de villes vide : tout le pays est accepté.
    result = apply_prefilter([offer(city="Brive-la-Gaillarde")], criteria)
    assert len(result.kept) == 1


def test_rejects_non_targeted_contract_types(criteria: Criteria) -> None:
    result = apply_prefilter([offer(contract_type="CDD")], criteria)
    assert result.kept == []
    assert "contrat non ciblé" in reasons(result)[0]


def test_rejects_excluded_keywords(criteria: Criteria) -> None:
    result = apply_prefilter(
        [offer(description="Développement WordPress et PHP au quotidien.")], criteria
    )
    assert result.kept == []
    assert "mot-clé exclu" in reasons(result)[0]


def test_rejects_offers_already_seen(criteria: Criteria) -> None:
    result = apply_prefilter([offer(source_offer_id="déjà")], criteria, known_ids={"déjà"})
    assert result.kept == []
    assert reasons(result) == ["déjà vue"]


def test_rejects_titles_with_no_targeted_term(criteria: Criteria) -> None:
    result = apply_prefilter(
        [offer(title="Chargé de clientèle", description="Accueil et vente en agence.")],
        criteria,
    )
    assert result.kept == []
    assert "aucun intitulé ciblé" in reasons(result)[0]


# -- Salaire : n'écarte que sur un montant connu ----------------------------


def test_rejects_salary_below_floor(criteria: Criteria) -> None:
    result = apply_prefilter([offer(salary_max=28000)], criteria)  # plancher FR : 38 000
    assert result.kept == []
    assert "plancher" in reasons(result)[0]


def test_keeps_offers_without_advertised_salary(criteria: Criteria) -> None:
    """Le cas le plus fréquent : écarter ici ferait perdre l'essentiel du flux."""
    result = apply_prefilter([offer(salary_max=None)], criteria)
    assert len(result.kept) == 1


def test_keeps_salary_above_floor(criteria: Criteria) -> None:
    result = apply_prefilter([offer(salary_max=45000)], criteria)
    assert len(result.kept) == 1


# -- La preuve que rien n'est codé en dur ------------------------------------


@pytest.mark.parametrize(
    "mutate, expect_kept",
    [
        # Retirer l'intitulé recherché doit faire tomber l'offre.
        (lambda c: c.titles_include.clear() or c.titles_include.append("juriste"), False),
        # Ajouter un mot-clé d'exclusion présent dans l'offre doit l'écarter.
        (lambda c: c.keywords_exclude.append("power bi"), False),
        # Élargir les contrats doit laisser passer une offre en CDD.
        (lambda c: c.contract_types.append("CDD"), True),
    ],
)
def test_criteria_drive_behaviour(criteria: Criteria, mutate, expect_kept) -> None:
    """Modifier les critères change le résultat : aucun critère n'est en dur."""
    candidate = offer(contract_type="CDD" if expect_kept else "CDI")
    mutate(criteria)

    result = apply_prefilter([candidate], criteria)
    assert bool(result.kept) is expect_kept


def test_raising_the_salary_floor_rejects_a_previously_kept_offer(criteria: Criteria) -> None:
    candidate = offer(salary_max=40000)
    assert apply_prefilter([candidate], criteria).kept  # plancher 38 000 : gardée

    criteria.salary_min_by_country["FR"] = 60000
    assert apply_prefilter([candidate], criteria).kept == []
