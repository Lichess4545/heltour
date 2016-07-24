#!/var/www/heltour.lakin.ca/env/bin/python
"""
WSGI config for heltour project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.9/howto/deployment/wsgi/
"""
import os

local_dir = os.path.join(os.path.dirname(__file__))
activate_this = '/var/www/heltour.lakin.ca/env/bin/activate_this.py'
if os.path.exists(activate_this):
    execfile(activate_this, dict(__file__=activate_this))


from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "heltour.settings")

application = get_wsgi_application()


