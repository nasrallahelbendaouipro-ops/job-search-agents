"""Tests de l'étage LLM du filtre, avec un faux modèle.

Aucun appel réseau : on vérifie la construction du prompt, le découpage en
lots, et surtout la robustesse au parsing — une réponse malformée ne doit
jamais faire disparaître silencieusement une offre.
"""

from __future__ import annotations

import json

import pytest

from agents.filter import BATCH_SIZE, _criteria_block, _parse_verdicts, classify
from agents.llm.client import LLMResponse
from agents.models import Criteria, RawOffer


class FakeFilterLLM:
    """Faux modèle : renvoie des réponses scriptées et enregistre les appels."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []
        self.model = "fake-filter"

    async def complete(self, system: str, user: str, *, max_tokens: int = 4000):
        self.calls.append((system, user))
        payload = self._responses.pop(0) if self._responses else '{"verdicts": []}'
        return LLMResponse(text=payload, input_tokens=100, output_tokens=50, model=self.model)


class FakeBudget:
    def __init__(self, *, fail_after: int | None = None):
        self.checks = 0
        self.records: list[dict] = []
        self._fail_after = fail_after

    def check(self) -> None:
        self.checks += 1
        if self._fail_after is not None and self.checks > self._fail_after:
            from agents.llm.budget import BudgetExceeded

            raise BudgetExceeded("plafond atteint")

    def record(self, **kwargs) -> float:
        self.records.append(kwargs)
        return 0.0


def offer(n: int) -> RawOffer:
    return RawOffer(
        source="france_travail",
        source_offer_id=str(n),
        country="FR",
        title=f"Data Analyst {n}",
        url=f"https://example.com/{n}",
        description="Analyse de données.",
    )


def verdicts_payload(ids: list[str], *, score: int = 80, keep: bool = True) -> str:
    return json.dumps(
        {
            "verdicts": [
                {"source_offer_id": i, "score": score, "keep": keep, "reason": "test"}
                for i in ids
            ]
        }
    )


# -- Construction du prompt --------------------------------------------------


def test_criteria_block_reflects_the_criteria(criteria: Criteria) -> None:
    block = _criteria_block(criteria)
    assert "data analyst" in block
    assert "Pays FR (priorité 1)" in block
    assert "Casablanca" in block  # villes marocaines du seed


def test_prompt_changes_with_the_criteria(criteria: Criteria) -> None:
    """Preuve que le prompt est bien dérivé des critères, pas figé."""
    before = _criteria_block(criteria)
    criteria.titles_include.append("ingénieur qualité")
    assert "ingénieur qualité" in _criteria_block(criteria)
    assert before != _criteria_block(criteria)


# -- Parsing des verdicts ----------------------------------------------------


def test_parses_a_well_formed_response() -> None:
    batch = [offer(1), offer(2)]
    verdicts = _parse_verdicts(verdicts_payload(["1", "2"]), batch)

    assert [v.source_offer_id for v in verdicts] == ["1", "2"]
    assert all(v.keep for v in verdicts)


def test_keeps_offers_missing_from_the_response() -> None:
    """Une offre oubliée par le modèle est conservée pour revue manuelle."""
    batch = [offer(1), offer(2)]
    verdicts = _parse_verdicts(verdicts_payload(["1"]), batch)

    missing = next(v for v in verdicts if v.source_offer_id == "2")
    assert missing.keep is True
    assert "manuellement" in missing.reason


def test_keeps_everything_when_the_response_is_not_json() -> None:
    batch = [offer(1), offer(2)]
    verdicts = _parse_verdicts("désolé, je ne peux pas répondre", batch)

    assert len(verdicts) == 2
    assert all(v.keep for v in verdicts)


def test_clamps_out_of_range_scores() -> None:
    payload = json.dumps(
        {"verdicts": [{"source_offer_id": "1", "score": 150, "keep": True, "reason": "x"}]}
    )
    assert _parse_verdicts(payload, [offer(1)])[0].score == 100


def test_survives_a_non_numeric_score() -> None:
    payload = json.dumps(
        {"verdicts": [{"source_offer_id": "1", "score": "élevé", "keep": True, "reason": "x"}]}
    )
    verdict = _parse_verdicts(payload, [offer(1)])[0]
    assert verdict.keep is True
    assert "illisible" in verdict.reason


def test_rejection_is_respected() -> None:
    verdicts = _parse_verdicts(verdicts_payload(["1"], score=20, keep=False), [offer(1)])
    assert verdicts[0].keep is False
    assert verdicts[0].score == 20


# -- Découpage en lots et budget --------------------------------------------


@pytest.mark.asyncio
async def test_batches_offers(criteria: Criteria) -> None:
    offers = [offer(i) for i in range(BATCH_SIZE + 3)]
    llm = FakeFilterLLM(
        [
            verdicts_payload([str(i) for i in range(BATCH_SIZE)]),
            verdicts_payload([str(i) for i in range(BATCH_SIZE, BATCH_SIZE + 3)]),
        ]
    )
    budget = FakeBudget()

    verdicts = await classify(offers, criteria, budget, llm=llm)  # type: ignore[arg-type]

    assert len(llm.calls) == 2
    assert len(verdicts) == BATCH_SIZE + 3
    assert len(budget.records) == 2


@pytest.mark.asyncio
async def test_respects_the_per_run_cap(criteria: Criteria) -> None:
    offers = [offer(i) for i in range(30)]
    llm = FakeFilterLLM([verdicts_payload([str(i) for i in range(5)])])

    verdicts = await classify(offers, criteria, FakeBudget(), llm=llm, max_offers=5)  # type: ignore[arg-type]

    assert len(verdicts) == 5
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_stops_when_the_budget_is_exhausted(criteria: Criteria) -> None:
    from agents.llm.budget import BudgetExceeded

    offers = [offer(i) for i in range(BATCH_SIZE * 2)]
    llm = FakeFilterLLM([verdicts_payload([str(i) for i in range(BATCH_SIZE)])])
    budget = FakeBudget(fail_after=1)

    with pytest.raises(BudgetExceeded):
        await classify(offers, criteria, budget, llm=llm)  # type: ignore[arg-type]

    # Le second lot n'a jamais été envoyé.
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_no_offers_means_no_llm_call(criteria: Criteria) -> None:
    llm = FakeFilterLLM([])
    assert await classify([], criteria, FakeBudget(), llm=llm) == []  # type: ignore[arg-type]
    assert llm.calls == []
