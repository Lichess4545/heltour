import os

from heltour.settings import *  # noqa: F403
from heltour.settings import INSTALLED_APPS, MIDDLEWARE

DEBUG = True
ALLOWED_HOSTS = ["localhost", "apiworker"]

LINK_PROTOCOL = os.getenv("HELTOUR_LINK_PROTOCOL", "http")

INSTALLED_APPS = INSTALLED_APPS + [
    "debug_toolbar",
    "static_precompiler",
]


MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE

DEBUG_TOOLBAR_PATCH_SETTINGS = False

STORAGES = {
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
