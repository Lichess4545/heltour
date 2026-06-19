from django.contrib.auth.models import User
from django.test import TestCase

from heltour.tournament.models import (
    League,
    Player,
    Season,
    SeasonPlayer,
)
from heltour.tournament.tests.testutils import (
    createCommonLeagueData,
    league_tag,
    season_tag,
    season_url,
    Shush,
)


def _create_fide_league():
    league = League.objects.create(
        name="FIDE League",
        tag=league_tag("fide"),
        competitor_type="lone",
        rating_type="fide_standard",
        show_fide_names=True,
    )
    season = Season.objects.create(
        league=league,
        name="FIDE Season",
        tag=season_tag("fide"),
        rounds=3,
    )
    return league, season


def _create_fide_player(season, username, fide_id, fide_profile):
    player = Player.objects.create(
        lichess_username=username,
        fide_id=fide_id,
        fide_profile=fide_profile,
    )
    SeasonPlayer.objects.create(season=season, player=player, is_active=True)
    return player


class BroadcastPlayersAccessTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season = _create_fide_league()
        cls.staff_user = User.objects.create_superuser(
            "admin", "admin@test.com", "test"
        )
        cls.regular_user = User.objects.create_user("regular", password="test")

    def test_requires_staff_login(self):
        response = self.client.get(season_url("fide", "broadcast_players"))
        self.assertEqual(response.status_code, 302)

    def test_non_staff_redirected(self):
        self.client.login(username="regular", password="test")
        response = self.client.get(season_url("fide", "broadcast_players"))
        self.assertEqual(response.status_code, 302)

    def test_staff_can_access(self):
        self.client.login(username="admin", password="test")
        response = self.client.get(season_url("fide", "broadcast_players"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "tournament/broadcast_players.html")


class BroadcastPlayersOutputTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season = _create_fide_league()
        cls.staff_user = User.objects.create_superuser(
            "admin", "admin@test.com", "test"
        )

        _create_fide_player(
            cls.season,
            "alice",
            "12345",
            {"name": "Smith, Alice", "title": "WGM", "standard": 2100},
        )
        _create_fide_player(
            cls.season,
            "bob",
            "67890",
            {"name": "Jones, Bob", "title": "FM", "standard": 2250},
        )
        _create_fide_player(
            cls.season,
            "charlie",
            "11111",
            {"name": "Brown, Charlie", "standard": 1900},
        )

    def test_output_format(self):
        self.client.login(username="admin", password="test")
        response = self.client.get(season_url("fide", "broadcast_players"))
        content = response.content.decode()

        self.assertIn("alice / 12345 / WGM / 2100 / Smith, Alice", content)
        self.assertIn("bob / 67890 / FM / 2250 / Jones, Bob", content)
        self.assertIn("charlie / 11111 /  / 1900 / Brown, Charlie", content)

    def test_players_without_fide_id_skipped(self):
        player_no_fide = Player.objects.create(
            lichess_username="nofide", fide_id=""
        )
        SeasonPlayer.objects.create(
            season=self.season, player=player_no_fide, is_active=True
        )

        self.client.login(username="admin", password="test")
        response = self.client.get(season_url("fide", "broadcast_players"))
        self.assertNotContains(response, "nofide")

    def test_inactive_players_excluded(self):
        _create_fide_player(
            self.season,
            "inactive_player",
            "99999",
            {"name": "Inactive, Player", "standard": 1500},
        )
        SeasonPlayer.objects.filter(
            player__lichess_username="inactive_player"
        ).update(is_active=False)

        self.client.login(username="admin", password="test")
        response = self.client.get(season_url("fide", "broadcast_players"))
        self.assertNotContains(response, "inactive_player")

    def test_missing_title_shows_empty(self):
        self.client.login(username="admin", password="test")
        response = self.client.get(season_url("fide", "broadcast_players"))
        self.assertIn("charlie / 11111 /  / 1900 / Brown, Charlie",
                      response.content.decode())

    def test_empty_season_shows_no_lines(self):
        league = League.objects.create(
            name="Empty FIDE League",
            tag="emptyfide",
            competitor_type="lone",
            rating_type="fide_standard",
            show_fide_names=True,
        )
        Season.objects.create(
            league=league, name="Empty Season", tag="emptyseason", rounds=1
        )

        self.client.login(username="admin", password="test")
        response = self.client.get(
            f"/emptyfide/season/emptyseason/dashboard/broadcast-players/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            '<textarea readonly',
            response.content.decode(),
        )


class BroadcastPlayersDashboardButtonTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.fide_league, cls.fide_season = _create_fide_league()
        cls.staff_user = User.objects.create_superuser(
            "admin", "admin@test.com", "test"
        )

    def test_button_shown_for_fide_league(self):
        self.client.login(username="admin", password="test")
        with Shush():
            response = self.client.get(season_url("fide", "league_dashboard"))
        self.assertContains(response, "Broadcast Players")

    def test_button_hidden_for_non_fide_team_league(self):
        self.client.login(username="admin", password="test")
        with Shush():
            response = self.client.get(season_url("team", "league_dashboard"))
        self.assertNotContains(response, "Broadcast Players")

    def test_button_hidden_for_non_fide_lone_league(self):
        self.client.login(username="admin", password="test")
        with Shush():
            response = self.client.get(season_url("lone", "league_dashboard"))
        self.assertNotContains(response, "Broadcast Players")
