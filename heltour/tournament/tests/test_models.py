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
        TeamScore.objects.create(team=team)
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

class TeamScoreTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)
        team3 = Team.objects.get(number=3)
        
        round1 = Round.objects.get(number=1)
        round1.is_completed = True
        round1.save()
        TeamPairing.objects.create(white_team=team1, black_team=team2, round=round1, pairing_order=0, white_points = 3)
        
        round2 = Round.objects.get(number=2)
        round2.is_completed = True
        round2.save()
        TeamPairing.objects.create(white_team=team3, black_team=team1, round=round2, pairing_order=0, black_points = 2)
    
    def test_teamscore_round_scores(self):
        teamscore = TeamScore.objects.get(team__number=1)
        
        self.assertItemsEqual([1.5, 1.0, None], teamscore.round_scores())
    
    def test_teamscore_cross_scores(self):
        teamscore = TeamScore.objects.get(team__number=1)
        pairing1 = TeamPairing.objects.get(round__number=1)
        pairing2 = TeamPairing.objects.get(round__number=2)
        
        self.assertItemsEqual([(1, None, None), (2, 1.5, pairing1.pk), (3, 1.0, pairing2.pk), (4, None, None)], teamscore.cross_scores())
    
    def test_teamscore_cmp(self):
        ts1 = TeamScore.objects.get(team__number=1)
        ts2 = TeamScore.objects.get(team__number=2)
        
        self.assertEqual(0, ts1.__cmp__(ts2))
        
        ts1.match_points = 2
        self.assertGreater(ts1, ts2)
        
        ts2.match_points = 2
        ts2.game_points = 1
        self.assertLess(ts1, ts2)

    