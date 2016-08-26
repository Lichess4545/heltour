#!/bin/bash

# crontab entry:
# * * * * * command-to-be-executed
# 15 * * * * /var/www/www.lichess4545.com/current/sysadmin/backup.sh
OF=/var/backups/heltour-sql/heltour-`date +%Y-%m-%d-%H%M`.sql
BZOF=/var/backups/heltour-sql/heltour-`date +%Y-%m-%d-%H%M`.sql.bz2
pg_dump --clean --no-owner --no-privileges --format=plain --host localhost heltour_lichess4545 --username heltour_lichess4545 >& $OF
bzip2 $OF
ln -sf $BZOF /var/backups/heltour-sql/latest.sql.bz2
find /var/backups/heltour-sql/ -mtime +7 -name heltour-* -delete

