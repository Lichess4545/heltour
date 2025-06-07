from subprocess import call
from os import environ
from sys import argv

def runserver():
    call(["python", "manage.py", "runserver", "0.0.0.0:8000"])

def runapiworker():
    call(["python", "manage.py", "runserver", "0.0.0.0:8880"], env=dict(environ, HELTOUR_APP="API_WORKER"))

def test():
    if len(argv) == 1:
        call(["python", "-Wall", "manage.py", "test"])
    else:
        call(["python", "-Wall", "manage.py", "test"] + argv[1:])

def showmigrations():
    if len(argv) == 1:
        call(["python", "manage.py", "showmigrations"])
    else:
        call(["python", "manage.py", "showmigrations"] + argv[1:])

def migrate():
    if len(argv) == 1:
        call(["python", "manage.py", "migrate"])
    else:
        call(["python", "manage.py", "migrate"] + argv[1:])
