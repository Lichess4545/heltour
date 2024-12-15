#!/home/lichess4545/web/www.lichess4545.com/env/bin/python
"""
WSGI config for heltour project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.9/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "heltour.settings_production")

application = get_wsgi_application()
