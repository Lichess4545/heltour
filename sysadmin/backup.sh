#!/bin/bash

# crontab entry:
# * * * * * command-to-be-executed
# 15 * * * * /home/lichess4545/web/www.lichess4545.com/current/sysadmin/backup.sh
OF=/home/lichess4545/backups/heltour-sql/hourly/heltour-`date +%Y-%m-%d-%H%M`.sql
BZOF=/home/lichess4545/backups/heltour-sql/hourly/heltour-`date +%Y-%m-%d-%H%M`.sql.bz2
pg_dump --clean --no-owner --no-privileges --format=plain --host localhost heltour_lichess4545 --username heltour_lichess4545 >& $OF
bzip2 $OF
ln -sf $BZOF /home/lichess4545/backups/heltour-sql/hourly/latest.sql.bz2
/home/lichess4545/web/www.lichess4545.com/env/bin/python /home/lichess4545/web/www.lichess4545.com/current/sysadmin/backup.py
