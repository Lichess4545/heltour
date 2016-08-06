from django.test import TestCase
from heltour.tournament.models import *
from django.core.urlresolvers import reverse

# For now we just have sanity checks for the templates used
# This could be enhanced by verifying the context data

def createCommonLeagueData():
    team_count = 4
    round_count = 3
    board_count = 2
    
    league = League.objects.create(name='Test League', tag='testleague')
    season = Season.objects.create(league=league, name='Test Season', rounds=round_count, boards=board_count)
    
    player_num = 1
    for n in range(1, team_count + 1):
        team = Team.objects.create(season=season, number=n, name='Team %s' % n)
        TeamScore.objects.create(team=team)
        for b in range(1, board_count + 1):
            player = Player.objects.create(lichess_username='Player %d' % player_num)
            player_num += 1
            TeamMember.objects.create(team=team, player=player, board_number=b)

class LeagueHomeTestCase(TestCase):
    def setUp(self):
        pass
    
    def test_template(self):
        response = self.client.get(reverse('league_home'))
        self.assertTemplateUsed(response, 'tournament/no_leagues.html')
        
        createCommonLeagueData()
        response = self.client.get(reverse('league_home'))
        self.assertTemplateUsed(response, 'tournament/league_home.html')
 
class SeasonLandingTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
     
    def test_template(self):
        response = self.client.get(reverse('season_landing'))
        self.assertTemplateUsed(response, 'tournament/season_landing.html')
 
class FaqTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
     
    def test_template(self):
        response = self.client.get(reverse('faq'))
        self.assertTemplateUsed(response, 'tournament/document.html')
 
class RostersTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
     
    def test_template(self):
        response = self.client.get(reverse('rosters'))
        self.assertTemplateUsed(response, 'tournament/rosters.html')
 
class StandingsTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
     
    def test_template(self):
        response = self.client.get(reverse('standings'))
        self.assertTemplateUsed(response, 'tournament/standings.html')
 
class CrosstableTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
     
    def test_template(self):
        response = self.client.get(reverse('crosstable'))
        self.assertTemplateUsed(response, 'tournament/crosstable.html')
 
class PairingsTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
     
    def test_template(self):
        response = self.client.get(reverse('pairings'))
        self.assertTemplateUsed(response, 'tournament/pairings.html')
 
class StatsTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
     
    def test_template(self):
        response = self.client.get(reverse('stats'))
        self.assertTemplateUsed(response, 'tournament/stats.html')
         
class RegisterTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
     
    def test_template(self):
        response = self.client.get(reverse('register'))
        self.assertTemplateUsed(response, 'tournament/registration_closed.html')
         
        season = Season.objects.all()[0]
        season.registration_open = True
        season.save()
         
        response = self.client.get(reverse('register'))
        self.assertTemplateUsed(response, 'tournament/register.html')
         
        response = self.client.get(reverse('registration_success'))
        self.assertTemplateUsed(response, 'tournament/registration_success.html')
