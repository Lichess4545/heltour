#!/bin/bash
cd /home/lichess4545/web/staging.lichess4545.com/
export PYTHONPATH=/home/lichess4545/web/staging.lichess4545.com/
/home/lichess4545/web/staging.lichess4545.com/env/bin/gunicorn --capture-output --error-logfile /home/lichess4545/log/staging.heltour/error-api.log -t 60 -w 2 -b 127.0.0.1:8780  heltour.staging_api_wsgi:application

