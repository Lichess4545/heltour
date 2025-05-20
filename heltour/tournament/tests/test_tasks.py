import logging
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch
from heltour.tournament.models import League, OauthToken, Player, Registration, Round, Team, TeamPairing, TeamPlayerPairing
from heltour.tournament.tasks import (active_player_usernames, not_updated_recently_usernames, start_games,
                                      update_player_ratings, validate_registration)
from heltour.tournament.tests.testutils import createCommonLeagueData, create_reg, get_league, get_player, get_round, get_season
from heltour.tournament.lichessapi import ApiClientError, ApiWorkerError


class TestHelpers(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_username_helpers(self, *args):
        playernames = ['Player' + str(i) for i in range(1, 9)]
        self.assertEqual(active_player_usernames(), playernames) # names are Player1, ..., Player8
        self.assertEqual(not_updated_recently_usernames(playernames), [])
        # could mock.patch timezone.now to change what "recently" means for more tests


class TestUpdateRatings(TestCase):
    def setUp(self):
        createCommonLeagueData()
        League.objects.create(name='c960 League', tag='960league',
                              competitor_type='lone', rating_type='chess960')

    @patch('heltour.tournament.lichessapi.enumerate_user_metas',
           return_value=[{"id":"Player1", "perfs":{"classical":{"games":25,"rating":2200}}},
                         {"id":"Player2", "perfs":{"chess960":{"games":12, "rating":1000},
                                                   "classical":{"games":10, "rating":1800}}}])
    def test_update_ratings(self, *args):
        # updating player ratings writes to the log, disable that temporarily for nicer test output
        logging.disable(logging.CRITICAL)
        try:
            update_player_ratings()
        finally:
            logging.disable(logging.NOTSET)
        tl = get_league('team')
        l960 = get_league('960')
        p2 = get_player('Player2')
        self.assertEqual(get_player('Player1').rating_for(league=tl), 2200)
        self.assertEqual(p2.rating_for(league=tl), 1800)
        self.assertEqual(p2.rating_for(league=l960), 1000)
        self.assertEqual(get_player('Player3').rating_for(league=tl), 0)


@patch('heltour.tournament.lichessapi.add_watch',
       return_value=None)
class TestAutostartGames(TestCase):
    def setUp(self):
        createCommonLeagueData()
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)
        Round.objects.filter(season__league__name='Team League', number=1).update(publish_pairings=True, start_date=timezone.now())
        rd = get_round(league_type='team', round_number=1)
        rd.season.league.get_leaguesetting().start_games = True
        rd.season.league.get_leaguesetting().save()
        tp = TeamPairing.objects.create(white_team=team1, black_team=team2,
                                        round=rd, pairing_order=0)
        TeamPlayerPairing.objects.create(
                team_pairing=tp, board_number=1,
                white=team1.teammember_set.get(board_number=1).player,
                black=team2.teammember_set.get(board_number=1).player,
                white_confirmed = True,
                black_confirmed = False
                )
        TeamPlayerPairing.objects.create(
                team_pairing=tp, board_number=2,
                white=team2.teammember_set.get(board_number=2).player,
                black=team1.teammember_set.get(board_number=2).player,
                white_confirmed = True,
                black_confirmed = True,
                )
        TeamPlayerPairing.objects.filter(team_pairing=tp).update(scheduled_time = timezone.now() + timedelta(minutes=5))
        o1 = OauthToken.objects.create(access_token="blah1", expires=timezone.now() + timedelta(minutes=10))
        o2 = OauthToken.objects.create(access_token="blah2", expires=timezone.now() + timedelta(minutes=10))
        o3 = OauthToken.objects.create(access_token="blah3", expires=timezone.now() + timedelta(minutes=10))
        o4 = OauthToken.objects.create(access_token="blah4", expires=timezone.now() + timedelta(minutes=10))
        Player.objects.filter(lichess_username=team1.teammember_set.get(board_number=1).player.lichess_username).update(
                oauth_token=o1)
        Player.objects.filter(lichess_username=team1.teammember_set.get(board_number=2).player.lichess_username).update(
                oauth_token=o2)
        Player.objects.filter(lichess_username=team2.teammember_set.get(board_number=1).player.lichess_username).update(
                oauth_token=o3)
        Player.objects.filter(lichess_username=team2.teammember_set.get(board_number=2).player.lichess_username).update(
                oauth_token=o4)

    @patch('heltour.tournament.lichessapi.bulk_start_games',
           return_value={"id": "RVAcwgg7", "games": [{"id": "NKop9IyD", "black": "player2", "white": "player4"}]})
    def test_start_game(self, *args):
        # start_games writes to the log, disable that temporarily for nicer test output
        logging.disable(logging.CRITICAL)
        try:
            start_games()
        finally:
            logging.disable(logging.NOTSET)
        tpp2 = TeamPlayerPairing.objects.get(board_number=2)
        tpp1 = TeamPlayerPairing.objects.get(board_number=1)
        self.assertEqual(tpp2.game_link, "https://lichess.org/NKop9IyD")
        self.assertEqual(tpp1.game_link, "")

    @patch('heltour.tournament.lichessapi.bulk_start_games',
           return_value={"id": "RVAcwgg7", "games": [{"id": "NKop9IyD", "black": "player2", "white": "player4"},
                                                     {"id": "KT837Aut", "black": "player3", "white": "player1"}]})
    def test_start_games(self, *args):
        TeamPlayerPairing.objects.filter(board_number=1).update(black_confirmed = True)
        # start_games writes to the log, disable that temporarily for nicer test output
        logging.disable(logging.CRITICAL)
        try:
            start_games()
        finally:
            logging.disable(logging.NOTSET)
        tpp2 = TeamPlayerPairing.objects.get(board_number=2)
        tpp1 = TeamPlayerPairing.objects.get(board_number=1)
        self.assertEqual(tpp2.game_link, "https://lichess.org/NKop9IyD")
        self.assertEqual(tpp1.game_link, "https://lichess.org/KT837Aut")

    @patch('heltour.tournament.lichessapi.bulk_start_games',
           side_effect=[ApiClientError('{"tokens": ["blah2"]}'),
               {"id": "RVAcwgg7", "games": [{"id": "KT837Aut", "black": "player3", "white": "player1"}]}])
    def test_start_invalid_token(self, *args):
        TeamPlayerPairing.objects.filter(board_number=1).update(black_confirmed = True)
        # start_games writes to the log, disable that temporarily for nicer test output
        logging.disable(logging.CRITICAL)
        try:
            start_games()
        finally:
            logging.disable(logging.NOTSET)
        tpp2 = TeamPlayerPairing.objects.get(board_number=2)
        tpp1 = TeamPlayerPairing.objects.get(board_number=1)
        # test that the tpp2 game link was not set
        self.assertEqual(tpp2.game_link, "")
        # test that the ttp1 game was set, that is a bad token pairing was removed and the remaining pairing still used
        self.assertEqual(tpp1.game_link, "https://lichess.org/KT837Aut")
        # test that the expiry of the bad token was set to a time in the past
        self.assertTrue(tpp2.black.oauth_token.expires < timezone.now() - timedelta(minutes=30))


