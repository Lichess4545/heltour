from heltour.api_v2.tests.testutils import ApiV2TestCase


class MountTestCase(ApiV2TestCase):
    def test_when_api_v2_is_mounted_the_token_test_route_still_answers(self) -> None:
        self.assertEqual(self.status_of("/api/v2/token/test/"), 204)
