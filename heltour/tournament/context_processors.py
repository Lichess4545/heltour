from django.conf import settings


def common_settings(request):
    return {
        'DEBUG': settings.DEBUG
    }
