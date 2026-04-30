from django.conf import settings
from django.contrib.staticfiles.storage import StaticFilesStorage


class VersionedStaticFilesStorage(StaticFilesStorage):
    def url(self, name):
        url = super().url(name)
        version = getattr(settings, "HELTOUR_VERSION", "") or ""
        if not version or version == "unknown":
            return url
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}v={version}"
