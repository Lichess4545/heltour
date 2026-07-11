import os
from datetime import timedelta

import django_stubs_ext
import environ
from celery.schedules import crontab

django_stubs_ext.monkeypatch()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# FileAwareEnv gives every env() call below an implicit <VAR>_FILE override
# (e.g. SECRET_KEY_FILE) for Docker/Compose secrets, read before the plain
# <VAR>. This is separate from the *_FILE_PATH settings further down, which
# are heltour's own convention: app code opens those paths itself.
env = environ.FileAwareEnv(
    DEBUG=(bool, False),
    STATIC_ROOT=(str, ""),
    MEDIA_ROOT=(str, ""),
    ALLOWED_HOSTS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
    LINK_PROTOCOL=(str, "https"),
    API_WORKER_HOST=(str, "http://localhost:8880"),
    LICHESS_DOMAIN=(str, "https://lichess.org/"),
    LICHESS_NAME=(str, "lichess"),
    LICHESS_TOPLEVEL=(str, "org"),
    LICHESS_OAUTH_CLIENTID=(str, "heltour"),
    # Must include "://": oauth.py does a literal http_url.replace("http://", ...).
    LICHESS_OAUTH_REDIRECT_SCHEME=(str, "https://"),
    HELTOUR_APP=(str, "tournament"),
    HELTOUR_ENV=(str, "dev"),
    HELTOUR_VERSION=(str, "unknown"),
    SLACK_ANNOUNCE_CHANNEL=(str, "C2UP34BCZ"),
    SLACK_TEAM_ID=(str, "T0CSGMP0R"),
    CHESSTER_USER_ID=(str, "U020MSB1FV0"),
    JAVAFO_COMMAND=(str, "java -jar ./thirdparty/javafo.jar"),
    EMAIL_USE_TLS=(bool, True),
    EMAIL_PORT=(int, 587),
    EMAIL_HOST=(str, "localhost"),
    EMAIL_HOST_USER=(str, ""),
    EMAIL_HOST_PASSWORD=(str, ""),
    CELERY_DEFAULT_QUEUE=(str, "heltour-{}"),
    REDIS_URL=(str, "redis://localhost:6379/1"),
    SLEEP_UNIT=(float, 1.0),
    SECRET_KEY=(str, "this-is-only-for-testing"),
    TEAMGEN_PROCESSES_NUMBER=(int, 8),
)

environ.FileAwareEnv.read_env(os.path.join(BASE_DIR, ".env"))

SECRET_KEY = env("SECRET_KEY")

DEBUG = env("DEBUG")
STAGING = env("HELTOUR_ENV") == "stage"

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")
LINK_PROTOCOL = env("LINK_PROTOCOL")

ADMINS = []

SITE_ID = 1

HELTOUR_APP = env("HELTOUR_APP")
HELTOUR_VERSION = env("HELTOUR_VERSION")

INSTALLED_APPS = [
    "cacheops",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "heltour.%s" % HELTOUR_APP,  # "tournament" or "api_worker"; urls.py switches the same way
    "reversion",
    "bootstrap3",
    "ckeditor",
    "ckeditor_uploader",
    "django_comments",
    "heltour.comments",
    "impersonate",
    "sass_processor",
    "django_celery_beat",
    "django_celery_results",
]

if DEBUG:
    INSTALLED_APPS.append("debug_toolbar")

COMMENTS_APP = "heltour.comments"

API_WORKER_HOST = env("API_WORKER_HOST")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "impersonate.middleware.ImpersonateMiddleware",
    "heltour.tournament.middlewares.RejectNullMiddleware",
]

if DEBUG:
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")

ROOT_URLCONF = "heltour.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "heltour.tournament.context_processors.common_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "heltour.wsgi.application"

DATABASES = {"default": env.db()}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "heltour.tournament.auth.LeagueAuthBackend",
]

IMPERSONATE_REDIRECT_URL = "/"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = env("STATIC_ROOT", default=os.path.join(BASE_DIR, "static"))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "heltour.storage.VersionedStaticFilesStorage"},
}

MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=os.path.join(BASE_DIR, "media"))

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "sass_processor.finders.CssFinder",
]

SASS_PROCESSOR_ROOT = STATIC_ROOT
SASS_PROCESSOR_INCLUDE_DIRS = [
    os.path.join(BASE_DIR, "heltour/tournament/static/tournament/css"),
]
SASS_PROCESSOR_ENABLE_SOURCEMAPS = DEBUG
SASS_PROCESSOR_AUTO_INCLUDE = False
SASS_PROCESSOR_PRECISION = 8
SASS_OUTPUT_STYLE = "nested" if DEBUG else "compressed"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env("EMAIL_PORT")
EMAIL_USE_TLS = env("EMAIL_USE_TLS")
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")

SERVER_EMAIL = env("SERVER_EMAIL", default="noreply@lichess.org")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@lichess.org")

REDIS_URL = env("REDIS_URL")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

