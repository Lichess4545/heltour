#!/bin/bash
export HELTOUR_ENV=LIVE
/var/www/www.lichess4545.com/env/bin/celery -A heltour worker -B -f /var/log/heltour/celery.log -s /var/www/www.lichess4545.com/celerybeat-schedule

