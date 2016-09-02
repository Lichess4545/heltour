"""
Django settings for heltour project.

Generated by 'django-admin startproject' using Django 1.9.7.

For more information on this file, see
https://docs.djangoproject.com/en/1.9/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.9/ref/settings/
"""

import os
from datetime import timedelta


ADMINS = []

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.9/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'gje)lme+inrew)s%@2mvhj+0$vip^n500i22-o23lm$t1)aq8e'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = [
    'www.lichess4545.tv',
    'lichess4545.tv',
    'www.lichess4545.com',
    'lichess4545.com',
    'heltour.lakin.ca',
    'heltour.lakin.ca',
    'localhost:8880',
]


# Application definition

if 'HELTOUR_APP' in os.environ and os.environ['HELTOUR_APP'] == 'API_WORKER':
    HELTOUR_APP = 'api_worker'
else:
    HELTOUR_APP = 'tournament'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'heltour.%s' % HELTOUR_APP,
    'reversion',
    'bootstrap3',
    'ckeditor',
    'ckeditor_uploader',
    'debug_toolbar',
    'cacheops',
    'django_comments'
]

API_WORKER_HOST = 'http://localhost:8880'

MIDDLEWARE_CLASSES = [
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'heltour.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'heltour.tournament.context_processors.common_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'heltour.wsgi.application'

SITE_ID = 1


# Database
# https://docs.djangoproject.com/en/1.9/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': 'localhost',
        'NAME': 'heltour_lichess4545',
        'USER': 'heltour_lichess4545',
        'PASSWORD': 'sown shuts combiner chattels',
    }
}


# Password validation
# https://docs.djangoproject.com/en/1.9/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/1.9/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Email
# https://docs.djangoproject.com/en/1.10/topics/email/

DEFAULT_FROM_EMAIL = 'noreply@lichess4545.com'


# Celery (tasks)

BROKER_URL = 'redis://localhost:6379/1'

CELERYBEAT_SCHEDULE = {
    'update-ratings': {
        'task': 'heltour.tournament.tasks.update_player_ratings',
        'schedule': timedelta(minutes=30),
        'args': ()
    },
}

CELERY_TIMEZONE = 'UTC'


# Django-Redis

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.9/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = 'static'

BOOTSTRAP3 = {
    'set_placeholder': False
}

CKEDITOR_CONFIGS = {
    'default': {
        'toolbar': 'full',
        'width': 930,
        'height': 300,
    },
}
CKEDITOR_UPLOAD_PATH = "uploads/"
MEDIA_ROOT = 'media'
MEDIA_URL = '/media/'
CKEDITOR_ALLOW_NONIMAGE_FILES = False

LOGIN_URL = '/admin/login/'

DEBUG_TOOLBAR_PATCH_SETTINGS = False
INTERNAL_IPS = ['127.0.0.1', '::1']

CACHEOPS_REDIS = {
    'host': 'localhost',
    'port': 6379,
    'db': 1,
}
CACHEOPS_DEGRADE_ON_FAILURE = True
CACHEOPS = {
    '*.*': {'ops': 'all', 'timeout': 60 * 60},
}

GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH = '/etc/heltour/gspread.conf'
SLACK_API_TOKEN_FILE_PATH = '/etc/heltour/slack-token.conf'
JAVAFO_COMMAND = 'java -jar /etc/heltour/javafo.jar'

# Testing overrides
import sys
TESTING = 'test' in sys.argv
if TESTING:
    CACHEOPS = {}

# Host-based settings overrides.
import platform
import re
try:
    hostname = platform.node().split('.')[0]
    exec 'from .local.%s import *' % re.sub('[^\w]', '_', hostname)
except ImportError:
    pass # ignore missing local settings

# Allow live settings (which aren't in the repository) to override the development settings.
import os
import json
if os.path.exists("/etc/heltour/production.json"):
    overrides = json.loads(open("/etc/heltour/production.json", "r").read())
    DATABASES = overrides.get("DATABASES", DATABASES)
    ADMINS = overrides.get("ADMINS", locals().get('ADMINS'))
    EMAIL_HOST = overrides.get("EMAIL_HOST", locals().get('EMAIL_HOST'))
    EMAIL_PORT = overrides.get("EMAIL_PORT", locals().get('EMAIL_PORT'))
    EMAIL_USE_TLS = overrides.get("EMAIL_USE_TLS", locals().get('EMAIL_USE_TLS'))
    EMAIL_HOST_USER = overrides.get("EMAIL_HOST_USER", locals().get('EMAIL_HOST_USER'))
    EMAIL_HOST_PASSWORD = str(overrides.get("EMAIL_HOST_PASSWORD", locals().get('EMAIL_HOST_PASSWORD')))
    SERVER_EMAIL = overrides.get("SERVER_EMAIL", locals().get('SERVER_EMAIL'))
    DEFAULT_FROM_EMAIL = overrides.get("DEFAULT_FROM_EMAIL", locals().get('DEFAULT_FROM_EMAIL'))
    GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH = overrides.get("GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH", GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH)
    SLACK_API_TOKEN_FILE_PATH = overrides.get("SLACK_API_TOKEN_FILE_PATH", SLACK_API_TOKEN_FILE_PATH)
    MEDIA_ROOT = overrides.get("MEDIA_ROOT", MEDIA_ROOT)
    SECRET_KEY = overrides.get("SECRET_KEY", SECRET_KEY)
