from django.test import TestCase, SimpleTestCase
from django.utils import timezone
from datetime import datetime, timedelta
from heltour.tournament.models import (add_system_comment, Alternate,
        AlternateAssignment, AlternateBucket, AlternatesManagerSetting,
        format_score, get_fide_dp, get_gameid_from_gamelink, League,
        LonePlayerPairing, normalize_gamelink, OauthToken, Player, PlayerBye,
        PlayerPairing, Registration, Round, ScheduledNotification, Season,
        SeasonPlayer, Team, TeamPairing, TeamPlayerPairing, TeamScore)
from heltour.tournament.tests.testutils import (createCommonLeagueData,
        create_reg, get_league, get_player, get_season, set_rating, Shush)


class HelpersTestCase(SimpleTestCase):
    def test_format_score(self):
        self.assertEqual(format_score(score=None), '')
        self.assertEqual(format_score(score=0.5), '\u00BD')
        self.assertEqual(format_score(score=2.0), '2')
        self.assertEqual(format_score(score=2.5), '2\u00BD')
        self.assertEqual(format_score(score=1.0, game_played=False), '1X')
        self.assertEqual(format_score(score=0.5, game_played=False), '\u00BDZ')
        self.assertEqual(format_score(score=0.0, game_played=False), '0F')

    def test_get_fide_dp(self):
        self.assertEqual(get_fide_dp(0, 12), -800)
        self.assertEqual(get_fide_dp(12, 12), 800)

    def test_bad_gamelinks(self):
        self.assertEqual(get_gameid_from_gamelink(None), None)
        self.assertEqual(get_gameid_from_gamelink(''), None)
        self.assertEqual(get_gameid_from_gamelink('lichess.org/ABC2'), None)
        self.assertEqual(normalize_gamelink(''), ('', True))
        self.assertEqual(normalize_gamelink('https://licess.org/invalid'), ('https://licess.org/invalid', False))


class LeagueTestCase(TestCase):
    @classmethod
    def setUpTestData(self):
        self.league = League.objects.create(name='Lone League', tag='loneleague',
                                            competitor_type='lone',
                                            rating_type='classical')

    def test_time_control(self):
        self.assertEqual(str(self.league), 'Lone League')
        self.assertEqual(self.league.time_control_initial(), None)
        self.assertEqual(self.league.time_control_increment(), None)
        self.assertEqual(self.league.time_control_total(), None)
        self.league.time_control = '30+15'
        self.assertEqual(self.league.time_control_initial(), 1800)
        self.assertEqual(self.league.time_control_increment(), 15)
        self.assertEqual(self.league.time_control_total(), 2700)


