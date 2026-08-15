"""Agent Candidature : classe le canal de candidature et fixe le statut.

**Aucun envoi n'est effectué par ce module, en V1 ni ailleurs.** Il détermine
comment on pourrait postuler, prépare le statut correspondant, et s'arrête là.
L'envoi effectif est déclenché par toi depuis le dashboard.

Le flag `auto_send_enabled` existe dans les critères mais reste à `false` :
tant qu'il n'est pas basculé, même les offres candidatables par email restent
en `to_validate`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .models import ApplyChannel, Criteria, StoredOffer

logger = logging.getLogger(__name__)

#: Domaines dont la candidature passe forcément par un compte existant.
#: Aucune automatisation n'est tentée dessus (CGU).
ACCOUNT_DOMAINS = {
    "linkedin.com": "easy_apply",
    "www.linkedin.com": "easy_apply",
    "indeed.com": "account_required",
    "fr.indeed.com": "account_required",
    "de.indeed.com": "account_required",
    "welcometothejungle.com": "account_required",
    "workday.com": "account_required",
    "myworkdayjobs.com": "account_required",
    "successfactors.com": "account_required",
    "taleo.net": "account_required",
    "smartrecruiters.com": "account_required",
    "greenhouse.io": "form",
    "lever.co": "form",
}

#: Formulations qui signalent une candidature par email dans le texte.
_EMAIL_HINT = re.compile(
    r"(candidature|cv|lettre|postuler|envoyer)[^.]{0,60}?[\w.+-]+@[\w-]+\.[\w.-]+",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

#: Adresses génériques à ignorer : écrire à `contact@` ou `rgpd@` n'est pas
#: une candidature.
_IGNORED_MAILBOXES = {"noreply", "no-reply", "donotreply", "rgpd", "dpo", "privacy"}


@dataclass
class ApplyDecision:
    channel: ApplyChannel
    application_status: str
    apply_email: str | None
    note: str


def _usable_email(candidate: str | None) -> str | None:
    if not candidate:
        return None
    mailbox = candidate.split("@", 1)[0].lower()
    if mailbox in _IGNORED_MAILBOXES:
        return None
    return candidate


def detect_channel(offer: StoredOffer) -> tuple[ApplyChannel, str | None]:
    """Détermine par quel canal on pourrait postuler à cette offre."""
    domain = (urlparse(offer.url).netloc or "").lower()

    # Le domaine prime : une offre LinkedIn qui mentionne un email dans son
    # texte reste une candidature LinkedIn.
    for known, channel in ACCOUNT_DOMAINS.items():
        if domain == known or domain.endswith(f".{known}"):
            return channel, None  # type: ignore[return-value]

    email = _usable_email(offer.apply_email)
    if email:
        return "email", email

    # Email présent dans la description, dans un contexte de candidature.
    if offer.description:
        hint = _EMAIL_HINT.search(offer.description)
        if hint:
            found = _EMAIL_RE.search(hint.group(0))
            email = _usable_email(found.group(0) if found else None)
            if email:
                return "email", email

    # Domaine inconnu avec une URL de candidature : probablement un formulaire,
    # mais on ne s'y engage pas sans l'avoir vu.
    return "unknown", None


def decide(offer: StoredOffer, criteria: Criteria) -> ApplyDecision:
    """Traduit le canal détecté en statut de candidature.

    Invariant : cette fonction ne renvoie jamais `auto_applied`. L'envoi
    automatique n'existe pas dans le pipeline nocturne — il ne peut être
    déclenché que depuis le dashboard, offre par offre.
    """
    channel, email = detect_channel(offer)

    if channel == "email":
        if criteria.auto_send_enabled:
            # Même avec le flag activé, l'envoi reste une action du dashboard.
            # Le flag change seulement le libellé du bouton proposé.
            note = (
                f"Candidature par email possible ({email}). "
                "Auto-envoi activé : validation en un clic."
            )
        else:
            note = (
                f"Candidature par email possible ({email}). "
                "Auto-envoi désactivé : à valider manuellement."
            )
        return ApplyDecision("email", "to_validate", email, note)

    if channel == "form":
        return ApplyDecision(
            "form",
            "to_validate",
            None,
            "Formulaire sans création de compte. Documents prêts à joindre.",
        )

    if channel == "easy_apply":
        return ApplyDecision(
            "easy_apply",
            "manual_required",
            None,
            "Candidature simplifiée LinkedIn : soumission manuelle "
            "(l'automatiser violerait les CGU et exposerait le compte).",
        )

    if channel == "account_required":
        return ApplyDecision(
            "account_required",
            "manual_required",
            None,
            "Création de compte ou parcours multi-étapes requis. "
            "Lien et documents prêts.",
        )

    return ApplyDecision(
        "unknown",
        "manual_required",
        None,
        "Canal de candidature non identifié. Ouvre le lien pour vérifier.",
    )
