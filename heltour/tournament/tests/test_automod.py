from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from heltour.tournament.automod import automod_noshow
from heltour.tournament.models import LeagueSetting, LonePlayerPairing, PlayerPresence
from heltour.tournament.tests.testutils import createCommonLeagueData, get_league, get_player, get_round


class NoShowTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    @patch('heltour.tournament.signals.notify_noshow.send')
    def test_noSetting_Confirmed(self, noshow_sender):
        LeagueSetting.objects.filter(league__tag='teamleague').update(start_games=False)
        rd = get_round('team', round_number=1)
        player1 = get_player('Player1')
        player2 = get_player('Player2')
        player3 = get_player('Player3')
        player4 = get_player('Player4')
        pairing1 = LonePlayerPairing.objects.create(round=rd, white=player1, black=player2, game_link='', scheduled_time=timezone.now(), pairing_order=1, tv_state='has_moves')
        pairing2 = LonePlayerPairing.objects.create(round=rd, white=player3, black=player4, game_link='', scheduled_time=timezone.now(), pairing_order=1, tv_state='default')
        PlayerPresence.objects.create(player=player3, pairing=pairing2, round=rd, online_for_game=False)
        PlayerPresence.objects.create(player=player4, pairing=pairing2, round=rd, online_for_game=True)
        automod_noshow(pairing1)
        # pairing1 has moves, so the noshow_sender should not have been called.
        self.assertFalse(noshow_sender.called)
        # pairing2 has no moves, and one of the players is present while the other is not, so noshow_sender should have been called.
        automod_noshow(pairing2)
        self.assertTrue(noshow_sender.called)
        self.assertEqual(noshow_sender.call_args[1]["player"], pairing2.black)
        self.assertEqual(noshow_sender.call_args[1]["opponent"], pairing2.white)
