"""Tests de l'agent Candidature.

Le test le plus important est `test_pipeline_never_auto_applies` : il verrouille
la garantie de la V1 — le pipeline nocturne ne soumet jamais rien, quel que
soit l'état du flag `auto_send_enabled`.
"""

from __future__ import annotations

import pytest

from agents.apply import decide, detect_channel
from agents.models import Criteria, StoredOffer


def offer(**kwargs) -> StoredOffer:
    defaults = dict(
        id="00000000-0000-0000-0000-000000000001",
        source="france_travail",
        source_offer_id="1",
        country="FR",
        title="Data Analyst",
        url="https://candidat.francetravail.fr/offres/recherche/detail/1",
        company="ACME",
        city="Lyon",
        description="Analyse de données.",
    )
    defaults.update(kwargs)
    return StoredOffer(**defaults)


# -- Détection du canal ------------------------------------------------------


def test_detects_contact_email() -> None:
    channel, email = detect_channel(offer(apply_email="recrutement@acme.fr"))
    assert channel == "email"
    assert email == "recrutement@acme.fr"


def test_detects_email_buried_in_description() -> None:
    channel, email = detect_channel(
        offer(description="Merci d'envoyer votre CV à jobs@acme.fr avant le 30 septembre.")
    )
    assert channel == "email"
    assert email == "jobs@acme.fr"


def test_ignores_noreply_and_privacy_mailboxes() -> None:
    """Écrire à `noreply@` ou `dpo@` n'est pas une candidature."""
    for mailbox in ("noreply@acme.fr", "dpo@acme.fr", "rgpd@acme.fr"):
        channel, email = detect_channel(offer(apply_email=mailbox))
        assert channel == "unknown", mailbox
        assert email is None


def test_linkedin_is_easy_apply() -> None:
    channel, _ = detect_channel(offer(url="https://www.linkedin.com/jobs/view/123"))
    assert channel == "easy_apply"


def test_indeed_requires_an_account() -> None:
    channel, _ = detect_channel(offer(url="https://fr.indeed.com/viewjob?jk=abc"))
    assert channel == "account_required"


def test_domain_wins_over_an_email_in_the_text() -> None:
    """Une offre LinkedIn reste une candidature LinkedIn."""
    channel, _ = detect_channel(
        offer(
            url="https://www.linkedin.com/jobs/view/123",
            apply_email="recrutement@acme.fr",
        )
    )
    assert channel == "easy_apply"


def test_ats_form_domains_are_forms() -> None:
    channel, _ = detect_channel(offer(url="https://boards.greenhouse.io/acme/jobs/1"))
    assert channel == "form"


def test_unknown_domain_stays_unknown() -> None:
    channel, email = detect_channel(offer(url="https://carrieres.acme.fr/offre/42"))
    assert channel == "unknown"
    assert email is None


# -- Traduction en statut ----------------------------------------------------


def test_email_offer_awaits_validation(criteria: Criteria) -> None:
    decision = decide(offer(apply_email="recrutement@acme.fr"), criteria)
    assert decision.application_status == "to_validate"
    assert decision.apply_email == "recrutement@acme.fr"


def test_linkedin_offer_requires_manual_action(criteria: Criteria) -> None:
    decision = decide(offer(url="https://www.linkedin.com/jobs/view/123"), criteria)
    assert decision.application_status == "manual_required"
    assert "CGU" in decision.note


def test_account_required_offer_is_manual(criteria: Criteria) -> None:
    decision = decide(offer(url="https://acme.myworkdayjobs.com/job/1"), criteria)
    assert decision.application_status == "manual_required"


# -- La garantie de la V1 ----------------------------------------------------


@pytest.mark.parametrize("auto_send", [False, True])
@pytest.mark.parametrize(
    "url, apply_email",
    [
        ("https://candidat.francetravail.fr/offres/1", "recrutement@acme.fr"),
        ("https://boards.greenhouse.io/acme/jobs/1", None),
        ("https://www.linkedin.com/jobs/view/123", None),
        ("https://acme.myworkdayjobs.com/job/1", None),
        ("https://carrieres.acme.fr/offre/42", None),
    ],
)
def test_pipeline_never_auto_applies(
    criteria: Criteria, auto_send: bool, url: str, apply_email: str | None
) -> None:
    """Aucun chemin ne produit `auto_applied`, même avec l'auto-envoi activé.

    L'envoi ne peut être déclenché que depuis le dashboard, offre par offre.
    """
    criteria.auto_send_enabled = auto_send
    decision = decide(offer(url=url, apply_email=apply_email), criteria)
    assert decision.application_status in {"to_validate", "manual_required"}
    assert decision.application_status != "auto_applied"


def test_auto_send_flag_only_changes_the_note(criteria: Criteria) -> None:
    candidate = offer(apply_email="recrutement@acme.fr")

    criteria.auto_send_enabled = False
    off = decide(candidate, criteria)
    criteria.auto_send_enabled = True
    on = decide(candidate, criteria)

    assert off.application_status == on.application_status == "to_validate"
    assert "désactivé" in off.note
    assert "activé" in on.note
