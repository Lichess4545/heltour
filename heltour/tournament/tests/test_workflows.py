from django.test import TestCase
from heltour.tournament.models import Player
from heltour.tournament.workflows import ApproveRegistrationWorkflow, UpdateBoardOrderWorkflow
from heltour.tournament.tests.testutils import createCommonLeagueData, create_reg, get_player, get_season, set_rating, Shush


class TestLJPCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData(round_count=7)

    def test_ljp_none_rating(self, *args):
        new_player = Player.objects.create(lichess_username="newplayer", profile={"perfs": {"bullet": {"games": 50, "rating": 1650, "rd": 45, "prog": 10}}})
        season = get_season("lone")
        # creating a reg writes to the log, disable that temporarily for nicer test output
        with Shush():
            reg = create_reg(season, "newplayer")
        arw = ApproveRegistrationWorkflow(reg, 4)
        self.assertEqual(arw.default_byes, 2)
        self.assertEqual(arw.active_round_count, 3)
        self.assertEqual(arw.default_ljp, 0)


class UpdateBoardOrderWorkflow(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        s = get_season('team')
        cls.ubo = UpdateBoardOrderWorkflow(season=s)
        cls.players = []
        rating = 1000
        for player in Players.objects.all():
            rating += 100
            Player.objects.filter(pk=player.pk).update(profile={"perfs": {"classical": {"rating": rating}}})
            cls.players.append(player)

    def test_lone(self):
        self.ubo.run()
