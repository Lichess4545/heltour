from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from heltour.tournament.models import LeagueChannel, LeagueSetting, LonePlayerPairing
from heltour.tournament.notify import (
    _lichess_message,
    _message_multiple_users,
    _message_user,
    _send_notification,
    notify_players_game_scheduled,
)
from heltour.tournament.tests.testutils import (
    createCommonLeagueData,
    get_league,
    get_player,
    get_round,
)


@patch("heltour.tournament.slackapi.send_message", autospec=True)
class UnderscoreFunctions(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.l = get_league("team")
        cls.l.enable_notifications = True
        cls.l.save()
        cls.lc = LeagueChannel.objects.create(
            league=cls.l, type="mod", slack_channel="#test_mods"
        )
        cls.lc = LeagueChannel.objects.create(
            league=cls.l, type="captains", slack_channel="#test_captains"
        )

    def test_send_notification(self, sm):
        tm = "test message"
        atm = "another test message"
        result = _send_notification(notification_type="mod", league=self.l, text=tm)
        self.assertEqual(result, None)
        sm.assert_called_once_with("#test_mods", tm)
        sm.reset_mock()
        result_c = _send_notification(
            notification_type="captains", league=self.l, text=atm
        )
        self.assertEqual(result_c, None)
        sm.assert_called_once_with("#test_captains", atm)

    def test_message_user(self, sm):
        tm = "hello, how are you"
        atm = "you want to play against @random_user?"
        result = _message_user(league=self.l, username="glbert", text=tm)
        self.assertEqual(result, None)
        sm.assert_called_once_with("@glbert", text=tm)
        sm.reset_mock()
        result = _message_user(league=self.l, username="blah_$_blah", text=atm)
        sm.assert_called_once_with("@blah_$_blah", text=atm)

    def test_message_multiple_users(self, sm):
        tm = "you people should schedule your games! #scheduling"
        result = _message_multiple_users(
            league=self.l,
            usernames=["glbert", "test_user", "lakinwecker", "chesster"],
            text=tm,
        )
        self.assertEqual(result, None)
        sm.assert_called_once_with("@glbert+@test_user+@lakinwecker+@chesster", tm)

    @patch("heltour.tournament.lichessapi.send_mail")
    def test_lichess_message(self, lichessapi_sm, slack_sm):
        tm = "your game is starting soon."
        result = _lichess_message(
            league=self.l, username="Lichess4545", subject="test", text=tm
        )
        self.assertEqual(result, None)
        slack_sm.assert_not_called()
        lichessapi_sm.assert_called_once_with(
            "Lichess4545", "test", "your game is starting soon."
        )


class PairingNotificationsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.l = get_league("lone")
        p1 = get_player("Player1")
        p2 = get_player("Player2")
        cls.r1 = get_round("lone", round_number=1)
        cls.lp1 = LonePlayerPairing.objects.create(
            white=p1,
            black=p2,
            round=cls.r1,
            pairing_order=1,
            scheduled_time=timezone.now(),
        )
        LeagueSetting.objects.filter(league=cls.l).update(start_games=True)

    @patch("heltour.tournament.notify.send_pairing_notification")
    def test_notify_scheduled_game(self, pn):
        notify_players_game_scheduled(pairing=self.lp1, round_=self.r1)
        self.assertTrue(pn.called)
        self.assertEqual(pn.call_args.kwargs["type_"], "game_scheduled")
        self.assertEqual(pn.call_args.kwargs["pairing"], self.lp1)
