"""Clients LLM : un modèle low-cost pour le filtrage, Claude pour la rédaction.

Le filtrage passe par un client compatible OpenAI (DeepSeek ou Gemini), la
rédaction par le SDK Anthropic. Les deux renvoient le texte **et** le compte de
tokens, pour que `BudgetGuard` puisse tenir le plafond.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import anthropic
from openai import AsyncOpenAI

from ..config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class FilterLLM:
    """Modèle low-cost pour la classification des offres.

    DeepSeek et Gemini exposent tous deux une API compatible OpenAI ; changer
    de fournisseur est un changement de variables d'environnement, pas de code.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.filter_model
        self._client = AsyncOpenAI(
            api_key=settings.filter_api_key,
            base_url=settings.filter_base_url,
        )

    async def complete(self, system: str, user: str, *, max_tokens: int = 4000) -> LLMResponse:
        res = await self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0,  # classification : on veut un verdict stable
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        usage = res.usage
        return LLMResponse(
            text=res.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=self.model,
        )


class WriterLLM:
    """Claude Haiku 4.5 pour la rédaction des lettres de motivation.

    Le compromis qualité/prix visé par le cahier des charges : 1 $ / 5 $ par
    million de tokens pour un texte qui représente la candidature.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.writer_model
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def complete(self, system: str, user: str, *, max_tokens: int = 2000) -> LLMResponse:
        res = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in res.content if block.type == "text")
        return LLMResponse(
            text=text,
            input_tokens=res.usage.input_tokens,
            output_tokens=res.usage.output_tokens,
            model=self.model,
        )
