#!/bin/bash
export HELTOUR_ENV=STAGING
/var/www/staging.lichess4545.com/env/bin/celery -A heltour worker -B -f /var/log/staging.heltour/celery.log -s /var/www/staging.lichess4545.com/celerybeat-schedule

