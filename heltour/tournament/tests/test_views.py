from django.test import TestCase
from heltour.tournament.models import *
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from .test_models import create_reg


# For now we just have sanity checks for the templates used
# This could be enhanced by verifying the context data

def createCommonLeagueData():
    team_count = 4
    round_count = 3
    board_count = 2

    league = League.objects.create(name='Team League', tag='team', competitor_type='team')
    season = Season.objects.create(league=league, name='Team Season', tag='team',
                                   rounds=round_count, boards=board_count)
    league2 = League.objects.create(name='Lone League', tag='lone')
    season2 = Season.objects.create(league=league2, name='Lone Season', tag='lone',
                                    rounds=round_count, boards=board_count)

    player_num = 1
    for n in range(1, team_count + 1):
        team = Team.objects.create(season=season, number=n, name='Team %s' % n)
        TeamScore.objects.create(team=team)
        for b in range(1, board_count + 1):
            player = Player.objects.create(lichess_username='Player%d' % player_num)
            player_num += 1
            TeamMember.objects.create(team=team, player=player, board_number=b)


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
        response = self.client.get(reverse('by_league:league_home', args=['team']))
        self.assertTemplateUsed(response, 'tournament/team_league_home.html')

        response = self.client.get(reverse('by_league:league_home', args=['lone']))
        self.assertTemplateUsed(response, 'tournament/lone_league_home.html')


class SeasonLandingTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(
            reverse('by_league:by_season:season_landing', args=['team', 'team']))
        self.assertTemplateUsed(response, 'tournament/team_season_landing.html')

        response = self.client.get(
            reverse('by_league:by_season:season_landing', args=['lone', 'lone']))
        self.assertTemplateUsed(response, 'tournament/lone_season_landing.html')

        for s in Season.objects.all():
            s.is_completed = True
            s.save()

        response = self.client.get(
            reverse('by_league:by_season:season_landing', args=['team', 'team']))
        self.assertTemplateUsed(response, 'tournament/team_completed_season_landing.html')

        response = self.client.get(
            reverse('by_league:by_season:season_landing', args=['lone', 'lone']))
        self.assertTemplateUsed(response, 'tournament/lone_completed_season_landing.html')


class RostersTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:by_season:rosters', args=['team', 'team']))
        self.assertTemplateUsed(response, 'tournament/team_rosters.html')

        response = self.client.get(reverse('by_league:by_season:rosters', args=['lone', 'lone']))
        self.assertEqual(404, response.status_code)


class StandingsTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:by_season:standings', args=['team', 'team']))
        self.assertTemplateUsed(response, 'tournament/team_standings.html')

        response = self.client.get(reverse('by_league:by_season:standings', args=['lone', 'lone']))
        self.assertTemplateUsed(response, 'tournament/lone_standings.html')


class CrosstableTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:by_season:crosstable', args=['team', 'team']))
        self.assertTemplateUsed(response, 'tournament/team_crosstable.html')

        response = self.client.get(reverse('by_league:by_season:crosstable', args=['lone', 'lone']))
        self.assertEqual(404, response.status_code)


class WallchartTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:by_season:wallchart', args=['team', 'team']))
        self.assertEqual(404, response.status_code)

        response = self.client.get(reverse('by_league:by_season:wallchart', args=['lone', 'lone']))
        self.assertTemplateUsed(response, 'tournament/lone_wallchart.html')


class PairingsTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:by_season:pairings', args=['team', 'team']))
        self.assertTemplateUsed(response, 'tournament/team_pairings.html')

        response = self.client.get(reverse('by_league:by_season:pairings', args=['lone', 'lone']))
        self.assertTemplateUsed(response, 'tournament/lone_pairings.html')


class StatsTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:by_season:stats', args=['team', 'team']))
        self.assertTemplateUsed(response, 'tournament/team_stats.html')

        response = self.client.get(reverse('by_league:by_season:stats', args=['lone', 'lone']))
        self.assertTemplateUsed(response, 'tournament/lone_stats.html')


class RegisterTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
        User.objects.create_user('Player1', password='test')

    def test_require_login(self):
        response = self.client.get(reverse('by_league:by_season:register', args=['team', 'team']))
        self.assertRedirects(response, reverse('by_league:login', args=['team']),
                             fetch_redirect_response=False)

    def test_template(self):
        self.client.login(username='Player1', password='test')
        response = self.client.get(reverse('by_league:by_season:register', args=['team', 'team']))
        self.assertTemplateUsed(response, 'tournament/registration_closed.html')

        season = Season.objects.get(tag='team')
        season.registration_open = True
        season.save()

        response = self.client.get(reverse('by_league:by_season:register', args=['team', 'team']))
        self.assertTemplateUsed(response, 'tournament/register.html')

        response = self.client.get(
            reverse('by_league:by_season:registration_success', args=['team', 'team']))
        self.assertTemplateUsed(response, 'tournament/registration_success.html')

    def test_register_text(self):
        user = User.objects.first()
        self.client.login(username='Player1', password='test')

        for league in ['team', 'lone']:
            response = self.client.get(reverse('by_league:league_home', args=[league]))
            self.assertNotContains(response, 'Register')
            self.assertNotContains(response, 'Change Registration')

            season = Season.objects.get(tag=league)
            season.registration_open = True
            season.save()

            response = self.client.get(reverse('by_league:league_home', args=[league]))
            self.assertContains(response, 'Register')
            self.assertNotContains(response, 'Change Registration')

            registration = create_reg(season, user.username)
            registration.classical_rating = 1600
            registration.save()

            response = self.client.get(reverse('by_league:league_home', args=[league]))
            self.assertContains(response, 'Change Registration')
            self.assertNotContains(response, 'Register')

            user.username = user.username.lower()
            user.save()
            response = self.client.get(reverse('by_league:league_home', args=[league]))
            self.assertContains(response, 'Change Registration')
            self.assertNotContains(response, 'Register')

            registration.status = 'rejected'
            registration.save()

            response = self.client.get(reverse('by_league:league_home', args=[league]))
            self.assertNotContains(response, 'Register')
            self.assertNotContains(response, 'Change Registration')
