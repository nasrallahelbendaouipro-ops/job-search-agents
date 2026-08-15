"""API interne du service d'agents.

Ce service n'est jamais exposé sur Internet : il écoute sur le réseau Docker
interne, et seuls le dashboard et le timer systemd l'appellent, avec l'en-tête
`X-Internal-Token`.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .config import get_settings
from .graph import Pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agents recherche d'emploi", docs_url=None, redoc_url=None)


def require_internal_token(x_internal_token: str = Header(default="")) -> None:
    expected = get_settings().internal_token
    if not expected:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_TOKEN non configuré côté serveur.",
        )
    # Comparaison à temps constant : le jeton ne doit pas fuiter par timing.
    if not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton interne invalide.")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run/nightly", dependencies=[Depends(require_internal_token)])
async def run_nightly() -> dict:
    """Exécute le pipeline complet et renvoie le résumé de l'exécution."""
    return await Pipeline().run()
