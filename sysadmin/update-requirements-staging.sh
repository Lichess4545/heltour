#!/bin/bash
pushd /var/www/staging.lichess4545.com/
source /var/www/staging.lichess4545.com/env/bin/activate
pushd /var/www/staging.lichess4545.com/current/
/var/www/staging.lichess4545.com/env/bin/pip install -r /var/www/staging.lichess4545.com/current/sysadmin/heltour-requirements.txt
popd
popd
