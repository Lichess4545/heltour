import shlex
import subprocess

from django.core.management.base import BaseCommand
from django.utils import autoreload

start_celery_command = ' '.join((
        'celery',
        'worker',
        '-A heltour', # Tells it what app to run
        '-B', # Run the 'celery beat'
        '-f .ignore/celery.log', # log file
        '--loglevel=DEBUG',
        '-Ofair', # optimization flag
        # Needed for running celery in vagrant
        '--scheduler django_celery_beat.schedulers:DatabaseScheduler'))

kill_celery_command = 'pkill -9 celery'

def restart_celery():
    subprocess.call(shlex.split(kill_celery_command))
    subprocess.call(shlex.split(start_celery_command))


class Command(BaseCommand):

    def handle(self, *args, **options):
        print('Starting celery worker with autoreload...')
        autoreload.main(restart_celery)
