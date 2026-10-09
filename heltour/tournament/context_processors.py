import re

from django.conf import settings

RELEASES_URL = "https://github.com/Lichess4545/heltour/releases/tag/"
RELEASE_VERSION = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")


def release_url(version):
    if version and RELEASE_VERSION.match(version):
        return f"{RELEASES_URL}v{version}"
    return None


def common_settings(request):
    return {
        'DEBUG': settings.DEBUG,
        'heltour_version': settings.HELTOUR_VERSION,
        'release_url': release_url(settings.HELTOUR_VERSION),
    }
