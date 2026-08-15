"""Fixtures partagées et chargement des critères réels depuis le seed SQL.

Les tests du filtre s'appuient sur les mêmes critères que la production : si le
seed change, les tests reflètent le changement au lieu de valider une copie
figée.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from agents.models import Criteria

SEED_PATH = Path(__file__).resolve().parents[2] / "supabase" / "seed.sql"


def _jsonb_to_python(sql: str) -> dict:
    """Évalue les appels `jsonb_build_*` du seed en structures Python.

    Une dépendance à psycopg pour lire un fichier statique serait
    disproportionnée ; ces trois fonctions suffisent à couvrir le seed.
    """
    from ast import literal_eval

    expr = sql
    expr = re.sub(r"jsonb_build_object\s*\(", "__obj(", expr)
    expr = re.sub(r"jsonb_build_array\s*\(", "__arr(", expr)
    # Les chaînes SQL sont en quotes simples, avec '' pour un apostrophe.
    expr = expr.replace("''", "\\'")

    def __obj(*args):
        return {args[i]: args[i + 1] for i in range(0, len(args), 2)}

    def __arr(*args):
        return list(args)

    return eval(expr, {"__obj": __obj, "__arr": __arr, "true": True, "false": False})  # noqa: S307


@pytest.fixture(scope="session")
def seeded_criteria() -> Criteria:
    """Critères tels que définis dans supabase/seed.sql."""
    sql = SEED_PATH.read_text(encoding="utf-8")
    match = re.search(r"(jsonb_build_object\s*\(.*\n\s*\)\s*)\nwhere exists", sql, re.DOTALL)
    assert match, "Impossible de localiser le bloc jsonb_build_object dans seed.sql"

    # Retire les commentaires SQL, qui ne sont pas du Python valide.
    body = "\n".join(
        line for line in match.group(1).splitlines() if not line.strip().startswith("--")
    )
    data = _jsonb_to_python(body)
    return Criteria.model_validate(data)


@pytest.fixture
def criteria(seeded_criteria: Criteria) -> Criteria:
    """Copie modifiable des critères, pour ne pas polluer les autres tests."""
    return seeded_criteria.model_copy(deep=True)
