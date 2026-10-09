import mimetypes
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.staticfiles.storage import StaticFilesStorage
from django.utils.encoding import filepath_to_uri
from storages.backends.s3 import S3Storage


class VersionedStaticFilesStorage(StaticFilesStorage):
    def url(self, name):
        url = super().url(name)
        version = getattr(settings, "HELTOUR_VERSION", "") or ""
        if not version or version == "unknown":
            return url
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}v={version}"


class MediaS3Storage(S3Storage):
    def get_object_parameters(self, name):
        params = super().get_object_parameters(name)
        params.setdefault(
            "ContentType", mimetypes.guess_type(name)[0] or self.default_content_type
        )
        return params

    def url(self, name, parameters=None, expire=None, http_method=None):
        return urljoin(settings.MEDIA_URL, filepath_to_uri(name).lstrip("/"))
