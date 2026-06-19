from django.test import TestCase
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
from heltour.tournament.tests.testutils import (
    league_tag,
    season_tag,
    season_url,
)


def _create_fide_league_data():
    league = League.objects.create(
        name="FIDE League",
        tag=league_tag("fide"),
        competitor_type="lone",
        rating_type="classical",
        show_fide_names=True,
    )
    season = Season.objects.create(
        league=league,
        name="FIDE Season",
        tag=season_tag("fide"),
        rounds=2,
    )

    alice = Player.objects.create(
        lichess_username="alice_chess",
        fide_profile={"name": "Smith, Alice"},
    )
    bob = Player.objects.create(
        lichess_username="bob_plays",
        fide_profile={"name": "Jones, Bob"},
    )
    charlie = Player.objects.create(
        lichess_username="charlie99",
        fide_profile=None,
    )

    sp_alice = SeasonPlayer.objects.create(season=season, player=alice)
    sp_bob = SeasonPlayer.objects.create(season=season, player=bob)
    sp_charlie = SeasonPlayer.objects.create(season=season, player=charlie)

    LonePlayerScore.objects.create(season_player=sp_alice)
    LonePlayerScore.objects.create(season_player=sp_bob)
    LonePlayerScore.objects.create(season_player=sp_charlie)

    rd = Round.objects.get(season=season, number=1)
    rd.publish_pairings = True
    rd.start_date = timezone.now()
    rd.save()

    LonePlayerPairing.objects.create(
        round=rd,
        white=alice,
        black=bob,
        pairing_order=1,
        result="1-0",
    )
    LonePlayerPairing.objects.create(
        round=rd,
        white=bob,
        black=charlie,
        pairing_order=2,
    )

    return league, season, alice, bob, charlie


def _create_fide_team_league_data():
    league = League.objects.create(
        name="FIDE Team League",
        tag=league_tag("fideteam"),
        competitor_type="team",
        rating_type="classical",
        show_fide_names=True,
    )
    season = Season.objects.create(
        league=league,
        name="FIDE Team Season",
        tag=season_tag("fideteam"),
        rounds=1,
        boards=2,
    )

    p1 = Player.objects.create(
        lichess_username="fide_p1",
        fide_profile={"name": "Andersson, Sven"},
    )
    p2 = Player.objects.create(
        lichess_username="fide_p2",
        fide_profile={"name": "Mueller, Hans"},
    )
    p3 = Player.objects.create(
        lichess_username="fide_p3",
        fide_profile=None,
    )
    p4 = Player.objects.create(
        lichess_username="fide_p4",
        fide_profile={"name": "Ivanov, Boris"},
    )

    team_a = Team.objects.create(season=season, number=1, name="Alpha")
    team_b = Team.objects.create(season=season, number=2, name="Beta")
    TeamScore.objects.create(team=team_a)
    TeamScore.objects.create(team=team_b)

    TeamMember.objects.create(team=team_a, player=p1, board_number=1)
    TeamMember.objects.create(team=team_a, player=p2, board_number=2)
    TeamMember.objects.create(team=team_b, player=p3, board_number=1)
    TeamMember.objects.create(team=team_b, player=p4, board_number=2)

    rd = Round.objects.get(season=season, number=1)
    rd.publish_pairings = True
    rd.start_date = timezone.now()
    rd.save()

    tp = TeamPairing.objects.create(
        white_team=team_a,
        black_team=team_b,
        round=rd,
        pairing_order=0,
    )
    TeamPlayerPairing.objects.create(
        team_pairing=tp,
        board_number=1,
        white=p1,
        black=p3,
    )
    TeamPlayerPairing.objects.create(
        team_pairing=tp,
        board_number=2,
        white=p4,
        black=p2,
    )

    return league, season, p1, p2, p3, p4


class FideDisplayNameLoneStandingsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season, cls.alice, cls.bob, cls.charlie = (
            _create_fide_league_data()
        )

    def test_standings_shows_fide_names(self):
        response = self.client.get(season_url("fide", "standings"))
        content = response.content.decode()
        self.assertIn("Smith, Alice (alice_chess)", content)
        self.assertIn("Jones, Bob (bob_plays)", content)
        self.assertIn("charlie99", content)
        self.assertNotIn("Smith, Alice (charlie99)", content)

    def test_standings_shows_lichess_only_when_disabled(self):
        self.league.show_fide_names = False
        self.league.save()
        response = self.client.get(season_url("fide", "standings"))
        content = response.content.decode()
        self.assertIn("alice_chess", content)
        self.assertNotIn("Smith, Alice", content)


class FideDisplayNameLonePairingsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season, cls.alice, cls.bob, cls.charlie = (
            _create_fide_league_data()
        )

    def test_pairings_shows_fide_names(self):
        response = self.client.get(season_url("fide", "pairings"))
        content = response.content.decode()
        self.assertIn("Smith, Alice (alice_chess)", content)
        self.assertIn("Jones, Bob (bob_plays)", content)

    def test_pairings_preserves_lichess_urls(self):
        response = self.client.get(season_url("fide", "pairings"))
        content = response.content.decode()
        self.assertIn("games/user/alice_chess?perfType=classical", content)
        self.assertIn("games/user/bob_plays?perfType=classical", content)

    def test_pairings_shows_lichess_only_when_disabled(self):
        self.league.show_fide_names = False
        self.league.save()
        response = self.client.get(season_url("fide", "pairings"))
        content = response.content.decode()
        self.assertNotIn("Smith, Alice", content)
        self.assertIn("alice_chess", content)


class FideDisplayNameWallchartTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season, cls.alice, cls.bob, cls.charlie = (
            _create_fide_league_data()
        )

    def test_wallchart_shows_fide_names(self):
        response = self.client.get(season_url("fide", "wallchart"))
        content = response.content.decode()
        self.assertIn("Smith, Alice (alice_chess)", content)
        self.assertIn("Jones, Bob (bob_plays)", content)
        self.assertIn("charlie99", content)


class FideDisplayNamePlayerProfileTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season, cls.alice, cls.bob, cls.charlie = (
            _create_fide_league_data()
        )

    def _profile_url(self, username):
        from django.urls import reverse

        return reverse(
            "by_league:by_season:player_profile",
            args=[league_tag("fide"), season_tag("fide"), username],
        )

    def test_profile_heading_shows_fide_name(self):
        response = self.client.get(self._profile_url("alice_chess"))
        content = response.content.decode()
        self.assertIn("Smith, Alice (alice_chess)", content)

    def test_profile_title_shows_fide_name(self):
        response = self.client.get(self._profile_url("alice_chess"))
        content = response.content.decode()
        self.assertIn("<title>", content)
        title_start = content.index("<title>")
        title_end = content.index("</title>")
        title = content[title_start:title_end]
        self.assertIn("Smith, Alice (alice_chess)", title)

    def test_profile_game_history_shows_fide_names(self):
        response = self.client.get(self._profile_url("alice_chess"))
        content = response.content.decode()
        self.assertIn("Smith, Alice (alice_chess)", content)
        self.assertIn("Jones, Bob (bob_plays)", content)

    def test_profile_preserves_lichess_urls(self):
        response = self.client.get(self._profile_url("alice_chess"))
        content = response.content.decode()
        self.assertIn("lichess.org/@/alice_chess", content)
        self.assertIn("lichess.org/api/games/user/alice_chess", content)

    def test_player_without_fide_profile(self):
        response = self.client.get(self._profile_url("charlie99"))
        content = response.content.decode()
        self.assertIn("charlie99", content)
        # Should not get FIDE-formatted display name
        self.assertNotIn(">charlie99 (charlie99)", content)

    def test_profile_disabled_shows_lichess_only(self):
        self.league.show_fide_names = False
        self.league.save()
        response = self.client.get(self._profile_url("alice_chess"))
        content = response.content.decode()
        self.assertNotIn("Smith, Alice", content)


class FideDisplayNameTeamPairingsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season, cls.p1, cls.p2, cls.p3, cls.p4 = (
            _create_fide_team_league_data()
        )

    def test_team_pairings_shows_fide_names(self):
        response = self.client.get(season_url("fideteam", "pairings"))
        content = response.content.decode()
        self.assertIn("Andersson, Sven (fide_p1)", content)
        self.assertIn("Mueller, Hans (fide_p2)", content)
        self.assertIn("Ivanov, Boris (fide_p4)", content)

    def test_team_pairings_no_fide_profile_player(self):
        response = self.client.get(season_url("fideteam", "pairings"))
        content = response.content.decode()
        self.assertIn("fide_p3", content)
        # Player without FIDE profile should not get a FIDE-formatted display name.
        # Note: "(fide_p3)" appears in alt attributes, so check the link text specifically.
        self.assertNotIn(">fide_p3 (fide_p3)", content)


class FideDisplayNameTeamRostersTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season, cls.p1, cls.p2, cls.p3, cls.p4 = (
            _create_fide_team_league_data()
        )

    def test_rosters_shows_fide_names(self):
        response = self.client.get(season_url("fideteam", "rosters"))
        content = response.content.decode()
        self.assertIn("Andersson, Sven (fide_p1)", content)
        self.assertIn("Mueller, Hans (fide_p2)", content)
        self.assertIn("fide_p3", content)

    def test_rosters_disabled_shows_lichess_only(self):
        self.league.show_fide_names = False
        self.league.save()
        response = self.client.get(season_url("fideteam", "rosters"))
        content = response.content.decode()
        self.assertNotIn("Andersson, Sven", content)
        self.assertIn("fide_p1", content)


class FideDisplayNameTeamProfileTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season, cls.p1, cls.p2, cls.p3, cls.p4 = (
            _create_fide_team_league_data()
        )

    def _team_profile_url(self, team_number):
        from django.urls import reverse

        return reverse(
            "by_league:by_season:team_profile",
            args=[league_tag("fideteam"), season_tag("fideteam"), team_number],
        )

    def test_team_profile_shows_fide_names(self):
        response = self.client.get(self._team_profile_url(1))
        content = response.content.decode()
        self.assertIn("Andersson, Sven (fide_p1)", content)
        self.assertIn("Mueller, Hans (fide_p2)", content)

    def test_team_profile_no_fide_shows_plain_username(self):
        response = self.client.get(self._team_profile_url(2))
        content = response.content.decode()
        self.assertIn("fide_p3", content)
        self.assertNotIn("(fide_p3)", content)


class FideDisplayNameLoneCompletedSeasonTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season, cls.alice, cls.bob, cls.charlie = (
            _create_fide_league_data()
        )
        cls.season.is_completed = True
        cls.season.save()

    def test_completed_landing_shows_fide_names(self):
        response = self.client.get(season_url("fide", "season_landing"))
        content = response.content.decode()
        self.assertIn("Smith, Alice (alice_chess)", content)

    def test_completed_landing_disabled_shows_lichess_only(self):
        self.league.show_fide_names = False
        self.league.save()
        response = self.client.get(season_url("fide", "season_landing"))
        content = response.content.decode()
        self.assertNotIn("Smith, Alice", content)
        self.assertIn("alice_chess", content)


class FideDisplayNameLoneSeasonLandingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season, cls.alice, cls.bob, cls.charlie = (
            _create_fide_league_data()
        )

    def test_season_landing_shows_fide_names(self):
        response = self.client.get(season_url("fide", "season_landing"))
        content = response.content.decode()
        self.assertIn("Smith, Alice (alice_chess)", content)
        self.assertIn("Jones, Bob (bob_plays)", content)

    def test_season_landing_disabled(self):
        self.league.show_fide_names = False
        self.league.save()
        response = self.client.get(season_url("fide", "season_landing"))
        content = response.content.decode()
        self.assertNotIn("Smith, Alice", content)


class FideDisplayNameByeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season, cls.alice, cls.bob, cls.charlie = (
            _create_fide_league_data()
        )
        rd = Round.objects.get(season=cls.season, number=1)
        PlayerBye.objects.create(round=rd, player=cls.alice, type="full-point-bye")

    def test_bye_pairings_shows_fide_name(self):
        response = self.client.get(season_url("fide", "pairings"))
        content = response.content.decode()
        self.assertIn("Smith, Alice (alice_chess)", content)
