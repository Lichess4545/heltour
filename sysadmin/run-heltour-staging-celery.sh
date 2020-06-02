#!/bin/bash
export HELTOUR_ENV=STAGING
cd /home/lichess4545/web/staging.lichess4545.com
/home/lichess4545/web/staging.lichess4545.com/env/bin/celery -A heltour worker -B -c 2 --loglevel=INFO -Ofair
