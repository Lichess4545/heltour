from django.conf import settings


def common_settings(request):
    return {
        'STAGING': settings.STAGING,
        'DEBUG': settings.DEBUG
    }