class SeasonTestCase(TestCase):
    @classmethod
    def setUpTestData(self):
        createCommonLeagueData()
        self.season = Season.objects.create(league=League.objects.all()[0], name='Test 2',
                                            start_date=datetime(2016, 7, 1,
                                                                tzinfo=timezone.get_current_timezone()),
                                            rounds=4, boards=6)

    def test_season_save_round_creation(self):
        self.assertEqual(4, self.season.round_set.count())

        self.season.rounds = 6
        self.season.save()

        self.assertEqual(6, self.season.round_set.count())

    def test_season_save_prize_creation(self):
        season = get_season('team')
        self.assertEqual(1, season.seasonprize_set.filter(rank=1).count())
        self.assertEqual(1, season.seasonprize_set.filter(rank=2).count())
        self.assertEqual(1, season.seasonprize_set.filter(rank=3).count())

        season2 = get_season('lone')
        self.assertEqual(2, season2.seasonprize_set.filter(rank=1).count())
        self.assertEqual(1, season2.seasonprize_set.filter(rank=2).count())
        self.assertEqual(1, season2.seasonprize_set.filter(rank=3).count())

    def test_season_save_round_date(self):
        self.assertEqual(datetime(2016, 7, 22, tzinfo=timezone.get_current_timezone()),
                         self.season.round_set.order_by('-number')[0].start_date)
        self.assertEqual(datetime(2016, 7, 29, tzinfo=timezone.get_current_timezone()),
                         self.season.round_set.order_by('-number')[0].end_date)

        self.season.start_date = datetime(2016, 7, 2, tzinfo=timezone.get_current_timezone())
        self.season.save()

        self.assertEqual(datetime(2016, 7, 23, tzinfo=timezone.get_current_timezone()),
                         self.season.round_set.order_by('-number')[0].start_date)
        self.assertEqual(datetime(2016, 7, 30, tzinfo=timezone.get_current_timezone()),
                         self.season.round_set.order_by('-number')[0].end_date)

    def test_season_end_date(self):
        self.assertEqual(datetime(2016, 7, 29, tzinfo=timezone.get_current_timezone()),
                         self.season.end_date())

    def test_season_board_number_list(self):
        self.season.boards=4
        self.season.save()

        self.assertEqual([1, 2, 3, 4], self.season.board_number_list())

    def test_season_calculate_team_scores(self):
        season = get_season('team')
        rounds = list(season.round_set.order_by('number'))
        teams = list(season.team_set.order_by('number'))

        def score_matrix():
            scores = list(TeamScore.objects.order_by('team__number'))
            return [(s.match_count, s.match_points, s.game_points, s.head_to_head, s.games_won,
                     s.sb_score) for s in scores]

        self.assertEqual(
            [(0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0)],
            score_matrix())

        TeamPairing.objects.create(round=rounds[0], pairing_order=0, white_team=teams[0],
                                   black_team=teams[1], white_points=2.0, white_wins=2,
                                   black_points=1.0, black_wins=1)
        TeamPairing.objects.create(round=rounds[0], pairing_order=0, white_team=teams[2],
                                   black_team=teams[3], white_points=1.5, white_wins=1,
                                   black_points=1.5, black_wins=1)
        self.assertEqual(
            [(0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 0)],
            score_matrix())

        rounds[0].is_completed = True
        rounds[0].save()
        self.assertEqual([(1, 2, 2, 0, 2, 0), (1, 0, 1, 0, 1, 0), (1, 1, 1.5, 1, 1, 0.5),
                          (1, 1, 1.5, 1, 1, 0.5)], score_matrix())

    def test_season_calculate_lone_scores(self):
        season = get_season('lone')
        rounds = list(season.round_set.order_by('number'))
        season_players = list(season.seasonplayer_set.order_by('player__lichess_username'))[:4]
        players = [sp.player for sp in season_players]

        def score_matrix():
            scores = [sp.loneplayerscore for sp in season_players]
            for s in scores:
                s.refresh_from_db()
            return [(s.points, s.tiebreak1, s.tiebreak2, s.tiebreak3, s.tiebreak4) for s in scores]

        self.assertEqual([(0, 0, 0, 0, 0), (0, 0, 0, 0, 0), (0, 0, 0, 0, 0), (0, 0, 0, 0, 0)],
                         score_matrix())

        LonePlayerPairing.objects.create(round=rounds[0], pairing_order=0, white=players[0],
                                         black=players[1], result='1-0')
        LonePlayerPairing.objects.create(round=rounds[0], pairing_order=0, white=players[2],
                                         black=players[3], result='1/2-1/2')
        self.assertEqual([(0, 0, 0, 0, 0), (0, 0, 0, 0, 0), (0, 0, 0, 0, 0), (0, 0, 0, 0, 0)],
                         score_matrix())

        rounds[0].is_completed = True
        rounds[0].save()
        self.assertEqual(
            [(1, 0, 0, 1, 0), (0, 0, 1, 0, 1), (0.5, 0, 0.5, 0.5, 0.5), (0.5, 0, 0.5, 0.5, 0.5)],
            score_matrix())

        LonePlayerPairing.objects.create(round=rounds[1], pairing_order=0, white=players[2],
                                         black=players[0], result='0-1')
        LonePlayerPairing.objects.create(round=rounds[1], pairing_order=0, white=players[3],
                                         black=players[1], result='1/2-1/2')

        rounds[1].is_completed = True
        rounds[1].save()
        self.assertEqual(
            [(2, 0.5, 1, 3, 1.5), (0.5, 1, 3, 0.5, 4.5), (0.5, 1, 3, 1, 4.5), (1, 0, 1, 1.5, 1.5)],
            score_matrix())

        rounds[2].is_completed = True
        rounds[2].save()
        self.assertEqual([(2, 2, 2, 5, 2.5), (0.5, 1.5, 4, 1, 7.5), (0.5, 1.5, 4, 1.5, 7.5),
                          (1, 1, 2, 2.5, 2.5)], score_matrix())

    def test_export_players_basic(self):
        Season.objects.filter(name='Test Season').update(start_date=timezone.now())
        SeasonPlayer.objects.create(season=get_season('team'), player=get_player('Player1'))
        self.assertEqual(Season.objects.get(name='Test Season', tag='teamseason').export_players(),
                         [{'name': 'Player1', 'rating': 0, 'has_20_games': False, 'in_slack': False,
                           'account_status': 'normal', 'date_created': None, 'friends': None, 'avoid': None,
                           'prefers_alt': False, 'alt_fine': False, 'previous_season_alternate': False}])

    def test_export_players_detailed(self):
        Season.objects.filter(name='Test Season').update(start_date=timezone.now())
        with Shush():
            reg = Registration.objects.create(season=get_season('team'), status='approved', lichess_username='Player1',
                                              email='a@test.com', has_played_20_games=True, can_commit=True,
                                              agreed_to_rules=True, agreed_to_tos=True, alternate_preference='full_time')
        SeasonPlayer.objects.create(season=get_season('team'), player=get_player('Player1'), registration=reg)
        season_old = Season.objects.create(league=get_league('team'), name='Previous Season', tag='Prev Team', rounds=1, boards=1, start_date=timezone.now() - timedelta(days=7))
        sp = SeasonPlayer.objects.create(season=season_old, player=get_player('Player1'))
        Alternate.objects.create(season_player=sp, board_number=1)
        self.assertEqual(Season.objects.get(name='Test Season', tag='teamseason').export_players(),
                         [{'name': 'Player1', 'rating': 0, 'has_20_games': False, 'in_slack': False,
                           'account_status': 'normal', 'date_created': reg.date_created.isoformat(),
                           'friends': '', 'avoid': '',
                           'prefers_alt': False, 'alt_fine': False, 'previous_season_alternate': True}])

    def test_season_alternates_manager(self):
        self.assertFalse(self.season.alternates_manager_enabled())
        self.assertEqual(self.season.alternates_manager_setting(), None)
        am = AlternatesManagerSetting.objects.create(league=self.season.league)
        self.assertTrue(self.season.alternates_manager_enabled())
        self.assertEqual(self.season.alternates_manager_setting(), am)