CELERY_BROKER_URL = env("BROKER_URL", default=REDIS_URL)
# celery.py loads config with namespace="CELERY", so the setting name must be
# CELERY_TASK_DEFAULT_QUEUE, not CELERY_DEFAULT_QUEUE (the latter is silently
# ignored and the queue falls back to celery's hardcoded "celery"). The env
# var name stays CELERY_DEFAULT_QUEUE.
CELERY_TASK_DEFAULT_QUEUE = env("CELERY_DEFAULT_QUEUE").format(env("HELTOUR_ENV").lower())
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_RESULT_BACKEND = "django-db"
CELERY_RESULT_EXTENDED = True
CELERY_TASK_TRACK_STARTED = True
CELERY_RESULT_EXPIRES = timedelta(days=7)
CELERY_TIMEZONE = "UTC"

CELERY_BEAT_SCHEDULE = {
    "update-ratings": {
        "task": "heltour.tournament.tasks.update_player_ratings",
        "schedule": timedelta(minutes=60),
        "args": (),
    },
    "update-tv-state": {
        "task": "heltour.tournament.tasks.update_tv_state",
        "schedule": timedelta(minutes=5),
        "args": (),
    },
    "update-slack-users": {
        "task": "heltour.tournament.tasks.update_slack_users",
        "schedule": timedelta(minutes=30),
        "args": (),
    },
    "populate-historical-ratings": {
        "task": "heltour.tournament.tasks.populate_historical_ratings",
        "schedule": timedelta(minutes=60),
        "args": (),
    },
    "run_scheduled_events": {
        "task": "heltour.tournament.tasks.run_scheduled_events",
        "schedule": timedelta(minutes=10),
        "args": (),
    },
    "alternates_manager_tick": {
        "task": "heltour.tournament.tasks.alternates_manager_tick",
        "schedule": timedelta(minutes=2),
        "args": (),
    },
    "update_lichess_presence": {
        "task": "heltour.tournament.tasks.update_lichess_presence",
        "schedule": timedelta(minutes=1),
        "args": (),
    },
    "celery_is_up": {
        "task": "heltour.tournament.tasks.celery_is_up",
        "schedule": timedelta(minutes=5),
        "args": (),
    },
    "start_games": {
        "task": "heltour.tournament.tasks.start_games",
        "schedule": crontab(minute="*/5"),
        "args": (),
    },
    "celery-backend-cleanup": {
        "task": "celery.backend_cleanup",
        "schedule": crontab(hour=4, minute=0),
        "args": (),
    },
}

# tasks.py reads this pre-namespace Celery 3 name directly (settings.CELERYBEAT_SCHEDULE[...]).
CELERYBEAT_SCHEDULE = CELERY_BEAT_SCHEDULE

BOOTSTRAP3 = {
    "set_placeholder": False,
}

CKEDITOR_CONFIGS = {
    "default": {
        "toolbar": "full",
        "width": 930,
        "height": 300,
    },
}
CKEDITOR_UPLOAD_PATH = "uploads/"
CKEDITOR_ALLOW_NONIMAGE_FILES = True

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
SESSION_COOKIE_AGE = 4838400

DEBUG_TOOLBAR_PATCH_SETTINGS = False
INTERNAL_IPS = ["127.0.0.1", "::1"]
if DEBUG:
    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda request: True,
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

SLEEP_UNIT = env("SLEEP_UNIT")

TEAMGEN_PROCESSES_NUMBER = env("TEAMGEN_PROCESSES_NUMBER")

GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH = env("GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH", default="")
SLACK_API_TOKEN_FILE_PATH = env("SLACK_API_TOKEN_FILE_PATH", default="")
SLACK_CHANNEL_BUILDER_TOKEN_FILE_PATH = env("SLACK_CHANNEL_BUILDER_TOKEN_FILE_PATH", default="")
SLACK_WEBHOOK_FILE_PATH = env("SLACK_WEBHOOK_FILE_PATH", default="")
LICHESS_API_TOKEN_FILE_PATH = env("LICHESS_API_TOKEN_FILE_PATH", default="")
FCM_API_KEY_FILE_PATH = env("FCM_API_KEY_FILE_PATH", default="")
JAVAFO_COMMAND = env("JAVAFO_COMMAND")

SLACK_APP_TOKEN = env("SLACK_APP_TOKEN", default="")
SLACK_ANNOUNCE_CHANNEL = env("SLACK_ANNOUNCE_CHANNEL")
SLACK_TEAM_ID = env("SLACK_TEAM_ID")
CHESSTER_USER_ID = env("CHESSTER_USER_ID")

LICHESS_NAME = env("LICHESS_NAME")
LICHESS_TOPLEVEL = env("LICHESS_TOPLEVEL")
LICHESS_DOMAIN = env("LICHESS_DOMAIN")
LICHESS_OAUTH_ACCOUNT_URL = f"{LICHESS_DOMAIN}api/account"
LICHESS_OAUTH_EMAIL_URL = f"{LICHESS_DOMAIN}api/email"
LICHESS_OAUTH_AUTHORIZE_URL = f"{LICHESS_DOMAIN}oauth"
LICHESS_OAUTH_TOKEN_URL = f"{LICHESS_DOMAIN}api/token"
LICHESS_OAUTH_REDIRECT_SCHEME = env("LICHESS_OAUTH_REDIRECT_SCHEME")
LICHESS_OAUTH_CLIENTID = env("LICHESS_OAUTH_CLIENTID")

DATA_UPLOAD_MAX_MEMORY_SIZE = 26214400

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "mail_admins": {
            "level": "ERROR",
            "class": "django.utils.log.AdminEmailHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "DEBUG",
    },
}
