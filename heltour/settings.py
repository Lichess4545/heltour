"""
Django settings for heltour project using django-environ.
"""

import os
from datetime import timedelta
from celery.schedules import crontab
import environ

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Initialize environ
env = environ.Env(
    # Set casting, default values
    DEBUG=(bool, False),
    STATIC_ROOT=(str, ""),
    ALLOWED_HOSTS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
    LINK_PROTOCOL=(str, "https"),
    API_WORKER_HOST=(str, "http://localhost:8880"),
    LICHESS_DOMAIN=(str, "https://lichess.org/"),
    LICHESS_NAME=(str, "lichess"),
    LICHESS_TOPLEVEL=(str, "org"),
    LICHESS_OAUTH_REDIRECT_SCHEME=(str, "https"),
    HELTOUR_APP=(str, "tournament"),
    HELTOUR_ENV=(str, "dev"),
    SLACK_ANNOUNCE_CHANNEL=(str, ""),
    SLACK_TEAM_ID=(str, ""),
    CHESSTER_USER_ID=(str, ""),
    JAVAFO_COMMAND=(str, "java -jar ./thirdparty/javafo.jar"),
    EMAIL_USE_TLS=(bool, True),
    EMAIL_PORT=(int, 587),
    CELERY_DEFAULT_QUEUE=(str, "heltour-{}"),
    REDIS_HOST=(str, "localhost"),
    REDIS_PORT=(int, 6379),
    REDIS_DB=(int, 1),
    CACHEOPS_REDIS_DB=(int, 3),
    SLEEP_UNIT=(float, 1.0),
    SECRET_KEY=(str, "this-is-only-for-testing"),
)

# Read .env file if it exists
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")
STAGING = env("HELTOUR_ENV") == "staging"

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")
LINK_PROTOCOL = env("LINK_PROTOCOL")

# Admin configuration
ADMINS = []

# Sites framework
SITE_ID = 1

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",  # Required by django_comments
    "static_precompiler",  # For SCSS compilation
    "bootstrap3",
    "ckeditor",
    "impersonate",
    "reversion",
    "cacheops",
    "django_comments",
    "heltour.tournament",
    "heltour.comments",
    "heltour.api_worker",
    "django_celery_beat",
]

# Middleware configuration
if DEBUG:
    INSTALLED_APPS.append("debug_toolbar")

if DEBUG:
    MIDDLEWARE = [
        "debug_toolbar.middleware.DebugToolbarMiddleware",
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "impersonate.middleware.ImpersonateMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]
else:
    MIDDLEWARE = [
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "impersonate.middleware.ImpersonateMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]

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

# Database
# https://docs.djangoproject.com/en/1.9/ref/settings/#databases
DATABASES = {"default": env.db()}  # Reads DATABASE_URL

# Password validation
# https://docs.djangoproject.com/en/1.9/ref/settings/#auth-password-validators
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

# Internationalization
# https://docs.djangoproject.com/en/1.9/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.9/howto/static-files/
STATIC_URL = "/static/"
STATIC_ROOT = env("STATIC_ROOT", default=os.path.join(BASE_DIR, "static"))

MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=os.path.join(BASE_DIR, "media"))

# Static precompiler settings for SCSS
STATICFILES_FINDERS = (
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "static_precompiler.finders.StaticPrecompilerFinder",
)

# SCSS compiler configuration
STATIC_PRECOMPILER_OUTPUT_DIR = "../heltour/tournament/static/"
STATIC_PRECOMPILER_COMPILERS = (
    (
        "static_precompiler.compilers.SCSS",
        {
            "executable": "sass",
            "sourcemap_enabled": True,
            "output_style": "compact",
        },
    ),
)

# Email configuration
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env("EMAIL_PORT")
EMAIL_USE_TLS = env("EMAIL_USE_TLS")
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
SERVER_EMAIL = env("SERVER_EMAIL", default="webmaster@lots.lichess.ca")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="webmaster@lots.lichess.ca")

# Cache configuration
REDIS_HOST = env("REDIS_HOST")
REDIS_PORT = env("REDIS_PORT")
REDIS_DB = env("REDIS_DB")

# Use Django-Redis for caching
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# Celery configuration
CELERY_BROKER_URL = env(
    "BROKER_URL", default=f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
)
CELERY_DEFAULT_QUEUE = env("CELERY_DEFAULT_QUEUE").format(env("HELTOUR_ENV").lower())
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
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
    "validate_pending_registrations": {
        "task": "heltour.tournament.tasks.validate_pending_registrations",
        "schedule": timedelta(minutes=5),
        "args": (),
    },
    "celery_is_up": {
        "task": "heltour.tournament.tasks.celery_is_up",
        "schedule": timedelta(minutes=5),
        "args": (),
    },
    "start_games": {
        "task": "heltour.tournament.tasks.start_games",
        "schedule": crontab(minute="*/5"),  # run every 5 minutes
        "args": (),
    },
}
CELERY_TIMEZONE = "UTC"

