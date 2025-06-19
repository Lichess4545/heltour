from unittest.mock import PropertyMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.test.client import RequestFactory

from heltour.tournament.models import (
    AlternatesManagerSetting,
    Player,
    SeasonPlayer,
    TeamMember,
)
from heltour.tournament.tests.testutils import (
    Shush,
    create_reg,
    createCommonLeagueData,
    get_season,
)
from heltour.tournament.workflows import (
    ApproveRegistrationWorkflow,
    UpdateBoardOrderWorkflow,
)


class ApproveRegistrationWorkflowTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData(round_count=7)
        Player.objects.create(
            lichess_username="newplayer",
            profile={
                "perfs": {"bullet": {"games": 50, "rating": 1650, "rd": 45, "prog": 10}}
            },
            rating=1650,
        )
        cls.superuser = User.objects.create(
            username="superuser", password="password", is_superuser=True, is_staff=True
        )
        cls.season = get_season("lone")
        # creating a reg writes to the log,
        # disable that temporarily for nicer test output
        with Shush():
            cls.reg = create_reg(cls.season, "newplayer")
        cls.arw = ApproveRegistrationWorkflow(cls.reg, 4)
        cls.rf = RequestFactory()

    def test_ljp_none_rating(self):
        self.assertEqual(self.arw.default_byes, 2)
        self.assertEqual(self.arw.active_round_count, 3)
        self.assertEqual(self.arw.default_ljp, 0)

    @patch("django.contrib.admin.ModelAdmin.message_user", new_callable=PropertyMock)
    def test_approve_reg(self, model_admin):
        approve_request = self.rf.post("admin:approve_registration")
        approve_request.user = self.superuser
        self.assertEqual(self.reg.status, "pending")
        self.assertEqual(
            SeasonPlayer.objects.filter(player__lichess_username="newplayer").count(), 0
        )
        self.arw.approve_reg(
            approve_request,
            modeladmin=model_admin,
            send_confirm_email=False,
            invite_to_slack=False,
            season=self.season,
            retroactive_byes=0,
            late_join_points=0,
        )
        self.assertEqual(self.reg.status, "approved")
        self.assertEqual(
            SeasonPlayer.objects.filter(player__lichess_username="newplayer").count(), 1
        )


class UpdateBoardOrderWorkflowTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.s = get_season("team")
        AlternatesManagerSetting(league=cls.s.league)
        cls.ubo = UpdateBoardOrderWorkflow(cls.s)
        cls.players = []
        rating = 1000
        for player in Player.objects.all():
            rating += 100
            Player.objects.filter(pk=player.pk).update(
                profile={"perfs": {"classical": {"rating": rating}}}
            )
            cls.players.append(player)

    def test_lonewolf(self):
        self.assertEqual(
            UpdateBoardOrderWorkflow(get_season("lone")).run(alternates_only=True), None
        )

    def test_team_board_order(self):
        self.assertEqual(TeamMember.objects.get(player=self.players[0]).board_number, 1)
        self.assertEqual(TeamMember.objects.get(player=self.players[1]).board_number, 2)
        self.ubo.run(alternates_only=False)
        self.assertEqual(TeamMember.objects.get(player=self.players[0]).board_number, 2)
        self.assertEqual(TeamMember.objects.get(player=self.players[1]).board_number, 1)
