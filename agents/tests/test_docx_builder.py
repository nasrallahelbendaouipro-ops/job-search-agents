"""Vérifie que la lettre générée reprend bien le style des lettres existantes.

Les assertions portent sur le XML produit, pas sur l'API python-docx : c'est ce
XML que Word lit, et c'est lui qu'on a comparé aux fichiers d'origine
(`Cover-Letter-BCG-X.docx`, `Lettre-motivation-ALTEN-MAROC.docx`).
"""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from agents.docx_builder import (
    LetterContent,
    Recipient,
    build_letter_docx,
    format_date_fr,
    parse_letter_text,
)


@pytest.fixture
def sample_docx_xml() -> str:
    content = LetterContent(
        subject="Candidature au poste de Data Analyst",
        salutation="Madame, Monsieur,",
        body_paragraphs=[
            "Premier paragraphe du corps de la lettre, suffisamment long pour être justifié.",
            "Deuxième paragraphe, qui décrit une expérience professionnelle précise.",
        ],
        closing="Je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.",
    )
    data = build_letter_docx(
        content,
        Recipient(company="Alstom", city="Saint-Ouen"),
        letter_date=date(2026, 8, 15),
    )
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read("word/document.xml").decode("utf-8")


def test_uses_calibri_everywhere(sample_docx_xml: str) -> None:
    assert 'w:ascii="Calibri"' in sample_docx_xml
    # Aucune autre police ne doit apparaître dans le document.
    assert "Times New Roman" not in sample_docx_xml
    assert "Arial" not in sample_docx_xml


def test_font_size_is_11pt(sample_docx_xml: str) -> None:
    # w:sz est en demi-points : 22 = 11 pt, comme dans les lettres d'origine.
    assert 'w:sz w:val="22"' in sample_docx_xml


def test_body_is_justified(sample_docx_xml: str) -> None:
    assert 'w:jc w:val="both"' in sample_docx_xml


def test_body_line_spacing_matches_template(sample_docx_xml: str) -> None:
    # 1,15 -> w:line="276" avec lineRule auto.
    assert 'w:line="276"' in sample_docx_xml


def test_header_uses_brand_blue(sample_docx_xml: str) -> None:
    assert 'w:color w:val="1F3C73"' in sample_docx_xml


def test_contains_letter_content(sample_docx_xml: str) -> None:
    assert "Candidature au poste de Data Analyst" in sample_docx_xml
    assert "Alstom" in sample_docx_xml
    assert "15 août 2026" in sample_docx_xml


def test_date_is_right_aligned(sample_docx_xml: str) -> None:
    assert 'w:jc w:val="right"' in sample_docx_xml


def test_format_date_fr_uses_french_months() -> None:
    assert format_date_fr(date(2026, 8, 15)) == "15 août 2026"
    assert format_date_fr(date(2026, 1, 3)) == "3 janvier 2026"


# -- Découpage du texte renvoyé par le modèle -------------------------------


def test_parse_letter_text_extracts_sections() -> None:
    raw = """Objet : Candidature au poste d'Analytics Engineer

Madame, Monsieur,

Premier paragraphe du corps.

Second paragraphe du corps.

Je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées."""

    parsed = parse_letter_text(raw, fallback_subject="secours")

    assert parsed.subject == "Candidature au poste d'Analytics Engineer"
    assert parsed.salutation == "Madame, Monsieur,"
    assert parsed.body_paragraphs == [
        "Premier paragraphe du corps.",
        "Second paragraphe du corps.",
    ]
    assert parsed.closing.startswith("Je vous prie d'agréer")


def test_parse_letter_text_falls_back_when_format_ignored() -> None:
    """Un modèle qui ignore la consigne ne doit pas faire échouer la génération."""
    parsed = parse_letter_text("Un seul bloc de texte.", fallback_subject="Candidature")

    assert parsed.subject == "Candidature"
    assert parsed.salutation == "Madame, Monsieur,"
    assert parsed.body_paragraphs == ["Un seul bloc de texte."]
    assert parsed.closing  # une formule de politesse par défaut est fournie


def test_parse_letter_text_drops_duplicate_signature() -> None:
    """Le builder ajoute la signature ; celle du modèle ferait doublon."""
    raw = """Objet : Candidature

Madame, Monsieur,

Le corps de la lettre.

Nasr Allah El Bendaoui

Cordialement."""

    parsed = parse_letter_text(raw, fallback_subject="secours")

    assert "Nasr Allah El Bendaoui" not in parsed.body_paragraphs
