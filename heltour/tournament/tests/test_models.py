from django.test import TestCase
from heltour.tournament.models import *

def createCommonLeagueData():
    team_count = 4
    round_count = 3
    board_count = 2
    
    league = League.objects.create(name='Test League', tag='testleague')
    season = Season.objects.create(league=league, name='Test Season', rounds=round_count, boards=board_count)
    
    player_num = 1
    for n in range(1, team_count + 1):
        team = Team.objects.create(season=season, number=n, name='Team %s' % n)
        for b in range(1, board_count + 1):
            player = Player.objects.create(lichess_username='Player %d' % player_num)
            player_num += 1
            TeamMember.objects.create(team=team, player=player, board_number=b)
    
    for n in range(1, round_count + 1):
        Round.objects.create(season=season, number=n)

class TeamTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
    
    def test_team_boards(self):
        team = Team.objects.get(number=1)
        bd1 = team.teammember_set.get(board_number=1)
        bd2 = team.teammember_set.get(board_number=2)
        
        self.assertItemsEqual([bd1, bd2], team.boards())
        
        bd1.delete()
        self.assertItemsEqual([None, bd2], team.boards())
    
    def test_team_average_rating(self):
        team = Team.objects.get(number=1)
        bd1 = team.teammember_set.get(board_number=1)
        bd2 = team.teammember_set.get(board_number=2)
        
        self.assertEqual(None, team.average_rating())
        
        bd1.player.rating = 1800
        bd1.player.save()
        self.assertEqual(1800, team.average_rating())
        
        bd2.player.rating = 1600
        bd2.player.save()
        self.assertEqual(1700, team.average_rating())
        
        bd1.delete()
        self.assertEqual(1600, team.average_rating())
