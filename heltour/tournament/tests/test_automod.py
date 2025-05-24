from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from heltour.tournament.automod import automod_noshow
from heltour.tournament.models import LeagueSetting, LonePlayerPairing, PlayerPresence
from heltour.tournament.tests.testutils import createCommonLeagueData, get_league, get_player, get_round


class NoShowTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.rd = get_round('team', round_number=1)
        cls.player1 = get_player('Player1')
        cls.player2 = get_player('Player2')
        cls.pairing = LonePlayerPairing.objects.create(round=cls.rd, white=cls.player1, black=cls.player2, game_link='', scheduled_time=timezone.now(), pairing_order=1, tv_state='default')
        PlayerPresence.objects.create(player=cls.player1, pairing=cls.pairing, round=cls.rd)
        PlayerPresence.objects.create(player=cls.player2, pairing=cls.pairing, round=cls.rd)

    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_has_moves(self, noshow_sender):
        self.pairing.tv_state = 'has_moves'
        automod_noshow(self.pairing)
        # pairing has moves, so the noshow_sender should not have been called.
        self.assertFalse(noshow_sender.called)

    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_has_result(self, noshow_sender):
        self.pairing.result = '1-0'
        automod_noshow(self.pairing)
        # pairing has a result, so the noshow_sender should not have been called.
        self.assertFalse(noshow_sender.called)

    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_has_game_link(self, noshow_sender):
        self.pairing.game_link = 'https://lichess.org/NKop9IyD'
        automod_noshow(self.pairing)
        # pairing has a game_link, so the noshow_sender should not have been called.
        self.assertFalse(noshow_sender.called)

    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_no_confirmed_black_noshows(self, noshow_sender):
        PlayerPresence.objects.filter(player=self.player1, pairing=self.pairing, round=self.rd).update(online_for_game=False)
        PlayerPresence.objects.filter(player=self.player2, pairing=self.pairing, round=self.rd).update(online_for_game=True)
        automod_noshow(self.pairing)
        self.assertTrue(noshow_sender.called)
        # assert noshow by black
        self.assertEqual(noshow_sender.call_args[1]['player'], self.pairing.black)
        self.assertEqual(noshow_sender.call_args[1]['opponent'], self.pairing.white)

    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_no_confirmed_white_noshows(self, noshow_sender):
        PlayerPresence.objects.filter(player=self.player1, pairing=self.pairing, round=self.rd).update(online_for_game=True)
        PlayerPresence.objects.filter(player=self.player2, pairing=self.pairing, round=self.rd).update(online_for_game=False)
        automod_noshow(self.pairing)
        self.assertTrue(noshow_sender.called)
        # assert noshow by black
        self.assertEqual(noshow_sender.call_args[1]['player'], self.pairing.white)
        self.assertEqual(noshow_sender.call_args[1]['opponent'], self.pairing.black)

    @patch('heltour.tournament.lichessapi.get_game_meta',
            return_value={'moves': '1.e4 e5 2.Ke2'})
    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_confirmed_has_moves(self, noshow_sender, game_meta):
        self.pairing.white_confirmed=True
        self.pairing.black_confirmed=True
        self.pairing.game_link='https://lichess.org/NKop9IyD'
        automod_noshow(self.pairing)
        self.assertTrue(game_meta.called)
        # game_meta indicates that there are moves, there is no noshow.
        self.assertFalse(noshow_sender.called)

    @patch('heltour.tournament.lichessapi.get_game_meta',
            return_value={'moves': '1.e4'})
    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_confirmed_black_no_shows(self, noshow_sender, game_meta):
        PlayerPresence.objects.filter(player=self.player1, pairing=self.pairing, round=self.rd).update(online_for_game=True)
        PlayerPresence.objects.filter(player=self.player2, pairing=self.pairing, round=self.rd).update(online_for_game=False)
        self.pairing.white_confirmed=True
        self.pairing.black_confirmed=True
        self.pairing.game_link='https://lichess.org/NKop9IyD'
        automod_noshow(self.pairing)
        self.assertTrue(game_meta.called)
        self.assertTrue(noshow_sender.called)
        # assert noshow by black
        self.assertEqual(noshow_sender.call_args[1]['player'], self.pairing.white)
        self.assertEqual(noshow_sender.call_args[1]['opponent'], self.pairing.black)

    @patch('heltour.tournament.lichessapi.get_game_meta',
            return_value={'moves': '1.e4'})
    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_confirmed_white_no_shows(self, noshow_sender, game_meta):
        PlayerPresence.objects.filter(player=self.player1, pairing=self.pairing, round=self.rd).update(online_for_game=False)
        PlayerPresence.objects.filter(player=self.player2, pairing=self.pairing, round=self.rd).update(online_for_game=True)
        self.pairing.white_confirmed=True
        self.pairing.black_confirmed=True
        self.pairing.game_link='https://lichess.org/NKop9IyD'
        automod_noshow(self.pairing)
        self.assertTrue(game_meta.called)
        # assert a noshow by white
        self.assertTrue(noshow_sender.called)
        self.assertEqual(noshow_sender.call_args[1]['player'], self.pairing.black)
        self.assertEqual(noshow_sender.call_args[1]['opponent'], self.pairing.white)
