"""Socle pour les scrapers Playwright (Rekrute, HelloWork, StepStone, Xing).

Non utilisé en Phase 1 — France Travail passe par son API officielle. Ce module
existe pour que l'ajout d'un scraper n'ait pas à réinventer le rate limiting ni
le respect de robots.txt.

Aucun scraper LinkedIn ou Indeed n'est prévu ici : leurs CGU l'interdisent, et
le dashboard propose à la place des liens de recherche pré-remplis (page
`/liens`) à ouvrir manuellement.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import urllib.robotparser
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass
class RateLimiter:
    """Limiteur à jeton simple, avec délai aléatoire entre deux requêtes.

    `min_delay`/`max_delay` produisent un espacement irrégulier : une cadence
    parfaitement régulière est le signal le plus facile à repérer côté serveur.
    """

    min_delay: float = 2.0
    max_delay: float = 5.0
    _last_call: float = field(default=0.0, repr=False)

    async def wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        delay = random.uniform(self.min_delay, self.max_delay)
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
        self._last_call = time.monotonic()


class RobotsCache:
    """Vérifie robots.txt avant de visiter une URL, avec cache par domaine."""

    def __init__(self) -> None:
        self._parsers: dict[str, urllib.robotparser.RobotFileParser] = {}

    async def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        if origin not in self._parsers:
            parser = urllib.robotparser.RobotFileParser()
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.get(
                        f"{origin}/robots.txt", headers={"User-Agent": USER_AGENT}
                    )
                parser.parse(res.text.splitlines())
            except httpx.HTTPError:
                # robots.txt inaccessible : on refuse par prudence plutôt que
                # de supposer une autorisation.
                logger.warning("robots.txt illisible pour %s — accès refusé.", origin)
                parser.disallow_all = True
            self._parsers[origin] = parser

        return self._parsers[origin].can_fetch(USER_AGENT, url)


@asynccontextmanager
async def browser_page(*, headless: bool = True):
    """Ouvre une page Playwright configurée.

    Un seul navigateur à la fois par exécution : sur un VPS 2 vCPU / 8 Go,
    lancer plusieurs Chromium en parallèle sature la RAM et fait échouer le run
    entier plutôt qu'un seul scraper.
    """
    from playwright.async_api import async_playwright  # import tardif : lourd

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="fr-FR",
            viewport={"width": 1366, "height": 768},
        )
        page = await context.new_page()
        try:
            yield page
        finally:
            await context.close()
            await browser.close()
