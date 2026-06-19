"""
Tests for TRF16 export from Django ORM models.
"""

from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from heltour.tournament.models import (
    League,
    LonePlayerPairing,
    LonePlayerScore,
    Player,
    PlayerBye,
    Round,
    Season,
    SeasonPlayer,
    Team,
    TeamMember,
    TeamPairing,
    TeamPlayerPairing,
    TeamScore,
)
from heltour.tournament.trf16_export import season_to_trf16
from heltour.tournament_core.trf16 import TRF16Parser


class TestTeamSeasonExport(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name="Team League",
            tag="trf16team",
            competitor_type="team",
            rating_type="classical",
            time_control="15+10",
        )
        cls.season = Season.objects.create(
            league=cls.league,
            name="Season 1",
            tag="s1",
            rounds=2,
            boards=2,
            start_date=timezone.make_aware(datetime(2024, 1, 1)),
        )

        # Create players
        cls.players = []
        for i in range(1, 5):
            p = Player.objects.create(lichess_username=f"teamplayer{i}")
            p.profile = {"perfs": {"classical": {"rating": 2000 - (i * 50)}}}
            p.save()
            cls.players.append(p)

        # Create teams
        cls.team1 = Team.objects.create(
            season=cls.season, number=1, name="Dragons"
        )
        TeamScore.objects.create(team=cls.team1)
        TeamMember.objects.create(
            team=cls.team1, player=cls.players[0], board_number=1, player_rating=1950
        )
        TeamMember.objects.create(
            team=cls.team1, player=cls.players[1], board_number=2, player_rating=1900
        )

        cls.team2 = Team.objects.create(
            season=cls.season, number=2, name="Knights"
        )
        TeamScore.objects.create(team=cls.team2)
        TeamMember.objects.create(
            team=cls.team2, player=cls.players[2], board_number=1, player_rating=1850
        )
        TeamMember.objects.create(
            team=cls.team2, player=cls.players[3], board_number=2, player_rating=1800
        )

        # Round 1: Dragons vs Knights
        round1 = Round.objects.get(season=cls.season, number=1)
        tp1 = TeamPairing.objects.create(
            round=round1, pairing_order=0, white_team=cls.team1, black_team=cls.team2
        )
        # Board 1: Dragons player (white) wins
        TeamPlayerPairing.objects.create(
            team_pairing=tp1,
            board_number=1,
            white=cls.players[0],
            black=cls.players[2],
            result="1-0",
        )
        # Board 2: Knights player (white, colors alternate) draws
        TeamPlayerPairing.objects.create(
            team_pairing=tp1,
            board_number=2,
            white=cls.players[3],
            black=cls.players[1],
            result="1/2-1/2",
        )
        tp1.refresh_points()
        tp1.save()

        # Round 2: not yet played (no pairings)

    def test_export_produces_valid_trf16(self):
        output = season_to_trf16(self.season)

        parser = TRF16Parser(output)
        header, players, teams = parser.parse_all()

        self.assertEqual(header.num_players, 4)
        self.assertEqual(header.num_teams, 2)
        self.assertEqual(header.num_rounds, 2)
        self.assertIn("Team League", header.tournament_name)

    def test_export_has_all_players(self):
        output = season_to_trf16(self.season)

        parser = TRF16Parser(output)
        parser.parse_players()

        self.assertEqual(len(parser.players), 4)

        names = {p.name for p in parser.players.values()}
        for player in self.players:
            self.assertIn(player.lichess_username, names)

    def test_export_has_teams(self):
        output = season_to_trf16(self.season)

        parser = TRF16Parser(output)
        parser.parse_all()

        self.assertIn("Dragons", parser.teams)
        self.assertIn("Knights", parser.teams)
        self.assertEqual(len(parser.teams["Dragons"].player_ids), 2)
        self.assertEqual(len(parser.teams["Knights"].player_ids), 2)

    def test_export_results(self):
        output = season_to_trf16(self.season)

        parser = TRF16Parser(output)
        parser.parse_players()

        # Find teamplayer1 (Dragons board 1, start_num=1)
        p1 = parser.players[1]
        self.assertEqual(p1.name, "teamplayer1")
        # Round 1: played as white vs player 3 (Knights board 1, start_num=3), won
        self.assertEqual(p1.results[0], (3, "w", "1"))
        # Round 2: bye (no pairings)
        self.assertEqual(p1.results[1], (None, "-", "-"))

    def test_export_ratings(self):
        output = season_to_trf16(self.season)

        parser = TRF16Parser(output)
        parser.parse_players()

        # player_rating from TeamMember is used
        self.assertEqual(parser.players[1].rating, 1950)
        self.assertEqual(parser.players[2].rating, 1900)

    def test_export_points(self):
        output = season_to_trf16(self.season)

        parser = TRF16Parser(output)
        parser.parse_players()

        # teamplayer1: won round 1, bye round 2 → 1.0
        self.assertEqual(parser.players[1].points, 1.0)
        # teamplayer2 (Dragons board 2): played as black in round 1, drew → 0.5
        self.assertEqual(parser.players[2].points, 0.5)


