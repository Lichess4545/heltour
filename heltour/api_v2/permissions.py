from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from heltour.tournament.models import ApiKey


class ApiKeyPermission(BasePermission):
    permission: str

    def has_permission(self, request: Request, view: APIView) -> bool:
        api_key = request.auth
        return isinstance(api_key, ApiKey) and api_key.has_perm(self.permission)


class CanFindPlayersByEmail(ApiKeyPermission):
    permission = "tournament.find_player_by_email"