# Cacheops configuration
CACHEOPS_REDIS = {
    "host": REDIS_HOST,
    "port": REDIS_PORT,
    "db": env("CACHEOPS_REDIS_DB"),
    "socket_timeout": 3,
    "socket_connect_timeout": 3,
}

CACHEOPS_DEFAULTS = {"timeout": 60 * 60}

CACHEOPS = {
    "auth.user": {"ops": "get", "timeout": 60 * 15},
    "tournament.*": {"ops": {"fetch", "get"}, "timeout": 60 * 15},
    "*.*": {},
}

# API Keys and External Services
# Lichess OAuth
LICHESS_OAUTH_CLIENTID = env("LICHESS_OAUTH_CLIENTID", default="lots.lichess.ca")
LICHESS_DOMAIN = env("LICHESS_DOMAIN")
LICHESS_NAME = env("LICHESS_NAME")
LICHESS_TOPLEVEL = env("LICHESS_TOPLEVEL")
LICHESS_OAUTH_REDIRECT_SCHEME = env("LICHESS_OAUTH_REDIRECT_SCHEME")
LICHESS_OAUTH_AUTHORIZE_URL = f"{LICHESS_DOMAIN}oauth"
LICHESS_OAUTH_TOKEN_URL = f"{LICHESS_DOMAIN}api/token"
LICHESS_OAUTH_ACCOUNT_URL = f"{LICHESS_DOMAIN}api/account"

# Google Service Account
GOOGLE_SERVICE_ACCOUNT_KEY = env("GOOGLE_SERVICE_ACCOUNT_KEY", default="")

# Slack Configuration
SLACK_API_TOKEN = env("SLACK_API_TOKEN", default="")
SLACK_CHANNEL_BUILDER_TOKEN = env("SLACK_CHANNEL_BUILDER_TOKEN", default="")
SLACK_WEBHOOK_URL = env("SLACK_WEBHOOK_URL", default="")
SLACK_APP_TOKEN = env("SLACK_APP_TOKEN", default="")
SLACK_ANNOUNCE_CHANNEL = env("SLACK_ANNOUNCE_CHANNEL")
SLACK_TEAM_ID = env("SLACK_TEAM_ID")
CHESSTER_USER_ID = env("CHESSTER_USER_ID")

# Lichess API
LICHESS_API_TOKEN = env("LICHESS_API_TOKEN", default="")

# Firebase Cloud Messaging
FCM_API_KEY = env("FCM_API_KEY", default="")

# Application-specific settings
HELTOUR_APP = env("HELTOUR_APP")
API_WORKER_HOST = env("API_WORKER_HOST")
JAVAFO_COMMAND = env("JAVAFO_COMMAND")

# Sleep interval for alternates manager (in seconds)
SLEEP_UNIT = env("SLEEP_UNIT", default=1.0)

# Django Auth
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"

# Session configuration
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_SAVE_EVERY_REQUEST = True

# Other Django settings
APPEND_SLASH = True
FIXTURE_DIRS = (os.path.join(BASE_DIR, "fixtures"),)

# CKEditor
CKEDITOR_UPLOAD_PATH = "uploads/"
CKEDITOR_CONFIGS = {
    "default": {
        "toolbar": "Custom",
        "toolbar_Custom": [
            [
                "Styles",
                "Format",
                "Bold",
                "Italic",
                "Underline",
                "Strike",
                "SpellChecker",
                "Undo",
                "Redo",
            ],
            ["Link", "Unlink", "Anchor"],
            ["Image", "Table", "HorizontalRule"],
            ["TextColor", "BGColor"],
            ["Smiley", "SpecialChar"],
            ["Source"],
        ],
        "height": 300,
        "width": "100%",
    }
}

# Django Reversion
REVERSION_COMPARE_FOREIGN_OBJECTS_AS_ID = False
REVERSION_COMPARE_IGNORE_NOT_REGISTERED = False

# Debug Toolbar (development only)
if DEBUG:
    INTERNAL_IPS = ("127.0.0.1",)
    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda request: True,
    }

# Ensure log directory exists
log_file = env("LOG_FILE", default=os.path.join(BASE_DIR, "logs", "all.log"))

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "default": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": log_file,
            "maxBytes": 1024 * 1024 * 15,  # 15MB
            "backupCount": 10,
            "formatter": "standard",
        },
        "mail_admins": {
            "level": "ERROR",
            "class": "django.utils.log.AdminEmailHandler",
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"] if DEBUG else ["default"],
            "level": "INFO",
            "propagate": True,
        },
        "heltour": {
            "handlers": ["console"] if DEBUG else ["default"],
            "level": "DEBUG",
            "propagate": True,
        },
    },
}