class TeamTestCase(TestCase):
    @classmethod
    def setUpTestData(self):
        createCommonLeagueData()
        self.team = Team.objects.get(number=1)
        self.bd1 = self.team.teammember_set.get(board_number=1)
        self.bd2 = self.team.teammember_set.get(board_number=2)

    def test_team_boards(self):
        self.assertEqual([(1, self.bd1), (2, self.bd2)], self.team.boards())

        self.bd1.delete()
        self.assertEqual([(1, None), (2, self.bd2)], self.team.boards())

    def test_team_average_rating(self):
        # players without rating return 0 now instead of None
        self.assertEqual(0, self.team.average_rating())

        set_rating(self.bd1.player, 1800)
        self.bd1.player.save()
        self.assertEqual(900, self.team.average_rating())

        set_rating(self.bd2.player, 1600)
        self.bd2.player.save()
        self.assertEqual(1700, self.team.average_rating())

        self.bd1.delete()
        self.assertEqual(1600, self.team.average_rating())


class TeamScoreTestCase(TestCase):
    @classmethod
    def setUpTestData(self):
        createCommonLeagueData()
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)
        team3 = Team.objects.get(number=3)

        round1 = Round.objects.get(season__tag='teamseason', number=1)
        round1.is_completed = True
        round1.save()
        self.pairing1 = TeamPairing.objects.create(white_team=team1, black_team=team2, round=round1,
                                                   pairing_order=0, white_points=1.5, black_points=0.5)

        round2 = Round.objects.get(season__tag='teamseason', number=2)
        round2.is_completed = True
        round2.save()
        self.pairing2 = TeamPairing.objects.create(white_team=team3, black_team=team1, round=round2,
                                                   pairing_order=0, black_points=1.0, white_points=1.0)
        self.teamscore = TeamScore.objects.get(team__number=1)

    def test_teamscore_round_scores(self):
        self.assertEqual([(1.5, 0.5, 1), (1.0, 1.0, 2), (None, None, None)],
                         list(self.teamscore.round_scores()))

    def test_teamscore_cross_scores(self):
        self.assertEqual(
            [(1, None, None, None), (2, 1.5, 0.5, 1), (3, 1.0, 1.0, 2), (4, None, None, None)],
            list(self.teamscore.cross_scores()))

    def test_teamscore_cmp(self):
        ts1 = TeamScore()
        ts2 = TeamScore()

        # Only the lt operator is implemented so we have to manually work around that
        self.assertTrue(not (ts1 < ts2))
        self.assertTrue(not (ts2 < ts1))

        ts1.match_points = 2
        self.assertLess(ts2, ts1)

        ts2.match_points = 2
        ts2.game_points = 1.0
        self.assertLess(ts1, ts2)


