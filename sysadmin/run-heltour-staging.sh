#!/bin/bash
cd /var/www/staging.lichess4545.com/
export PYTHONPATH=/var/www/staging.lichess4545.com/
/var/www/staging.lichess4545.com/env/bin/gunicorn --capture-output --error-logfile /var/log/staging.heltour/error.log -w 4 -b 127.0.0.1:8680  heltour.staging_wsgi:application

