#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────
# Dump the HOBB Postgres database to a timestamped gzip file.
#
# Usage:   ./scripts/backup_db.sh [backup_dir]
# Cron:    0 2 * * *  /opt/hobb/scripts/backup_db.sh /var/backups/hobb
# ────────────────────────────────────────────────────────────────────
set -euo pipefail

BACKUP_DIR="${1:-./backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="${BACKUP_DIR}/hobb_db_${STAMP}.sql.gz"
CONTAINER="${HOBB_DB_CONTAINER:-hobb-db}"
KEEP_DAYS="${HOBB_BACKUP_KEEP_DAYS:-14}"

mkdir -p "${BACKUP_DIR}"

# Source env if present (so POSTGRES_USER / POSTGRES_DB are available)
if [[ -f .env ]]; then
  # shellcheck disable=SC2046
  export $(grep -E '^(POSTGRES_USER|POSTGRES_DB)=' .env | xargs)
fi

PG_USER="${POSTGRES_USER:-hobb}"
PG_DB="${POSTGRES_DB:-hobb}"

echo "[backup_db] dumping ${PG_DB} as ${PG_USER} from ${CONTAINER} -> ${OUT}"
docker exec -e PGPASSWORD -i "${CONTAINER}" \
    pg_dump -U "${PG_USER}" -d "${PG_DB}" --no-owner --clean --if-exists \
  | gzip -9 > "${OUT}"

echo "[backup_db] done: $(du -h "${OUT}" | cut -f1)"

# Prune old backups
find "${BACKUP_DIR}" -name 'hobb_db_*.sql.gz' -type f -mtime +"${KEEP_DAYS}" -print -delete || true
echo "[backup_db] pruned backups older than ${KEEP_DAYS} day(s)"
