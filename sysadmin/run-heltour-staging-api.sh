#!/bin/bash
cd /var/www/staging.lichess4545.com/
export PYTHONPATH=/var/www/staging.lichess4545.com/
/var/www/staging.lichess4545.com/env/bin/gunicorn --capture-output --error-logfile /var/log/staging.heltour/error-api.log -t 60 -w 2 -b 127.0.0.1:8780  heltour.staging_api_wsgi:application

