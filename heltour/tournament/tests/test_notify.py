from datetime import timedelta
from unittest.mock import patch

from django.db.models.signals import post_save
from django.test import TestCase
from django.utils import timezone

from heltour.tournament.models import (
    LeagueChannel,
    LeagueSetting,
    LonePlayerPairing,
    PlayerLateRegistration,
    PlayerWithdrawal,
    Registration,
)
from heltour.tournament.notify import (
    _lichess_message,
    _message_multiple_users,
    _message_user,
    _send_notification,
    latereg_saved,
    notify_mods_no_result,
    notify_mods_unscheduled,
    notify_players_game_scheduled,
    pairing_forfeit_changed,
    player_account_status_changed,
    registration_saved,
    withdrawal_saved,
)
from heltour.tournament.tests.testutils import (
    DisconnectSignal,
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


@patch("heltour.tournament.notify._send_notification", autospec=True)
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
        with DisconnectSignal(
            signal=post_save,
            receiver=registration_saved,
            sender=Registration,
            dispatch_uid="heltour.tournament.notify",
        ):
            cls.reg = create_reg(season=cls.s, name=cls.player_str)

    def test_registration_saved_preseason(self, sn):
        self.s.start_date = timezone.now() + timedelta(hours=5)
        registration_saved(instance=self.reg, created=True)
        sn.assert_not_called()
        setting = self.s.league.get_leaguesetting()
        setting.notify_for_pre_season_registrations = True
        setting.save()
        registration_saved(instance=self.reg, created=True)
        sn.assert_called_once_with(
            "mod",
            self.l,
            self.message_str,
        )

    def test_registration_saved(self, sn):
        registration_saved(instance=self.reg, created=True)
        sn.assert_called_once_with(
            "mod",
            self.l,
            self.message_str,
        )


@patch("heltour.tournament.notify._send_notification", autospec=True)
class ModNotifications(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.r = get_round(league_type="lone", round_number=1)
        cls.p = get_player("Player1")
        cls.p2 = get_player("Player2")
        cls.p3 = get_player("Player3")
        cls.p4 = get_player("Player4")
        cls.reg = PlayerLateRegistration.objects.create(round=cls.r, player=cls.p)
        cls.withdrawal = PlayerWithdrawal.objects.create(round=cls.r, player=cls.p)
        cls.pp = LonePlayerPairing.objects.create(
            white=cls.p, black=cls.p2, result="1F-0X", pairing_order=1, round=cls.r
        )
        cls.pp2 = LonePlayerPairing.objects.create(
            white=cls.p3, black=cls.p4, pairing_order=2, round=cls.r
        )

    def test_latereg_saved(self, sn):
        latereg_saved(instance=self.reg, created=True)
        sn.assert_called_once_with(
            "mod",
            self.reg.round.season.league,
            f"@{self.p.lichess_username} <https://example.com/admin/tournament/"
            f"season/{self.r.season.pk}/manage_players/|added> for round {self.r.number}",
        )

    def test_withrawal(self, sn):
        withdrawal_saved(instance=self.withdrawal, created=True)
        sn.assert_called_once_with(
            "mod",
            self.withdrawal.round.season.league,
            f"@{self.p.lichess_username} <https://example.com/admin/tournament/season"
            f"/{self.r.season.pk}/manage_players/|withdrawn> for round {self.r.number}",
        )

    def test_pairing_forfeit_changed(self, sn):
        pairing_forfeit_changed(instance=self.pp)
        sn.assert_called_with(
            "mod",
            self.pp.round.season.league,
            f"@{self.pp.white.lichess_username.lower()} vs "
            f"@{self.pp.black.lichess_username.lower()} 1F-0X",
        )

    def test_player_account_status_changed(self, sn):
        player_account_status_changed(
            instance=self.p, old_value="normal", new_value="closed"
        )
        sn.assert_called_once_with(
            "mod",
            self.r.season.league,
            f"@{self.p.lichess_username.lower()} marked as closed on "
            f"<https://lichess.org/@/{self.p.lichess_username}|lichess>. "
            "<https://example.com/loneleague/player/"
            f"{self.p.lichess_username}/|Player profile>",
        )
        sn.reset_mock()
        player_account_status_changed(
            instance=self.p, old_value="closed", new_value="normal"
        )
        sn.assert_called_once_with(
            "mod",
            self.r.season.league,
            f"@{self.p.lichess_username.lower()} "
            f"<https://lichess.org/@/{self.p.lichess_username}|lichess> account"
            " status changed from closed to normal. "
            "<https://example.com/loneleague/player/"
            f"{self.p.lichess_username}/|Player profile>",
        )

    def test_notify_mods_unscheduled(self, sn):
        notify_mods_unscheduled(round_=self.r)
        sn.assert_called_once_with(
            "mod",
            self.r.season.league,
            f"{self.r} - The following games are "
            f"unscheduled: @{self.p3.lichess_username.lower()}"
            f" vs @{self.p4.lichess_username.lower()}",
        )

    def test_notify_mods_missing_result(self, sn):
        notify_mods_no_result(round_=self.r)
        sn.assert_called_once_with(
            "mod",
            self.r.season.league,
            f"{self.r} - The following games are "
            f"missing results: @{self.p3.lichess_username.lower()}"
            f" vs @{self.p4.lichess_username.lower()}",
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
