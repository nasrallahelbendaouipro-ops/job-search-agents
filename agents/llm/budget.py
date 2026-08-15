"""Plafond de dépense LLM.

Trois barrières, du plus large au plus fin :

1. plafond mensuel en euros (`MONTHLY_BUDGET_EUR`) ;
2. plafonds par exécution (nombre de lettres, nombre d'offres classées) ;
3. journalisation de chaque appel dans `llm_usage`, qui alimente le point 1.

Le dépassement lève `BudgetExceeded`, que le graphe attrape pour terminer
l'exécution proprement en `budget_exceeded` au lieu de continuer à dépenser.
"""

from __future__ import annotations

import logging

from ..config import get_settings
from ..db import Database
from .pricing import cost_eur

logger = logging.getLogger(__name__)


class BudgetExceeded(RuntimeError):
    """Levée quand un appel ferait dépasser le plafond mensuel."""


class BudgetGuard:
    def __init__(self, db: Database, run_id: str):
        self.db = db
        self.run_id = run_id
        settings = get_settings()
        self.monthly_budget = settings.monthly_budget_eur
        # Le total du mois est lu une fois au démarrage puis maintenu en
        # mémoire : une requête par appel LLM serait du bruit inutile sur
        # Postgres pour une valeur qui ne bouge que de notre fait.
        self._spent = db.spend_this_month_eur()
        logger.info(
            "Budget : %.4f € déjà dépensés ce mois-ci sur %.2f €.",
            self._spent,
            self.monthly_budget,
        )

    @property
    def spent_eur(self) -> float:
        return self._spent

    @property
    def remaining_eur(self) -> float:
        return max(0.0, self.monthly_budget - self._spent)

    def check(self) -> None:
        """À appeler avant chaque appel LLM."""
        if self._spent >= self.monthly_budget:
            raise BudgetExceeded(
                f"Plafond mensuel atteint : {self._spent:.4f} € / "
                f"{self.monthly_budget:.2f} €. Le pipeline s'arrête."
            )

    def record(
        self, *, agent: str, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Journalise un appel et met à jour le total du mois."""
        cost = cost_eur(model, input_tokens, output_tokens)
        self._spent += cost
        self.db.record_usage(
            run_id=self.run_id,
            agent=agent,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_eur=cost,
        )
        return cost
