import os

import django_stubs_ext

from .environment import BASE_DIR, DEBUG, HELTOUR_APP, STATIC_ROOT

django_stubs_ext.monkeypatch()

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

ADMINS = []

SITE_ID = 1

INSTALLED_APPS = [
    "cacheops",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "heltour.%s" % HELTOUR_APP,
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

LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/"
SESSION_COOKIE_AGE = 4838400

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
MEDIA_URL = "/media/"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "heltour.storage.VersionedStaticFilesStorage"},
}

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "sass_processor.finders.CssFinder",
]

SASS_PROCESSOR_ROOT = STATIC_ROOT
SASS_PROCESSOR_INCLUDE_DIRS = [
    os.path.join(BASE_DIR, "heltour/tournament/static/tournament/css"),
]
SASS_PROCESSOR_AUTO_INCLUDE = False
SASS_PRECISION = 8
SASS_OUTPUT_STYLE = "nested" if DEBUG else "compressed"

DATA_UPLOAD_MAX_MEMORY_SIZE = 26214400

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

DEBUG_TOOLBAR_PATCH_SETTINGS = False
INTERNAL_IPS = ["127.0.0.1", "::1"]
if DEBUG:
    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda request: True,
    }
