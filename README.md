# Plateforme d'agents IA — recherche d'emploi automatisée

Dashboard personnel qui, chaque nuit, récupère les offres d'emploi, les filtre
selon des critères configurables, rédige une lettre de motivation pour celles
qui sont retenues, et prépare la candidature. Le matin, tout est prêt à être
relu et envoyé.

**Le pipeline ne postule jamais tout seul.** Il prépare et s'arrête. L'envoi est
une action que tu déclenches depuis le dashboard, offre par offre.

## État actuel — Phase 1

| Brique | État |
|---|---|
| Schéma Supabase + RLS | fait |
| Source France Travail (API officielle) | fait |
| Pré-filtre déterministe | fait |
| Filtre LLM low-cost | fait |
| Rédaction des lettres (Claude Haiku 4.5) + `.docx` | fait |
| Classification du canal de candidature | fait |
| Plafond de dépense | fait |
| Dashboard (6 pages) | fait |
| Docker + Caddy + timer systemd | fait |
| Scrapers Rekrute / HelloWork / StepStone / Xing | à venir |

Aucun scraper LinkedIn ou Indeed n'est prévu : leurs conditions d'utilisation
l'interdisent. La page `/liens` génère à la place des recherches pré-remplies à
ouvrir manuellement.

## Architecture

```
VPS Hostinger KVM 2
├── caddy   : seul service exposé (80/443), HTTPS automatique
├── web     : dashboard Next.js
├── agents  : FastAPI + LangGraph + Playwright, réseau interne uniquement
└── timer systemd (03:00 Europe/Paris) → pipeline

Supabase : Postgres + Auth + Storage (CV, lettres générées)
```

Pipeline : `scraper → pré-filtre → filtre LLM → rédacteur → candidature`.
Chaque étape écrit son résultat en base avant la suivante, pour qu'un échec en
milieu de chaîne ne perde pas le travail déjà fait.

## Maîtrise du coût

Cible : 3 à 8 €/mois. Quatre mécanismes :

1. **Déduplication** — une offre déjà vue n'est jamais re-filtrée ni re-rédigée.
2. **Pré-filtre déterministe** — écarte la majorité des offres sans appel LLM.
3. **Deux modèles** — un modèle low-cost pour classer, Claude Haiku 4.5
   (1 $ / 5 $ par 1M tokens) seulement pour rédiger.
4. **Plafonds** — budget mensuel en euros, nombre de lettres par nuit, nombre
   d'offres classées par nuit. Chaque appel est journalisé dans `llm_usage` et
   affiché sur `/runs`.

Le dépassement du plafond n'est pas une erreur : l'exécution se termine
proprement en `budget_exceeded` avec tout ce qui a été produit jusque-là.

## Développement local

Service Python :

```bash
python -m venv .venv
.venv/Scripts/pip install -r agents/requirements.txt
.venv/Scripts/python -m pytest
```

Dashboard (Node 22 requis — `@supabase/supabase-js` ne supporte plus Node 20) :

```bash
cd web && npm install && npm run dev
```

## Configuration des critères

Aucun critère de matching n'est codé en dur. Ils vivent dans la table
`profile_criteria` (JSONB versionné) et s'éditent depuis `/criteres`. Le format
a deux définitions qui doivent rester alignées :

- `web/lib/schemas/criteria.ts` (Zod, validation du formulaire) ;
- `agents/models.py::Criteria` (Pydantic, lecture par le pipeline).

Le test `test_seed_loads_into_criteria_model` échoue si les deux divergent.

## Déploiement

Voir [`deploy/README-deploy.md`](deploy/README-deploy.md).

## Historique du dépôt

Ce dépôt s'ouvre sur un commit unique : la Phase 1 y a été publiée d'un bloc,
après avoir été prototypée localement hors versionnement. L'historique ne
reflète donc pas le déroulé réel du développement, et je préfère le dire plutôt
que de le maquiller après coup.

Les phases suivantes (scrapers Rekrute / HelloWork / StepStone / Xing, cf. le
tableau d'état plus haut) sont versionnées normalement, commit par commit.

## Hors périmètre V1

Conformément au cahier des charges : pas de notifications push ou email en
arrière-plan, pas d'auto-candidature LinkedIn Easy Apply, pas de suivi des
relances ni des entretiens.
