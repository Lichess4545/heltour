#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update
sudo apt-get -y upgrade
sudo apt-get -y install postgresql postgresql-client postgresql-server-dev-9.3 postgresql-contrib
