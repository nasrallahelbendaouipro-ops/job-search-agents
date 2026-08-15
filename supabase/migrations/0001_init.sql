-- Plateforme d'agents IA — recherche d'emploi automatisée
-- Schéma initial : offres, critères, candidatures, documents, exécutions, usage LLM.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Types énumérés
-- ---------------------------------------------------------------------------

create type match_status as enum ('pending', 'matched', 'rejected');

create type apply_channel as enum (
  'email',            -- adresse de contact trouvée dans l'offre
  'form',             -- formulaire simple, sans création de compte
  'easy_apply',       -- candidature simplifiée avec compte existant (LinkedIn)
  'account_required', -- création de compte / parcours complexe
  'unknown'
);

create type application_status as enum (
  'to_validate',      -- tout est prêt, en attente de ta validation
  'auto_applied',     -- envoyé automatiquement (seulement si auto_send_enabled)
  'manual_required',  -- action manuelle nécessaire
  'sent',             -- envoyé après validation
  'rejected'          -- écarté par toi
);

create type document_kind as enum ('cv', 'letter_template');

create type run_status as enum ('running', 'succeeded', 'failed', 'budget_exceeded');

-- ---------------------------------------------------------------------------
-- profile_criteria : critères de matching, versionnés, éditables sans code
-- ---------------------------------------------------------------------------

create table profile_criteria (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references auth.users (id) on delete cascade,
  version     integer not null,
  is_active   boolean not null default false,
  criteria    jsonb not null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (owner_id, version)
);

-- Une seule version active par utilisateur.
create unique index profile_criteria_one_active
  on profile_criteria (owner_id)
  where is_active;

comment on column profile_criteria.criteria is
  'JSONB validé côté app par web/lib/schemas/criteria.ts. Aucun critère en dur dans le code Python.';

-- ---------------------------------------------------------------------------
-- agent_runs : trace de chaque exécution du pipeline
-- ---------------------------------------------------------------------------

create table agent_runs (
  id                uuid primary key default gen_random_uuid(),
  owner_id          uuid not null references auth.users (id) on delete cascade,
  status            run_status not null default 'running',
  started_at        timestamptz not null default now(),
  finished_at       timestamptz,
  offers_scraped    integer not null default 0,
  offers_matched    integer not null default 0,
  letters_generated integer not null default 0,
  errors            jsonb not null default '[]'::jsonb
);

create index agent_runs_owner_started on agent_runs (owner_id, started_at desc);

-- ---------------------------------------------------------------------------
-- offers : offres récupérées, une ligne par annonce et par source
-- ---------------------------------------------------------------------------

create table offers (
  id              uuid primary key default gen_random_uuid(),
  owner_id        uuid not null references auth.users (id) on delete cascade,
  run_id          uuid references agent_runs (id) on delete set null,

  source          text not null,          -- 'france_travail', 'rekrute', ...
  source_offer_id text not null,          -- identifiant natif chez la source
  country         text not null,          -- 'FR', 'MA', 'DE'

  title           text not null,
  company         text,
  city            text,
  url             text not null,
  description     text,

  salary_min      numeric,
  salary_max      numeric,
  salary_raw      text,
  contract_type   text,                   -- 'CDI', 'CDD', 'stage', ...
  remote_policy   text,                   -- 'onsite', 'hybrid', 'remote', null si inconnu
  posted_at       timestamptz,
  scraped_at      timestamptz not null default now(),

  match_status    match_status not null default 'pending',
  match_score     integer,                -- 0-100
  match_reason    text,

  apply_channel   apply_channel not null default 'unknown',
  apply_email     text,

  constraint offers_score_range check (match_score is null or (match_score between 0 and 100))
);

-- Clé de déduplication : le cœur du contrôle de coût, une offre déjà vue
-- n'est jamais re-filtrée ni re-rédigée.
create unique index offers_dedup on offers (owner_id, source, source_offer_id);

create index offers_owner_status_scraped on offers (owner_id, match_status, scraped_at desc);
create index offers_run on offers (run_id);

-- ---------------------------------------------------------------------------
-- documents : CV (3 variantes) et template de lettre, stockés dans Storage
-- ---------------------------------------------------------------------------

create table documents (
  id            uuid primary key default gen_random_uuid(),
  owner_id      uuid not null references auth.users (id) on delete cascade,
  kind          document_kind not null,
  label         text not null,        -- 'data_analyst' | 'data_scientist' | 'industrial_engineer'
  language      text not null default 'fr',
  storage_path  text not null,        -- 'cvs/<owner>/<fichier>.pdf'
  created_at    timestamptz not null default now(),
  unique (owner_id, kind, label, language)
);

-- ---------------------------------------------------------------------------
-- applications : une candidature par offre retenue
-- ---------------------------------------------------------------------------

create table applications (
  id                  uuid primary key default gen_random_uuid(),
  owner_id            uuid not null references auth.users (id) on delete cascade,
  offer_id            uuid not null references offers (id) on delete cascade,
  run_id              uuid references agent_runs (id) on delete set null,

  status              application_status not null default 'to_validate',
  letter_text         text,               -- éditable dans le dashboard avant envoi
  letter_storage_path text,               -- 'letters/<owner>/<offre>.docx'
  cv_document_id      uuid references documents (id) on delete set null,

  created_at          timestamptz not null default now(),
  action_at           timestamptz,        -- date d'envoi / de rejet
  error               text,

  unique (offer_id)
);

create index applications_owner_status on applications (owner_id, status, created_at desc);

-- ---------------------------------------------------------------------------
-- llm_usage : journal de chaque appel LLM, alimente le plafond de dépense
-- ---------------------------------------------------------------------------

create table llm_usage (
  id            uuid primary key default gen_random_uuid(),
  owner_id      uuid not null references auth.users (id) on delete cascade,
  run_id        uuid references agent_runs (id) on delete set null,
  agent         text not null,          -- 'filter' | 'writer'
  model         text not null,
  input_tokens  integer not null default 0,
  output_tokens integer not null default 0,
  cost_eur      numeric(10, 6) not null default 0,
  created_at    timestamptz not null default now()
);

create index llm_usage_owner_created on llm_usage (owner_id, created_at desc);

-- ---------------------------------------------------------------------------
-- updated_at automatique sur profile_criteria
-- ---------------------------------------------------------------------------

create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger profile_criteria_set_updated_at
  before update on profile_criteria
  for each row execute function set_updated_at();
