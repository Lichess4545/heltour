#!/bin/bash
export HELTOUR_ENV=STAGING
cd /var/www/staging.lichess4545.com
/var/www/staging.lichess4545.com/env/bin/celery -A heltour worker -B -f /var/log/staging.heltour/celery.log
