import re

import environ
from django.core.exceptions import ImproperlyConfigured
from environ.fileaware_mapping import FileAwareMapping


class SecretFileMapping(FileAwareMapping):
    def __getitem__(self, key):
        if not self.env.get(key + "_FILE"):
            return self.env[key]
        if key in self.env:
            raise ImproperlyConfigured(f"{key} and {key}_FILE cannot both be set")
        return re.sub(r"\r?\n\Z", "", super().__getitem__(key))


class SecretFileEnv(environ.Env):
    ENVIRON = SecretFileMapping()
