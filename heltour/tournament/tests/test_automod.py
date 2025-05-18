from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from heltour.tournament.automod import automod_noshow
from heltour.tournament.models import LeagueSetting, LonePlayerPairing, PlayerPresence
from heltour.tournament.tests.testutils import createCommonLeagueData, get_league, get_player, get_round


class NoShowTestCase(TestCase):
    @classmethod
    def setUpTestData(self):
        createCommonLeagueData()
        self.rd = get_round('team', round_number=1)
        self.player1 = get_player('Player1')
        self.player2 = get_player('Player2')
        self.pairing = LonePlayerPairing.objects.create(round=self.rd, white=self.player1, black=self.player2, game_link='', scheduled_time=timezone.now(), pairing_order=1, tv_state='default')
        PlayerPresence.objects.create(player=self.player1, pairing=self.pairing, round=self.rd)
        PlayerPresence.objects.create(player=self.player2, pairing=self.pairing, round=self.rd)

    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_has_moves(self, noshow_sender):
        LonePlayerPairing.objects.filter(round=self.rd, white=self.player1, black=self.player2).update(tv_state='has_moves')
        automod_noshow(self.pairing)
        # pairing has moves, so the noshow_sender should not have been called.
        self.assertFalse(noshow_sender.called)

    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_has_result(self, noshow_sender):
        LonePlayerPairing.objects.filter(round=self.rd, white=self.player1, black=self.player2).update(result='1-0')
        automod_noshow(self.pairing)
        # pairing has a result, so the noshow_sender should not have been called.
        self.assertFalse(noshow_sender.called)

    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_has_game_link(self, noshow_sender):
        LonePlayerPairing.objects.filter(round=self.rd, white=self.player1, black=self.player2).update(game_link="https://lichess.org/NKop9IyD")
        automod_noshow(self.pairing)
        # pairing has a game_link, so the noshow_sender should not have been called.
        self.assertFalse(noshow_sender.called)

    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_nosetting_confirmed_black_noshows(self, noshow_sender):
        # pairing2 has no moves, and one of the players is present while the other is not, so noshow_sender should have been called.
        PlayerPresence.objects.filter(player=self.player1, pairing=self.pairing, round=self.rd).update(online_for_game=False)
        PlayerPresence.objects.filter(player=self.player2, pairing=self.pairing, round=self.rd).update(online_for_game=True)
        automod_noshow(self.pairing)
        self.assertTrue(noshow_sender.called)
        self.assertEqual(noshow_sender.call_args[1]["player"], self.pairing.black)
        self.assertEqual(noshow_sender.call_args[1]["opponent"], self.pairing.white)

    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_nosetting_confirmed_white_noshows(self, noshow_sender):
        PlayerPresence.objects.filter(player=self.player2, pairing=self.pairing, round=self.rd).update(online_for_game=False)
        PlayerPresence.objects.filter(player=self.player1, pairing=self.pairing, round=self.rd).update(online_for_game=True)
        automod_noshow(self.pairing)
        self.assertTrue(noshow_sender.called)
        self.assertEqual(noshow_sender.call_args[1]["player"], self.pairing.white)
        self.assertEqual(noshow_sender.call_args[1]["opponent"], self.pairing.black)
