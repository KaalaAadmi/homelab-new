#!/bin/bash
# Creates one login and one database per app, owned by that login.
# Runs by itself the first time Postgres starts with an empty data folder.
# Safe to run again later (it skips what already exists), for example after adding an app:
#   docker compose up -d        # so the container sees the new password in .env
#   docker exec postgres bash /docker-entrypoint-initdb.d/10-app-databases.sh
set -euo pipefail

# database  login  password variable  extensions
APPS=(
  "authentik authentik AUTHENTIK_DB_PASSWORD -"
  "miniflux  miniflux  MINIFLUX_DB_PASSWORD  -"
  "speedtest speedtest SPEEDTEST_DB_PASSWORD -"
  "nextcloud nextcloud NEXTCLOUD_DB_PASSWORD -"
  "firefly   firefly   FIREFLY_DB_PASSWORD   -"
  "litellm   litellm   LITELLM_DB_PASSWORD   -"
  "kan       kan       KAN_DB_PASSWORD       -"
  "n8n       n8n       N8N_DB_PASSWORD       -"
  "neohabit  neohabit  NEOHABIT_DB_PASSWORD  -"
  "vaultwarden vaultwarden VAULTWARDEN_DB_PASSWORD -"
  "sherpa    sherpa    SHERPA_DB_PASSWORD    -"
  "paperless paperless PAPERLESS_DB_PASSWORD -"
  "mealie    mealie    MEALIE_DB_PASSWORD    -"
  "yeti      yeti      YETI_DB_PASSWORD      vector,pg_trgm"
  "yeti_dev  yeti_dev  YETI_DEV_DB_PASSWORD  vector,pg_trgm"
)

for line in "${APPS[@]}"; do
  read -r db user var exts <<<"$line"
  pass="${!var:-}"
  if [ -z "$pass" ]; then
    echo "skipping $db: $var is empty"
    continue
  fi
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
       -v db="$db" -v user="$user" -v pass="$pass" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'user', :'pass')
  WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'user') \gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'user', :'pass') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'db', :'user')
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'db') \gexec
SQL
  if [ "$exts" != "-" ]; then
    for ext in ${exts//,/ }; do
      psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" -c "CREATE EXTENSION IF NOT EXISTS \"$ext\";"
    done
  fi
  echo "ready: database $db, login $user"
done