class TestValidateRegistration(TestCase):
    @classmethod
    def setUpTestData(self):
        createCommonLeagueData()
        # updating player ratings writes to the log, disable that temporarily for nicer test output
        s = get_season('team')
        logging.disable(logging.CRITICAL)
        try:
            self.reg = create_reg(s, name="Player1")
        finally:
            logging.disable(logging.NOTSET)

    @patch('heltour.tournament.lichessapi.get_user_meta',
           return_value={"id":"Player1", "perfs":{"classical":{"games":25,"rating":2200,"prov":False}}})
    def test_validation_ok(self, user_meta):
        validate_registration(self.reg.id)
        # validate_registration does not change the object directly but updates it from a new query,
        # so for checks we have to as well
        reg = Registration.objects.get(pk=self.reg.id)
        self.assertTrue(user_meta.called)
        self.assertEqual(user_meta.call_args[0], ('Player1', 1))
        self.assertTrue(reg.has_played_20_games)
        self.assertTrue(reg.validation_ok)
        self.assertFalse(reg.validation_warning)

    @patch('heltour.tournament.lichessapi.get_user_meta',
           return_value={"id":"Player1", "perfs":{"classical":{"games":25,"rating":2200,"prov":True}}})
    def test_validation_prov(self, user_meta):
        validate_registration(self.reg.id)
        reg = Registration.objects.get(pk=self.reg.id)
        self.assertTrue(user_meta.called)
        self.assertTrue(reg.has_played_20_games)
        self.assertTrue(reg.validation_ok)
        self.assertTrue(reg.validation_warning)

    @patch('heltour.tournament.lichessapi.get_user_meta',
           return_value={"id":"Player1", "tosViolation": True,
                         "perfs":{"classical":{"games":25,"rating":2200,"prov":False}}})
    def test_validation_tos(self, user_meta):
        validate_registration(self.reg.id)
        reg = Registration.objects.get(pk=self.reg.id)
        self.assertTrue(user_meta.called)
        self.assertTrue(reg.has_played_20_games)
        self.assertFalse(reg.validation_ok)
        self.assertFalse(reg.validation_warning)

    @patch('heltour.tournament.lichessapi.get_user_meta',
           return_value={"id":"Player1", "disabled": True,
                         "perfs":{"classical":{"games":25,"rating":2200,"prov":False}}})
    def test_validation_closed(self, user_meta):
        validate_registration(self.reg.id)
        reg = Registration.objects.get(pk=self.reg.id)
        self.assertTrue(user_meta.called)
        self.assertTrue(reg.has_played_20_games)
        self.assertFalse(reg.validation_ok)
        self.assertFalse(reg.validation_warning)

    @patch('heltour.tournament.lichessapi.get_user_meta',
           side_effect=ApiClientError)
    def test_validation_clienterror(self, user_meta):
        validate_registration(self.reg.id)
        reg = Registration.objects.get(pk=self.reg.id)
        self.assertTrue(user_meta.called)
        self.assertTrue(reg.has_played_20_games)
        self.assertFalse(reg.validation_ok)
        self.assertFalse(reg.validation_warning)

    @patch('heltour.tournament.lichessapi.get_user_meta',
           side_effect=ApiWorkerError)
    def test_validation_workererror(self, user_meta):
        validate_registration(self.reg.id)
        reg = Registration.objects.get(pk=self.reg.id)
        self.assertTrue(user_meta.called)
        self.assertTrue(reg.has_played_20_games)
        self.assertFalse(reg.validation_ok)
        self.assertFalse(reg.validation_warning)
