from unittest.mock import patch

from django.test import TestCase

from heltour.tournament.alternates_manager import do_alternate_search
from heltour.tournament.models import (
    Alternate,
    AlternateSearch,
    AlternatesManagerSetting,
    Player,
    PlayerAvailability,
    SeasonPlayer,
)
from heltour.tournament.tests.testutils import (
    Shush,
    createCommonLeagueData,
    get_league,
    get_player,
    get_round,
    get_season,
    get_team,
)


class AlternatesManagerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.l = get_league(league_type="team")
        cls.s = get_season(league_type="team")
        cls.r = get_round(league_type="team", round_number=1)
        cls.t1 = get_team("Team 1")
        cls.p1 = get_player("Player1")
        cls.setting = AlternatesManagerSetting.objects.create(league=cls.l)
        cls.palt = Player.objects.create(lichess_username="AltPlayer")
        cls.spalt = SeasonPlayer.objects.create(season=cls.s, player=cls.palt)
        cls.alt = Alternate.objects.create(season_player=cls.spalt, board_number=1)

    def _create_published_pairing(self):
        self.l.enable_notifications = True
        self.l.save()
        type(self.r).objects.filter(pk=self.r.pk).update(publish_pairings=True)
        self.r.refresh_from_db()
        team_pairing = self.r.teampairing_set.create(
            white_team=self.t1,
            black_team=get_team("Team 2"),
            pairing_order=0,
        )
        return team_pairing.teamplayerpairing_set.create(
            board_number=1,
            white=self.p1,
            black=get_player("Player3"),
        )

    def _run_search(self):
        with patch("heltour.tournament.signals.alternate_needed.send"), \
             patch("heltour.tournament.signals.alternate_spots_filled.send"), \
             patch("heltour.tournament.alternates_manager.time.sleep"):
            do_alternate_search(
                season=self.s,
                round_=self.r,
                board_number=1,
                setting=self.setting,
            )

    @patch("heltour.tournament.notify.time.sleep")
    @patch("heltour.tournament.notify.send_pairing_notification")
    def test_pairing_notification_sent_when_player_returns(self, send_pairing, sleep):
        from heltour.tournament.notify import notify_players_round_start

        pairing = self._create_published_pairing()
        availability = PlayerAvailability.objects.create(
            player=self.p1, round=self.r, is_available=False
        )

        notify_players_round_start(self.r)
        send_pairing.assert_not_called()
        pairing.refresh_from_db()
        self.assertIs(pairing.round_start_notification_sent, False)

        self._run_search()
        search = AlternateSearch.objects.get(
            round=self.r, team=self.t1, board_number=1
        )
        self.assertEqual(search.status, "started")

        availability.is_available = True
        availability.save()
        send_pairing.return_value = True
        self._run_search()
        send_pairing.assert_called_once()

        send_pairing.reset_mock()
        self._run_search()
        send_pairing.assert_not_called()

        search.refresh_from_db()
        self.assertEqual(search.status, "cancelled")
        pairing.refresh_from_db()
        self.assertIs(pairing.round_start_notification_sent, True)

        availability.is_available = False
        availability.save()
        self._run_search()
        search.refresh_from_db()
        self.assertEqual(search.status, "started")
        send_pairing.assert_not_called()

    @patch("heltour.tournament.notify.time.sleep")
    @patch("heltour.tournament.notify.send_pairing_notification", return_value=True)
    def test_no_duplicate_if_player_becomes_unavailable_after_round_start(
        self, send_pairing, sleep
    ):
        from heltour.tournament.notify import notify_players_round_start

        pairing = self._create_published_pairing()
        notify_players_round_start(self.r)
        send_pairing.assert_called_once()
        pairing.refresh_from_db()
        self.assertIs(pairing.round_start_notification_sent, True)

        availability = PlayerAvailability.objects.create(
            player=self.p1, round=self.r, is_available=False
        )
        self._run_search()
        availability.is_available = True
        availability.save()

        self._run_search()
        send_pairing.assert_called_once()

        search = AlternateSearch.objects.get(
            round=self.r, team=self.t1, board_number=1
        )
        self.assertEqual(search.status, "cancelled")

    def test_do_empty_alternate_search(self):
        do_alternate_search(
            season=self.s, round_=self.r, board_number=1, setting=self.setting
        )
        self.assertEqual(AlternateSearch.objects.all().count(), 0)

    @patch("heltour.tournament.signals.alternate_needed.send")
    def test_alternate_search(self, altneeded):
        PlayerAvailability.objects.create(
            player=self.p1,
            round=self.r,
            is_available=False,
        )
        with Shush():
            do_alternate_search(
                season=self.s, round_=self.r, board_number=1, setting=self.setting
            )
        self.assertEqual(AlternateSearch.objects.all().count(), 1)
        alt_s = AlternateSearch.objects.all().first()
        self.assertEqual(alt_s.board_number, 1)
        self.assertEqual(alt_s.team, self.t1)
        self.assertTrue(altneeded.called)
        self.assertEqual(altneeded.call_args.kwargs["alternate"], self.alt)
        self.assertEqual(
            altneeded.call_args.kwargs["accept_url"],
            "/teamleague/season/teamseason/round/1/alternate/accept/",
        )
        self.assertEqual(
            altneeded.call_args.kwargs["decline_url"],
            "/teamleague/season/teamseason/round/1/alternate/decline/",
        )
