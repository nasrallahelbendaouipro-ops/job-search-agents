"""Interface commune à toutes les sources d'offres.

Ajouter une source (Rekrute, HelloWork, StepStone…) revient à écrire une classe
qui hérite de `JobSource` et normalise vers `RawOffer`. Le reste du pipeline
n'a alors rien à changer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Criteria, RawOffer


class JobSource(ABC):
    #: Identifiant stocké dans `offers.source`.
    name: str
    #: Code pays ISO des offres renvoyées par cette source.
    country: str

    @abstractmethod
    async def fetch(self, criteria: Criteria) -> list[RawOffer]:
        """Récupère les offres correspondant grossièrement aux critères.

        La source fait un premier tri côté serveur quand l'API le permet
        (mots-clés, type de contrat, date). Le filtrage fin est la
        responsabilité de `agents/filter.py` — une source ne doit jamais
        décider seule qu'une offre n'est pas pertinente.
        """
        raise NotImplementedError
