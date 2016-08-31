#!/bin/bash

# crontab entry:
# * * * * * command-to-be-executed
# 15 * * * * /var/www/www.lichess4545.com/current/sysadmin/backup.sh
OF=/var/backups/heltour-sql/hourly/heltour-`date +%Y-%m-%d-%H%M`.sql
BZOF=/var/backups/heltour-sql/hourly/heltour-`date +%Y-%m-%d-%H%M`.sql.bz2
pg_dump --clean --no-owner --no-privileges --format=plain --host localhost heltour_lichess4545 --username heltour_lichess4545 >& $OF
bzip2 $OF
ln -sf $BZOF /var/backups/heltour-sql/hourly/latest.sql.bz2
/var/www/www.lichess4545.com/env/bin/python /var/www/www.lichess4545.com/current/sysadmin/backup.py
