from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from heltour.tournament.automod import automod_noshow
from heltour.tournament.models import LeagueSetting, LonePlayerPairing
from heltour.tournament.tests.testutils import createCommonLeagueData, get_league, get_player, get_round


class NoShowTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_noSetting_Confirmed(self):
        LeagueSetting.objects.filter(league__tag='teamleague').update(start_games=False)
        rd = get_round('team', round_number=1)
        player1 = get_player('Player1')
        player2 = get_player('Player2')
        pairing = LonePlayerPairing.objects.create(round=rd, white=player1, black=player2, game_link='https://lichess.org/KT837Aut', scheduled_time=timezone.now(), pairing_order=1, tv_state='has_moves')
        # Create MagicMock-Handler
        handler = MagicMock()
        handler.signals.notify_noshow.send(handler, sender='test')
        automod_noshow(pairing)
        handler.assert_not_called()
