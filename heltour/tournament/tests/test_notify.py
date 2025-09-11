import contextlib
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from heltour.tournament.models import (
    LeagueChannel,
    LeagueSetting,
    LonePlayerPairing,
)
from heltour.tournament.notify import (
    _lichess_message,
    _message_multiple_users,
    _message_user,
    _send_notification,
    notify_players_game_scheduled,
    registration_saved,
)
from heltour.tournament.tests.testutils import (
    Shush,
    create_reg,
    createCommonLeagueData,
    get_league,
    get_player,
    get_round,
    get_season,
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


@patch("heltour.tournament.slackapi.send_message", autospec=True)
class RegistrationsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.l = get_league("lone")
        cls.l.enable_notifications = True
        cls.l.save()
        cls.lc = LeagueChannel.objects.create(
            league=cls.l, type="mod", slack_channel="#test_mods"
        )
        cls.s = get_season("lone")
        cls.s.start_date = timezone.now() - timedelta(hours=5)
        cls.s.save()
        cls.player_str = "Player10"
        cls.message_str = (
            f"@{cls.player_str} (0) has "
            "<https://example.com/admin/tournament/registration/1/review/?"
            "_changelist_filters=status__exact%3Dpending"
            f"%26season__id__exact%3D{cls.s.pk}|registered>"
            f" for {cls.l.name}. "
            "<https://example.com/admin/tournament/registration/"
            f"?status__exact=pending&season__id__exact={cls.s.pk}|1 pending>"
        )
        with contextlib.redirect_stdout(None):
            cls.reg = create_reg(season=cls.s, name=cls.player_str)

    def test_registration_saved_preseason(self, sm):
        self.s.start_date = timezone.now() + timedelta(hours=5)
        registration_saved(instance=self.reg, created=True)
        sm.assert_not_called()
        setting = self.s.league.get_leaguesetting()
        setting.notify_for_pre_season_registrations = True
        setting.save()
        registration_saved(instance=self.reg, created=True)
        sm.assert_called_once_with(
            "#test_mods",
            self.message_str,
        )

    def test_registration_saved(self, sm):
        registration_saved(instance=self.reg, created=True)
        sm.assert_called_once_with(
            "#test_mods",
            self.message_str,
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
