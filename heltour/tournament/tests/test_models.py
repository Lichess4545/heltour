from django.test import TestCase
from heltour.tournament.models import *
from datetime import datetime
from django.utils import timezone

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

class SeasonTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
    
    def test_save_round_creation(self):
        season = Season.objects.create(league=League.objects.all()[0], name='Test 2', rounds=4, boards=6)
        
        self.assertEqual(4, season.round_set.count())
        
        season.rounds = 6
        season.save()
        
        self.assertEqual(6, season.round_set.count())
    
    def test_save_round_date(self):
        season = Season.objects.create(league=League.objects.all()[0], name='Test 2', start_date=datetime(2016, 7, 1, tzinfo=timezone.get_current_timezone()), rounds=4, boards=6)
        
        self.assertEqual(datetime(2016, 7, 22, tzinfo=timezone.get_current_timezone()), season.round_set.order_by('-number')[0].start_date)
        self.assertEqual(datetime(2016, 7, 29, tzinfo=timezone.get_current_timezone()), season.round_set.order_by('-number')[0].end_date)
        
        season.start_date = datetime(2016, 7, 2, tzinfo=timezone.get_current_timezone())
        season.save()
        
        self.assertEqual(datetime(2016, 7, 23, tzinfo=timezone.get_current_timezone()), season.round_set.order_by('-number')[0].start_date)
        self.assertEqual(datetime(2016, 7, 30, tzinfo=timezone.get_current_timezone()), season.round_set.order_by('-number')[0].end_date)
    
    def test_end_date(self):
        season = Season.objects.create(league=League.objects.all()[0], name='Test 2', start_date=datetime(2016, 7, 1, tzinfo=timezone.get_current_timezone()), rounds=4, boards=6)
        
        self.assertEqual(datetime(2016, 7, 29, tzinfo=timezone.get_current_timezone()), season.end_date())
        
    def test_board_number_list(self):
        season = Season.objects.create(league=League.objects.all()[0], name='Test 2', rounds=2, boards=4)
        
        self.assertItemsEqual([1, 2, 3, 4], season.board_number_list())

class TeamTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
    
    def test_team_boards(self):
        team = Team.objects.get(number=1)
        bd1 = team.teammember_set.get(board_number=1)
        bd2 = team.teammember_set.get(board_number=2)
        
        self.assertItemsEqual([(1, bd1), (2, bd2)], team.boards())
        
        bd1.delete()
        self.assertItemsEqual([(1, None), (2, bd2)], team.boards())
    
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
        
        self.assertGreaterEqual(ts1, ts2)
        self.assertLessEqual(ts1, ts2)
        
        ts1.match_points = 2
        self.assertGreater(ts1, ts2)
        
        ts2.match_points = 2
        ts2.game_points = 1
        self.assertLess(ts1, ts2)

class TeamPairingTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
    
    def test_teampairing_refresh_points(self):
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)
        
        tp = TeamPairing.objects.create(white_team=team1, black_team=team2, round=Round.objects.all()[0], pairing_order=0)
        
        pp1 = PlayerPairing.objects.create(white=team1.teammember_set.all()[0].player, black=team2.teammember_set.all()[0].player)
        TeamPlayerPairing.objects.create(player_pairing=pp1, team_pairing=tp, board_number=1)
        
        pp2 = PlayerPairing.objects.create(white=team2.teammember_set.all()[1].player, black=team1.teammember_set.all()[1].player)
        TeamPlayerPairing.objects.create(player_pairing=pp2, team_pairing=tp, board_number=2)
        
        tp.refresh_points()
        self.assertEqual(0, tp.white_points)
        self.assertEqual(0, tp.black_points)
        
        pp1.result = '1-0'
        pp1.save()
        pp2.result = '1/2-1/2'
        pp2.save()
        
        tp.refresh_points()
        self.assertEqual(3, tp.white_points)
        self.assertEqual(1, tp.black_points)
        
        pp1.result = '0-1'
        pp1.save()
        pp2.result = '0-1'
        pp2.save()
        
        tp.refresh_points()
        self.assertEqual(2, tp.white_points)
        self.assertEqual(2, tp.black_points)

class PlayerPairingTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
    
    def test_playerpairing_score(self):
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)
        
        pp = PlayerPairing.objects.create(white=team1.teammember_set.all()[0].player, black=team2.teammember_set.all()[0].player)
        
        self.assertEqual(None, pp.white_score())
        self.assertEqual(None, pp.black_score())
        
        pp.result = '1-0'
        self.assertEqual(1, pp.white_score())
        self.assertEqual(0, pp.black_score())
        
        pp.result = '1/2-1/2'
        self.assertEqual(0.5, pp.white_score())
        self.assertEqual(0.5, pp.black_score())
        
        pp.result = '0-1'
        self.assertEqual(0, pp.white_score())
        self.assertEqual(1, pp.black_score())
