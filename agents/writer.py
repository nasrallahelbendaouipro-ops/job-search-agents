"""Agent Rédacteur : une lettre de motivation personnalisée par offre retenue.

Le modèle ne produit que du **texte**. La mise en forme (Calibri 11 pt, corps
justifié, en-tête bleu) est appliquée par `docx_builder`, ce qui garantit que le
style reste identique d'une lettre à l'autre quoi que renvoie le LLM.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

from .docx_builder import Recipient, build_letter_docx, parse_letter_text
from .llm.budget import BudgetGuard
from .llm.client import WriterLLM
from .models import StoredOffer

logger = logging.getLogger(__name__)

#: Longueur de description transmise au rédacteur. Plus généreux que pour le
#: filtre : la personnalisation dépend directement de ce que la lettre peut
#: citer de l'offre.
DESCRIPTION_CHARS = 4000


SYSTEM_PROMPT = """Tu rédiges des lettres de motivation en français pour Nasr Allah El Bendaoui.

## Son parcours
- 25 ans, basé en France.
- Master Data & Intelligence Artificielle, École Centrale de Lyon (2025).
- Diplôme d'ingénieur, EMSI (Maroc).
- Stage chez Safran Aircraft Engines : tableaux de bord Power BI, Python, modèles LSTM pour la maintenance prédictive.
- CDI chez Akkodis : gestion des nomenclatures MBOM/EBOM pour Alstom et Stellantis, dashboards KPI de production.
- Outils : Python (pandas, scikit-learn), SQL, Power BI, Excel avancé.
- Français natif, anglais professionnel.

## Style attendu
Le style doit rester cohérent avec ses lettres existantes : sobre, direct, factuel.
- Trois paragraphes de corps, pas davantage.
- Paragraphe 1 : pourquoi cette entreprise et ce poste précisément. Cite un élément concret de l'annonce.
- Paragraphe 2 : l'expérience la plus pertinente pour CETTE offre, avec un résultat tangible.
- Paragraphe 3 : ce qu'il apporterait à l'équipe, et la disponibilité.
- Vouvoiement, présent de l'indicatif.
- Pas de superlatifs ni de formules creuses (« passionné depuis toujours », « leader du marché », « challenge excitant »).
- N'invente jamais une expérience, une certification ou un chiffre absent du parcours ci-dessus.
- Si l'offre exige une compétence qu'il n'a pas, ne mens pas : passe-la sous silence.

## Format de sortie
Réponds uniquement avec le texte de la lettre, dans cet ordre exact et sans commentaire :

Objet : <objet en une ligne>

<salutation>

<paragraphe 1>

<paragraphe 2>

<paragraphe 3>

<formule de politesse>

N'ajoute ni en-tête, ni coordonnées, ni date, ni signature : ils sont ajoutés automatiquement."""


@dataclass
class GeneratedLetter:
    offer_id: str
    text: str
    docx: bytes
    filename: str


def _slugify(value: str, *, max_length: int = 40) -> str:
    """Nom de fichier sûr : ASCII, minuscules, tirets."""
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return (slug[:max_length].rstrip("-")) or "offre"


def letter_filename(offer: StoredOffer) -> str:
    company = _slugify(offer.company or "entreprise", max_length=30)
    title = _slugify(offer.title, max_length=40)
    return f"lettre-{company}-{title}-{offer.id[:8]}.docx"


def _user_prompt(offer: StoredOffer) -> str:
    description = (offer.description or "")[:DESCRIPTION_CHARS]
    fields = [
        f"Intitulé : {offer.title}",
        f"Entreprise : {offer.company or 'non précisée'}",
        f"Lieu : {offer.city or 'non précisé'} ({offer.country})",
        f"Contrat : {offer.contract_type or 'non précisé'}",
    ]
    if offer.salary_raw:
        fields.append(f"Rémunération annoncée : {offer.salary_raw}")
    if offer.remote_policy:
        fields.append(f"Télétravail : {offer.remote_policy}")

    return (
        "Rédige la lettre de motivation pour l'offre suivante.\n\n"
        + "\n".join(fields)
        + f"\n\nDescription de l'offre :\n{description}"
    )


async def write_letter(
    offer: StoredOffer,
    budget: BudgetGuard,
    *,
    llm: WriterLLM | None = None,
) -> GeneratedLetter:
    """Génère la lettre d'une offre et renvoie texte + .docx."""
    budget.check()
    llm = llm or WriterLLM()

    response = await llm.complete(SYSTEM_PROMPT, _user_prompt(offer))
    cost = budget.record(
        agent="writer",
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )
    logger.info("Lettre générée pour « %s » (%.4f €).", offer.title, cost)

    content = parse_letter_text(
        response.text, fallback_subject=f"Candidature au poste de {offer.title}"
    )
    docx = build_letter_docx(
        content,
        Recipient(company=offer.company or "l'entreprise", city=offer.city),
    )

    return GeneratedLetter(
        offer_id=offer.id,
        text=response.text.strip(),
        docx=docx,
        filename=letter_filename(offer),
    )


def choose_cv(offer: StoredOffer, cv_documents: list[dict]) -> dict | None:
    """Sélectionne la variante de CV la plus proche de l'intitulé.

    Règle volontairement simple et lisible : un LLM n'apporterait rien ici, et
    coûterait un appel par offre.
    """
    if not cv_documents:
        return None

    title = offer.title.lower()
    by_label = {doc["label"]: doc for doc in cv_documents}

    if any(term in title for term in ("scientist", "machine learning", "ia ", "ai ", "nlp")):
        preference = ["data_scientist", "data_analyst", "industrial_engineer"]
    elif any(
        term in title
        for term in ("industriel", "industrial", "production", "supply", "méthodes", "process")
    ):
        preference = ["industrial_engineer", "data_analyst", "data_scientist"]
    else:
        preference = ["data_analyst", "data_scientist", "industrial_engineer"]

    for label in preference:
        if label in by_label:
            return by_label[label]
    return cv_documents[0]
