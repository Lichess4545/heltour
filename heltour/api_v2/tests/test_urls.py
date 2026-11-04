from django.test import TestCase

from heltour.tournament.models import ApiKey


class MountTestCase(TestCase):
    def test_when_api_v2_is_mounted_the_token_test_route_still_answers(self) -> None:
        api_key = ApiKey.objects.create(name="test_key")
        response = self.client.get(
            "/api/v2/token/test/",
            headers={"authorization": f"Token {api_key.secret_token}"},
        )
        self.assertEqual(response.status_code, 204)
