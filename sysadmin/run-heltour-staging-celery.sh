#!/bin/bash
export HELTOUR_ENV=STAGING
cd /home/lichess4545/web/staging.lichess4545.com
/home/lichess4545/web/staging.lichess4545.com/env/bin/celery -A heltour worker -B -f /home/lichess4545/log/staging.heltour/celery.log -c 2 -Ofair
