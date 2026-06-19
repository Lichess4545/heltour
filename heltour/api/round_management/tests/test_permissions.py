"""Permission-injection test for the round-matches service.

Demonstrates the DI seam: ``ChangePairingPermission`` accepts a
``has_perm_fn`` so tests can swap the real Django check for a stub
without provisioning django-guardian permissions or a real User.
"""

from django.test import TestCase

from heltour.api.round_management.permissions import ChangePairingPermission
from heltour.api.round_management.service import _build_round_matches
from heltour.api.round_management.tests.builders import make_team_round
from heltour.api.shared.auth import Viewer


_AUTHED = Viewer(user_id=1, is_authenticated=True, is_staff=False)


class ChangePairingPermissionInjectionTests(TestCase):
    def test_authenticated_viewer_with_perm_sees_edit_flag(self):
        rnd = make_team_round(
            league_tag="perm-y", season_tag="s", boards=2, team_count=2,
        )
        always_allow = ChangePairingPermission(has_perm_fn=lambda _u, _l: True)

        dto = _build_round_matches(rnd, _AUTHED, None, change_pairing=always_allow)

        self.assertTrue(dto.viewer.can_edit_pairings)
        self.assertTrue(dto.viewer.can_view_presence_log)

    def test_authenticated_viewer_without_perm_does_not_see_edit_flag(self):
        rnd = make_team_round(
            league_tag="perm-n", season_tag="s", boards=2, team_count=2,
        )
        always_deny = ChangePairingPermission(has_perm_fn=lambda _u, _l: False)

        dto = _build_round_matches(rnd, _AUTHED, None, change_pairing=always_deny)

        self.assertFalse(dto.viewer.can_edit_pairings)
        self.assertEqual(dto.presence_events, {})
