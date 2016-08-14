from django.test import TestCase
from heltour.tournament.models import *
from django.core.urlresolvers import reverse

# For now we just have sanity checks for the templates used
# This could be enhanced by verifying the context data

def createCommonLeagueData():
    team_count = 4
    round_count = 3
    board_count = 2

    league = League.objects.create(name='Team League', tag='team', competitor_type='team')
    season = Season.objects.create(league=league, name='Team Season', rounds=round_count, boards=board_count)
    league2 = League.objects.create(name='Lone League', tag='lone')
    season2 = Season.objects.create(league=league2, name='Lone Season', rounds=round_count, boards=board_count)

    player_num = 1
    for n in range(1, team_count + 1):
        team = Team.objects.create(season=season, number=n, name='Team %s' % n)
        TeamScore.objects.create(team=team)
        for b in range(1, board_count + 1):
            player = Player.objects.create(lichess_username='Player %d' % player_num)
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
        response = self.client.get(reverse('by_league:season_landing', args=['team']))
        self.assertTemplateUsed(response, 'tournament/team_season_landing.html')

        response = self.client.get(reverse('by_league:season_landing', args=['lone']))
        self.assertTemplateUsed(response, 'tournament/lone_season_landing.html')

        for s in Season.objects.all():
            s.is_completed = True
            s.save()

        response = self.client.get(reverse('by_league:season_landing', args=['team']))
        self.assertTemplateUsed(response, 'tournament/team_completed_season_landing.html')

        response = self.client.get(reverse('by_league:season_landing', args=['lone']))
        self.assertTemplateUsed(response, 'tournament/lone_completed_season_landing.html')

class FaqTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:faq', args=['team']))
        self.assertTemplateUsed(response, 'tournament/document.html')

        response = self.client.get(reverse('by_league:faq', args=['lone']))
        self.assertTemplateUsed(response, 'tournament/document.html')

class RostersTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:rosters', args=['team']))
        self.assertTemplateUsed(response, 'tournament/team_rosters.html')

        response = self.client.get(reverse('by_league:rosters', args=['lone']))
        self.assertEqual(404, response.status_code)

class StandingsTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:standings', args=['team']))
        self.assertTemplateUsed(response, 'tournament/team_standings.html')

        response = self.client.get(reverse('by_league:standings', args=['lone']))
        self.assertTemplateUsed(response, 'tournament/lone_standings.html')

class CrosstableTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:crosstable', args=['team']))
        self.assertTemplateUsed(response, 'tournament/team_crosstable.html')

        response = self.client.get(reverse('by_league:crosstable', args=['lone']))
        self.assertEqual(404, response.status_code)

class WallchartTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:wallchart', args=['team']))
        self.assertEqual(404, response.status_code)

        response = self.client.get(reverse('by_league:wallchart', args=['lone']))
        self.assertTemplateUsed(response, 'tournament/lone_wallchart.html')

class PairingsTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:pairings', args=['team']))
        self.assertTemplateUsed(response, 'tournament/team_pairings.html')

        response = self.client.get(reverse('by_league:pairings', args=['lone']))
        self.assertTemplateUsed(response, 'tournament/lone_pairings.html')

class StatsTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:stats', args=['team']))
        self.assertTemplateUsed(response, 'tournament/team_stats.html')

        response = self.client.get(reverse('by_league:stats', args=['lone']))
        self.assertEqual(404, response.status_code)

class RegisterTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_template(self):
        response = self.client.get(reverse('by_league:register', args=['team']))
        self.assertTemplateUsed(response, 'tournament/registration_closed.html')

        season = Season.objects.all()[0]
        season.registration_open = True
        season.save()

        response = self.client.get(reverse('by_league:register', args=['team']))
        self.assertTemplateUsed(response, 'tournament/register.html')

        response = self.client.get(reverse('by_league:registration_success', args=['team']))
        self.assertTemplateUsed(response, 'tournament/registration_success.html')
