import re

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from heltour.tournament.models import ApiKey

TOKEN = re.compile(r"\s*Token\s*(\w+)\s*")


class ApiKeyHolder:
    is_authenticated = True


class ApiKeyAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[ApiKeyHolder, ApiKey] | None:
        header: str | None = request.META.get("HTTP_AUTHORIZATION")
        if header is None:
            return None
        api_key = api_key_from(header)
        if api_key is None:
            raise AuthenticationFailed
        return ApiKeyHolder(), api_key

    def authenticate_header(self, request: Request) -> str:
        return "Token"


def api_key_from(header: str) -> ApiKey | None:
    match = TOKEN.match(header)
    if match is None:
        return None
    return ApiKey.objects.filter(secret_token=match.group(1)).first()
