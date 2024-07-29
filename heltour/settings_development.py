from heltour.settings import *

ALLOWED_HOSTS = ['localhost']

LINK_PROTOCOL = os.getenv('HELTOUR_LINK_PROTOCOL', 'http')

INSTALLED_APPS =  INSTALLED_APPS + [
    'debug_toolbar',
    'static_precompiler',
]

    
MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE

DEBUG_TOOLBAR_PATCH_SETTINGS = False
