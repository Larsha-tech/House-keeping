#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────
# Snapshot the uploads directory to a timestamped tar.gz.
#
# Usage:   ./scripts/backup_uploads.sh [backup_dir]
# Cron:    30 2 * * *  /opt/hobb/scripts/backup_uploads.sh /var/backups/hobb
# ────────────────────────────────────────────────────────────────────
set -euo pipefail

BACKUP_DIR="${1:-./backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="${BACKUP_DIR}/hobb_uploads_${STAMP}.tar.gz"
KEEP_DAYS="${HOBB_BACKUP_KEEP_DAYS:-14}"

# Source env for UPLOAD_VOLUME
if [[ -f .env ]]; then
  # shellcheck disable=SC2046
  export $(grep -E '^UPLOAD_VOLUME=' .env | xargs) || true
fi

SRC="${UPLOAD_VOLUME:-./storage/uploads}"

if [[ ! -d "${SRC}" ]]; then
  echo "[backup_uploads] source directory ${SRC} does not exist, skipping"
  exit 0
fi

mkdir -p "${BACKUP_DIR}"

echo "[backup_uploads] archiving ${SRC} -> ${OUT}"
tar -czf "${OUT}" -C "$(dirname "${SRC}")" "$(basename "${SRC}")"

echo "[backup_uploads] done: $(du -h "${OUT}" | cut -f1)"

# Prune
find "${BACKUP_DIR}" -name 'hobb_uploads_*.tar.gz' -type f -mtime +"${KEEP_DAYS}" -print -delete || true
echo "[backup_uploads] pruned archives older than ${KEEP_DAYS} day(s)"
