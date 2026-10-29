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

Le timer est horaire, donc le fuseau n'affecte pas son déclenchement — mais il
détermine les dates affichées dans les lettres et les logs :

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

## 5. Durcir le serveur

Pour un fonctionnement non surveillé, trois choses manquent par défaut : Docker
ne redémarre pas forcément au boot, les correctifs de sécurité ne s'appliquent
pas seuls, et SSH est exposé au bourrinage.

```bash
bash deploy/harden-vps.sh
```

Le script active Docker au démarrage, installe `unattended-upgrades` (correctifs
de sécurité uniquement, **sans redémarrage automatique** — un reboot surprise en
pleine exécution serait pire que le délai d'un correctif), installe `fail2ban`,
et borne les logs du démon Docker.

Il est idempotent : tu peux le relancer après une mise à jour du projet.

## 6. Installer le déclenchement horaire

```bash
cp deploy/agents-pipeline.service deploy/agents-pipeline.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now agents-pipeline.timer
```

La cadence du timer doit rester cohérente avec `RUN_INTERVAL_HOURS` dans
`.env` : c'est cette variable qui fixe la fenêtre de recherche envoyée aux
sources. Un timer horaire avec `RUN_INTERVAL_HOURS=24` interrogerait 26 h
d'offres chaque heure pour rien ; l'inverse ferait rater des annonces.

Le nombre de lettres est borné par `MAX_LETTERS_PER_DAY` (10 par défaut),
toutes exécutions confondues — pas par exécution.

Contrôles :

```bash
systemctl list-timers agents-pipeline.timer   # prochaine exécution dans l'heure
systemctl start agents-pipeline.service        # déclenchement manuel immédiat
journalctl -u agents-pipeline.service -n 100 --no-pager
```

## 7. Vérifier le premier passage

Après une exécution manuelle, ouvre le dashboard :

- `/runs` — l'exécution apparaît avec ses compteurs et la dépense du mois ;
- `/` — les offres retenues, groupées par statut ;
- ouvre une offre, relis la lettre, télécharge le `.docx` et compare-le à une
  de tes lettres existantes.

Tant que `auto_send_enabled` est à `false` (le défaut), aucune candidature
n'est transmise : le pipeline prépare, tu décides.

## Vérifier que ça survit à un redémarrage

C'est le test qui valide réellement le 24/7 :

```bash
reboot
```

Reconnecte-toi deux minutes plus tard et vérifie que tout est remonté seul :

```bash
docker compose ps                              # les 3 services en « Up »
systemctl list-timers agents-pipeline.timer    # prochaine exécution dans l'heure
curl -sI https://<domaine> | head -1           # le dashboard répond
```

Si un service manque, c'est que `harden-vps.sh` n'a pas été exécuté.

## Exploitation courante

```bash
# Logs en direct
docker compose logs -f agents

# Mise à jour du code
cd /opt/job-search && git pull && docker compose up -d --build

# Suspendre les exécutions
systemctl disable --now agents-pipeline.timer
```

## Sauvegardes

Les données vivent dans Supabase, pas sur le VPS : les sauvegardes sont celles
du projet Supabase. Le seul fichier irremplaçable côté serveur est `.env` —
garde-en une copie dans ton gestionnaire de mots de passe.
