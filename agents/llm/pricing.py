"""Tarifs par modèle, en dollars par million de tokens.

Sert uniquement à estimer le coût pour le plafond de dépense et l'affichage
dans le dashboard — ce n'est pas une facture. Les tarifs des fournisseurs
changent : vérifie-les avant de te fier au chiffre affiché.

Sources : tarifs publics au 2026-08. Claude Haiku 4.5 = 1 $ / 5 $ (confirmé
via la documentation officielle de l'API Anthropic).
"""

from __future__ import annotations

#: Taux de conversion USD -> EUR. Approximation assumée : le plafond est un
#: garde-fou, pas un poste comptable.
USD_TO_EUR = 0.92

#: (prix input, prix output) par million de tokens, en USD.
PRICING: dict[str, tuple[float, float]] = {
    # Rédaction des lettres
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
    # Filtrage low-cost
    "deepseek-v4-flash": (0.14, 0.28),
    "gemini-2.5-flash-lite": (0.10, 0.40),
}

#: Tarif appliqué à un modèle inconnu. Volontairement pessimiste : mieux vaut
#: déclencher le plafond trop tôt que dépenser sans le voir.
FALLBACK = (5.00, 25.00)


def cost_eur(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICING.get(model, FALLBACK)
    usd = (input_tokens * price_in + output_tokens * price_out) / 1_000_000
    return round(usd * USD_TO_EUR, 6)
