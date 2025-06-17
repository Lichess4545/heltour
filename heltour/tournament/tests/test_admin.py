from unittest.mock import patch

from django.contrib import admin, messages
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from heltour.tournament.models import (
    Alternate,
    LonePlayerPairing,
    Player,
    Round,
    Season,
    SeasonPlayer,
    Team,
    TeamMember,
    TeamPairing,
    TeamPlayerPairing,
)
from heltour.tournament.tests.testutils import (
    createCommonLeagueData,
    get_round,
    get_season,
)


class AdminSearchTestCase(TestCase):
    def test_all_search_fields(self):
        superuser = User(
            username="superuser",
            password="Password",
            is_superuser=True,
            is_staff=True,
        )
        superuser.save()
        self.client.force_login(user=superuser)
        for model_class, admin_class in admin.site._registry.items():
            with self.subTest(model_class._meta.model_name):
                path = reverse(
                    f"admin:{model_class._meta.app_label}_{model_class._meta.model_name}_changelist"
                )
                response = self.client.get(path + "?q=whatever")
                self.assertEqual(response.status_code, 200)


class SeasonAdminTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.superuser = User.objects.create(
            username="superuser", password="password", is_superuser=True, is_staff=True
        )
        cls.t1 = Team.objects.get(number=1)
        cls.t2 = Team.objects.get(number=2)
        cls.r1 = get_round("team", 1)
        Round.objects.filter(pk=cls.r1.pk).update(publish_pairings=True)
        cls.tp1 = TeamPairing.objects.create(
            white_team=cls.t1, black_team=cls.t2, round=cls.r1, pairing_order=1
        )
        cls.p1 = Player.objects.get(lichess_username="Player1")
        cls.p2 = Player.objects.get(lichess_username="Player2")
        cls.p3 = Player.objects.get(lichess_username="Player3")
        cls.p4 = Player.objects.get(lichess_username="Player4")
        cls.s = get_season("team")
        cls.sp1 = SeasonPlayer.objects.create(player=cls.p1, season=cls.s)
        cls.path_s_changelist = reverse("admin:tournament_season_changelist")
        cls.path_m_p = reverse("admin:manage_players", args=[cls.s.pk])

    @patch("heltour.tournament.simulation.simulate_season")
    @patch("django.contrib.admin.ModelAdmin.message_user")
    def test_simulate(self, message, simulate):
        self.client.force_login(user=self.superuser)
        self.client.post(
            self.path_s_changelist,
            data={
                "action": "simulate_tournament",
                "_selected_action": get_season("lone").pk,
            },
            follow=True,
        )
        self.assertTrue(simulate.called)
        self.assertTrue(message.called)
        self.assertEqual(message.call_args.args[1], "Simulation complete.")

    @patch("heltour.tournament.models.Season.calculate_scores")
    @patch("heltour.tournament.models.TeamPairing.refresh_points")
    @patch("heltour.tournament.models.TeamPairing.save")
    @patch("django.contrib.admin.ModelAdmin.message_user")
    def test_recalculate(self, message, tpsave, tprefresh, scalculate):
        self.client.force_login(user=self.superuser)
        self.client.post(
            self.path_s_changelist,
            data={
                "action": "recalculate_scores",
                "_selected_action": get_season("lone").pk,
            },
            follow=True,
        )
        self.assertFalse(tprefresh.called)
        self.assertFalse(tpsave.called)
        self.assertTrue(scalculate.called)
        self.assertTrue(message.called)
        self.assertEqual(message.call_args.args[1], "Scores recalculated.")
        message.reset_mock()
        scalculate.reset_mock()
        self.client.post(
            self.path_s_changelist,
            data={
                "action": "recalculate_scores",
                "_selected_action": Season.objects.all().values_list("pk", flat=True),
            },
            follow=True,
        )
        self.assertTrue(tprefresh.called)
        self.assertTrue(tpsave.called)
        self.assertTrue(scalculate.called)
        self.assertEqual(scalculate.call_count, 2)
        self.assertTrue(message.called)
        self.assertEqual(message.call_args.args[1], "Scores recalculated.")

    @patch("django.contrib.admin.ModelAdmin.message_user")
    @patch(
        "heltour.tournament.admin.normalize_gamelink",
        side_effect=[("incorrectlink1", False), ("mockedlink2", True)],
    )
    def test_verify(self, gamelink, message):
        self.client.force_login(user=self.superuser)
        self.client.post(
            self.path_s_changelist,
            data={
                "action": "verify_data",
                "_selected_action": Season.objects.all().values_list("pk", flat=True),
            },
            follow=True,
        )
        self.assertTrue(message.called)
        self.assertEqual(message.call_args.args[1], "Data verified.")
        message.reset_mock()
        lr1 = get_round("lone", 1)
        lpp1 = LonePlayerPairing.objects.create(
            round=lr1,
            white=self.p1,
            black=self.p2,
            game_link="incorrectlink1",
            pairing_order=0,
        )
        lpp2 = LonePlayerPairing.objects.create(
            round=lr1,
            white=self.p3,
            black=self.p4,
            game_link="incorrectlink2",
            pairing_order=1,
        )
        self.client.post(
            self.path_s_changelist,
            data={
                "action": "verify_data",
                "_selected_action": Season.objects.all().values_list("pk", flat=True),
            },
            follow=True,
        )
        lpp2.refresh_from_db()
        self.assertEqual(gamelink.call_count, 2)
        self.assertTrue(message.call_count, 2)
        self.assertEqual(
            message.call_args_list[0][0][1], "1 bad gamelinks for Test Season."
        )
        self.assertEqual(message.call_args_list[1][0][1], "Data verified.")
        self.assertEqual(lpp1.game_link, "incorrectlink1")
        self.assertEqual(lpp2.game_link, "mockedlink2")

    @patch("django.contrib.admin.ModelAdmin.message_user")
    def test_review_nominated(self, message):
        self.client.force_login(user=self.superuser)
        TeamPlayerPairing.objects.create(
            white=self.p1,
            black=self.p2,
            board_number=1,
            team_pairing=self.tp1,
            game_link="https://lichess.org/rgame01",
        )
        TeamPlayerPairing.objects.create(
            white=self.p3,
            black=self.p4,
            board_number=2,
            team_pairing=self.tp1,
            game_link="https://lichess.org/rgame02",
        )
        response = self.client.post(
            self.path_s_changelist,
            data={
                "action": "review_nominated_games",
                "_selected_action": Season.objects.all().values_list("pk", flat=True),
            },
            follow=True,
        )
        self.assertTrue(message.called)
        self.assertEqual(
            message.call_args.args[1],
            "Nominated games can only be reviewed one season at a time.",
        )
        message.reset_mock()
        response = self.client.post(
            self.path_s_changelist,
            data={"action": "review_nominated_games", "_selected_action": self.s.pk},
            follow=True,
        )
        self.assertEqual(response.context["original"], self.s)
        self.assertEqual(response.context["title"], "Review nominated games")
        self.assertEqual(response.context["nominations"], [])
        self.assertFalse(message.called)
        Season.objects.filter(pk=self.s.pk).update(nominations_open=True)
        response = self.client.post(
            self.path_s_changelist,
            data={"action": "review_nominated_games", "_selected_action": self.s.pk},
            follow=True,
        )
        self.assertTrue(message.called)
        self.assertEqual(
            message.call_args.args[1],
            "Nominations are still open. You should edit the season and close nominations before reviewing.",
        )

    @patch("django.contrib.admin.ModelAdmin.message_user")
    def test_round_transition(self, message):
        self.client.force_login(user=self.superuser)
        response = self.client.post(
            self.path_s_changelist,
            data={
                "action": "round_transition",
                "_selected_action": Season.objects.all().values_list("pk", flat=True),
            },
            follow=True,
        )
        self.assertTrue(message.called)
        self.assertEqual(
            message.call_args.args[1],
            "Rounds can only be transitioned one season at a time.",
        )
        message.reset_mock()
        response = self.client.post(
            self.path_s_changelist,
            data={"action": "round_transition", "_selected_action": self.s.pk},
            follow=True,
        )
        self.assertFalse(message.called)
        self.assertTemplateUsed(response, "tournament/admin/round_transition.html")

    @patch("django.contrib.admin.ModelAdmin.message_user")
    @patch(
        "heltour.tournament.workflows.RoundTransitionWorkflow.run",
        return_value=[("workflow_mock", messages.INFO)],
    )
    def test_round_transition_view(self, workflow, message):
        self.client.force_login(user=self.superuser)
        path = reverse("admin:round_transition", args=[self.s.pk])
        # test invalid form
        response = self.client.post(
            path, data={"round_to_open": 2, "generate_pairings": True}, follow=True
        )
        self.assertFalse(message.called)
        self.assertTemplateUsed(response, "tournament/admin/round_transition.html")
        # test valid form
        response = self.client.post(
            path,
            data={"round_to_close": 1, "round_to_open": 2, "generate_pairings": True},
            follow=True,
        )
        self.assertTrue(message.called)
        self.assertEqual(message.call_args.args[1], "workflow_mock")
        self.assertTemplateUsed(response, "tournament/admin/review_team_pairings.html")
        # don't generate pairings
        response = self.client.post(
            path,
            data={"round_to_close": 1, "round_to_open": 2, "generate_pairings": False},
            follow=True,
        )
        self.assertTemplateUsed(response, "admin/change_list.html")

    @patch("django.contrib.admin.ModelAdmin.message_user")
    def test_team_spam(self, message):
        self.client.force_login(user=self.superuser)
        path = reverse("admin:tournament_season_changelist")
        response = self.client.post(
            path,
            data={
                "action": "team_spam",
                "_selected_action": Season.objects.all().values_list("pk", flat=True),
            },
            follow=True,
        )
        self.assertTrue(message.called)
        self.assertEqual(
            message.call_args.args[1],
            "Team spam can only be sent one season at a time.",
        )
        message.reset_mock()
        response = self.client.post(
            path,
            data={"action": "team_spam", "_selected_action": self.s.pk},
            follow=True,
        )
        self.assertFalse(message.called)
        self.assertTemplateUsed(response, "tournament/admin/team_spam.html")

    @patch("heltour.tournament.slackapi.send_message")
    @patch("django.contrib.admin.ModelAdmin.message_user")
    def test_team_spam_view(self, message, slack_message):
        self.client.force_login(user=self.superuser)
        path = reverse("admin:team_spam", args=[self.s.pk])
        # no confirm_send, no messages
        response = self.client.post(
            path,
            data={"text": "message sent to teams", "confirm_send": False},
            follow=True,
        )
        self.assertFalse(message.called)
        self.assertFalse(slack_message.called)
        self.assertTemplateUsed(response, "tournament/admin/team_spam.html")
        # teams have no slack channels
        response = self.client.post(
            path,
            data={"text": "message sent to teams", "confirm_send": True},
            follow=True,
        )
        self.assertTrue(message.called)
        self.assertEqual(
            message.call_args.args[1], "Spam sent to 4 teams."
        )  # bug that should be fixed, spam was not sent to 4 teams.
        self.assertFalse(slack_message.called)
        self.assertTemplateUsed(response, "admin/change_list.html")
        # create slack channels
        Team.objects.all().update(slack_channel="channel")
        response = self.client.post(
            path,
            data={"text": "message sent to teams", "confirm_send": True},
            follow=True,
        )
        self.assertTrue(message.called)
        self.assertEqual(
            message.call_args.args[1], "Spam sent to 4 teams."
        )  # correct now.
        self.assertEqual(slack_message.call_count, 4)
        self.assertEqual(slack_message.call_args.args[1], "message sent to teams")
        self.assertTemplateUsed(response, "admin/change_list.html")

    def test_manage_players_add_delete_alternate(self):
        Season.objects.filter(pk=self.s.pk).update(start_date=timezone.now())
        self.client.force_login(user=self.superuser)
        self.client.post(
            self.path_m_p,
            data={
                "changes": '[{"action": "create-alternate", "board_number": 1, "player_name": "Player1"}]'
            },
        )
        # check that the correct alternate was created
        self.assertEqual(Alternate.objects.all().count(), 1)
        self.assertEqual(
            Alternate.objects.all().first().season_player.player.lichess_username,
            "Player1",
        )
        self.client.post(
            self.path_m_p,
            data={
                "changes": '[{"action": "delete-alternate", "board_number": 1, "player_name": "Player1"}]'
            },
        )
        self.assertEqual(Alternate.objects.all().count(), 0)

    @patch("django.contrib.admin.ModelAdmin.message_user")
    def test_manage_players_switch_team_players(self, message):
        # assert the correct team player order
        self.assertEqual(
            TeamMember.objects.get(team=self.t1, board_number=1).player, self.p1
        )
        self.assertEqual(
            TeamMember.objects.get(team=self.t2, board_number=1).player, self.p3
        )
        self.client.force_login(user=self.superuser)
        # switch team players between teams
        datastring = (
            '[{"action": "change-member", "team_number": 1, "board_number": 1,'
            ' "player": {"name": "Player3", "is_captain": false, "is_vice_captain": false}}, '
            '{"action": "change-member", "team_number": 2, "board_number": 1,'
            ' "player": {"name": "Player1", "is_captain": false, "is_vice_captain": false}}]'
        )
        self.client.post(
            self.path_m_p,
            data={"changes": datastring},
        )
        self.assertFalse(message.called)
        # assert new order
        self.assertEqual(
            TeamMember.objects.get(team=self.t1, board_number=1).player, self.p3
        )
        self.assertEqual(
            TeamMember.objects.get(team=self.t2, board_number=1).player, self.p1
        )
        # try malformed data
        self.client.post(
            self.path_m_p,
            data={
                "changes": (
                    '[{"action": "change-member",'
                    '"team_number": 1, "board_nuber": 1}]'
                )
            },
        )
        # message should be called allerting us to the problem
        self.assertTrue(message.called)
        self.assertEqual(message.call_args[0][1], "Some changes could not be saved.")

    @patch("django.contrib.admin.ModelAdmin.message_user")
    def test_manage_players_empty_team_player(self, message):
        # assert the correct team player order
        self.assertEqual(
            TeamMember.objects.get(team=self.t1, board_number=1).player, self.p1
        )
        self.client.force_login(user=self.superuser)
        # switch team players between teams
        datastring = (
            '[{"action": "change-member", "team_number": 1, "board_number": 1,'
            ' "player": null}]'
        )
        self.client.post(
            self.path_m_p,
            data={"changes": datastring},
        )
        self.assertFalse(message.called)
        self.assertEqual(
            TeamMember.objects.filter(team=self.t1, board_number=1).count(), 0
        )


class SeasonAdminNoPublishedPairingsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.superuser = User.objects.create(
            username="superuser", password="password", is_superuser=True, is_staff=True
        )
        cls.t1 = Team.objects.get(number=1)
        cls.p1 = Player.objects.get(lichess_username="Player1")
        cls.s = get_season("team")
        cls.sp1 = SeasonPlayer.objects.create(player=cls.p1, season=cls.s)
        cls.path_m_p = reverse("admin:manage_players", args=[cls.s.pk])

    @patch("django.contrib.admin.ModelAdmin.message_user")
    def test_change_team(self, message):
        # assert the correct team player order
        self.assertEqual(self.t1.name, "Team 1")
        self.client.force_login(user=self.superuser)
        # rename team
        datastring = (
            '[{"action": "change-team", "team_number": 1, "team_name": "TestTeam"}]'
        )
        self.client.post(
            self.path_m_p,
            data={"changes": datastring},
        )
        self.assertFalse(message.called)
        self.assertEqual(Team.objects.get(pk=self.t1.pk).name, "TestTeam")

    @patch("django.contrib.admin.ModelAdmin.message_user")
    def test_create_team(self, message):
        self.assertEqual(Team.objects.all().count(), 4)
        self.client.force_login(user=self.superuser)
        datastring = (
            '[{"action": "create-team", "team_number": 5, '
            '"model": {"number": 5, "name": "AddTeam", "boards": ['
            '{"name": "Player1", "is_captain": false},'
            '{"name": "Player2", "is_captain": true}]}}]'
        )
        self.client.post(
            self.path_m_p,
            data={"changes": datastring},
        )
        self.assertEqual(Team.objects.all().count(), 5)
        self.assertEqual(Team.objects.get(number=5).name, "AddTeam")
        self.assertFalse(message.called)
