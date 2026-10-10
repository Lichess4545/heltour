from django.conf import settings
from django.contrib.staticfiles.storage import StaticFilesStorage


class VersionedStaticFilesStorage(StaticFilesStorage):
    def url(self, name):
        url = super().url(name)
        version = getattr(settings, "HELTOUR_VERSION", "") or ""
        # directory urls are used as base paths (e.g. ckeditor's), so a query string would break them
        if not version or version == "unknown" or name.endswith("/"):
            return url
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}v={version}"