class TestLoneSeasonExport(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name="Lone League",
            tag="trf16lone",
            competitor_type="lone",
            rating_type="classical",
            time_control="90+30",
        )
        cls.season = Season.objects.create(
            league=cls.league,
            name="Season 1",
            tag="ls1",
            rounds=2,
            start_date=timezone.make_aware(datetime(2024, 1, 1)),
        )

        cls.players = []
        for i in range(1, 4):
            p = Player.objects.create(lichess_username=f"loneplayer{i}")
            p.profile = {"perfs": {"classical": {"rating": 2100 - (i * 100)}}}
            p.save()
            cls.players.append(p)

        # Create season players with seed ratings
        for i, p in enumerate(cls.players):
            sp = SeasonPlayer.objects.create(
                season=cls.season, player=p, seed_rating=2100 - ((i + 1) * 100)
            )
            LonePlayerScore.objects.create(season_player=sp)

        # Round 1: player1 vs player2 (player1 wins), player3 has bye
        round1 = Round.objects.get(season=cls.season, number=1)
        LonePlayerPairing.objects.create(
            round=round1,
            pairing_order=0,
            white=cls.players[0],
            black=cls.players[1],
            result="1-0",
        )
        PlayerBye.objects.create(
            round=round1, player=cls.players[2], type="half-point-bye"
        )

        # Round 2: player1 vs player3 (draw), player2 has bye
        round2 = Round.objects.get(season=cls.season, number=2)
        LonePlayerPairing.objects.create(
            round=round2,
            pairing_order=0,
            white=cls.players[2],
            black=cls.players[0],
            result="1/2-1/2",
        )
        PlayerBye.objects.create(
            round=round2, player=cls.players[1], type="half-point-bye"
        )

    def test_export_produces_valid_trf16(self):
        output = season_to_trf16(self.season)

        parser = TRF16Parser(output)
        header, players, teams = parser.parse_all()

        self.assertEqual(header.num_players, 3)
        self.assertEqual(header.num_teams, 0)
        self.assertEqual(header.num_rounds, 2)
        self.assertEqual(len(teams), 0)

    def test_export_no_team_lines(self):
        output = season_to_trf16(self.season)
        self.assertNotIn("\n013 ", output)

    def test_export_player_ordering_by_seed(self):
        output = season_to_trf16(self.season)

        parser = TRF16Parser(output)
        parser.parse_players()

        # Ordered by seed_rating descending: player1 (2000), player2 (1900), player3 (1800)
        self.assertEqual(parser.players[1].name, "loneplayer1")
        self.assertEqual(parser.players[2].name, "loneplayer2")
        self.assertEqual(parser.players[3].name, "loneplayer3")

    def test_export_results(self):
        output = season_to_trf16(self.season)

        parser = TRF16Parser(output)
        parser.parse_players()

        # Player 1 (start_num=1): round 1 white vs player2 (sn=2) won, round 2 black vs player3 (sn=3) drew
        p1 = parser.players[1]
        self.assertEqual(p1.results[0], (2, "w", "1"))
        self.assertEqual(p1.results[1], (3, "b", "="))

        # Player 2 (start_num=2): round 1 black vs player1 lost, round 2 bye
        p2 = parser.players[2]
        self.assertEqual(p2.results[0], (1, "b", "0"))
        self.assertEqual(p2.results[1], (None, "-", "-"))

        # Player 3 (start_num=3): round 1 bye, round 2 white vs player1 drew
        p3 = parser.players[3]
        self.assertEqual(p3.results[0], (None, "-", "-"))
        self.assertEqual(p3.results[1], (1, "w", "="))

    def test_export_points(self):
        output = season_to_trf16(self.season)

        parser = TRF16Parser(output)
        parser.parse_players()

        # Player 1: 1 (win) + 0.5 (draw) = 1.5
        self.assertEqual(parser.players[1].points, 1.5)
        # Player 2: 0 (loss) + 0 (bye) = 0.0
        self.assertEqual(parser.players[2].points, 0.0)
        # Player 3: 0 (bye) + 0.5 (draw) = 0.5
        self.assertEqual(parser.players[3].points, 0.5)


