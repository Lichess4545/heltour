#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# Define backup directory
BACKUP_DIR=~/heltour/backups

# Check if backup directory exists
if [ ! -d "$BACKUP_DIR" ]; then
    echo "Error: Backup directory does not exist: $BACKUP_DIR" >&2
    exit 1
fi

# Find all backup files and sort them by modification time (newest first)
mapfile -t BACKUP_FILES < <(find "$BACKUP_DIR" -name "*.sql.bz2" -type f | sort -r)

# Check if any backups exist
if [ ${#BACKUP_FILES[@]} -eq 0 ]; then
    echo "No backup files found in $BACKUP_DIR" >&2
    exit 1
fi

# Display available backups
echo "Available backups:"
echo "-----------------"

for i in "${!BACKUP_FILES[@]}"; do
    # Extract filename from path and creation time
    FILENAME=$(basename "${BACKUP_FILES[$i]}")
    CREATION_TIME=$(stat -c "%y" "${BACKUP_FILES[$i]}" | cut -d '.' -f1)
    
    # Show index, filename and creation time
    echo "[$i] $FILENAME (created: $CREATION_TIME)"
    
    # Mark the latest backup
    if [ $i -eq 0 ]; then
        echo "     ^ LATEST"
    fi
done

echo

# Prompt for selection
echo "Enter the number of the backup to restore [0 for latest]:"
read -r SELECTION

# Default to the latest backup if empty
if [ -z "$SELECTION" ]; then
    SELECTION=0
fi

# Validate selection
if ! [[ "$SELECTION" =~ ^[0-9]+$ ]] || [ "$SELECTION" -ge ${#BACKUP_FILES[@]} ]; then
    echo "Error: Invalid selection" >&2
    exit 1
fi

SELECTED_BACKUP="${BACKUP_FILES[$SELECTION]}"
SELECTED_FILENAME=$(basename "$SELECTED_BACKUP")

echo
echo "You selected: $SELECTED_FILENAME"
echo "WARNING: This will overwrite the current database!"
echo "Are you sure you want to continue? (y/n):"
read -r CONFIRM

if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Restore cancelled."
    exit 0
fi

echo "Restoring database from backup..."
echo "This may take a while..."

# Check if Django might be running and using the database
if pgrep -f "runserver" > /dev/null; then
    echo "Warning: Django runserver appears to be running. This may prevent dropping the database."
    echo "Do you want to continue anyway? (y/n):"
    read -r DJANGO_CONFIRM
    
    if [[ ! "$DJANGO_CONFIRM" =~ ^[Yy]$ ]]; then
        echo "Restore cancelled. Please stop Django server first."
        exit 1
    fi
    
    echo "Attempting to continue despite Django running..."
fi

# Drop existing database with error handling
echo "Dropping existing database..."
if ! sudo -u postgres dropdb heltour_lichess4545; then
    echo "Error: Failed to drop database!" >&2
    echo "This is often because the database is still in use."
    echo "Please ensure all connections to the database are closed:"
    echo "  - Stop any Django development servers"
    echo "  - Close any psql sessions"
    echo "  - Terminate other database connections"
    
    # Offer to terminate connections
    echo "Would you like to force terminate all connections to the database? (y/n):"
    read -r TERM_CONFIRM
    
    if [[ "$TERM_CONFIRM" =~ ^[Yy]$ ]]; then
        echo "Terminating all connections to heltour_lichess4545..."
        sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='heltour_lichess4545' AND pid <> pg_backend_pid();"
        
        echo "Trying to drop database again..."
        if ! sudo -u postgres dropdb heltour_lichess4545; then
            echo "Error: Still unable to drop database. Please check manually." >&2
            exit 1
        fi
    else
        echo "Restore cancelled." >&2
        exit 1
    fi
fi

# Create a new database
echo "Creating new database..."
if ! sudo -u postgres createdb -O heltour_lichess4545 heltour_lichess4545; then
    echo "Error: Failed to create database!" >&2
    exit 1
fi

# Restore from the selected backup
echo "Restoring from backup..."
if ! (bzcat "$SELECTED_BACKUP" | psql -h localhost -U heltour_lichess4545 heltour_lichess4545); then
    echo "Error: Restore operation failed!" >&2
    echo "The database might be in an inconsistent state."
    exit 1
fi

echo "Restore completed successfully!"
