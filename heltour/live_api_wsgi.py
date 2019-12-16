#!/home/lichess4545/web/www.lichess4545.com/env/bin/python
"""
WSGI config for heltour project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.9/howto/deployment/wsgi/
"""
import os

local_dir = os.path.join(os.path.dirname(__file__))
activate_this = '/home/lichess4545/web/www.lichess4545.com/env/bin/activate_this.py'
if os.path.exists(activate_this):
    exec (compile(open(activate_this).read(), activate_this, 'exec'), dict(__file__=activate_this))

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("HELTOUR_APP", "API_WORKER")
os.environ.setdefault("HELTOUR_ENV", "LIVE")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "heltour.settings")

application = get_wsgi_application()
