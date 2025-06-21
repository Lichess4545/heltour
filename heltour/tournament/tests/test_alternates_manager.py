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
