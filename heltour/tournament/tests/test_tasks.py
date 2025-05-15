from datetime import timedelta
import logging
from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch
from heltour.tournament.models import OauthToken, Player, Round, Team, TeamPairing, TeamPlayerPairing
from heltour.tournament.tasks import start_games
from heltour.tournament.tests.testutils import createCommonLeagueData #, get_league, league_tag, league_url, season_url
from heltour.tournament.lichessapi import ApiClientError


@patch('heltour.tournament.lichessapi.add_watch',
       return_value=None)
class TestAutostartGames(TestCase):
    def setUp(self):
        createCommonLeagueData()
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)
        Round.objects.filter(season__league__name="Team League", number=1).update(publish_pairings=True, start_date=timezone.now())
        rd = Round.objects.get(season__league__name="Team League", number=1)
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
        logging.disable(logging.CRITICAL)
        start_games()
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
        logging.disable(logging.CRITICAL)
        start_games()
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
        logging.disable(logging.CRITICAL)
        start_games()
        logging.disable(logging.NOTSET)
        tpp2 = TeamPlayerPairing.objects.get(board_number=2)
        tpp1 = TeamPlayerPairing.objects.get(board_number=1)
        # test that the tpp2 game link was not set
        self.assertEqual(tpp2.game_link, "")
        # test that the ttp1 game was set, that is a bad token pairing was removed and the remaining pairing still used
        self.assertEqual(tpp1.game_link, "https://lichess.org/KT837Aut")
        # test that the expiry of the bad token was set to a time in the past
        self.assertTrue(tpp2.black.oauth_token.expires < timezone.now() - timedelta(minutes=30))
