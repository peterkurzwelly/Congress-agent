#!/bin/sh
# SQLite backup script for Congress Trades
# Runs inside the backup container; expects DB_PATH and BACKUP_DIR env vars.

set -e

DB_PATH="${DB_PATH:-/app/data/congress_trades.db}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_DAYS=7

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
BACKUP_NAME="congress_trades_${TIMESTAMP}.db"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"
COMPRESSED_PATH="${BACKUP_PATH}.gz"

log() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"
}

log "Starting SQLite backup"
log "Source: ${DB_PATH}"
log "Destination: ${COMPRESSED_PATH}"

# Verify the source database exists
if [ ! -f "${DB_PATH}" ]; then
    log "ERROR: database file not found at ${DB_PATH}"
    exit 1
fi

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

# Perform an online backup using sqlite3's .backup command.
# This is safe to run while the database is open (WAL-safe).
log "Running sqlite3 .backup command..."
sqlite3 "${DB_PATH}" ".backup '${BACKUP_PATH}'"

# Verify the backup was created and is non-empty
if [ ! -s "${BACKUP_PATH}" ]; then
    log "ERROR: backup file is empty or was not created"
    exit 1
fi

BACKUP_SIZE=$(du -sh "${BACKUP_PATH}" | cut -f1)
log "Backup created successfully (${BACKUP_SIZE}), compressing..."

# Compress with gzip (best compression)
gzip -9 "${BACKUP_PATH}"

COMPRESSED_SIZE=$(du -sh "${COMPRESSED_PATH}" | cut -f1)
log "Compressed backup: ${COMPRESSED_PATH} (${COMPRESSED_SIZE})"

# Prune backups older than KEEP_DAYS days
log "Pruning backups older than ${KEEP_DAYS} days..."
PRUNED=0
find "${BACKUP_DIR}" -name "congress_trades_*.db.gz" -type f -mtime "+${KEEP_DAYS}" | while read -r old_file; do
    log "  Removing old backup: ${old_file}"
    rm -f "${old_file}"
    PRUNED=$((PRUNED + 1))
done

TOTAL=$(find "${BACKUP_DIR}" -name "congress_trades_*.db.gz" -type f | wc -l)
log "Backup complete. ${TOTAL} backup(s) retained in ${BACKUP_DIR}."
