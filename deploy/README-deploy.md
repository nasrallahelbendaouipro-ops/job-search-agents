# Déploiement sur VPS Hostinger KVM 2

Cible : Ubuntu 24.04, 2 vCPU / 8 Go. Tout tourne sur ce serveur ; seul Supabase
(Postgres, Auth, Storage) est dans le cloud.

## 1. Préparer le serveur

```bash
ssh root@<ip-du-vps>
```

```bash
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 git ufw
```

Le timer se déclenche sur l'heure locale du serveur — sans ça, « 3 h » sera 3 h UTC :

```bash
timedatectl set-timezone Europe/Paris
```

Pare-feu : seuls SSH et HTTPS sont ouverts. Les ports 3000 et 8000 ne sont
jamais exposés, Caddy est le seul point d'entrée.

```bash
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
```

## 2. Récupérer le projet

```bash
git clone <url-du-depot> /opt/job-search
cd /opt/job-search
cp .env.example .env
```

Génère le jeton interne et reporte-le dans `.env` :

```bash
openssl rand -hex 32
```

Renseigne ensuite dans `.env` : les clés Supabase, `OWNER_ID` (ton uuid dans
`auth.users`), les identifiants France Travail, les clés LLM, et `DOMAIN`
(le sous-domaine qui pointe vers l'IP du VPS).

Vérifie que le fichier n'est pas lisible par tous :

```bash
chmod 600 .env
```

## 3. Initialiser la base

Applique les migrations depuis ta machine (ou via l'éditeur SQL Supabase) :

```bash
psql "$SUPABASE_DB_URL" -f supabase/migrations/0001_init.sql
psql "$SUPABASE_DB_URL" -f supabase/migrations/0002_rls.sql
```

Crée ton compte dans Supabase Auth (onglet Authentication → Add user), puis
seulement ensuite :

```bash
psql "$SUPABASE_DB_URL" -f supabase/seed.sql
```

Le seed échoue silencieusement si aucun utilisateur n'existe — c'est voulu,
`owner_id` référence `auth.users`.

Enfin, dépose tes trois CV dans le bucket `cvs`, sous `<owner_id>/`, et
déclare-les :

```sql
insert into documents (owner_id, kind, label, language, storage_path) values
  ('<owner_id>', 'cv', 'data_analyst',        'fr', '<owner_id>/cv-data-analyst.pdf'),
  ('<owner_id>', 'cv', 'data_scientist',      'fr', '<owner_id>/cv-data-scientist.pdf'),
  ('<owner_id>', 'cv', 'industrial_engineer', 'fr', '<owner_id>/cv-ingenieur-industriel.pdf');
```

## 4. Lancer la pile

```bash
cd /opt/job-search
docker compose up -d --build
docker compose ps
```

Caddy demande le certificat au premier accès HTTPS : le DNS doit déjà pointer
vers le VPS, sinon la demande échoue et il retentera.

Vérifie que le service d'agents répond **depuis l'intérieur** du réseau Docker :

```bash
docker compose exec agents curl -s localhost:8000/health
```

Depuis Internet, `https://<domaine>:8000` doit être injoignable — c'est le
comportement attendu.

## 5. Installer le déclenchement nocturne

```bash
cp deploy/agents-nightly.service deploy/agents-nightly.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now agents-nightly.timer
```

Contrôles :

```bash
systemctl list-timers agents-nightly.timer   # prochaine exécution vers 03:00
systemctl start agents-nightly.service        # déclenchement manuel immédiat
journalctl -u agents-nightly.service -n 100 --no-pager
```

## 6. Vérifier le premier passage

Après une exécution manuelle, ouvre le dashboard :

- `/runs` — l'exécution apparaît avec ses compteurs et la dépense du mois ;
- `/` — les offres retenues, groupées par statut ;
- ouvre une offre, relis la lettre, télécharge le `.docx` et compare-le à une
  de tes lettres existantes.

Tant que `auto_send_enabled` est à `false` (le défaut), aucune candidature
n'est transmise : le pipeline prépare, tu décides.

## Exploitation courante

```bash
# Logs en direct
docker compose logs -f agents

# Mise à jour du code
cd /opt/job-search && git pull && docker compose up -d --build

# Suspendre les exécutions nocturnes
systemctl disable --now agents-nightly.timer
```

## Sauvegardes

Les données vivent dans Supabase, pas sur le VPS : les sauvegardes sont celles
du projet Supabase. Le seul fichier irremplaçable côté serveur est `.env` —
garde-en une copie dans ton gestionnaire de mots de passe.
