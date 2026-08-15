-- Seed des critères de matching.
--
-- À exécuter UNE FOIS, après avoir créé ton compte via Supabase Auth
-- (les migrations ne peuvent pas le faire : elles tournent avant qu'un
-- utilisateur existe, et owner_id est une clé étrangère vers auth.users).
--
--   psql "$SUPABASE_DB_URL" -f supabase/seed.sql
--
-- Le script cible le premier utilisateur créé. L'app est mono-utilisateur ;
-- s'il y en a plusieurs, remplace la sous-requête par ton uuid explicite.

insert into profile_criteria (owner_id, version, is_active, criteria)
select
  (select id from auth.users order by created_at limit 1),
  1,
  true,
  jsonb_build_object(
    -- Intitulés recherchés. Le pré-filtre garde une offre si un de ces
    -- termes apparaît dans le titre (comparaison insensible à la casse
    -- et aux accents).
    'titles_include', jsonb_build_array(
      'data analyst', 'analytics engineer', 'analyste de données',
      'analyste data', 'business intelligence', 'ingénieur data',
      'data engineer', 'ingénieur industriel', 'industrial engineer',
      'consultant data', 'chargé de mission data'
    ),

    -- Intitulés qui disqualifient immédiatement, même si un terme
    -- recherché est présent ailleurs dans le titre.
    'titles_exclude', jsonb_build_array(
      'stage', 'stagiaire', 'internship', 'alternance', 'apprenti',
      'alternant', 'praktikum', 'werkstudent', 'freelance', 'indépendant',
      'senior manager', 'directeur', 'head of', 'vp '
    ),

    -- Mots-clés qui augmentent le score sans être obligatoires.
    'keywords_bonus', jsonb_build_array(
      'power bi', 'sql', 'python', 'dbt', 'snowflake', 'airflow',
      'tableau', 'looker', 'databricks', 'etl', 'kpi', 'dataviz',
      'industrie', 'aéronautique', 'automobile', 'conseil', 'secteur public'
    ),

    -- Mots-clés qui disqualifient (technos ou métiers hors profil).
    'keywords_exclude', jsonb_build_array(
      'commercial terrain', 'télévente', 'sap abap', 'salesforce admin',
      'php', 'wordpress', 'community manager'
    ),

    -- Pays ciblés, par ordre de priorité (1 = priorité la plus haute).
    -- `cities` vide = tout le pays.
    'countries', jsonb_build_array(
      jsonb_build_object(
        'code', 'FR', 'priority', 1, 'cities', jsonb_build_array()
      ),
      jsonb_build_object(
        'code', 'MA', 'priority', 2,
        'cities', jsonb_build_array('Casablanca', 'Rabat', 'Tanger', 'Marrakech')
      ),
      jsonb_build_object(
        'code', 'DE', 'priority', 2,
        'cities', jsonb_build_array('Berlin', 'Munich', 'Hambourg', 'Francfort', 'Stuttgart')
      )
    ),

    -- Langues que tu peux assurer en entretien et au quotidien.
    -- Une offre exigeant une langue absente de cette liste est écartée.
    'languages_ok', jsonb_build_array('fr', 'en'),

    -- Salaire annuel brut minimum, par pays, dans la devise locale.
    -- Une offre sans salaire affiché n'est jamais écartée sur ce critère.
    'salary_min_by_country', jsonb_build_object(
      'FR', 38000,
      'MA', 180000,
      'DE', 50000
    ),

    -- 'any' | 'prefer_remote' | 'prefer_hybrid' | 'prefer_onsite'
    -- Influence le score, n'écarte jamais une offre à elle seule.
    'remote_preference', 'prefer_hybrid',

    'contract_types', jsonb_build_array('CDI'),

    'sectors', jsonb_build_array('conseil', 'industrie', 'secteur public'),

    -- Score minimum (0-100) attribué par le LLM pour retenir une offre.
    'min_score_to_keep', 65,

    -- Interrupteur d'auto-envoi. Reste à false : l'agent prépare tout et
    -- attend ta validation dans le dashboard. Ne passe à true qu'après
    -- avoir vérifié la qualité des lettres sur plusieurs semaines.
    'auto_send_enabled', false
  )
where exists (select 1 from auth.users)
on conflict (owner_id, version) do nothing;
