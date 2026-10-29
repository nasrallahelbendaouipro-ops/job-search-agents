"""Tests de la cadence horaire.

Deux garde-fous qui n'existaient pas quand le pipeline tournait une fois par
nuit, et sans lesquels passer en horaire multiplie par 24 le nombre de lettres
et le nombre d'appels API.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agents.sources.france_travail import FranceTravailSource


# -- Fenêtre de recherche adaptative ----------------------------------------


@pytest.mark.parametrize(
    "interval, expected",
    [
        (1.0, 3.0),    # horaire   -> 1 h + 2 h de marge
        (6.0, 8.0),    # 4x/jour
        (24.0, 26.0),  # nocturne  -> conserve l'ancien comportement
    ],
)
def test_lookback_follows_the_run_interval(interval: float, expected: float) -> None:
    source = FranceTravailSource("id", "secret", run_interval_hours=interval)
    assert source._lookback_hours == expected


def test_lookback_can_still_be_forced() -> None:
    """Une valeur explicite reste prioritaire, pour rattraper un trou."""
    source = FranceTravailSource("id", "secret", lookback_hours=72, run_interval_hours=1)
    assert source._lookback_hours == 72


def test_hourly_window_is_far_smaller_than_nightly() -> None:
    """Le gain qui motive le changement : moins d'appels API par exécution."""
    hourly = FranceTravailSource("id", "s", run_interval_hours=1)._lookback_hours
    nightly = FranceTravailSource("id", "s", run_interval_hours=24)._lookback_hours
    assert hourly < nightly / 8


# -- Plafond quotidien de lettres -------------------------------------------


def _pipeline(*, already_today: int, per_run: int, per_day: int):
    """Pipeline avec une base mockée et des plafonds choisis."""
    from agents.graph import Pipeline

    db = MagicMock()
    db.letters_generated_today.return_value = already_today
    db.cv_documents.return_value = []

    pipeline = Pipeline(db=db)
    pipeline.settings = pipeline.settings.model_copy(
        update={"max_letters_per_run": per_run, "max_letters_per_day": per_day}
    )
    return pipeline


def _offers(count: int):
    from agents.models import StoredOffer

    return [
        StoredOffer(
            id=f"00000000-0000-0000-0000-{i:012d}",
            source="france_travail",
            source_offer_id=str(i),
            country="FR",
            title="Data Analyst",
            url=f"https://example.com/{i}",
        )
        for i in range(count)
    ]


async def test_daily_cap_blocks_further_writing(criteria) -> None:
    """Une fois le quota du jour atteint, aucune rédaction n'est tentée."""
    pipeline = _pipeline(already_today=10, per_run=10, per_day=10)
    pipeline.budget = MagicMock()

    result = await pipeline.node_write(
        {"run_id": "r", "criteria": criteria, "matched": _offers(5), "errors": []}
    )

    assert result["letters_generated"] == 0
    # Aucun appel LLM, donc aucun upload de lettre.
    pipeline.db.upload_letter.assert_not_called()


async def test_daily_cap_limits_a_partial_run(criteria, monkeypatch) -> None:
    """Avec 8 lettres déjà produites, une exécution n'en ajoute que 2."""
    pipeline = _pipeline(already_today=8, per_run=10, per_day=10)

    written: list[str] = []

    async def fake_write_letter(offer, budget, **kwargs):
        from agents.writer import GeneratedLetter

        written.append(offer.id)
        return GeneratedLetter(offer_id=offer.id, text="texte", docx=b"x", filename="l.docx")

    monkeypatch.setattr("agents.graph.write_letter", fake_write_letter)
    pipeline.budget = MagicMock()

    result = await pipeline.node_write(
        {"run_id": "r", "criteria": criteria, "matched": _offers(5), "errors": []}
    )

    assert result["letters_generated"] == 2
    assert len(written) == 2


async def test_hourly_schedule_cannot_exceed_the_daily_cap(criteria, monkeypatch) -> None:
    """24 exécutions d'affilée ne produisent pas plus que le plafond du jour.

    C'est le test qui justifie l'existence du plafond quotidien : sans lui,
    24 exécutions × 10 lettres donneraient 240 candidatures par jour.
    """
    total = 0
    cap = 10

    async def fake_write_letter(offer, budget, **kwargs):
        from agents.writer import GeneratedLetter

        return GeneratedLetter(offer_id=offer.id, text="t", docx=b"x", filename="l.docx")

    monkeypatch.setattr("agents.graph.write_letter", fake_write_letter)

    for _ in range(24):
        pipeline = _pipeline(already_today=total, per_run=10, per_day=cap)
        pipeline.budget = MagicMock()
        result = await pipeline.node_write(
            {"run_id": "r", "criteria": criteria, "matched": _offers(10), "errors": []}
        )
        total += result["letters_generated"]

    assert total == cap, f"{total} lettres produites, plafond attendu {cap}"
