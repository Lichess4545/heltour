from django.core.exceptions import ImproperlyConfigured
from environ import Env

from .environment import DATABASE_URL, REDIS_URL

DATABASES = {"default": Env.db_url_config(DATABASE_URL)}
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("DATABASE_URL must be a postgres URL")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

CACHEOPS_REDIS = REDIS_URL
CACHEOPS_DEGRADE_ON_FAILURE = True
CACHEOPS_DEFAULTS = {
    "timeout": 60 * 60,
}
CACHEOPS = {
    "admin.*": {"ops": "all"},
    "auth.*": {"ops": "all"},
    "heltour.*": {"ops": "all"},
    "tournament.*": {"ops": "all"},
    "*.*": {},
}
CACHEOPS_ENABLED = True
