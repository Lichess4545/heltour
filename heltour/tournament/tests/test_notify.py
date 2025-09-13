from datetime import timedelta
from unittest.mock import patch

from django.db.models.signals import post_save
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from heltour.tournament.models import (
    LeagueChannel,
    LeagueSetting,
    LonePlayerPairing,
    PlayerLateRegistration,
    PlayerWithdrawal,
    Registration,
    abs_url,
)
from heltour.tournament.notify import (
    _lichess_message,
    _message_multiple_users,
    _message_user,
    _send_notification,
    latereg_saved,
    notify_mods_no_result,
    notify_mods_pairings_published,
    notify_mods_pending_regs,
    notify_mods_round_start_done,
    notify_mods_unscheduled,
    notify_players_game_scheduled,
    pairings_generated,
    pairing_forfeit_changed,
    player_account_status_changed,
    registration_saved,
    starting_round_transition,
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
        with DisconnectSignal(
            signal=post_save,
            receiver=registration_saved,
            sender=Registration,
            dispatch_uid="heltour.tournament.notify",
        ):
            cls.reg = create_reg(season=cls.s, name=cls.player_str)

        url_review = abs_url(reverse("admin:review_registration", args=[cls.reg.pk]))
        url_regs = abs_url(reverse("admin:tournament_registration_changelist"))
        cls.message_str = (
            f"@{cls.player_str} (0) has <"
            f"{url_review}?_changelist_filters=status__exact%3Dpending"
            f"%26season__id__exact%3D{cls.s.pk}|registered>"
            f" for {cls.l.name}. "
            f"<{url_regs}?status__exact=pending&season__id__exact={cls.s.pk}|1 pending>"
        )

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

    def test_notify_mods_pending_regs(self, sn):
        r = get_round(league_type="lone", round_number=1)
        notify_mods_pending_regs(round_=r)
        url = abs_url(reverse("admin:tournament_registration_changelist"))
        sn.assert_called_once_with(
            "mod",
            self.l,
            f"<{url}?status__exact=pending&season__id__exact="
            f"{r.season.pk}|1 pending registrations>",
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
        url = abs_url(reverse("admin:manage_players", args=[self.r.season.pk]))
        sn.assert_called_once_with(
            "mod",
            self.reg.round.season.league,
            f"@{self.p.lichess_username} <{url}|added> for round {self.r.number}",
        )

    def test_withrawal(self, sn):
        withdrawal_saved(instance=self.withdrawal, created=True)
        url = abs_url(reverse("admin:manage_players", args=[self.r.season.pk]))
        sn.assert_called_once_with(
            "mod",
            self.withdrawal.round.season.league,
            f"@{self.p.lichess_username} <{url}|withdrawn> for round {self.r.number}",
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
        url = abs_url(
            reverse(
                "by_league:player_profile",
                args=[self.r.season.league.tag, self.p.lichess_username],
            )
        )
        sn.assert_called_once_with(
            "mod",
            self.r.season.league,
            f"@{self.p.lichess_username.lower()} marked as closed on "
            f"<https://lichess.org/@/{self.p.lichess_username}|lichess>. "
            f"<{url}|Player profile>",
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
            f"<{url}|Player profile>",
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

    def test_notify_mods_pairings_published(self, sn):
        notify_mods_pairings_published(round_=self.r)
        sn.assert_called_once_with(
            "mod",
            self.r.season.league,
            f"{self.r} pairings published.",
        )

    def test_notify_mods_round_start_done(self, sn):
        notify_mods_round_start_done(round_=self.r)
        sn.assert_called_once_with(
            "mod",
            self.r.season.league,
            f"{self.r} notifications sent.",
        )

    def test_pairings_generated(self, sn):
        pairings_generated(round_=self.r)
        url = abs_url(reverse("admin:review_pairings", args=[self.r.pk]))
        sn.assert_called_once_with(
            "mod",
            self.r.season.league,
            f"Pairings generated for round {self.r.number}. " f"<{url}|Review>",
        )

    def test_starting_round_transition(self, sn):
        starting_round_transition(
            season=self.r.season, msg_list=[("blah", None), ("bosh", None)]
        )
        sn.assert_called_once_with(
            "mod",
            self.r.season.league,
            "Starting automatic round transition...\nblah\nbosh",
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
