#!/bin/bash
pushd /home/lichess4545/web/www.lichess4545.com/
source /home/lichess4545/web/www.lichess4545.com/env/bin/activate
pushd /home/lichess4545/web/www.lichess4545.com/current/
/home/lichess4545/web/www.lichess4545.com/env/bin/poetry install
popd
popd