class TestExportForfeits(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name="Forfeit League",
            tag="trf16forfeit",
            competitor_type="lone",
            rating_type="classical",
        )
        cls.season = Season.objects.create(
            league=cls.league, name="Forfeit Season", tag="fs1", rounds=1
        )

        cls.player1 = Player.objects.create(lichess_username="winner")
        cls.player2 = Player.objects.create(lichess_username="loser")
        # Different seed ratings so ordering is deterministic
        ratings = {cls.player1: 1600, cls.player2: 1500}
        for p in [cls.player1, cls.player2]:
            r = ratings[p]
            p.profile = {"perfs": {"classical": {"rating": r}}}
            p.save()
            sp = SeasonPlayer.objects.create(
                season=cls.season, player=p, seed_rating=r
            )
            LonePlayerScore.objects.create(season_player=sp)

        round1 = Round.objects.get(season=cls.season, number=1)
        LonePlayerPairing.objects.create(
            round=round1,
            pairing_order=0,
            white=cls.player1,
            black=cls.player2,
            result="1X-0F",
        )

    def test_forfeit_export(self):
        output = season_to_trf16(self.season)

        parser = TRF16Parser(output)
        parser.parse_players()

        # Winner gets forfeit win
        p1 = parser.players[1]
        self.assertEqual(p1.results[0][2], "+")
        self.assertEqual(p1.points, 1.0)

        # Loser gets forfeit loss (appears as bye in TRF16)
        p2 = parser.players[2]
        self.assertEqual(p2.results[0][2], "-")
        self.assertEqual(p2.points, 0.0)


class TestExportColorsReversed(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name="Reversed League",
            tag="trf16rev",
            competitor_type="lone",
            rating_type="classical",
        )
        cls.season = Season.objects.create(
            league=cls.league, name="Reversed Season", tag="rs1", rounds=1
        )

        cls.player1 = Player.objects.create(lichess_username="actualblack")
        cls.player2 = Player.objects.create(lichess_username="actualwhite")
        for p in [cls.player1, cls.player2]:
            p.profile = {"perfs": {"classical": {"rating": 1500}}}
            p.save()
            sp = SeasonPlayer.objects.create(
                season=cls.season, player=p, seed_rating=1500
            )
            LonePlayerScore.objects.create(season_player=sp)

        round1 = Round.objects.get(season=cls.season, number=1)
        # White in DB is player1, but colors_reversed means player1 actually played black
        LonePlayerPairing.objects.create(
            round=round1,
            pairing_order=0,
            white=cls.player1,
            black=cls.player2,
            result="1-0",
            colors_reversed=True,
        )

    def test_colors_reversed(self):
        output = season_to_trf16(self.season)

        parser = TRF16Parser(output)
        parser.parse_players()

        # player1 is "white" in DB but colors_reversed → actually played black
        # "1-0" means white (DB) wins, but with reversed colors, player1 (actual black) wins
        # So in TRF16: player1 played as black and won
        p1 = parser.players[1]
        self.assertEqual(p1.results[0][1], "b")  # actual color is black

        p2 = parser.players[2]
        self.assertEqual(p2.results[0][1], "w")  # actual color is white


class TestTRF16ExportView(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name="View League",
            tag="trf16view",
            competitor_type="lone",
            rating_type="classical",
        )
        cls.season = Season.objects.create(
            league=cls.league, name="View Season", tag="vs1", rounds=1
        )
        p = Player.objects.create(lichess_username="viewplayer")
        p.profile = {"perfs": {"classical": {"rating": 1500}}}
        p.save()
        sp = SeasonPlayer.objects.create(season=cls.season, player=p, seed_rating=1500)
        LonePlayerScore.objects.create(season_player=sp)

        cls.staff_user = User.objects.create_superuser(
            username="staff", password="testpass"
        )
        cls.normal_user = User.objects.create_user(
            username="normal", password="testpass", is_staff=False
        )

    def test_staff_can_download(self):
        self.client.login(username="staff", password="testpass")
        url = reverse(
            "by_league:by_season:export_trf16",
            args=[self.league.tag, self.season.tag],
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".trf", response["Content-Disposition"])

        # Verify the content is valid TRF16
        content = response.content.decode("utf-8")
        parser = TRF16Parser(content)
        header, players, _ = parser.parse_all()
        self.assertEqual(header.num_players, 1)

    def test_non_staff_redirected(self):
        self.client.login(username="normal", password="testpass")
        url = reverse(
            "by_league:by_season:export_trf16",
            args=[self.league.tag, self.season.tag],
        )
        response = self.client.get(url)

        # staff_member_required redirects non-staff users
        self.assertNotEqual(response.status_code, 200)

    def test_anonymous_redirected(self):
        url = reverse(
            "by_league:by_season:export_trf16",
            args=[self.league.tag, self.season.tag],
        )
        response = self.client.get(url)

        self.assertNotEqual(response.status_code, 200)