class TeamPairingTestCase(TestCase):
    @classmethod
    def setUpTestData(self):
        createCommonLeagueData()

    def test_teampairing_refresh_points(self):
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)

        tp = TeamPairing.objects.create(white_team=team1, black_team=team2,
                                        round=Round.objects.all()[0], pairing_order=0)

        pp1 = TeamPlayerPairing.objects.create(team_pairing=tp, board_number=1,
                                               white=team1.teammember_set.get(
                                                   board_number=1).player,
                                               black=team2.teammember_set.get(
                                                   board_number=1).player)
        pp2 = TeamPlayerPairing.objects.create(team_pairing=tp, board_number=2,
                                               white=team2.teammember_set.get(
                                                   board_number=2).player,
                                               black=team1.teammember_set.get(
                                                   board_number=2).player)

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
    @classmethod
    def setUpTestData(self):
        createCommonLeagueData()
        self.season = get_season('lone')
        self.round1 = self.season.round_set.get(number=1)
        self.round2 = self.season.round_set.get(number=2)
        self.sps = self.season.seasonplayer_set.all()

    def test_loneplayerpairing_save_and_delete(self):
        sp1 = self.season.seasonplayer_set.all()[0]
        sp2 = self.season.seasonplayer_set.all()[1]
        score1 = sp1.loneplayerscore
        score2 = sp2.loneplayerscore

        self.round1.is_completed = True
        self.round1.save()
        self.assertEqual(0, score1.points)
        self.assertEqual(0, score2.points)

        pairing = LonePlayerPairing.objects.create(round=self.round1, white=sp1.player, black=sp2.player,
                                                   pairing_order=1, result='1/2-1/2')
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
        self.round1.is_completed = True
        self.round1.save()
        self.round2.is_completed = True
        self.round2.save()

        pairing1 = LonePlayerPairing.objects.create(round=self.round1, white=self.sps[0].player,
                                                    black=self.sps[1].player, pairing_order=1,
                                                    result='1-0')
        pairing2 = LonePlayerPairing.objects.create(round=self.round2, white=self.sps[1].player,
                                                    black=self.sps[0].player, pairing_order=1,
                                                    result='1/2-1/2')
        pairing2.refresh_ranks()
        self.assertEqual(2, pairing2.white_rank)
        self.assertEqual(1, pairing2.black_rank)

        pairing1.result = '0-1'
        pairing1.save()
        pairing2.refresh_ranks()
        self.assertEqual(1, pairing2.white_rank)
        self.assertEqual(2, pairing2.black_rank)

    def test_scheduling_creates_notification(self):
        pairing1 = LonePlayerPairing.objects.create(round=self.round1, white=self.sps[0].player,
                                                    black=self.sps[1].player, pairing_order=1)

        pairing1.scheduled_time = timezone.now() + timedelta(hours=2)
        pairing1.save()
        sno1 = ScheduledNotification.objects.get(pairing=pairing1, setting__player=self.sps[1].player)
        self.assertTrue(sno1.notification_time > timezone.now() + timedelta(minutes=55))
        self.assertTrue(sno1.notification_time < timezone.now() + timedelta(hours=1, minutes=5))

    def test_loneplayerpairing_token_getters(self):
        o1 = OauthToken.objects.create(access_token="blah1", expires=timezone.now() + timedelta(minutes=10))
        o2 = OauthToken.objects.create(access_token="blah2", expires=timezone.now() + timedelta(minutes=10))
        Player.objects.filter(lichess_username="Player1").update(oauth_token=o1)
        Player.objects.filter(lichess_username="Player2").update(oauth_token=o2)
        pairing1 = LonePlayerPairing.objects.create(round=self.round1,
                                                    white=Player.objects.get(lichess_username="Player1"),
                                                    black=Player.objects.get(lichess_username="Player2"), pairing_order=1)
        pairing2 = LonePlayerPairing.objects.create(round=self.round1,
                                                    white=Player.objects.get(lichess_username="Player3"),
                                                    black=Player.objects.get(lichess_username="Player4"), pairing_order=2)
        self.assertEqual(pairing1.get_white_access_token(), "blah1")
        self.assertEqual(pairing1.get_black_access_token(), "blah2")
        self.assertEqual(pairing2.get_white_access_token(), None)
        self.assertEqual(pairing2.get_black_access_token(), None)


