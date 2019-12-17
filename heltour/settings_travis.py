from .settings_default import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': 'localhost',
        'NAME': 'heltour_lichess4545',
        'USER': 'postgres',
    }
}
CACHEOPS = {}
