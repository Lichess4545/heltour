

import os

from celery import Celery
from celery.signals import after_setup_logger

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'heltour.settings')

from django.conf import settings  # noqa

app = Celery('heltour')

app.config_from_object('django.conf:settings')

@after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    """
      Handler names is a list of handlers from your settings.py you want to
      attach to this
    """

    handler_names = ['mail_admins']

    import logging.config
    from django.conf import settings
    logging.config.dictConfig(settings.LOGGING)

    logger = kwargs.get('logger')

    handlers = [x for x in logging.root.handlers if x.name in handler_names]
    for handler in handlers:
        logger.addHandler(handler)
        logger.setLevel(handler.level)
        logger.propagate = False

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
