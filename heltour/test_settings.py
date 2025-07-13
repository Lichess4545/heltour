"""
Test settings - disables debug toolbar and sets DEBUG=False for tests
"""

from .settings import *

# Remove debug_toolbar from INSTALLED_APPS if present
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "debug_toolbar"]

# Remove debug toolbar middleware
MIDDLEWARE = [m for m in MIDDLEWARE if "debug_toolbar" not in m]

SECRET_KEY = "test-secret-key-only-for-testing"
