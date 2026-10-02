from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from heltour.tournament.models import (
    League,
    LeagueChannel,
    LeagueSetting,
    LonePlayerPairing,
    PlayerAvailability,
    TeamPairing,
    TeamPlayerPairing,
)
from heltour.tournament.notify import notify_players_game_scheduled
from heltour.tournament.tests.testutils import (
    Shush,
    createCommonLeagueData,
    get_league,
    get_player,
    get_round,
    get_team,
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


class AvailabilityModNotificationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.p1 = get_player("Player1")
        cls.p2 = get_player("Player2")
        cls.lr1 = get_round("lone", round_number=1)
        cls.lw = get_league("lone")
        League.objects.all().update(enable_notifications=True)
        LeagueChannel.objects.create(
            league=cls.lw, type="mod", slack_channel="#test_mods"
        )

    @patch("heltour.tournament.notify._send_notification")
    def test_notify_availability_change_team(self, mn):
        tr1 = get_round("team", round_number=1)
        t1 = get_team("Team 1")
        t2 = get_team("Team 2")

        tp = TeamPairing.objects.create(
            white_team=t1, black_team=t2, round=tr1, pairing_order=0
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp,
            board_number=1,
            white=self.p1,
            black=self.p2,
            white_confirmed=False,
            black_confirmed=False,
        )
        PlayerAvailability.objects.create(player=self.p1, round=tr1, is_available=False)
        # notification not called because it is a team league
        mn.assert_not_called()

    @patch("heltour.tournament.notify._send_notification")
    def test_notify_availability_change_lw_no_pairings(self, mn):
        PlayerAvailability.objects.create(
            player=self.p1, round=self.lr1, is_available=False
        )
        # notification not called because there are not pairings
        mn.assert_not_called()

    @patch("heltour.tournament.notify._send_notification")
    def test_notify_availability_change_lw_pairings_published(self, mn):
        LonePlayerPairing.objects.create(
            white=self.p1,
            black=self.p2,
            round=self.lr1,
            pairing_order=1,
            scheduled_time=timezone.now(),
        )
        self.lr1.publish_pairings = True
        with Shush():
            self.lr1.save()
        PlayerAvailability.objects.create(
            player=self.p1, round=self.lr1, is_available=False
        )
        # notification not called because pairings are published
        mn.assert_not_called()

    @patch("heltour.tournament.notify._send_notification", autospec=True)
    def test_notify_availability_change_lw(self, mn):
        LonePlayerPairing.objects.create(
            white=self.p1,
            black=self.p2,
            round=self.lr1,
            pairing_order=1,
            scheduled_time=timezone.now(),
        )
        pa = PlayerAvailability.objects.create(
            player=self.p1, round=self.lr1, is_available=False
        )
        # unpublished pairings exist, notify called on creation
        mn.assert_called_once_with(
            "mod",
            self.lw,
            "Player Player1 changed to NOT available for Test Season - Round 1, unpublished pairings already exist.",
        )
        mn.reset_mock()
        pa.is_available = True
        pa.save()
        # unpublished pairings exist, notify called on edit
        mn.assert_called_once_with(
            "mod",
            self.lw,
            "Player Player1 changed to available for Test Season - Round 1, unpublished pairings already exist.",
        )
