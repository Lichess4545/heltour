#!/bin/bash
virtualenv env --no-site-packages --prompt="(heltour):" --python=/usr/bin/python2
source env/bin/activate
pip install -r requirements.txt
fab update
