from .settings import *

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "debug_toolbar"]

MIDDLEWARE = [m for m in MIDDLEWARE if "debug_toolbar" not in m]

SECRET_KEY = "test-secret-key-only-for-testing"

# MD5 instead of PBKDF2: fast test runs, not for anything but tests.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
