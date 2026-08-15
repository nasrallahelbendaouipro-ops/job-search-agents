"""Construction du .docx de la lettre de motivation.

Le style ne dépend jamais du LLM : le modèle ne renvoie que du texte, et c'est
ce module qui applique la mise en forme. Une lettre mal générée reste donc
toujours une lettre correctement formatée.

Mise en forme reprise des lettres existantes
(`Cover-Letter-BCG-X.docx`, `Lettre-motivation-ALTEN-MAROC.docx`) :

    Calibri partout, w:sz=22 (11 pt)
    corps justifié (w:jc=both), interligne w:line=276 (soit 1,15)
    espacements w:after de 200 / 300 / 400 twips (10 / 15 / 20 pt)

Les fichiers d'origine n'ont aucune couleur ; le bleu #1F3C73 demandé est
**ajouté** sur l'en-tête (identité, destinataire, objet).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

FONT = "Calibri"
FONT_SIZE = Pt(11)  # w:sz=22 (demi-points)
HEADER_BLUE = RGBColor(0x1F, 0x3C, 0x73)
LINE_SPACING = 1.15  # w:line=276 avec lineRule auto

SPACE_SMALL = Pt(10)  # w:after=200
SPACE_MEDIUM = Pt(15)  # w:after=300
SPACE_LARGE = Pt(20)  # w:after=400

MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


@dataclass
class LetterContent:
    """Texte de la lettre, tel que renvoyé par le rédacteur."""

    subject: str
    salutation: str
    body_paragraphs: list[str]
    closing: str


@dataclass
class SenderIdentity:
    name: str = "Nasr Allah El Bendaoui"
    headline: str = "Data Analyst — MSc Data & IA, École Centrale de Lyon"
    email: str = "nasrallah.elbendaoui.pro@gmail.com"
    phone: str = "+33 7 61 62 76 86"


@dataclass
class Recipient:
    company: str
    city: str | None = None
    team: str = "Service Recrutement"


def format_date_fr(value: date) -> str:
    return f"{value.day} {MOIS_FR[value.month - 1]} {value.year}"


def _configure_base_style(document: Document) -> None:
    """Applique Calibri 11 pt au style Normal, dont héritent tous les runs."""
    normal = document.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = FONT_SIZE
    # Sans w:eastAsia, Word peut substituer une autre police sur certaines
    # installations — les fichiers d'origine le posent explicitement.
    normal.element.rPr.rFonts.set(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", FONT
    )


def _add_paragraph(
    document: Document,
    text: str,
    *,
    bold: bool = False,
    color: RGBColor | None = None,
    align: WD_ALIGN_PARAGRAPH | None = None,
    space_after: Pt | None = None,
    space_before: Pt | None = None,
    justified: bool = False,
):
    paragraph = document.add_paragraph()
    fmt = paragraph.paragraph_format
    fmt.space_after = space_after if space_after is not None else Pt(0)
    if space_before is not None:
        fmt.space_before = space_before

    if justified:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        fmt.line_spacing = LINE_SPACING
    elif align is not None:
        paragraph.alignment = align

    run = paragraph.add_run(text)
    run.font.name = FONT
    run.font.size = FONT_SIZE
    run.bold = bold
    if color is not None:
        run.font.color.rgb = color
    return paragraph


def build_letter_docx(
    content: LetterContent,
    recipient: Recipient,
    *,
    sender: SenderIdentity | None = None,
    letter_date: date | None = None,
) -> bytes:
    """Produit le .docx et le renvoie en mémoire, prêt pour Supabase Storage."""
    sender = sender or SenderIdentity()
    letter_date = letter_date or date.today()

    document = Document()
    _configure_base_style(document)

    # -- En-tête expéditeur (bleu) ------------------------------------------
    _add_paragraph(document, sender.name, bold=True, color=HEADER_BLUE)
    _add_paragraph(document, sender.headline, color=HEADER_BLUE)
    _add_paragraph(document, f"{sender.email} • {sender.phone}", color=HEADER_BLUE)

    # -- Destinataire --------------------------------------------------------
    _add_paragraph(
        document, recipient.company, bold=True, color=HEADER_BLUE, space_before=SPACE_MEDIUM
    )
    _add_paragraph(document, recipient.team)
    _add_paragraph(document, recipient.city or "", space_after=SPACE_LARGE)

    # -- Date, alignée à droite ---------------------------------------------
    _add_paragraph(
        document,
        format_date_fr(letter_date),
        align=WD_ALIGN_PARAGRAPH.RIGHT,
        space_after=SPACE_LARGE,
    )

    # -- Objet : libellé en gras et en bleu, contenu en noir -----------------
    subject_paragraph = document.add_paragraph()
    subject_paragraph.paragraph_format.space_after = SPACE_LARGE
    label = subject_paragraph.add_run("Objet : ")
    label.font.name = FONT
    label.font.size = FONT_SIZE
    label.bold = True
    label.font.color.rgb = HEADER_BLUE
    value = subject_paragraph.add_run(content.subject)
    value.font.name = FONT
    value.font.size = FONT_SIZE

    # -- Corps ---------------------------------------------------------------
    _add_paragraph(document, content.salutation, space_after=SPACE_MEDIUM)

    for paragraph_text in content.body_paragraphs:
        _add_paragraph(document, paragraph_text, justified=True, space_after=SPACE_SMALL)

    _add_paragraph(
        document, content.closing, justified=True, space_after=SPACE_MEDIUM
    )
    _add_paragraph(document, sender.name)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def parse_letter_text(text: str, *, fallback_subject: str) -> LetterContent:
    """Découpe le texte brut du modèle en sections.

    Le rédacteur reçoit la consigne de produire « Objet : … » puis la
    salutation, le corps et la formule de politesse. On reste tolérant : si le
    format n'est pas respecté, on retombe sur un découpage par paragraphes
    plutôt que d'échouer.
    """
    lines = [line.strip() for line in text.strip().splitlines()]
    paragraphs = [line for line in lines if line]

    subject = fallback_subject
    if paragraphs and re.match(r"^objet\s*:", paragraphs[0], re.IGNORECASE):
        subject = re.sub(r"^objet\s*:\s*", "", paragraphs.pop(0), flags=re.IGNORECASE)

    salutation = "Madame, Monsieur,"
    if paragraphs and re.match(
        r"^(madame|monsieur|bonjour|cher|chère)", paragraphs[0], re.IGNORECASE
    ):
        salutation = paragraphs.pop(0)

    # La formule de politesse est le dernier paragraphe, sauf s'il ne reste
    # qu'un seul bloc — auquel cas il constitue tout le corps.
    closing = "Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées."
    if len(paragraphs) > 1:
        closing = paragraphs.pop()

    # La signature répétée par le modèle ferait doublon avec celle ajoutée par
    # le builder.
    body = [p for p in paragraphs if p.lower() != "nasr allah el bendaoui"]

    return LetterContent(
        subject=subject,
        salutation=salutation,
        body_paragraphs=body,
        closing=closing,
    )
