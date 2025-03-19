#!/bin/bash

# Create backup directory if it doesn't exist
BACKUP_DIR=~/heltour/backups
mkdir -p "$BACKUP_DIR"

# Generate timestamp for the backup filename
TIMESTAMP=$(date +%Y%m%d_%H%M)

# Ask for an optional name
echo "Enter an optional name for this backup (press enter to skip):"
read BACKUP_NAME

# Construct the filename
if [ -z "$BACKUP_NAME" ]; then
    FILENAME="heltour_backup_${TIMESTAMP}.sql.bz2"
else
    # Replace spaces with underscores in the backup name
    BACKUP_NAME=$(echo "$BACKUP_NAME" | tr ' ' '_')
    FILENAME="heltour_backup_${TIMESTAMP}_${BACKUP_NAME}.sql.bz2"
fi

BACKUP_PATH="$BACKUP_DIR/$FILENAME"

# Perform the backup with pg_dump and compress with bzip2
echo "Creating backup at $BACKUP_PATH..."
pg_dump -h localhost -U heltour_lichess4545 heltour_lichess4545 | bzip2 > "$BACKUP_PATH"

# Check if the backup was successful
if [ $? -eq 0 ]; then
    echo "Backup completed successfully!"
    echo "Backup saved to: $BACKUP_PATH"
else
    echo "Backup failed!" >&2
    exit 1
fi
