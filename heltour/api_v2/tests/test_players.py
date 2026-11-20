from typing import Any

from heltour.api_v2.tests.testutils import ApiV2TestCase, ShushedApiV2TestCase, grant
from heltour.tournament.models import ApiKey, OauthToken, Player

PATH = "/api/v2/players/by-email/"
ALICE = {"name": "Alice", "id": "alice"}


def token_with_email(account_email: str) -> OauthToken:
    return OauthToken.objects.create(
        access_token="access",
        token_type="bearer",
        expires="2030-01-01T00:00:00Z",
        account_username="someone",
        account_email=account_email,
    )


class PlayerByEmailFixture(ApiV2TestCase):
    permission = "find_player_by_email"

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        Player.objects.create(lichess_username="Alice", email="alice@gmail.com")

    def _found(self, email: str) -> Any:
        return self.post_json(PATH, {"email": email})

    def _status_of(self, email: str, api_key: ApiKey | None = None) -> int:
        return self.status_of_post(PATH, {"email": email}, api_key)


class PlayerByEmailTestCase(PlayerByEmailFixture):
    def test_when_the_email_was_typed_by_the_player_the_player_is_found(
        self,
    ) -> None:
        self.assertEqual(self._found("alice@gmail.com"), ALICE)

    def test_when_the_email_has_a_plus_tag_the_player_is_found(self) -> None:
        self.assertEqual(self._found("alice+league@gmail.com"), ALICE)

    def test_when_a_gmail_address_has_dots_the_player_is_found(self) -> None:
        self.assertEqual(self._found("a.lice@gmail.com"), ALICE)

    def test_when_the_email_is_the_lichess_account_email_the_player_is_found(
        self,
    ) -> None:
        Player.objects.create(
            lichess_username="Bob", oauth_token=token_with_email("bob@example.com")
        )
        self.assertEqual(self._found("bob@example.com"), {"name": "Bob", "id": "bob"})

    def test_when_the_player_has_the_email_twice_the_player_is_found(self) -> None:
        Player.objects.filter(lichess_username="Alice").update(
            oauth_token=token_with_email("alice@gmail.com")
        )
        self.assertEqual(self._found("alice@gmail.com"), ALICE)


class PlayerByEmailErrorTestCase(ShushedApiV2TestCase, PlayerByEmailFixture):
    def test_when_the_email_is_unknown_the_player_is_not_found(self) -> None:
        self.assertEqual(self._status_of("nobody@example.com"), 404)

    def test_when_another_players_lichess_account_has_the_email_it_is_ambiguous(
        self,
    ) -> None:
        Player.objects.create(
            lichess_username="Mallory",
            oauth_token=token_with_email("alice@gmail.com"),
        )
        self.assertEqual(self._status_of("alice@gmail.com"), 409)

    def test_when_the_email_is_not_an_email_the_request_is_bad(self) -> None:
        self.assertEqual(self._status_of("alice"), 400)

    def test_when_the_keys_groups_lack_the_permission_the_request_is_forbidden(
        self,
    ) -> None:
        doxer = ApiKey.objects.create(name="doxer")
        grant(doxer, "dox")
        self.assertEqual(self._status_of("alice@gmail.com", doxer), 403)
