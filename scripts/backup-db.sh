#!/bin/sh
# InvestAI — Database backup script
# Runs pg_dump and keeps last 7 days of backups

BACKUP_DIR="/backups"
DATE=$(date +%Y-%m-%d_%H-%M-%S)
FILENAME="investai_${DATE}.sql.gz"

echo "[$(date)] Starting backup..."

pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "${BACKUP_DIR}/${FILENAME}"

if [ $? -eq 0 ]; then
    echo "[$(date)] Backup successful: ${FILENAME}"
    # Remove backups older than 7 days
    find "$BACKUP_DIR" -name "investai_*.sql.gz" -mtime +7 -delete
    echo "[$(date)] Old backups cleaned up"
else
    echo "[$(date)] ERROR: Backup failed!"
    exit 1
fi
