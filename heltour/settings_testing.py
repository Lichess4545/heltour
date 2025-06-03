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
