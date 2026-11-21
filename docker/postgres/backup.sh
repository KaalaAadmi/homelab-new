#!/bin/bash
# Dumps every app database to ~/volumes/postgres-backups/<db>-<date>.dump and keeps 14 days.
# Run it by hand, or nightly with the systemd timer in the README.
set -euo pipefail
docker exec postgres bash -c '
  set -euo pipefail
  stamp=$(date +%F)
  for db in $(psql -U postgres -Atc "SELECT datname FROM pg_database WHERE datname NOT IN ('"'"'postgres'"'"','"'"'template0'"'"','"'"'template1'"'"')"); do
    pg_dump -U postgres -Fc "$db" > "/backups/$db-$stamp.dump"
    echo "dumped $db"
  done
  pg_dumpall -U postgres --globals-only > "/backups/globals-$stamp.sql"
  find /backups -name "*.dump" -mtime +14 -delete
  find /backups -name "globals-*.sql" -mtime +14 -delete
'
