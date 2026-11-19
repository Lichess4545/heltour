from typing import Any

from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from heltour.tournament.models import ApiKey
from heltour.tournament.tests.testutils import Shush


def grant(api_key: ApiKey, codename: str) -> None:
    group, _ = Group.objects.get_or_create(name=codename)
    group.permissions.add(Permission.objects.get(codename=codename))
    api_key.groups.add(group)


class ApiV2TestCase(TestCase):
    api_key: ApiKey
    permission: str | None = None

    @classmethod
    def setUpTestData(cls) -> None:
        cls.api_key = ApiKey.objects.create(name="test_key")
        if cls.permission is not None:
            grant(cls.api_key, cls.permission)

    def authorization(self, api_key: ApiKey | None = None) -> dict[str, str]:
        token = (api_key or self.api_key).secret_token
        return {"authorization": f"Token {token}"}

    def status_of(self, path: str, **query: str) -> int:
        return self.client.get(path, query, headers=self.authorization()).status_code

    def get_json(self, path: str, **query: str) -> Any:
        response = self.client.get(path, query, headers=self.authorization())
        self.assertEqual(response.status_code, 200)
        return response.json()

    def status_of_post(
        self, path: str, body: dict[str, str], api_key: ApiKey | None = None
    ) -> int:
        response = self.client.post(
            path,
            body,
            content_type="application/json",
            headers=self.authorization(api_key),
        )
        return response.status_code

    def post_json(self, path: str, body: dict[str, str]) -> Any:
        response = self.client.post(
            path, body, content_type="application/json", headers=self.authorization()
        )
        self.assertEqual(response.status_code, 200)
        return response.json()


class ShushedApiV2TestCase(ApiV2TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.enterClassContext(Shush())
