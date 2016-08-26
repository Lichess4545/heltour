#!/bin/bash
pushd /var/www/staging.lichess4545.com/
source /var/www/staging.lichess4545.com/env/bin/activate
pushd /var/www/staging.lichess4545.com/current/
/var/www/staging.lichess4545.com/env/bin/python ./manage_staging.py migrate
popd
popd
