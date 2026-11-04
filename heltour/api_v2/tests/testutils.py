from typing import Any

from django.test import TestCase

from heltour.tournament.models import ApiKey


class ApiV2TestCase(TestCase):
    api_key: ApiKey

    @classmethod
    def setUpTestData(cls) -> None:
        cls.api_key = ApiKey.objects.create(name="test_key")

    def authorization(self) -> dict[str, str]:
        return {"authorization": f"Token {self.api_key.secret_token}"}

    def status_of(self, path: str, **query: str) -> int:
        return self.client.get(path, query, headers=self.authorization()).status_code

    def get_json(self, path: str, **query: str) -> Any:
        response = self.client.get(path, query, headers=self.authorization())
        self.assertEqual(response.status_code, 200)
        return response.json()
