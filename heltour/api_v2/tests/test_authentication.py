from heltour.api_v2.tests.testutils import ApiV2TestCase, ShushedApiV2TestCase


class ApiKeyAuthenticationTestCase(ApiV2TestCase):
    def test_when_the_token_is_known_the_request_is_answered(self) -> None:
        self.assertEqual(self.status_of("/api/v2/leagues/"), 200)


class ApiKeyAuthenticationErrorTestCase(ShushedApiV2TestCase):
    def test_when_no_token_is_given_the_request_is_unauthorized(self) -> None:
        response = self.client.get("/api/v2/leagues/")
        self.assertEqual(response.status_code, 401)

    def test_when_the_token_is_unknown_the_request_is_unauthorized(self) -> None:
        response = self.client.get(
            "/api/v2/leagues/", headers={"authorization": "Token unknown"}
        )
        self.assertEqual(response.status_code, 401)

    def test_when_the_header_is_not_a_token_the_request_is_unauthorized(self) -> None:
        response = self.client.get(
            "/api/v2/leagues/",
            headers={"authorization": f"Bearer {self.api_key.secret_token}"},
        )
        self.assertEqual(response.status_code, 401)
