from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User
from heltour.tournament.models import Round, Season, Team, TeamPairing, TeamPlayerPairing
from heltour.tournament.tests.testutils import (createCommonLeagueData, create_reg, get_season,
                                                league_url, reverse, season_tag, season_url)


# For now we just have sanity checks for the templates used
# This could be enhanced by verifying the context data


class HomeTestCase(TestCase):
    def setUp(self):
        pass

    def test_template(self):
        response = self.client.get(reverse('home'))
        self.assertTemplateUsed(response, 'tournament/home.html')


class LeagueHomeTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(league_url('team', 'league_home'))
        self.assertTemplateUsed(response, 'tournament/team_league_home.html')

        response = self.client.get(league_url('lone', 'league_home'))
        self.assertTemplateUsed(response, 'tournament/lone_league_home.html')


class SeasonLandingTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(season_url('team', 'season_landing'))
        self.assertTemplateUsed(response, 'tournament/team_season_landing.html')

        response = self.client.get(season_url('lone', 'season_landing'))
        self.assertTemplateUsed(response, 'tournament/lone_season_landing.html')

        for s in Season.objects.all():
            s.is_completed = True
            s.save()

        response = self.client.get(season_url('team', 'season_landing'))
        self.assertTemplateUsed(response, 'tournament/team_completed_season_landing.html')

        response = self.client.get(season_url('lone', 'season_landing'))
        self.assertTemplateUsed(response, 'tournament/lone_completed_season_landing.html')


class RostersTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(season_url('team', 'rosters'))
        self.assertTemplateUsed(response, 'tournament/team_rosters.html')

        response = self.client.get(season_url('lone', 'rosters'))
        self.assertEqual(404, response.status_code)


class StandingsTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(season_url('team', 'standings'))
        self.assertTemplateUsed(response, 'tournament/team_standings.html')

        response = self.client.get(season_url('lone', 'standings'))
        self.assertTemplateUsed(response, 'tournament/lone_standings.html')


class CrosstableTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(season_url('team', 'crosstable'))
        self.assertTemplateUsed(response, 'tournament/team_crosstable.html')

        response = self.client.get(season_url('lone', 'crosstable'))
        self.assertEqual(404, response.status_code)


class WallchartTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(season_url('team', 'wallchart'))
        self.assertEqual(404, response.status_code)

        response = self.client.get(season_url('lone', 'wallchart'))
        self.assertTemplateUsed(response, 'tournament/lone_wallchart.html')


class PairingsTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)
        Round.objects.filter(season__league__name="Team League", number=1).update(publish_pairings=True, start_date=timezone.now())
        rd = Round.objects.get(season__league__name="Team League", number=1)
        tp = TeamPairing.objects.create(white_team=team1, black_team=team2,
                                        round=rd, pairing_order=0)
        TeamPlayerPairing.objects.create(
                team_pairing=tp, board_number=1,
                white=team1.teammember_set.get(board_number=1).player,
                black=team2.teammember_set.get(board_number=1).player,
                white_confirmed = False,
                black_confirmed = False
                )
        TeamPlayerPairing.objects.create(
                team_pairing=tp, board_number=2,
                white=team2.teammember_set.get(board_number=2).player,
                black=team1.teammember_set.get(board_number=2).player,
                white_confirmed = False,
                black_confirmed = False
                )

    def test_template(self):
        response = self.client.get(season_url('team', 'pairings'))
        self.assertTemplateUsed(response, 'tournament/team_pairings.html')
        self.assertNotContains(response, 'icon-confirmed')

        response = self.client.get(season_url('lone', 'pairings'))
        self.assertTemplateUsed(response, 'tournament/lone_pairings.html')

        pp1 = TeamPlayerPairing.objects.filter(board_number=1).update(white_confirmed=True, black_confirmed=True)
        response = self.client.get(season_url('team', 'pairings'))
        self.assertContains(response, 'icon-confirmed')


class StatsTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(season_url('team', 'stats'))
        self.assertTemplateUsed(response, 'tournament/team_stats.html')

        response = self.client.get(season_url('lone', 'stats'))
        self.assertTemplateUsed(response, 'tournament/lone_stats.html')


class RegisterTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
        User.objects.create_user('Player1', password='test')

    def test_require_login(self):
        response = self.client.get(season_url('team', 'register'))
        self.assertRedirects(response, league_url('team', 'login'), fetch_redirect_response=False)

    def test_template(self):
        self.client.login(username='Player1', password='test')
        response = self.client.get(season_url('team', 'register'))
        self.assertTemplateUsed(response, 'tournament/registration_closed.html')

        season = get_season('team')
        season.registration_open = True
        season.save()

        response = self.client.get(season_url('team', 'register'))
        self.assertTemplateUsed(response, 'tournament/register.html')

        response = self.client.get(season_url('team', 'registration_success'))
        self.assertTemplateUsed(response, 'tournament/registration_success.html')

    def test_register_text(self):
        user = User.objects.first()
        self.client.login(username='Player1', password='test')

        for league_type in ['team', 'lone']:
            response = self.client.get(league_url(league_type, 'league_home'))
            self.assertNotContains(response, 'Register')
            self.assertNotContains(response, 'Change Registration')

            season = get_season(league_type)
            season.registration_open = True
            season.save()

            response = self.client.get(league_url(league_type, 'league_home'))
            self.assertContains(response, 'Register')
            self.assertNotContains(response, 'Change Registration')

            registration = create_reg(season, user.username)
            registration.classical_rating = 1600
            registration.save()

            response = self.client.get(league_url(league_type, 'league_home'))
            self.assertContains(response, 'Change Registration')
            self.assertNotContains(response, 'Register')

            user.username = user.username.lower()
            user.save()
            response = self.client.get(league_url(league_type, 'league_home'))
            self.assertContains(response, 'Change Registration')
            self.assertNotContains(response, 'Register')

            registration.status = 'rejected'
            registration.save()

            response = self.client.get(league_url(league_type, 'league_home'))
            self.assertNotContains(response, 'Register')
            self.assertNotContains(response, 'Change Registration')
