#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────
# Restore a HOBB Postgres dump.
#
# Usage: ./scripts/restore_db.sh /path/to/hobb_db_YYYYMMDD.sql.gz
# ────────────────────────────────────────────────────────────────────
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <dump.sql.gz>" >&2
  exit 2
fi

DUMP="$1"
CONTAINER="${HOBB_DB_CONTAINER:-hobb-db}"

if [[ ! -f "${DUMP}" ]]; then
  echo "[restore] file not found: ${DUMP}" >&2
  exit 1
fi

if [[ -f .env ]]; then
  # shellcheck disable=SC2046
  export $(grep -E '^(POSTGRES_USER|POSTGRES_DB)=' .env | xargs)
fi

PG_USER="${POSTGRES_USER:-hobb}"
PG_DB="${POSTGRES_DB:-hobb}"

read -r -p "This will OVERWRITE database ${PG_DB}. Continue? [y/N] " ok
[[ "${ok,,}" == "y" ]] || { echo "aborted"; exit 1; }

echo "[restore] piping ${DUMP} into ${CONTAINER}"
gunzip -c "${DUMP}" | docker exec -i "${CONTAINER}" psql -U "${PG_USER}" -d "${PG_DB}"

echo "[restore] done"
