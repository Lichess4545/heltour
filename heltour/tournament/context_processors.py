from django.conf import settings
from .models import Announcement


def common_settings(request):
    return {
        'STAGING': settings.STAGING,
        'DEBUG': settings.DEBUG,
        'CUSTOM_THEME_PRIMARY_COLOR': settings.CUSTOM_THEME_PRIMARY_COLOR,
        'CUSTOM_THEME_DARK_PRIMARY_COLOR': settings.CUSTOM_THEME_DARK_PRIMARY_COLOR,
        'CUSTOM_THEME_SECONDARY_COLOR': settings.CUSTOM_THEME_SECONDARY_COLOR,
        'CUSTOM_THEME_NAV_FOCUS_COLOR': settings.CUSTOM_THEME_NAV_FOCUS_COLOR,
        'CUSTOM_THEME_LOGO_URL': settings.CUSTOM_THEME_LOGO_URL,
        'LITOUR_API_BASE_URL': getattr(settings, 'LITOUR_API_BASE_URL', ''),
    }


def announcements(request):
    """Add active announcements for the current path to the context"""
    current_announcements = []
    if hasattr(request, 'path'):
        current_announcements = Announcement.get_active_for_path(request.path)

    return {
        'announcements': current_announcements
    }
