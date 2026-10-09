from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User
from django.http.response import Http404
from unittest.mock import patch
from heltour.tournament.models import (
    League,
    Player,
    Registration,
    Round,
    Season,
    Team,
    TeamPairing,
    TeamPlayerPairing,
    LonePlayerPairing,
)
from heltour.tournament.tests.testutils import (
    createCommonLeagueData,
    create_reg,
    get_league,
    get_season,
    league_tag,
    league_url,
    reverse,
    season_tag,
    season_url,
    Shush,
)
from heltour.tournament.views import _get_league, _get_season


class HelperWoLeagueTestCase(TestCase):
    def test_get_league(self):
        self.assertRaises(Http404, lambda: _get_league(None, False))
        self.assertEqual(_get_league(None, True), None)
        League.objects.create(
            name="c960 League",
            tag="960league",
            competitor_type="lone",
            rating_type="chess960",
        )
        self.assertRaises(
            Http404,
            lambda: _get_season(
                season_tag=None, league_tag="960league", allow_none=False
            ),
        )


class DarkModeTestCase(TestCase):
    def test_suspicious_redirect(self):
        with Shush():
            response = self.client.get(
                "/toggle/darkmode/?redirect_url=test", follow=True
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [("/", 302)])


class TemplatesRedirectTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()

    def test_helper_get_league(self):
        self.assertEqual(_get_league(None), get_league("team"))

    def test_home_template(self):
        response = self.client.get(reverse("home"))
        self.assertTemplateUsed(response, "tournament/home.html")

    def test_league_home_template(self):
        response = self.client.get(league_url("team", "league_home"))
        self.assertTemplateUsed(response, "tournament/team_league_home.html")

        response = self.client.get(league_url("lone", "league_home"))
        self.assertTemplateUsed(response, "tournament/lone_league_home.html")

    def test_season_landing_template(self):
        response = self.client.get(season_url("team", "season_landing"))
        self.assertTemplateUsed(response, "tournament/team_season_landing.html")

        response = self.client.get(season_url("lone", "season_landing"))
        self.assertTemplateUsed(response, "tournament/lone_season_landing.html")

        for s in Season.objects.all():
            s.is_completed = True
            s.save()

        response = self.client.get(season_url("team", "season_landing"))
        self.assertTemplateUsed(
            response, "tournament/team_completed_season_landing.html"
        )

        response = self.client.get(season_url("lone", "season_landing"))
        self.assertTemplateUsed(
            response, "tournament/lone_completed_season_landing.html"
        )

    def test_rosters_template(self):
        response = self.client.get(season_url("team", "rosters"))
        self.assertTemplateUsed(response, "tournament/team_rosters.html")

        # triggering a 404 writes to the log, disable that temporarily for nicer test output
        with Shush():
            response = self.client.get(season_url("lone", "rosters"))
        self.assertEqual(404, response.status_code)

    def test_standings_template(self):
        response = self.client.get(season_url("team", "standings"))
        self.assertTemplateUsed(response, "tournament/team_standings.html")

        response = self.client.get(season_url("lone", "standings"))
        self.assertTemplateUsed(response, "tournament/lone_standings.html")

    def test_crosstable_template(self):
        response = self.client.get(season_url("team", "crosstable"))
        self.assertTemplateUsed(response, "tournament/team_crosstable.html")
        # triggering a 404 writes to the log, disable that temporarily for nicer test output
        with Shush():
            response = self.client.get(season_url("lone", "crosstable"))
        self.assertEqual(404, response.status_code)

    def test_wallchart_template(self):
        # triggering a 404 writes to the log, disable that temporarily for nicer test output
        with Shush():
            response = self.client.get(season_url("team", "wallchart"))
        self.assertEqual(404, response.status_code)

        response = self.client.get(season_url("lone", "wallchart"))
        self.assertTemplateUsed(response, "tournament/lone_wallchart.html")

    def test_pairings_template(self):
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)
        Round.objects.filter(season__league__name="Team League", number=1).update(
            publish_pairings=True, start_date=timezone.now()
        )
        rd = Round.objects.get(season__league__name="Team League", number=1)
        tp = TeamPairing.objects.create(
            white_team=team1, black_team=team2, round=rd, pairing_order=0
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp,
            board_number=1,
            white=team1.teammember_set.get(board_number=1).player,
            black=team2.teammember_set.get(board_number=1).player,
            white_confirmed=False,
            black_confirmed=False,
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp,
            board_number=2,
            white=team2.teammember_set.get(board_number=2).player,
            black=team1.teammember_set.get(board_number=2).player,
            white_confirmed=False,
            black_confirmed=False,
        )
        response = self.client.get(season_url("team", "pairings"))
        self.assertTemplateUsed(response, "tournament/team_pairings.html")
        self.assertNotContains(response, "icon-confirmed")

        response = self.client.get(season_url("lone", "pairings"))
        self.assertTemplateUsed(response, "tournament/lone_pairings.html")

        TeamPlayerPairing.objects.filter(board_number=1).update(
            white_confirmed=True, black_confirmed=True
        )
        response = self.client.get(season_url("team", "pairings"))
        self.assertContains(response, "icon-confirmed")

    def test_stats_template(self):
        response = self.client.get(season_url("team", "stats"))
        self.assertTemplateUsed(response, "tournament/team_stats.html")

        response = self.client.get(season_url("lone", "stats"))
        self.assertTemplateUsed(response, "tournament/lone_stats.html")


class RegisterTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.user = User.objects.create_user("Player1", password="test")

    def test_require_login(self):
        for page_name in ["register", "registration_success"]:
            with self.subTest(page_name=page_name):
                response = self.client.get(season_url("team", page_name))
                self.assertRedirects(
                    response,
                    league_url("team", "login"),
                    fetch_redirect_response=False,
                )

    def test_template(self):
        self.client.login(username="Player1", password="test")
        response = self.client.get(season_url("team", "register"))
        self.assertTemplateUsed(response, "tournament/registration_closed.html")

        season = get_season("team")
        season.registration_open = True
        season.save()

        response = self.client.get(season_url("team", "register"))
        self.assertTemplateUsed(response, "tournament/register.html")

        response = self.client.get(season_url("team", "registration_success"))
        self.assertTemplateUsed(response, "tournament/registration_success.html")

    def test_register_text(self):
        self.client.login(username="Player1", password="test")

        for league_type in ["team", "lone"]:
            response = self.client.get(league_url(league_type, "league_home"))
            self.assertNotContains(response, "Register")
            self.assertNotContains(response, "Change Registration")

            season = get_season(league_type)
            season.registration_open = True
            season.save()

            response = self.client.get(league_url(league_type, "league_home"))
            self.assertContains(response, "Register")
            self.assertNotContains(response, "Change Registration")

            with Shush():
                registration = create_reg(season, self.user.username)
                registration.classical_rating = 1600
                registration.save()

            response = self.client.get(league_url(league_type, "league_home"))
            self.assertContains(response, "Change Registration")
            self.assertNotContains(response, "Register")

            self.user.username = self.user.username.lower()
            self.user.save()
            response = self.client.get(league_url(league_type, "league_home"))
            self.assertContains(response, "Change Registration")
            self.assertNotContains(response, "Register")

            registration.status = "rejected"
            registration.save()

            response = self.client.get(league_url(league_type, "league_home"))
            self.assertNotContains(response, "Register")
            self.assertNotContains(response, "Change Registration")

    def test_register_post(self):
        self.client.login(username="Player1", password="test")
        Season.objects.filter(league__name="Team League", name="Test Season").update(
            registration_open=True,
            start_date=timezone.now() + timedelta(hours=1),
            round_duration=timedelta(hours=1),
        )
        season = get_season("team")
        Round.objects.filter(season=season).update(
            start_date=timezone.now() + timedelta(hours=1)
        )
        # invalid form
        response = self.client.post(
            season_url("team", "register"),
            data={
                "email": "player1@example.com",
                "has_played_20_games": False,
                "can_commit": True,
                "agreed_to_rules": True,
                "agreed_to_tos": True,
                "weeks_unavailable": "",
                "friends": "",
                "avoid": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Registration.objects.filter(player__lichess_username="Player1").count(), 0
        )
        with Shush():
            response = self.client.post(
                league_url("team", "register"),
                data={
                    "email": "player1@example.com",
                    "has_played_20_games": False,
                    "can_commit": True,
                    "agreed_to_rules": True,
                    "agreed_to_tos": True,
                    "weeks_unavailable": "",
                    "friends": "",
                    "avoid": "",
                    "alternate_preference": "full_time",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Registration.objects.filter(player__lichess_username="Player1").first().email,
            "player1@example.com",
        )

    def _open_registration(self, league_type):
        season = get_season(league_type)
        season.registration_open = True
        season.start_date = timezone.now() + timedelta(days=14)
        season.round_duration = timedelta(days=7)
        season.save()
        for round_number, round_ in enumerate(
                season.round_set.order_by("number"), start=1):
            round_.start_date = timezone.now() + timedelta(days=round_number)
            round_.end_date = round_.start_date + timedelta(days=7)
            round_.save()
        return season

    def _registration_data(self, league_type, alternate_preference="full_time"):
        data = {
            "email": "player1@example.com",
            "has_played_20_games": True,
            "can_commit": True,
            "agreed_to_rules": True,
            "agreed_to_tos": True,
            "weeks_unavailable": ["2"],
        }
        if league_type == "team":
            data.update({
                "friends": "Player2",
                "avoid": "Player3",
                "alternate_preference": alternate_preference,
            })
        return data

    def test_registration_success_summary_and_update_highlights(self):
        self.client.login(username="Player1", password="test")
        self._open_registration("team")

        with Shush():
            response = self.client.post(
                season_url("team", "register"),
                self._registration_data("team"),
                follow=True,
            )
        self.assertContains(response, "Successfully registered.")
        summary = {
            row["field"]: row for row in response.context["registration_summary"]
        }
        self.assertEqual(summary["status"]["value"], "Pending")
        self.assertEqual(summary["alternate_preference"]["value"], "Full Time")
        self.assertEqual(summary["friends"]["value"], "Player2")
        self.assertIn("Round 2", summary["weeks_unavailable"]["value"])
        self.assertFalse(any(row["changed"] for row in summary.values()))

        with Shush():
            response = self.client.post(
                season_url("team", "register"),
                self._registration_data("team", alternate_preference="alternate"),
                follow=True,
            )
        self.assertContains(response, "Your registration was successfully updated.")
        summary = {
            row["field"]: row for row in response.context["registration_summary"]
        }
        self.assertEqual(summary["alternate_preference"]["value"], "Alternate")
        self.assertTrue(summary["alternate_preference"]["changed"])
        self.assertFalse(summary["weeks_unavailable"]["changed"])
        self.assertContains(
            response,
            'data-registration-field="alternate_preference" class="success"',
        )
        self.assertEqual(response.content.decode().count(">Changed</span>"), 1)

        response = self.client.get(season_url("team", "registration_success"))
        self.assertContains(response, "Your current registration details are shown below.")
        self.assertNotContains(response, ">Changed</span>")

    def test_lone_and_chess960_summaries_omit_team_options(self):
        User.objects.create_user("NewPlayer", password="test")
        self.client.login(username="NewPlayer", password="test")
        League.objects.create(
            name="c960 League",
            tag=league_tag("960"),
            competitor_type="lone",
            rating_type="chess960",
        )
        Season.objects.create(
            league=League.objects.get(tag=league_tag("960")),
            name="Season960",
            tag=season_tag("960"),
            rounds=3,
        )

        for league_type in ["lone", "960"]:
            with self.subTest(league_type=league_type):
                self._open_registration(league_type)
                with Shush():
                    response = self.client.post(
                        season_url(league_type, "register"),
                        self._registration_data(league_type),
                        follow=True,
                    )
                summary_fields = {
                    row["field"] for row in response.context["registration_summary"]
                }
                self.assertIn("email", summary_fields)
                self.assertIn("weeks_unavailable", summary_fields)
                self.assertNotIn("alternate_preference", summary_fields)
                self.assertNotIn("friends", summary_fields)
                self.assertNotIn("avoid", summary_fields)
                self.assertNotContains(response, "Player preference")

    def test_registration_success_only_shows_the_logged_in_players_data(self):
        self.client.login(username="Player1", password="test")
        season = self._open_registration("team")
        create_reg(season, "Player1")
        registration = Registration.objects.get(
            season=season, player__lichess_username="Player1"
        )
        registration.email = "player1@example.com"
        registration.save()
        other_registration = create_reg(season, "Player2")
        other_registration.email = "player2-private@example.com"
        other_registration.save()

        response = self.client.get(season_url("team", "registration_success"))

        self.assertContains(response, "player1@example.com")
        self.assertNotContains(response, "player2-private@example.com")


@patch("heltour.tournament.lichessapi.watch_games", return_value=None)
class TvTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        Round.objects.filter(season__league__name="Lone League", number=1).update(
            publish_pairings=True, start_date=timezone.now()
        )
        rd = Round.objects.get(season__league__name="Lone League", number=1)
        cls.player1 = Player.objects.get(lichess_username="Player1")
        cls.player2 = Player.objects.get(lichess_username="Player2")
        LonePlayerPairing.objects.create(
            round=rd,
            white=cls.player1,
            black=cls.player2,
            game_link="https://lichess.org/KT837Aut",
            scheduled_time=timezone.now(),
            pairing_order=1,
            tv_state="has_moves",
        )

    def test_tv(self, *args):
        response = self.client.get(season_url("lone", "tv"))
        self.assertContains(response, "KT837Aut")
        self.assertContains(response, "Player1")
        self.assertNotContains(response, "Player3")
        LonePlayerPairing.objects.filter(
            white__lichess_username="Player1",
            black__lichess_username="Player2",
            game_link="https://lichess.org/KT837Aut",
        ).update(tv_state="default")
        response = self.client.get(season_url("lone", "tv"))
        self.assertContains(response, "KT837Aut")
        self.assertContains(response, "Player1")
        self.assertNotContains(response, "Player3")
        LonePlayerPairing.objects.filter(
            white__lichess_username="Player1",
            black__lichess_username="Player2",
            game_link="https://lichess.org/KT837Aut",
        ).update(tv_state="hide")
        response = self.client.get(season_url("lone", "tv"))
        self.assertNotContains(response, "KT837Aut")
        self.assertNotContains(response, "Player1")
        self.assertNotContains(response, "Player3")

    def test_non_classical_tv(self, *args):
        l960 = League.objects.create(
            name="c960 League",
            tag=league_tag("960"),
            competitor_type="lone",
            rating_type="chess960",
        )
        s960 = Season.objects.create(
            league=l960,
            name="Season960",
            tag=season_tag("960"),
            rounds=1,
            is_active=True,
            is_completed=False,
        )
        r960 = Round.objects.get(season=s960)
        #        sp1 = SeasonPlayer.objects.create(season=s960, player=self.player1)
        #        sp2 = SeasonPlayer.objects.create(season=s960, player=self.player2)
        Player.objects.filter(pk=self.player1.pk).update(
            rating=1911,
            profile={
                "id": "Player1",
                "perfs": {
                    "chess960": {"games": 12, "rating": 1621},
                    "classical": {"games": 10, "rating": 1911},
                },
            },
        )
        Player.objects.filter(pk=self.player2.pk).update(
            rating=1833,
            profile={
                "id": "Player2",
                "perfs": {
                    "chess960": {"games": 12, "rating": 1684},
                    "classical": {"games": 10, "rating": 1833},
                },
            },
        )
        LonePlayerPairing.objects.create(
            round=r960,
            white=self.player1,
            black=self.player2,
            game_link="https://lichess.org/KT837Aut",
            tv_state="has_moves",
            pairing_order=1,
        )
        response = self.client.get(season_url("960", "tv"))
        self.assertNotContains(response, '"white": "Player1 (1911)"')
        self.assertNotContains(response, '"black": "Player2 (1833)"')
        self.assertNotContains(response, '"white_rating": 1911')
        self.assertNotContains(response, '"black_rating": 1833')
        self.assertContains(response, '"white_rating": 1621')
        self.assertContains(response, '"black_rating": 1684')
