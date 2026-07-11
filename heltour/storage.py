from django.conf import settings
from django.contrib.staticfiles.storage import StaticFilesStorage


class VersionedStaticFilesStorage(StaticFilesStorage):
    """Appends ?v=<HELTOUR_VERSION> to static URLs so a deploy busts browser caches."""

    def url(self, name):
        url = super().url(name)
        version = getattr(settings, "HELTOUR_VERSION", "") or ""
        if not version or version == "unknown":
            # "unknown" is FileAwareEnv's default when HELTOUR_VERSION isn't set.
            return url
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}v={version}"
