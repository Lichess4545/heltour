#!/bin/bash
export HELTOUR_ENV=LIVE
cd /home/lichess4545/web/www.lichess4545.com/
rm -f ./celerybeat-schedule.db
rm -f ./celerybeat-schedule.dat
rm -f ./celerybeat-schedule.dir
/home/lichess4545/web/www.lichess4545.com/env/bin/celery -A heltour worker -B -c 4 --loglevel=INFO -Ofair
