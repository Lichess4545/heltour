#!/bin/bash
pushd /var/www/www.lichess4545.com/
source /var/www/www.lichess4545.com/env/bin/activate
pushd /var/www/www.lichess4545.com/current/
/var/www/www.lichess4545.com/env/bin/python ./manage.py invalidate all
popd
popd
