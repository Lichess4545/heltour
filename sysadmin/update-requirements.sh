#!/bin/bash
pushd /var/www/heltour.lakin.ca/
source /var/www/heltour.lakin.ca/env/bin/activate
pushd /var/www/heltour.lakin.ca/current/
/var/www/heltour.lakin.ca/env/bin/pip install -r /var/www/heltour.lakin.ca/current/sysadmin/heltour-requirements.txt
popd
popd
