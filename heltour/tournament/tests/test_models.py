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

    def test_season_save_round_creation(self):
        season = Season.objects.create(league=League.objects.all()[0], name='Test 2', rounds=4, boards=6)

        self.assertEqual(4, season.round_set.count())

        season.rounds = 6
        season.save()

        self.assertEqual(6, season.round_set.count())

    def test_season_save_round_date(self):
        season = Season.objects.create(league=League.objects.all()[0], name='Test 2',
                                       start_date=datetime(2016, 7, 1, tzinfo=timezone.get_current_timezone()),
                                       rounds=4, boards=6)

        self.assertEqual(datetime(2016, 7, 22, tzinfo=timezone.get_current_timezone()), season.round_set.order_by('-number')[0].start_date)
        self.assertEqual(datetime(2016, 7, 29, tzinfo=timezone.get_current_timezone()), season.round_set.order_by('-number')[0].end_date)

        season.start_date = datetime(2016, 7, 2, tzinfo=timezone.get_current_timezone())
        season.save()

        self.assertEqual(datetime(2016, 7, 23, tzinfo=timezone.get_current_timezone()), season.round_set.order_by('-number')[0].start_date)
        self.assertEqual(datetime(2016, 7, 30, tzinfo=timezone.get_current_timezone()), season.round_set.order_by('-number')[0].end_date)

    def test_season_end_date(self):
        season = Season.objects.create(league=League.objects.all()[0], name='Test 2',
                                       start_date=datetime(2016, 7, 1, tzinfo=timezone.get_current_timezone()),
                                       rounds=4, boards=6)

        self.assertEqual(datetime(2016, 7, 29, tzinfo=timezone.get_current_timezone()), season.end_date())

    def test_season_board_number_list(self):
        season = Season.objects.create(league=League.objects.all()[0], name='Test 2', rounds=2, boards=4)

        self.assertItemsEqual([1, 2, 3, 4], season.board_number_list())

    def test_season_calculate_scores(self):
        rounds = list(Round.objects.order_by('number'))
        teams = list(Team.objects.order_by('number'))

        def score_matrix():
            scores = list(TeamScore.objects.order_by('team__number'))
            return [(s.match_count, s.match_points, s.game_points) for s in scores]

        self.assertItemsEqual([(0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0)], score_matrix())

        TeamPairing.objects.create(round=rounds[0], pairing_order=0, white_team=teams[0], black_team=teams[1], white_points=4, black_points=2)
        TeamPairing.objects.create(round=rounds[0], pairing_order=0, white_team=teams[2], black_team=teams[3], white_points=3, black_points=3)
        self.assertItemsEqual([(0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0)], score_matrix())

        rounds[0].is_completed = True
        rounds[0].save()
        self.assertItemsEqual([(1, 2, 4), (1, 0, 2), (1, 1, 3), (1, 1, 3)], score_matrix())

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
        TeamPairing.objects.create(white_team=team1, black_team=team2, round=round1, pairing_order=0, white_points=3)

        round2 = Round.objects.get(number=2)
        round2.is_completed = True
        round2.save()
        TeamPairing.objects.create(white_team=team3, black_team=team1, round=round2, pairing_order=0, black_points=2)

    def test_teamscore_round_scores(self):
        teamscore = TeamScore.objects.get(team__number=1)

        self.assertItemsEqual([1.5, 1.0, None], teamscore.round_scores())

    def test_teamscore_cross_scores(self):
        teamscore = TeamScore.objects.get(team__number=1)
        pairing1 = TeamPairing.objects.get(round__number=1)
        pairing2 = TeamPairing.objects.get(round__number=2)

        self.assertItemsEqual([(1, None, None), (2, 1.5, pairing1.pk), (3, 1.0, pairing2.pk), (4, None, None)], teamscore.cross_scores())

    def test_teamscore_cmp(self):
        ts1 = TeamScore()
        ts2 = TeamScore()

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

        self.assertEqual(3, tp.white_points)
        self.assertEqual(1, tp.black_points)

        pp1.result = '0-1'
        pp1.save()
        pp2.result = '0-1'
        pp2.save()

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

class RegistrationTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def create_reg(self, season, name):
        return Registration.objects.create(season=season, status='pending', lichess_username=name, slack_username=name,
                                           email='a@test.com', classical_rating=1500, peak_classical_rating=1600,
                                           has_played_20_games=True, already_in_slack_group=True, previous_season_alternate='new',
                                           can_commit=True, agreed_to_rules=True, alternate_preference='full_time')

    def test_registration_previous(self):
        season = Season.objects.all()[0]
        reg = self.create_reg(season, 'testuser')

        self.assertItemsEqual([], reg.previous_registrations())

        reg2 = self.create_reg(season, 'testuser')
        self.assertItemsEqual([], reg.previous_registrations())
        self.assertItemsEqual([reg], reg2.previous_registrations())

    def test_registration_other_seasons(self):
        season = Season.objects.all()[0]
        season2 = Season.objects.create(league=League.objects.all()[0], name='Test 2', rounds=4, boards=6)

        player = Player.objects.create(lichess_username='testuser')
        sp = SeasonPlayer.objects.create(season=season, player=player)
        reg = self.create_reg(season2, 'testuser')

        self.assertItemsEqual([sp], reg.other_seasons())

class AlternateTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_alternate_update_board_number(self):
        season = Season.objects.all()[0]
        season.boards = 3
        season.save()

        player = Player.objects.all()[0]
        sp = SeasonPlayer.objects.create(season=season, player=player)
        alt = Alternate.objects.create(season_player=sp, board_number=2)

        alt.update_board_number()
        self.assertEqual(2, alt.board_number)

        AlternateBucket.objects.create(season=season, board_number=1, max_rating=None, min_rating=2000)
        AlternateBucket.objects.create(season=season, board_number=2, max_rating=2000, min_rating=1800)
        AlternateBucket.objects.create(season=season, board_number=3, max_rating=1800, min_rating=None)

        player.rating = None
        alt.update_board_number()
        self.assertEqual(2, alt.board_number)

        player.rating = 2100
        alt.update_board_number()
        self.assertEqual(1, alt.board_number)

        player.rating = 1900
        alt.update_board_number()
        self.assertEqual(2, alt.board_number)

        player.rating = 1800
        alt.update_board_number()
        self.assertEqual(3, alt.board_number)

        player.rating = 1700
        alt.update_board_number()
        self.assertEqual(3, alt.board_number)

class AlternateAssignmentTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_alternateassignment_save(self):
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)

        tp = TeamPairing.objects.create(white_team=team1, black_team=team2, round=Round.objects.all()[0], pairing_order=0)

        pp1 = PlayerPairing.objects.create(white=team1.teammember_set.all()[0].player, black=team2.teammember_set.all()[0].player)
        TeamPlayerPairing.objects.create(player_pairing=pp1, team_pairing=tp, board_number=1)

        self.assertEqual('Player 1', pp1.white.lichess_username)

        AlternateAssignment.objects.create(round=tp.round, team=team1, board_number=1, player=Player.objects.create(lichess_username='Test User'))
        pp1.refresh_from_db()
        self.assertEqual('Test User', pp1.white.lichess_username)