class PlayerPairingTestCase(TestCase):
    @classmethod
    def setUpTestData(self):
        createCommonLeagueData()
        self.team1 = Team.objects.get(number=1)

    def test_playerpairing_score(self):
        team2 = Team.objects.get(number=2)

        pp = PlayerPairing.objects.create(white=self.team1.teammember_set.all()[0].player,
                                          black=team2.teammember_set.all()[0].player)

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

    def test_comments(self):
        try:
            add_system_comment(obj=self.team1, text='comment by system')
        except:
            self.fail("add_system_comment failed for system comment on team")
        try:
            add_system_comment(obj=self.team1, text='comment by glbert', user_name='glbert')
        except:
            self.fail("add_system_comment failed for comment by glbert on team")
        try:
            add_system_comment(obj=self.team1.teammember_set.all()[0].player, text='Player got a moderator warning', user_name='glbert')
        except:
            self.fail("add_system_comment failed for comment by glbert on player")


class RegistrationTestCase(TestCase):
    @classmethod
    def setUpTestData(self):
        createCommonLeagueData()
        self.season = get_season('team')

    def test_registration_previous(self):
        reg = create_reg(self.season, 'Player1')

        self.assertEqual([], list(reg.previous_registrations()))

        reg2 = create_reg(self.season, 'Player1')
        self.assertEqual([], list(reg.previous_registrations()))
        self.assertEqual([reg], list(reg2.previous_registrations()))

    def test_registration_other_seasons(self):
        season2 = Season.objects.create(league=League.objects.all()[0], name='Test 2', rounds=4,
                                        boards=6)

        player = Player.objects.create(lichess_username='testuser')
        sp = SeasonPlayer.objects.create(season=self.season, player=player)
        reg = create_reg(season2, 'testuser')

        self.assertEqual([sp], list(reg.other_seasons()))


