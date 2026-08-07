#!/bin/bash

# PostgreSQL Backup Script for Invest
# Runs daily backups with rotation (keeps last 7 days)
# Transfers to debian laptop via Cloudflare Tunnel

set -e

# Configuration
# Override with INVEST_BACKUP_DIR; defaults to backups/ inside the repo.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${INVEST_BACKUP_DIR:-$REPO_ROOT/backups}"
LOG_FILE="$BACKUP_DIR/backup.log"
KEEP_DAYS=7

# Credentials come from DB_URL, or from ~/.invest_db_url if that is unset —
# the same source the Python code uses. Nothing is hardcoded here.
DB_URL="${DB_URL:-$(cat "$HOME/.invest_db_url" 2>/dev/null)}"
if [ -z "$DB_URL" ]; then
    echo "DB_URL is not set and $HOME/.invest_db_url does not exist; cannot back up." >&2
    exit 1
fi

# Split postgresql://USER:PASSWORD@HOST[:PORT]/DBNAME into its parts.
_rest="${DB_URL#*://}"
_creds="${_rest%%@*}"
_target="${_rest#*@}"
_hostport="${_target%%/*}"
DB_USER="${_creds%%:*}"
DB_PASSWORD="${_creds#*:}"
DB_NAME="${_target##*/}"
DB_HOST="${_hostport%%:*}"
DB_PORT="${_hostport#*:}"
[ "$DB_PORT" = "$DB_HOST" ] && DB_PORT=5432

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.sql"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# ── Local backup ─────────────────────────────────────────────────────────

log_message "Starting PostgreSQL backup for invest..."

export PGPASSWORD="$DB_PASSWORD"

if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" > "$BACKUP_FILE"; then
    gzip "$BACKUP_FILE"
    BACKUP_FILE="$BACKUP_FILE.gz"
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log_message "Backup completed: $(basename "$BACKUP_FILE") ($BACKUP_SIZE)"

    log_message "Cleaning up backups older than $KEEP_DAYS days..."
    find "$BACKUP_DIR" -name "backup_*.sql.gz" -type f -mtime +$KEEP_DAYS -delete
    BACKUP_COUNT=$(find "$BACKUP_DIR" -name "backup_*.sql.gz" -type f | wc -l)
    log_message "Cleanup done. $BACKUP_COUNT backup files remaining."
else
    log_message "ERROR: Backup failed!"
    exit 1
fi

unset PGPASSWORD

# ── Transfer to debian laptop ────────────────────────────────────────────

log_message "Starting backup transfer to debian laptop..."

MAX_RETRIES=8
RETRY_DELAY=30
TRANSFER_SUCCESS=false

try_ssh_command() {
    timeout 120 bash -c "$1"
    return $?
}

for attempt in $(seq 1 $MAX_RETRIES); do
    log_message "Attempt $attempt/$MAX_RETRIES: Creating remote directory..."
    if try_ssh_command "ssh debian 'mkdir -p ~/backups/invest'"; then
        break
    else
        if [ $attempt -lt $MAX_RETRIES ]; then
            log_message "Failed to connect, retrying in ${RETRY_DELAY}s..."
            sleep $RETRY_DELAY
            RETRY_DELAY=$((RETRY_DELAY * 2))
        else
            log_message "ERROR: Failed to connect after $MAX_RETRIES attempts"
            log_message "Local backup OK, remote backup failed."
            exit 0
        fi
    fi
done

RETRY_DELAY=10

for attempt in $(seq 1 $MAX_RETRIES); do
    log_message "Attempt $attempt/$MAX_RETRIES: Transferring backup..."
    if try_ssh_command "scp '$BACKUP_FILE' debian:~/backups/invest/"; then
        log_message "Backup transferred to debian: $(basename "$BACKUP_FILE")"
        TRANSFER_SUCCESS=true
        break
    else
        if [ $attempt -lt $MAX_RETRIES ]; then
            log_message "Transfer failed, retrying in ${RETRY_DELAY}s..."
            sleep $RETRY_DELAY
            RETRY_DELAY=$((RETRY_DELAY * 2))
        else
            log_message "ERROR: Failed to transfer after $MAX_RETRIES attempts"
            log_message "Local backup OK, remote backup failed."
            exit 0
        fi
    fi
done

if [ "$TRANSFER_SUCCESS" = true ]; then
    log_message "Cleaning up old backups on debian..."
    if try_ssh_command "ssh debian 'find ~/backups/invest -name \"backup_*.sql.gz\" -type f -mtime +$KEEP_DAYS -delete'"; then
        REMOTE_COUNT=$(try_ssh_command "ssh debian 'find ~/backups/invest -name \"backup_*.sql.gz\" -type f | wc -l'")
        log_message "Remote cleanup done. $REMOTE_COUNT files on debian."
    else
        log_message "WARNING: Remote cleanup failed"
    fi
fi

log_message "Backup process completed."
