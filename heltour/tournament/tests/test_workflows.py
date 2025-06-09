from django.test import TestCase
from heltour.tournament.models import AlternatesManagerSetting, Player, TeamMember
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


class UpdateBoardOrderWorkflowTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.s = get_season('team')
        AlternatesManagerSetting(league=cls.s.league)
        cls.ubo = UpdateBoardOrderWorkflow(cls.s)
        cls.players = []
        rating = 1000
        for player in Player.objects.all():
            rating += 100
            Player.objects.filter(pk=player.pk).update(profile={"perfs": {"classical": {"rating": rating}}})
            cls.players.append(player)

    def test_lonewolf(self):
        self.assertEqual(UpdateBoardOrderWorkflow(get_season('lone')).run(alternates_only=True), None)

    def test_team_board_order(self):
        self.assertEqual(TeamMember.objects.get(player=self.players[0]).board_number, 1)
        self.assertEqual(TeamMember.objects.get(player=self.players[1]).board_number, 2)
        self.ubo.run(alternates_only=False)
        self.assertEqual(TeamMember.objects.get(player=self.players[0]).board_number, 2)
        self.assertEqual(TeamMember.objects.get(player=self.players[1]).board_number, 1)
