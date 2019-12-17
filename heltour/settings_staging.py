from .settings_default import *

ALLOWED_HOSTS = [
    'staging.lichess4545.tv',
    'staging.lichess4545.com',
    'localhost',
]

API_WORKER_HOST = 'http://localhost:8780'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': 'localhost',
        'NAME': 'heltour_lichess4545_staging',
        'USER': 'heltour_lichess4545_staging',
        'PASSWORD': 'sown shuts combiner chattels',
    }
}

# Celery
BROKER_URL = 'redis://localhost:6379/2'
CELERY_DEFAULT_QUEUE = 'heltour.staging'
# We don't update ratings in staging because it hits the lichess api too much
del CELERYBEAT_SCHEDULE['update-ratings']

# Django-Redis
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/2",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}
CACHEOPS_REDIS = {
    'host': 'localhost',
    'port': 6379,
    'db': 2,
}
CACHEOPS_DEGRADE_ON_FAILURE = True
CACHEOPS = {
    '*.*': {'ops': 'all', 'timeout': 60 * 60},
}

# Lichess
LICHESS_DOMAIN = 'https://lichess.dev/'
