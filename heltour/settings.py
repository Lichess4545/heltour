# This file pulls in settings from different sources depending on the environment.
#
# All environments -> settings_default.py.
# Local development -> add a file to the 'local' folder named after your machine name
# Testing (python manage.py test) -> settings_testing.py
# Staging -> settings_staging.py
# Travis CI -> settings_travis.py
#
# If you're running in production, you can also customize settings with a JSON file (see below).

import json
import os
import platform
import re
import sys
import django_stubs_ext

django_stubs_ext.monkeypatch()

TESTING = 'test' in sys.argv
STAGING = os.environ.get('HELTOUR_ENV', '').upper() == 'STAGING'
TRAVIS = 'TRAVIS' in os.environ

if TRAVIS:
    from .settings_travis import *
elif TESTING:
    from .settings_testing import *
elif STAGING:
    from .settings_staging import *
else:
    from .settings_default import *

# Host-based settings overrides.
try:
    hostname = platform.node().split('.')[0]
    exec('from .local.%s import *' % re.sub('[^\\w]', '_', hostname))
except ImportError:
    pass  # ignore missing local settings

# Allow live settings (which aren't in the repository) to override the development settings.
config_path = '/home/lichess4545/etc/heltour/%s.json' % ('staging' if STAGING else 'production')
if os.path.exists(config_path):
    overrides = json.loads(open(config_path, 'r').read())
    DATABASES = overrides.get('DATABASES', DATABASES)
    ADMINS = overrides.get('ADMINS', locals().get('ADMINS'))
    EMAIL_HOST = overrides.get('EMAIL_HOST', locals().get('EMAIL_HOST'))
    EMAIL_PORT = overrides.get('EMAIL_PORT', locals().get('EMAIL_PORT'))
    EMAIL_USE_TLS = overrides.get('EMAIL_USE_TLS', locals().get('EMAIL_USE_TLS'))
    EMAIL_HOST_USER = overrides.get('EMAIL_HOST_USER', locals().get('EMAIL_HOST_USER'))
    EMAIL_HOST_PASSWORD = str(
        overrides.get('EMAIL_HOST_PASSWORD', locals().get('EMAIL_HOST_PASSWORD')))
    SERVER_EMAIL = overrides.get('SERVER_EMAIL', locals().get('SERVER_EMAIL'))
    DEFAULT_FROM_EMAIL = overrides.get('DEFAULT_FROM_EMAIL', locals().get('DEFAULT_FROM_EMAIL'))
    GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH = overrides.get('GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH',
                                                        GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH)
    SLACK_API_TOKEN_FILE_PATH = overrides.get('SLACK_API_TOKEN_FILE_PATH',
                                              SLACK_API_TOKEN_FILE_PATH)
    SLACK_WEBHOOK_FILE_PATH = overrides.get('SLACK_WEBHOOK_FILE_PATH', SLACK_WEBHOOK_FILE_PATH)
    LICHESS_API_TOKEN_FILE_PATH = overrides.get('LICHESS_API_TOKEN_FILE_PATH', LICHESS_API_TOKEN_FILE_PATH)
    FCM_API_KEY_FILE_PATH = overrides.get('FCM_API_KEY_FILE_PATH', FCM_API_KEY_FILE_PATH)
    SLACK_APP_TOKEN = overrides.get('SLACK_APP_TOKEN', SLACK_APP_TOKEN)
    MEDIA_ROOT = overrides.get('MEDIA_ROOT', MEDIA_ROOT)
    SECRET_KEY = overrides.get('SECRET_KEY', SECRET_KEY)
    RECAPTCHA_PUBLIC_KEY = overrides.get('RECAPTCHA_PUBLIC_KEY', RECAPTCHA_PUBLIC_KEY)
    RECAPTCHA_PRIVATE_KEY = overrides.get('RECAPTCHA_PRIVATE_KEY', RECAPTCHA_PRIVATE_KEY)
    LICHESS_OAUTH_CLIENTID = overrides.get('LICHESS_OAUTH_CLIENTID', LICHESS_OAUTH_CLIENTID)
