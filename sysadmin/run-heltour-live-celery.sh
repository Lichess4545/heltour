#!/bin/bash
export HELTOUR_ENV=LIVE
cd /var/www/www.lichess4545.com/
/var/www/www.lichess4545.com/env/bin/celery -A heltour worker -B -f /var/log/heltour/celery.log -c 4

