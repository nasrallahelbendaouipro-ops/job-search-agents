-- Row Level Security : chaque table n'est lisible/modifiable que par son propriétaire.
-- Le service Python utilise la clé `service_role`, qui contourne la RLS par design ;
-- il filtre donc explicitement sur owner_id dans agents/db.py.

alter table profile_criteria enable row level security;
alter table agent_runs       enable row level security;
alter table offers           enable row level security;
alter table documents        enable row level security;
alter table applications     enable row level security;
alter table llm_usage        enable row level security;

-- Une policy « tout ou rien » par table : l'app est mono-utilisateur, il n'y a
-- pas de cas où on lit sans pouvoir écrire.
create policy owner_all on profile_criteria
  for all using (auth.uid() = owner_id) with check (auth.uid() = owner_id);

create policy owner_all on agent_runs
  for all using (auth.uid() = owner_id) with check (auth.uid() = owner_id);

create policy owner_all on offers
  for all using (auth.uid() = owner_id) with check (auth.uid() = owner_id);

create policy owner_all on documents
  for all using (auth.uid() = owner_id) with check (auth.uid() = owner_id);

create policy owner_all on applications
  for all using (auth.uid() = owner_id) with check (auth.uid() = owner_id);

create policy owner_all on llm_usage
  for all using (auth.uid() = owner_id) with check (auth.uid() = owner_id);

-- ---------------------------------------------------------------------------
-- Buckets Storage privés : les CV et les lettres ne doivent jamais être publics.
-- ---------------------------------------------------------------------------

insert into storage.buckets (id, name, public)
values ('cvs', 'cvs', false), ('letters', 'letters', false)
on conflict (id) do nothing;

-- Convention de chemin : <bucket>/<owner_id>/<fichier>. Le premier segment du
-- chemin porte donc l'identité du propriétaire.
create policy "owner reads own files" on storage.objects
  for select using (
    bucket_id in ('cvs', 'letters')
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy "owner writes own files" on storage.objects
  for insert with check (
    bucket_id in ('cvs', 'letters')
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy "owner updates own files" on storage.objects
  for update using (
    bucket_id in ('cvs', 'letters')
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy "owner deletes own files" on storage.objects
  for delete using (
    bucket_id in ('cvs', 'letters')
    and (storage.foldername(name))[1] = auth.uid()::text
  );
