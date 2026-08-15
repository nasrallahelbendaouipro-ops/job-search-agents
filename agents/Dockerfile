# Image du service d'agents.
#
# Basée sur l'image Playwright officielle : elle embarque déjà Chromium et
# toutes les bibliothèques système dont il dépend. En Phase 1 (France Travail
# via API) le navigateur n'est pas utilisé, mais l'avoir dès maintenant évite
# de reconstruire l'image au premier scraper.
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY agents/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY agents ./agents

# Le service n'est jamais exposé publiquement : il n'écoute que sur le réseau
# interne Docker, et Caddy ne lui route rien.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=4).raise_for_status()"

CMD ["uvicorn", "agents.main:app", "--host", "0.0.0.0", "--port", "8000"]
