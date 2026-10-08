def media_storage(
    *,
    bucket,
    endpoint_url,
    region,
    prefix,
    addressing_style,
    access_key,
    secret_key,
    default_acl,
):
    if not bucket:
        return {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    return {
        "BACKEND": "heltour.storage.MediaS3Storage",
        "OPTIONS": {
            "bucket_name": bucket,
            "endpoint_url": endpoint_url or None,
            "region_name": region or None,
            "location": prefix.strip("/"),
            "addressing_style": addressing_style,
            "access_key": access_key or None,
            "secret_key": secret_key or None,
            "default_acl": default_acl or None,
            "querystring_auth": False,
            "file_overwrite": False,
        },
    }
