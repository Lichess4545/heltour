#!/bin/bash
cd /var/www/heltour.lakin.ca/
export PYTHONPATH=/var/www/heltour.lakin.ca/
/var/www/heltour.lakin.ca/env/bin/gunicorn -w 4 -b 127.0.0.1:8580  heltour.wsgi:application

