import logging
from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth.models import User
from django.http.response import Http404
from unittest.mock import patch
from heltour.tournament.models import (League, Player, Round, Season, Team,
        TeamPairing, TeamPlayerPairing, LonePlayerPairing)
from heltour.tournament.tests.testutils import (createCommonLeagueData,
        create_reg, get_league, get_season, league_url, reverse, season_tag,
        season_url)
from heltour.tournament.views import _get_league, _get_season


class HelperWoLeagueTestCase(TestCase):
    def test_get_league(self):
        self.assertRaises(Http404, lambda: _get_league(None, False))
        self.assertEqual(_get_league(None, True), None)
        League.objects.create(name='c960 League', tag='960league',
                              competitor_type='lone', rating_type='chess960')
        self.assertRaises(Http404,
                          lambda: _get_season(season_tag=None, league_tag='960league',
                                              allow_none=False))

class HelperTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_get_league(self):
        self.assertEqual(_get_league(None), get_league('team'))


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

        logging.disable(logging.CRITICAL)
        response = self.client.get(season_url('lone', 'rosters'))
        logging.disable(logging.NOTSET)
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

        logging.disable(logging.CRITICAL)
        response = self.client.get(season_url('lone', 'crosstable'))
        logging.disable(logging.NOTSET)
        self.assertEqual(404, response.status_code)


class WallchartTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        logging.disable(logging.CRITICAL)
        response = self.client.get(season_url('team', 'wallchart'))
        logging.disable(logging.NOTSET)
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

@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
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


@patch('heltour.tournament.lichessapi.watch_games',
       return_value=None)
class TvTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
        Round.objects.filter(season__league__name='Lone League', number=1).update(publish_pairings=True, start_date=timezone.now())
        rd = Round.objects.get(season__league__name='Lone League', number=1)
        player1 = Player.objects.get(lichess_username='Player1')
        player2 = Player.objects.get(lichess_username='Player2')
        LonePlayerPairing.objects.create(round=rd, white=player1, black=player2, game_link='https://lichess.org/KT837Aut', scheduled_time=timezone.now(), pairing_order=1, tv_state='has_moves')

    def test_tv(self, *args):
        response = self.client.get(season_url('lone', 'tv'))
        self.assertContains(response, 'KT837Aut')
        self.assertContains(response, 'Player1')
        self.assertNotContains(response, 'Player3')
        LonePlayerPairing.objects.filter(white__lichess_username='Player1', black__lichess_username='Player2', game_link='https://lichess.org/KT837Aut').update(tv_state='default')
        response = self.client.get(season_url('lone', 'tv'))
        self.assertContains(response, 'KT837Aut')
        self.assertContains(response, 'Player1')
        self.assertNotContains(response, 'Player3')
        LonePlayerPairing.objects.filter(white__lichess_username='Player1', black__lichess_username='Player2', game_link='https://lichess.org/KT837Aut').update(tv_state='hide')
        response = self.client.get(season_url('lone', 'tv'))
        self.assertNotContains(response, 'KT837Aut')
        self.assertNotContains(response, 'Player1')
        self.assertNotContains(response, 'Player3')
