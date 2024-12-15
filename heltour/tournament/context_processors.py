from django.conf import settings


def common_settings(request):
    return {"STAGING": settings.HELTOUR_STAGING, "DEBUG": settings.DEBUG}
