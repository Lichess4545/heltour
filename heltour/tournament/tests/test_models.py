from django.test import TestCase
from heltour.tournament.models import *
from datetime import datetime
from django.utils import timezone

def createCommonLeagueData():
    team_count = 4
    round_count = 3
    board_count = 2

    league = League.objects.create(name='Team League', tag='teamleague', competitor_type='team')
    season = Season.objects.create(league=league, name='Test Season', tag='teamseason', rounds=round_count, boards=board_count)
    league2 = League.objects.create(name='Lone League', tag='loneleague', competitor_type='lone')
    season2 = Season.objects.create(league=league2, name='Test Season', tag='loneseason', rounds=round_count)

    player_num = 1
    for n in range(1, team_count + 1):
        team = Team.objects.create(season=season, number=n, name='Team %s' % n)
        TeamScore.objects.create(team=team)
        for b in range(1, board_count + 1):
            player = Player.objects.create(lichess_username='Player%d' % player_num)
            sp = SeasonPlayer.objects.create(season=season2, player=player)
            LonePlayerScore.objects.create(season_player=sp)
            player_num += 1
            TeamMember.objects.create(team=team, player=player, board_number=b)

def create_reg(season, name):
    return Registration.objects.create(season=season, status='pending', lichess_username=name, slack_username=name,
                                       email='a@test.com', classical_rating=1500, peak_classical_rating=1600,
                                       has_played_20_games=True, already_in_slack_group=True, previous_season_alternate='new',
                                       can_commit=True, agreed_to_rules=True, alternate_preference='full_time')

class SeasonTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_season_save_round_creation(self):
        season = Season.objects.create(league=League.objects.all()[0], name='Test 2', rounds=4, boards=6)

        self.assertEqual(4, season.round_set.count())

        season.rounds = 6
        season.save()

        self.assertEqual(6, season.round_set.count())

    def test_season_save_prize_creation(self):
        season = Season.objects.get(tag='teamseason')
        self.assertEqual(1, season.seasonprize_set.filter(rank=1).count())
        self.assertEqual(1, season.seasonprize_set.filter(rank=2).count())
        self.assertEqual(1, season.seasonprize_set.filter(rank=3).count())

        season2 = Season.objects.get(tag='loneseason')
        self.assertEqual(2, season2.seasonprize_set.filter(rank=1).count())
        self.assertEqual(1, season2.seasonprize_set.filter(rank=2).count())
        self.assertEqual(1, season2.seasonprize_set.filter(rank=3).count())

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

    def test_season_calculate_team_scores(self):
        season = Season.objects.get(tag='teamseason')
        rounds = list(season.round_set.order_by('number'))
        teams = list(season.team_set.order_by('number'))

        def score_matrix():
            scores = list(TeamScore.objects.order_by('team__number'))
            return [(s.match_count, s.match_points, s.game_points, s.head_to_head, s.games_won, s.sb_score) for s in scores]

        self.assertItemsEqual([(0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0)], score_matrix())

        TeamPairing.objects.create(round=rounds[0], pairing_order=0, white_team=teams[0], black_team=teams[1], white_points=2.0, white_wins=2, black_points=1.0, black_wins=1)
        TeamPairing.objects.create(round=rounds[0], pairing_order=0, white_team=teams[2], black_team=teams[3], white_points=1.5, white_wins=1, black_points=1.5, black_wins=1)
        self.assertItemsEqual([(0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0)], score_matrix())

        rounds[0].is_completed = True
        rounds[0].save()
        self.assertItemsEqual([(1, 2, 2, 0, 2, 0), (1, 0, 1, 0, 1, 0), (1, 1, 1.5, 1, 1, 0.5), (1, 1, 1.5, 1, 1, 0.5)], score_matrix())

    def test_season_calculate_lone_scores(self):
        season = Season.objects.get(tag='loneseason')
        rounds = list(season.round_set.order_by('number'))
        season_players = list(season.seasonplayer_set.order_by('player__lichess_username'))[:4]
        players = [sp.player for sp in season_players]

        def score_matrix():
            scores = [sp.loneplayerscore for sp in season_players]
            for s in scores:
                s.refresh_from_db()
            return [(s.points, s.tiebreak1, s.tiebreak2, s.tiebreak3, s.tiebreak4) for s in scores]

        self.assertItemsEqual([(0, 0, 0, 0, 0), (0, 0, 0, 0, 0), (0, 0, 0, 0, 0), (0, 0, 0, 0, 0)], score_matrix())

        LonePlayerPairing.objects.create(round=rounds[0], pairing_order=0, white=players[0], black=players[1], result='1-0')
        LonePlayerPairing.objects.create(round=rounds[0], pairing_order=0, white=players[2], black=players[3], result='1/2-1/2')
        self.assertItemsEqual([(0, 0, 0, 0, 0), (0, 0, 0, 0, 0), (0, 0, 0, 0, 0), (0, 0, 0, 0, 0)], score_matrix())

        rounds[0].is_completed = True
        rounds[0].save()
        self.assertItemsEqual([(1, 0, 0, 1, 0), (0, 0, 1, 0, 1), (0.5, 0, 0.5, 0.5, 0.5), (0.5, 0, 0.5, 0.5, 0.5)], score_matrix())

        LonePlayerPairing.objects.create(round=rounds[1], pairing_order=0, white=players[2], black=players[0], result='0-1')
        LonePlayerPairing.objects.create(round=rounds[1], pairing_order=0, white=players[3], black=players[1], result='1/2-1/2')

        rounds[1].is_completed = True
        rounds[1].save()
        self.assertItemsEqual([(2, 0.5, 1, 3, 1.5), (0.5, 1, 3, 0.5, 4.5), (0.5, 1, 3, 1, 4.5), (1, 0, 1, 1.5, 1.5)], score_matrix())

        rounds[2].is_completed = True
        rounds[2].save()
        self.assertItemsEqual([(2, 2, 2, 5, 2.5), (0.5, 1.5, 4, 1, 7.5), (0.5, 1.5, 4, 1.5, 7.5), (1, 1, 2, 2.5, 2.5)], score_matrix())

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

        round1 = Round.objects.get(season__tag='teamseason', number=1)
        round1.is_completed = True
        round1.save()
        TeamPairing.objects.create(white_team=team1, black_team=team2, round=round1, pairing_order=0, white_points=1.5, black_points=0.5)

        round2 = Round.objects.get(season__tag='teamseason', number=2)
        round2.is_completed = True
        round2.save()
        TeamPairing.objects.create(white_team=team3, black_team=team1, round=round2, pairing_order=0, black_points=1.0, white_points=1.0)

    def test_teamscore_round_scores(self):
        teamscore = TeamScore.objects.get(team__number=1)
        pairing1 = TeamPairing.objects.get(round__number=1)
        pairing2 = TeamPairing.objects.get(round__number=2)

        self.assertItemsEqual([(1.5, 0.5, pairing1.pk), (1.0, 1.0, pairing2.pk), (None, None, None)], teamscore.round_scores())

    def test_teamscore_cross_scores(self):
        teamscore = TeamScore.objects.get(team__number=1)
        pairing1 = TeamPairing.objects.get(round__number=1)
        pairing2 = TeamPairing.objects.get(round__number=2)

        self.assertItemsEqual([(1, None, None, None), (2, 1.5, 0.5, pairing1.pk), (3, 1.0, 1.0, pairing2.pk), (4, None, None, None)], teamscore.cross_scores())

    def test_teamscore_cmp(self):
        ts1 = TeamScore()
        ts2 = TeamScore()

        self.assertGreaterEqual(ts1, ts2)
        self.assertLessEqual(ts1, ts2)

        ts1.match_points = 2
        self.assertGreater(ts1, ts2)

        ts2.match_points = 2
        ts2.game_points = 1.0
        self.assertLess(ts1, ts2)

class TeamPairingTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_teampairing_refresh_points(self):
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)

        tp = TeamPairing.objects.create(white_team=team1, black_team=team2, round=Round.objects.all()[0], pairing_order=0)

        pp1 = TeamPlayerPairing.objects.create(team_pairing=tp, board_number=1, white=team1.teammember_set.all()[0].player, black=team2.teammember_set.all()[0].player)
        pp2 = TeamPlayerPairing.objects.create(team_pairing=tp, board_number=2, white=team2.teammember_set.all()[1].player, black=team1.teammember_set.all()[1].player)

        tp.refresh_points()
        self.assertEqual(0, tp.white_points)
        self.assertEqual(0, tp.black_points)
        self.assertEqual(0, tp.white_wins)
        self.assertEqual(0, tp.black_wins)

        pp1.result = '1-0'
        pp1.save()
        pp2.result = '1/2-1/2'
        pp2.save()
        tp.refresh_from_db()

        self.assertEqual(1.5, tp.white_points)
        self.assertEqual(0.5, tp.black_points)
        self.assertEqual(1, tp.white_wins)
        self.assertEqual(0, tp.black_wins)

        pp1.result = '0-1'
        pp1.save()
        pp2.result = '0-1'
        pp2.save()
        tp.refresh_from_db()

        self.assertEqual(1, tp.white_points)
        self.assertEqual(1, tp.black_points)
        self.assertEqual(1, tp.white_wins)
        self.assertEqual(1, tp.black_wins)

        pp1.delete()
        pp2.delete()
        tp.refresh_from_db()

        self.assertEqual(0, tp.white_points)
        self.assertEqual(0, tp.black_points)
        self.assertEqual(0, tp.white_wins)
        self.assertEqual(0, tp.black_wins)

class LonePlayerPairingTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_loneplayerpairing_save_and_delete(self):
        season = Season.objects.get(tag='loneseason')
        round1 = season.round_set.get(number=1)
        sp1 = season.seasonplayer_set.all()[0]
        sp2 = season.seasonplayer_set.all()[1]
        score1 = sp1.loneplayerscore
        score2 = sp2.loneplayerscore

        round1.is_completed = True
        round1.save()
        self.assertEqual(0, score1.points)
        self.assertEqual(0, score2.points)

        pairing = LonePlayerPairing.objects.create(round=round1, white=sp1.player, black=sp2.player, pairing_order=1, result='1/2-1/2')
        score1.refresh_from_db()
        score2.refresh_from_db()
        self.assertEqual(0.5, score1.points)
        self.assertEqual(0.5, score2.points)

        pairing.result = '1-0'
        pairing.save()
        score1.refresh_from_db()
        score2.refresh_from_db()
        self.assertEqual(1, score1.points)
        self.assertEqual(0, score2.points)

        pairing.delete()
        score1.refresh_from_db()
        score2.refresh_from_db()
        self.assertEqual(0, score1.points)
        self.assertEqual(0, score2.points)

    def test_loneplayerpairing_refresh_ranks(self):
        season = Season.objects.get(tag='loneseason')
        round1 = season.round_set.get(number=1)
        round2 = season.round_set.get(number=2)
        sps = season.seasonplayer_set.all()

        round1.is_completed = True
        round1.save()
        round2.is_completed = True
        round2.save()

        pairing1 = LonePlayerPairing.objects.create(round=round1, white=sps[0].player, black=sps[1].player, pairing_order=1, result='1-0')
        pairing2 = LonePlayerPairing.objects.create(round=round2, white=sps[1].player, black=sps[0].player, pairing_order=1, result='1/2-1/2')
        pairing2.refresh_ranks()
        self.assertEqual(2, pairing2.white_rank)
        self.assertEqual(1, pairing2.black_rank)

        pairing1.result = '0-1'
        pairing1.save()
        pairing2.refresh_ranks()
        self.assertEqual(1, pairing2.white_rank)
        self.assertEqual(2, pairing2.black_rank)

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
        self.assertEqual(1.0, pp.white_score())
        self.assertEqual(0.0, pp.black_score())

        pp.result = '1/2-1/2'
        self.assertEqual(0.5, pp.white_score())
        self.assertEqual(0.5, pp.black_score())

        pp.result = '0-1'
        self.assertEqual(0.0, pp.white_score())
        self.assertEqual(1.0, pp.black_score())

class RegistrationTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_registration_previous(self):
        season = Season.objects.all()[0]
        reg = create_reg(season, 'testuser')

        self.assertItemsEqual([], reg.previous_registrations())

        reg2 = create_reg(season, 'testuser')
        self.assertItemsEqual([], reg.previous_registrations())
        self.assertItemsEqual([reg], reg2.previous_registrations())

    def test_registration_other_seasons(self):
        season = Season.objects.all()[0]
        season2 = Season.objects.create(league=League.objects.all()[0], name='Test 2', rounds=4, boards=6)

        player = Player.objects.create(lichess_username='testuser')
        sp = SeasonPlayer.objects.create(season=season, player=player)
        reg = create_reg(season2, 'testuser')

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

    def test_priority_date(self):
        sp = SeasonPlayer.objects.all()[0]
        alt = Alternate.objects.create(season_player=sp, board_number=1)

        self.assertEqual(alt.date_created, alt.priority_date())

        time1 = timezone.now()
        sp.registration = create_reg(sp.season, 'testuser')
        sp.save()
        time2 = timezone.now()

        self.assertTrue(time1 <= alt.priority_date() <= time2)

        time3 = timezone.now()
        r = Round.objects.all()[0]
        r.start_date = time3
        r.save()
        AlternateAssignment.objects.create(round=r, team=Team.objects.all()[0], board_number=1, player=sp.player)

        self.assertEqual(time3, alt.priority_date())

        time4 = timezone.now()
        alt.priority_date_override = time4
        alt.save()

        self.assertEqual(time4, alt.priority_date())

        time5 = timezone.now()
        sp.unresponsive = True
        sp.save()
        time6 = timezone.now()
        alt.refresh_from_db()

        self.assertTrue(time5 <= alt.priority_date() <= time6)

        sp = SeasonPlayer.objects.get(pk=sp.pk)
        sp.unresponsive = False
        sp.save()
        alt.refresh_from_db()

        self.assertTrue(time5 <= alt.priority_date() <= time6)

class AlternateAssignmentTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_alternateassignment_save(self):
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)

        tp = TeamPairing.objects.create(white_team=team1, black_team=team2, round=Round.objects.all()[0], pairing_order=0)

        pp1 = TeamPlayerPairing.objects.create(team_pairing=tp, board_number=1, white=team1.teammember_set.all()[0].player, black=team2.teammember_set.all()[0].player)

        self.assertEqual('Player1', pp1.white.lichess_username)

        AlternateAssignment.objects.create(round=tp.round, team=team1, board_number=1, player=Player.objects.create(lichess_username='Test User'))
        pp1.refresh_from_db()
        self.assertEqual('Test User', pp1.white.lichess_username)

class PlayerByeTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_playerbye_save_and_delete(self):
        season = Season.objects.get(tag='loneseason')
        round1 = season.round_set.get(number=1)
        sp = season.seasonplayer_set.all()[0]
        score = sp.loneplayerscore

        round1.is_completed = True
        round1.save()
        self.assertEqual(0, score.points)

        bye = PlayerBye.objects.create(round=round1, player=sp.player, type='half-point-bye')
        score.refresh_from_db()
        self.assertEqual(0.5, score.points)

        bye.type = 'full-point-bye'
        bye.save()
        score.refresh_from_db()
        self.assertEqual(1, score.points)

        bye.type = 'zero-point-bye'
        bye.save()
        score.refresh_from_db()
        self.assertEqual(0, score.points)

        bye.type = 'full-point-pairing-bye'
        bye.save()
        score.refresh_from_db()
        self.assertEqual(1, score.points)

        bye.delete()
        score.refresh_from_db()
        self.assertEqual(0, score.points)

    def test_playerbye_refresh_rank(self):
        season = Season.objects.get(tag='loneseason')
        round1 = season.round_set.get(number=1)
        sp1 = season.seasonplayer_set.all()[0]
        sp2 = season.seasonplayer_set.all()[1]

        round1.is_completed = True
        round1.save()

        bye1 = PlayerBye.objects.create(round=round1, player=sp1.player, type='half-point-bye')
        bye2 = PlayerBye.objects.create(round=round1, player=sp2.player, type='full-point-bye')

        bye1.refresh_rank()
        self.assertEqual(2, bye1.player_rank)

        bye2.refresh_rank()
        self.assertEqual(1, bye2.player_rank)