class AlternateTestCase(TestCase):
    @classmethod
    def setUpTestData(self):
        createCommonLeagueData()
        self.season = get_season('team')
        self.player = Player.objects.all()[0]
        self.sp = SeasonPlayer.objects.create(season=self.season, player=self.player)

    def test_alternate_update_board_number(self):
        self.season.boards = 3

        alt = Alternate.objects.create(season_player=self.sp, board_number=2)

        alt.update_board_number()
        self.assertEqual(2, alt.board_number)

        AlternateBucket.objects.create(season=self.season, board_number=1, max_rating=None,
                                       min_rating=2000)
        AlternateBucket.objects.create(season=self.season, board_number=2, max_rating=2000,
                                       min_rating=1800)
        AlternateBucket.objects.create(season=self.season, board_number=3, max_rating=1800,
                                       min_rating=None)

        set_rating(self.player, None)
        alt.update_board_number()
        self.assertEqual(2, alt.board_number)

        set_rating(self.player, 2100)
        alt.update_board_number()
        self.assertEqual(1, alt.board_number)

        set_rating(self.player, 1900)
        alt.update_board_number()
        self.assertEqual(2, alt.board_number)

        set_rating(self.player, 1800)
        alt.update_board_number()
        self.assertEqual(3, alt.board_number)

        set_rating(self.player, 1700)
        alt.update_board_number()
        self.assertEqual(3, alt.board_number)

    def test_priority_date(self):
        alt = Alternate.objects.create(season_player=self.sp, board_number=1)

        self.assertEqual(alt.date_created, alt.priority_date())

        time1 = timezone.now()
        # creating a reg writes to the log, disable that temporarily for nicer test output
        with Shush():
            self.sp.registration = create_reg(self.sp.season, 'Player1')
        time2 = timezone.now()

        self.assertTrue(time1 <= alt.priority_date() <= time2)

        time3 = timezone.now()
        r = Round.objects.all()[0]
        r.end_date = time3
        r.save()
        AlternateAssignment.objects.create(round=r, team=Team.objects.all()[0], board_number=1,
                                           player=self.sp.player)

        self.assertEqual(time3, alt.priority_date())

        time4 = timezone.now()
        alt.priority_date_override = time4
        alt.save()

        self.assertEqual(time4, alt.priority_date())

        time5 = timezone.now()
        self.sp.unresponsive = True
        self.sp.save()
        time6 = timezone.now()
        alt.refresh_from_db()

        self.assertTrue(time5 <= alt.priority_date() <= time6)

        self.sp.unresponsive = False
        self.sp.save()
        alt.refresh_from_db()

        self.assertTrue(time5 <= alt.priority_date() <= time6)

    def test_alternateassignment_save(self):
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)

        tp = TeamPairing.objects.create(white_team=team1, black_team=team2,
                                        round=Round.objects.all()[0], pairing_order=0)

        pp1 = TeamPlayerPairing.objects.create(team_pairing=tp, board_number=1,
                                               white=team1.teammember_set.all()[0].player,
                                               black=team2.teammember_set.all()[0].player)

        self.assertEqual('Player1', pp1.white.lichess_username)

        AlternateAssignment.objects.create(round=tp.round, team=team1, board_number=1,
                                           player=Player.objects.create(
                                               lichess_username='Test User'))
        pp1.refresh_from_db()
        self.assertEqual('Test User', pp1.white.lichess_username)

    def test_last_season_alternates(self):
        Season.objects.filter(pk=self.season.pk).update(start_date=timezone.now())
        season_old = Season.objects.create(league=self.season.league, name='Previous Season', tag='Prev Team', rounds=1, boards=1, start_date=timezone.now() - timedelta(days=7))
        sp = SeasonPlayer.objects.create(season=season_old, player=self.player)
        Alternate.objects.create(season_player=sp, board_number=1)
        self.assertEqual(Season.objects.get(pk=self.season.pk).last_season_alternates(), {self.sp.player})



class PlayerByeTestCase(TestCase):
    @classmethod
    def setUpTestData(self):
        createCommonLeagueData()
        self.season = get_season('lone')
        self.round1 = self.season.round_set.get(number=1)
        self.round1.is_completed = True
        self.round1.save()
        self.sp1 = self.season.seasonplayer_set.all()[0]
        self.sp2 = self.season.seasonplayer_set.all()[1]

    def test_playerbye_save_and_delete(self):
        score = self.sp1.loneplayerscore
        self.assertEqual(0, score.points)

        bye = PlayerBye.objects.create(round=self.round1, player=self.sp1.player, type='half-point-bye')
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
        bye1 = PlayerBye.objects.create(round=self.round1, player=self.sp1.player, type='half-point-bye')
        bye2 = PlayerBye.objects.create(round=self.round1, player=self.sp2.player, type='full-point-bye')

        bye1.refresh_rank()
        self.assertEqual(2, bye1.player_rank)

        bye2.refresh_rank()
        self.assertEqual(1, bye2.player_rank)
