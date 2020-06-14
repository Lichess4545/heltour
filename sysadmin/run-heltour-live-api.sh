#!/bin/bash
cd /home/lichess4545/web/www.lichess4545.com/
export PYTHONPATH=/home/lichess4545/web/www.lichess4545.com/
/home/lichess4545/web/www.lichess4545.com/env/bin/gunicorn --error-logfile /home/lichess4545/log/heltour/gunicorn-error-api.log -t 60 -w 2 -b 127.0.0.1:8880  heltour.live_api_wsgi:application

