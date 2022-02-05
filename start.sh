#!/bin/bash
virtualenv env --prompt="(heltour):" --python=/usr/bin/python3
source env/bin/activate
pip install poetry
poetry install
fab update
