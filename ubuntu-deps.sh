#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update
sudo apt-get -y upgrade
sudo apt-get -y install python3.6 postgresql postgresql-client postgresql-server-dev-all mercurial libffi-dev libjpeg-dev
