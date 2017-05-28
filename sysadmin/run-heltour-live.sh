#!/bin/bash
cd /home/lichess4545/web/www.lichess4545.com/
export PYTHONPATH=/home/lichess4545/web/www.lichess4545.com/
/home/lichess4545/web/www.lichess4545.com/env/bin/gunicorn --capture-output --error-logfile /home/lichess4545/web/heltour/error.log -t 300 -w 4 -b 127.0.0.1:8580  heltour.wsgi:application

