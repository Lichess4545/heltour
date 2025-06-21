from .settings_default import *

CACHEOPS = {
    '*.*': {'ops': ()},
}
CACHEOPS_ENABLED = False
STORAGES = {
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
        },
}

# use a faster hasher for tests
PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher"
]

# using sqlite3 in memory speeds up tests
#DATABASES = {
#    'default': {
#        'ENGINE': 'django.db.backends.sqlite3',
#        'NAME': ':memory:',
#    }
#}

# we do not need debug toolbar for testing
INSTALLED_APPS = [
    'cacheops',
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
    'django_comments',
    'heltour.comments',
    'static_precompiler',
    'impersonate',
]

# remove some middleware for tests
MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ALLOWED_HOSTS = [
    'testserver',
]

SLEEP_UNIT = 0
