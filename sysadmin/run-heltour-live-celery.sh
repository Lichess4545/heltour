#!/bin/bash
export HELTOUR_ENV=LIVE
cd /home/lichess4545/web/www.lichess4545.com/
/home/lichess4545/web/www.lichess4545.com/env/bin/celery -A heltour worker -B -f /home/lichess4545/log/heltour/celery.log -c 4 --loglevel=DEBUG -Ofair
