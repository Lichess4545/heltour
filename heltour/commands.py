from subprocess import call
from os import environ

def runserver():
    call(["python", "manage.py", "runserver", "0.0.0.0:8000"])

def runapiworker():
    call(["python", "manage.py", "runserver", "0.0.0.0:8880"], env=dict(environ, HELTOUR_APP="API_WORKER"))

def test():
    call(["python", "-Wall", "manage.py", "test"])

def coverage():
    call(["coverage", "run", "--branch", "manage.py", "test"])
