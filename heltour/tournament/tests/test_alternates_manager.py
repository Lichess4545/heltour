from unittest.mock import patch

from django.test import TestCase

from heltour.tournament.alternates_manager import alternate_accepted, do_alternate_search
from heltour.tournament.models import (
    Alternate,
    AlternateAssignment,
    AlternateSearch,
    AlternatesManagerSetting,
    TeamPairing,
    TeamPlayerPairing,
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


class AlternateSearchPriorityTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.league = get_league(league_type="team")
        cls.season = get_season(league_type="team")
        cls.round = get_round(league_type="team", round_number=1)
        cls.round.publish_pairings = True
        cls.round.save()
        AlternatesManagerSetting.objects.create(
            league=cls.league, contact_before_round_start=False
        )

        cls.teams = [get_team(f"Team {n}") for n in range(1, 5)]
        cls.players = [
            team.teammember_set.get(board_number=1).player for team in cls.teams
        ]

        for pairing_order, (white_team, black_team) in enumerate(
            ((cls.teams[0], cls.teams[1]), (cls.teams[2], cls.teams[3]))
        ):
            team_pairing = TeamPairing.objects.create(
                round=cls.round,
                white_team=white_team,
                black_team=black_team,
                pairing_order=pairing_order,
            )
            TeamPlayerPairing.objects.create(
                team_pairing=team_pairing,
                board_number=1,
                white=white_team.teammember_set.get(board_number=1).player,
                black=black_team.teammember_set.get(board_number=1).player,
            )

        alt_player = Player.objects.create(lichess_username="AltPlayer")
        season_player = SeasonPlayer.objects.create(
            season=cls.season, player=alt_player
        )
        cls.alternate = Alternate.objects.create(
            season_player=season_player, board_number=1, status="contacted"
        )

    @patch("heltour.tournament.signals.alternate_assigned.send")
    def test_accepted_alternate_is_assigned_to_single_open_spot(
        self, alternate_assigned
    ):
        # The oldest search initially has the highest priority. A separate
        # single-open search starts next, then the oldest search's opponent also
        # becomes unavailable. The original search order remains unchanged, but
        # the accepted alternate should go to the single-open pairing.
        search_team_indexes = (0, 2, 1)
        searches = []
        for team_index in search_team_indexes:
            PlayerAvailability.objects.create(
                player=self.players[team_index], round=self.round, is_available=False
            )
            searches.append(
                AlternateSearch.objects.create(
                    round=self.round,
                    team=self.teams[team_index],
                    board_number=1,
                    status="started",
                )
            )

        with Shush():
            accepted = alternate_accepted(self.alternate)

        self.assertTrue(accepted)
        assignment = AlternateAssignment.objects.get(round=self.round, board_number=1)
        self.assertEqual(assignment.team, self.teams[2])
        searches[1].refresh_from_db()
        self.assertEqual(searches[1].status, "completed")
        self.assertTrue(alternate_assigned.called)
