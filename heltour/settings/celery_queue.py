from datetime import timedelta

from .environment import BROKER_URL, HELTOUR_ENV

CELERY_BROKER_URL = BROKER_URL
CELERY_TASK_DEFAULT_QUEUE = f"heltour-{HELTOUR_ENV.lower()}"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_RESULT_BACKEND = "django-db"
CELERY_RESULT_EXTENDED = True
CELERY_RESULT_EXPIRES = timedelta(days=7)
CELERY_TASK_TRACK_STARTED = True
