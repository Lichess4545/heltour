import json
import logging
from django.test import TestCase
from heltour.tournament.models import Player
from heltour.tournament.workflows import ApproveRegistrationWorkflow
from heltour.tournament.tests.testutils import createCommonLeagueData, create_reg, get_season, set_rating


class TestLJPCase(TestCase):
    def setUp(self):
        createCommonLeagueData(round_count=7)
        players = Player.objects.all()
        rating = 1000
        for player in players:
            set_rating(player, rating)
            rating += 100
        set_rating(players[0], None)

    def test_ljp(self, *args):
        new_player = Player.objects.create(lichess_username="newplayer")
        new_player.profile = json.loads('{"perfs": {"bullet": {"games": 50, "rating": 1650, "rd": 45, "prog": 10}}}')
        new_player.save()
        season = get_season("lone")
        logging.disable(logging.CRITICAL)
        reg = create_reg(season, "newplayer")
        logging.disable(logging.NOTSET)
        arw = ApproveRegistrationWorkflow(reg, 4)
        self.assertEqual(arw.default_byes, 2)
        self.assertEqual(arw.active_round_count, 3)
        self.assertEqual(arw.default_ljp, 0)
