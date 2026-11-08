from typing import Any

from django.contrib.auth.models import Group, Permission

from heltour.api_v2.tests.testutils import ApiV2TestCase
from heltour.tournament.models import ApiKey, OauthToken, Player

PATH = "/api/v2/players/by-email/"


def api_key_with_permission(name: str, codename: str) -> ApiKey:
    group = Group.objects.create(name=name)
    group.permissions.add(Permission.objects.get(codename=codename))
    api_key = ApiKey.objects.create(name=name)
    api_key.groups.add(group)
    return api_key


def token_with_email(account_email: str) -> OauthToken:
    return OauthToken.objects.create(
        access_token="access",
        token_type="bearer",
        expires="2030-01-01T00:00:00Z",
        account_username="someone",
        account_email=account_email,
    )


class PlayerByEmailTestCase(ApiV2TestCase):
    finder: ApiKey

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.finder = api_key_with_permission("finder", "find_player_by_email")
        Player.objects.create(lichess_username="Alice", email="alice@example.com")

    def _post(self, body: dict[str, str], api_key: ApiKey | None = None) -> Any:
        key = api_key or self.finder
        return self.client.post(
            PATH,
            body,
            content_type="application/json",
            headers={"authorization": f"Token {key.secret_token}"},
        )

    def _status_of(self, email: str, api_key: ApiKey | None = None) -> int:
        status: int = self._post({"email": email}, api_key).status_code
        return status

    def _found(self, email: str) -> Any:
        response = self._post({"email": email})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_when_the_email_was_typed_by_the_player_the_player_is_found(
        self,
    ) -> None:
        self.assertEqual(
            self._found("alice@example.com"), {"name": "Alice", "id": "alice"}
        )

    def test_when_the_domain_differs_in_case_the_player_is_found(self) -> None:
        self.assertEqual(
            self._found("alice@EXAMPLE.com"), {"name": "Alice", "id": "alice"}
        )

    def test_when_the_email_is_unknown_the_player_is_not_found(self) -> None:
        self.assertEqual(self._status_of("nobody@example.com"), 404)

    def test_when_the_email_is_the_lichess_account_email_the_player_is_found(
        self,
    ) -> None:
        Player.objects.create(
            lichess_username="Bob", oauth_token=token_with_email("bob@example.com")
        )
        self.assertEqual(self._found("bob@example.com"), {"name": "Bob", "id": "bob"})

    def test_when_the_player_has_the_email_twice_the_player_is_found(self) -> None:
        Player.objects.create(
            lichess_username="Bob",
            email="bob@example.com",
            oauth_token=token_with_email("bob@EXAMPLE.com"),
        )
        self.assertEqual(self._found("bob@example.com"), {"name": "Bob", "id": "bob"})

    def test_when_players_share_the_email_the_request_is_ambiguous(self) -> None:
        Player.objects.create(lichess_username="Carol", email="shared@example.com")
        Player.objects.create(lichess_username="Dave", email="shared@Example.com")
        self.assertEqual(self._status_of("shared@example.com"), 409)

    def test_when_another_players_lichess_account_has_the_email_it_is_ambiguous(
        self,
    ) -> None:
        Player.objects.create(
            lichess_username="Mallory",
            oauth_token=token_with_email("alice@example.com"),
        )
        self.assertEqual(self._status_of("alice@example.com"), 409)

    def test_when_the_email_has_a_comment_the_request_is_bad(self) -> None:
        self.assertEqual(self._status_of("alice(comment)@example.com"), 400)

    def test_when_the_email_has_a_plus_tag_the_untagged_player_is_not_found(
        self,
    ) -> None:
        self.assertEqual(self._status_of("alice+league@example.com"), 404)

    def test_when_the_email_is_blank_the_request_is_bad(self) -> None:
        Player.objects.create(lichess_username="NoEmail")
        self.assertEqual(self._status_of(""), 400)

    def test_when_the_email_is_not_an_email_the_request_is_bad(self) -> None:
        self.assertEqual(self._status_of("alice"), 400)

    def test_when_the_email_is_missing_the_request_is_bad(self) -> None:
        self.assertEqual(self._post({}).status_code, 400)

    def test_when_the_email_is_in_the_query_it_is_not_read(self) -> None:
        response = self.client.post(
            f"{PATH}?email=alice@example.com",
            headers={"authorization": f"Token {self.finder.secret_token}"},
        )
        self.assertEqual(response.status_code, 400)

    def test_when_the_key_has_no_group_the_request_is_forbidden(self) -> None:
        self.assertEqual(self._status_of("alice@example.com", self.api_key), 403)

    def test_when_the_keys_groups_lack_the_permission_the_request_is_forbidden(
        self,
    ) -> None:
        doxer = api_key_with_permission("doxer", "dox")
        self.assertEqual(self._status_of("alice@example.com", doxer), 403)

    def test_when_the_group_is_removed_from_the_key_the_request_is_forbidden(
        self,
    ) -> None:
        self.assertEqual(self._status_of("alice@example.com"), 200)
        self.finder.groups.clear()
        self.assertEqual(self._status_of("alice@example.com"), 403)

    def test_when_no_token_is_given_the_request_is_unauthorized(self) -> None:
        response = self.client.post(
            PATH, {"email": "alice@example.com"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 401)
