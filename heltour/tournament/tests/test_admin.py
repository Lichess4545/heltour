from unittest.mock import ANY, patch

from django.contrib import admin, messages
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from heltour.tournament.models import (
    Alternate,
    AlternateAssignment,
    AlternateSearch,
    InviteCode,
    KnockoutAdvancement,
    KnockoutBracket,
    KnockoutSeeding,
    League,
    LonePlayerPairing,
    Player,
    Round,
    Season,
    SeasonPlayer,
    Team,
    TeamBye,
    TeamMember,
    TeamMultiMatchProgress,
    TeamPairing,
    TeamPlayerPairing,
    TeamScore,
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
        cls.t3 = Team.objects.get(number=3)
        cls.t4 = Team.objects.get(number=4)
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

    @patch("django.contrib.admin.ModelAdmin.message_user")
    @patch("heltour.tournament.signals.do_create_broadcast.send")
    def test_create_several_broadcasts(self, dcb, message):
        self.client.force_login(user=self.superuser)
        self.client.post(
            reverse("admin:tournament_season_changelist"),
            data={
                "action": "create_broadcast",
                "_selected_action": Season.objects.all().values_list("pk", flat=True)
            },
            follow=True,
        )
        message.assert_called_once_with(
            ANY,
            "Can only create one broadcast at a time.",
            ANY
        )
        dcb.assert_not_called()


    @patch("heltour.tournament.simulation.simulate_season")
    @patch("django.contrib.admin.ModelAdmin.message_user")
    def test_simulate(self, message, simulate):
        with self.settings(DEBUG=True, STAGING=False):
            from django.conf import settings
            self.client.force_login(user=self.superuser)
            self.client.post(
                self.path_s_changelist,
                data={
                    "action": "simulate_tournament",
                    "_selected_action": get_season("lone").pk,
                },
                follow=True,
            )
            self.assertTrue(message.called)
            self.assertEqual(message.call_args.args[1], "Simulation complete.")
            self.assertTrue(simulate.called)

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
        self.assertEqual(message.call_args[0][1], "Data verified.")
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
                    '[{"action": "change-member","team_number": 1, "board_nuber": 1}]'
                )
            },
        )
        # message should be called allerting us to the problem
        self.assertTrue(message.called)
        self.assertEqual(message.call_args.args[1], "Some changes could not be saved.")

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

    def test_manage_players_get(self):
        # assert the correct team player order
        self.client.force_login(user=self.superuser)
        response = self.client.get(self.path_m_p)
        self.assertIn("red_players", response.context)
        self.assertIn("blue_players", response.context)
        self.assertIn("green_players", response.context)
        self.assertIn("purple_players", response.context)
        self.assertIn("unassigned_by_board", response.context)
        self.assertIn("teams", response.context)
        self.assertEqual(response.context["red_players"], {self.p1})
        self.assertEqual(response.context["blue_players"], set())
        self.assertEqual(response.context["green_players"], set())
        self.assertEqual(response.context["purple_players"], set())
        self.assertEqual(response.context["unassigned_by_board"], [(1, []), (2, [])])
        self.assertEqual(
            response.context["teams"], [self.t1, self.t2, self.t3, self.t4]
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


class TeamCopyAdminTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.superuser = User.objects.create(
            username="superuser", password="password", is_superuser=True, is_staff=True
        )
        
        # Get existing teams and season
        cls.original_season = get_season("team")
        cls.original_teams = Team.objects.filter(season=cls.original_season)[:2]  # Get first 2 teams
        
        # Create a new compatible season (same league, same boards)
        from heltour.tournament.models import League
        cls.target_league = League.objects.create(
            name="Test Target League",
            tag="TTL",
            competitor_type="team"
        )
        cls.target_season = Season.objects.create(
            league=cls.target_league,
            name="Target Season",
            tag="TS",
            rounds=10,  # Required field
            boards=2,  # Same as original (createCommonLeagueData uses 2 boards)
            is_active=True
        )
        
        # Create incompatible season (different boards)
        cls.incompatible_season = Season.objects.create(
            league=cls.target_league,
            name="Incompatible Season", 
            tag="IS",
            rounds=10,  # Required field
            boards=6,  # Different boards
            is_active=True
        )

    def test_copy_teams_to_season_view_get(self):
        """Test the GET request shows the form with compatible seasons"""
        self.client.force_login(user=self.superuser)
        team_ids = ','.join([str(team.id) for team in self.original_teams])
        response = self.client.get(f'/admin/tournament/team/copy_teams_to_season/?team_ids={team_ids}')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Copy Teams to New Season')
        self.assertContains(response, self.target_season.name)
        self.assertNotContains(response, self.incompatible_season.name)  # Should not show incompatible
        
        # Check teams are displayed
        for team in self.original_teams:
            self.assertContains(response, team.name)

    def test_copy_teams_success(self):
        """Test successful team copying"""
        self.client.force_login(user=self.superuser)
        team_ids = ','.join([str(team.id) for team in self.original_teams])
        
        # Count teams before
        original_count = Team.objects.filter(season=self.target_season).count()
        
        # Post the copy request
        response = self.client.post(
            f'/admin/tournament/team/copy_teams_to_season/?team_ids={team_ids}',
            data={'target_season': self.target_season.id},
            follow=True
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Successfully copied 2 teams')
        
        # Check teams were created
        new_teams = Team.objects.filter(season=self.target_season)
        self.assertEqual(new_teams.count(), original_count + 2)
        
        # Verify team data was copied correctly
        for original_team in self.original_teams:
            copied_team = new_teams.get(name=original_team.name)
            self.assertEqual(copied_team.company_name, original_team.company_name)
            self.assertEqual(copied_team.company_address, original_team.company_address)
            self.assertEqual(copied_team.team_contact_email, original_team.team_contact_email)
            self.assertEqual(copied_team.team_contact_number, original_team.team_contact_number)
            self.assertTrue(copied_team.is_active)
            self.assertEqual(copied_team.slack_channel, '')  # Should be blank
            self.assertEqual(copied_team.seed_rating, original_team.seed_rating)  # Should match original
            
            # Verify TeamScore object was created (required for standings)
            self.assertTrue(hasattr(copied_team, 'teamscore'))
            team_score = copied_team.teamscore
            self.assertIsNotNone(team_score)
            self.assertEqual(team_score.team, copied_team)
            
            # Check team members were copied
            original_members = original_team.teammember_set.all()
            copied_members = copied_team.teammember_set.all()
            self.assertEqual(copied_members.count(), original_members.count())
            
            for original_member in original_members:
                copied_member = copied_members.get(board_number=original_member.board_number)
                self.assertEqual(copied_member.player, original_member.player)
                self.assertEqual(copied_member.is_captain, original_member.is_captain)
                self.assertEqual(copied_member.is_vice_captain, original_member.is_vice_captain)
                
                # Check player was registered for target season
                self.assertTrue(
                    SeasonPlayer.objects.filter(
                        season=self.target_season,
                        player=original_member.player
                    ).exists()
                )

    def test_team_number_assignment(self):
        """Test that team numbers are assigned correctly using max + 1"""
        self.client.force_login(user=self.superuser)
        
        # Create an existing team with number 3 in target season
        existing_team = Team.objects.create(
            season=self.target_season,
            number=3,
            name="Existing Team",
            company_name="Existing Co",
            is_active=True
        )
        
        team_ids = str(self.original_teams[0].id)
        response = self.client.post(
            f'/admin/tournament/team/copy_teams_to_season/?team_ids={team_ids}',
            data={'target_season': self.target_season.id},
            follow=True
        )
        
        self.assertEqual(response.status_code, 200)
        
        # New team should get number 4 (max 3 + 1)
        new_team = Team.objects.filter(season=self.target_season, name=self.original_teams[0].name).first()
        self.assertIsNotNone(new_team)
        self.assertEqual(new_team.number, 4)

    def test_duplicate_team_name_handling(self):
        """Test that duplicate team names are handled by appending numbers"""
        self.client.force_login(user=self.superuser)
        
        # Create an existing team with the same name as one we'll copy
        original_team_name = self.original_teams[0].name
        Team.objects.create(
            season=self.target_season,
            number=1,
            name=original_team_name,  # Same name as original team
            company_name="Existing Co",
            is_active=True
        )
        
        # Copy the team
        team_ids = str(self.original_teams[0].id)
        response = self.client.post(
            f'/admin/tournament/team/copy_teams_to_season/?team_ids={team_ids}',
            data={'target_season': self.target_season.id},
            follow=True
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Successfully copied 1 teams')
        
        # Check that the copied team has a modified name
        copied_team = Team.objects.filter(
            season=self.target_season, 
            name=f"{original_team_name} (2)"
        ).first()
        self.assertIsNotNone(copied_team)
        self.assertEqual(copied_team.name, f"{original_team_name} (2)")
        
        # Verify the original name team still exists
        original_name_team = Team.objects.filter(
            season=self.target_season,
            name=original_team_name
        ).first()
        self.assertIsNotNone(original_name_team)

    def test_board_order_editing_after_copy(self):
        """Test that board order editing works on copied teams"""
        self.client.force_login(user=self.superuser)
        
        # Copy a team first
        team_ids = str(self.original_teams[0].id)
        self.client.post(
            f'/admin/tournament/team/copy_teams_to_season/?team_ids={team_ids}',
            data={'target_season': self.target_season.id}
        )
        
        # Get the copied team
        copied_team = Team.objects.get(season=self.target_season, name=self.original_teams[0].name)
        copied_members = list(copied_team.teammember_set.order_by('board_number'))
        
        # Verify we have team members to work with
        self.assertGreater(len(copied_members), 1)
        
        # Test the board order editing action
        response = self.client.post(
            reverse('admin:tournament_team_changelist'),
            data={
                'action': 'update_board_order_by_rating',
                '_selected_action': [copied_team.id]
            },
            follow=True
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Board order updated')
        
        # Verify board order was updated (members should be reordered by rating)
        updated_members = list(copied_team.teammember_set.order_by('board_number'))
        
        # Check that all members still exist and have valid board numbers
        self.assertEqual(len(updated_members), len(copied_members))
        for i, member in enumerate(updated_members):
            self.assertEqual(member.board_number, i + 1)

    def test_copy_teams_permission_denied(self):
        """Test that copying fails without proper permissions"""
        # Create a non-superuser
        regular_user = User.objects.create(
            username="regular", password="password", is_staff=True
        )
        self.client.force_login(user=regular_user)
        
        team_ids = str(self.original_teams[0].id)
        
        # Should return error message instead of raising exception
        response = self.client.post(
            f'/admin/tournament/team/copy_teams_to_season/?team_ids={team_ids}',
            data={'target_season': self.target_season.id},
            follow=True
        )
        
        # Should contain permission error or redirect back to team list
        self.assertEqual(response.status_code, 200)

    def test_copy_teams_invalid_target_season(self):
        """Test error handling for invalid target season"""
        self.client.force_login(user=self.superuser)
        team_ids = str(self.original_teams[0].id)

        response = self.client.post(
            f'/admin/tournament/team/copy_teams_to_season/?team_ids={team_ids}',
            data={'target_season': 99999},  # Non-existent season
            follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid target season')


class TeamMoveAdminTestCase(TestCase):
    """Tests for the move_teams_to_new_season admin action."""

    MOVE_URL = "/admin/tournament/team/move_teams_to_season/"

    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.superuser = User.objects.create(
            username="superuser",
            password="password",
            is_superuser=True,
            is_staff=True,
        )
        cls.source_season = get_season("team")
        cls.source_league = cls.source_season.league
        cls.t1 = Team.objects.get(season=cls.source_season, number=1)
        cls.t2 = Team.objects.get(season=cls.source_season, number=2)
        cls.t3 = Team.objects.get(season=cls.source_season, number=3)
        cls.t4 = Team.objects.get(season=cls.source_season, number=4)

        # Compatible target league/season (same boards as source: 2)
        cls.target_league = League.objects.create(
            name="Move Target League",
            tag="MTL",
            competitor_type="team",
            rating_type="classical",
        )
        cls.target_season = Season.objects.create(
            league=cls.target_league,
            name="Move Target Season",
            tag="MTS",
            rounds=3,
            boards=2,
            is_active=True,
        )
        # Different-board season — must NOT be offered as a target.
        cls.incompatible_season = Season.objects.create(
            league=cls.target_league,
            name="Incompatible Boards Season",
            tag="IBS",
            rounds=3,
            boards=4,
            is_active=True,
        )
        # Another season inside the SOURCE league — used to verify same-league moves work.
        cls.same_league_other_season = Season.objects.create(
            league=cls.source_league,
            name="Source League Other Season",
            tag="slother",
            rounds=3,
            boards=2,
            is_active=True,
        )

    def _post_move(self, team_ids, target_season_id, follow=True):
        ids_param = ",".join(str(i) for i in team_ids)
        return self.client.post(
            f"{self.MOVE_URL}?team_ids={ids_param}",
            data={"target_season": target_season_id},
            follow=follow,
        )

    # ---------------- view rendering ----------------

    def test_move_view_get_renders_form_with_compatible_seasons(self):
        self.client.force_login(user=self.superuser)
        ids = ",".join(str(t.id) for t in [self.t1, self.t2])
        response = self.client.get(f"{self.MOVE_URL}?team_ids={ids}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Move Teams to New Season")
        self.assertContains(response, self.t1.name)
        self.assertContains(response, self.t2.name)
        self.assertContains(response, self.target_season.name)
        # Source season should not appear in target dropdown.
        self.assertNotContains(response, f'value="{self.source_season.id}"')
        # Incompatible season should not be offered.
        self.assertNotContains(response, self.incompatible_season.name)
        # All teams unblocked → form is shown.
        self.assertContains(response, "Move Teams")

    def test_move_view_get_no_team_ids_redirects(self):
        self.client.force_login(user=self.superuser)
        response = self.client.get(self.MOVE_URL, follow=True)
        # Falls through the no-ids branch and lands on the changelist.
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No teams selected")

    def test_move_view_get_invalid_team_ids_redirects(self):
        self.client.force_login(user=self.superuser)
        response = self.client.get(f"{self.MOVE_URL}?team_ids=foo,bar", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid team IDs")

    def test_move_view_get_unknown_team_ids_redirects(self):
        self.client.force_login(user=self.superuser)
        response = self.client.get(f"{self.MOVE_URL}?team_ids=99998,99999", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No valid teams found")

    # ---------------- happy-path moves ----------------

    def test_move_single_team_success(self):
        self.client.force_login(user=self.superuser)
        original_pk = self.t1.pk
        original_score_pk = self.t1.teamscore.pk
        original_member_pks = list(
            self.t1.teammember_set.values_list("pk", flat=True)
        )

        response = self._post_move([self.t1.id], self.target_season.id)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Successfully moved 1 teams")

        moved = Team.objects.get(pk=original_pk)
        self.assertEqual(moved.season_id, self.target_season.id)
        # Same Team row, same TeamScore row (NOT recreated).
        self.assertEqual(moved.teamscore.pk, original_score_pk)
        self.assertEqual(
            sorted(moved.teammember_set.values_list("pk", flat=True)),
            sorted(original_member_pks),
        )
        # Original season no longer has this team.
        self.assertFalse(
            Team.objects.filter(season=self.source_season, pk=original_pk).exists()
        )

    def test_move_multiple_teams_success(self):
        self.client.force_login(user=self.superuser)
        response = self._post_move([self.t1.id, self.t2.id], self.target_season.id)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Successfully moved 2 teams")

        self.assertEqual(
            Team.objects.filter(
                season=self.target_season, pk__in=[self.t1.pk, self.t2.pk]
            ).count(),
            2,
        )
        # Source season is left with only the remaining (unmoved) teams.
        remaining = set(
            Team.objects.filter(season=self.source_season).values_list(
                "pk", flat=True
            )
        )
        self.assertEqual(remaining, {self.t3.pk, self.t4.pk})

    def test_move_preserves_team_attributes(self):
        self.client.force_login(user=self.superuser)
        # Set distinguishable values on t1 before move.
        self.t1.company_name = "Acme Inc"
        self.t1.company_address = "1 Main St"
        self.t1.team_contact_email = "captain@acme.test"
        self.t1.seed_rating = 1850
        self.t1.is_active = True
        self.t1.slack_channel = "#acme-old"
        self.t1.save()

        self._post_move([self.t1.id], self.target_season.id)

        moved = Team.objects.get(pk=self.t1.pk)
        self.assertEqual(moved.company_name, "Acme Inc")
        self.assertEqual(moved.company_address, "1 Main St")
        self.assertEqual(moved.team_contact_email, "captain@acme.test")
        self.assertEqual(moved.seed_rating, 1850)
        self.assertTrue(moved.is_active)
        # Slack channel is cleared since it was tied to the source season.
        self.assertEqual(moved.slack_channel, "")

    def test_move_creates_seasonplayer_in_target_season(self):
        self.client.force_login(user=self.superuser)
        member_players = list(self.t1.teammember_set.values_list("player_id", flat=True))
        # Sanity: no SeasonPlayer rows in target season for these players yet.
        self.assertFalse(
            SeasonPlayer.objects.filter(
                season=self.target_season, player_id__in=member_players
            ).exists()
        )

        self._post_move([self.t1.id], self.target_season.id)

        # All members are now registered in target season.
        for player_id in member_players:
            self.assertTrue(
                SeasonPlayer.objects.filter(
                    season=self.target_season, player_id=player_id
                ).exists()
            )

    def test_move_does_not_duplicate_existing_seasonplayer(self):
        self.client.force_login(user=self.superuser)
        member = self.t1.teammember_set.first()
        # Pre-create a SeasonPlayer in the target season.
        existing_sp = SeasonPlayer.objects.create(
            season=self.target_season, player=member.player
        )

        self._post_move([self.t1.id], self.target_season.id)

        sps = SeasonPlayer.objects.filter(
            season=self.target_season, player=member.player
        )
        self.assertEqual(sps.count(), 1)
        self.assertEqual(sps.first().pk, existing_sp.pk)

    def test_move_assigns_next_team_number_in_target(self):
        self.client.force_login(user=self.superuser)
        # Pre-populate target season with team #7.
        Team.objects.create(
            season=self.target_season,
            number=7,
            name="PreExisting",
            company_name="X",
            is_active=True,
        )

        self._post_move([self.t1.id], self.target_season.id)
        moved = Team.objects.get(pk=self.t1.pk)
        self.assertEqual(moved.number, 8)

    def test_move_resolves_name_collision_with_counter_suffix(self):
        self.client.force_login(user=self.superuser)
        original_name = self.t1.name
        # A team with the same name already exists in the target season.
        Team.objects.create(
            season=self.target_season,
            number=99,
            name=original_name,
            company_name="X",
            is_active=True,
        )

        self._post_move([self.t1.id], self.target_season.id)
        moved = Team.objects.get(pk=self.t1.pk)
        self.assertEqual(moved.name, f"{original_name} (2)")

    def test_move_resolves_name_collision_with_existing_2_suffix(self):
        self.client.force_login(user=self.superuser)
        original_name = self.t1.name
        Team.objects.create(
            season=self.target_season,
            number=98,
            name=original_name,
            company_name="X",
            is_active=True,
        )
        Team.objects.create(
            season=self.target_season,
            number=99,
            name=f"{original_name} (2)",
            company_name="X",
            is_active=True,
        )

        self._post_move([self.t1.id], self.target_season.id)
        moved = Team.objects.get(pk=self.t1.pk)
        self.assertEqual(moved.name, f"{original_name} (3)")

    def test_move_renumbers_when_collision_in_target(self):
        """Two teams with the same number in source can be moved into a new season."""
        self.client.force_login(user=self.superuser)
        # t1.number=1 collides with nothing yet in target. Pre-fill #1 anyway.
        Team.objects.create(
            season=self.target_season,
            number=1,
            name="Existing One",
            company_name="X",
            is_active=True,
        )
        self._post_move([self.t1.id, self.t2.id], self.target_season.id)
        # Both moved teams should have unique numbers > 1.
        moved_numbers = sorted(
            Team.objects.filter(pk__in=[self.t1.pk, self.t2.pk]).values_list(
                "number", flat=True
            )
        )
        self.assertEqual(moved_numbers, [2, 3])

    def test_move_across_leagues(self):
        self.client.force_login(user=self.superuser)
        self.assertNotEqual(self.target_season.league_id, self.source_season.league_id)
        self._post_move([self.t1.id], self.target_season.id)
        moved = Team.objects.get(pk=self.t1.pk)
        self.assertEqual(moved.season.league_id, self.target_league.id)

    def test_move_within_same_league(self):
        self.client.force_login(user=self.superuser)
        self._post_move([self.t1.id], self.same_league_other_season.id)
        moved = Team.objects.get(pk=self.t1.pk)
        self.assertEqual(moved.season_id, self.same_league_other_season.id)
        self.assertEqual(moved.season.league_id, self.source_league.id)

    def test_move_keeps_same_teamscore_row(self):
        self.client.force_login(user=self.superuser)
        score_pk = self.t1.teamscore.pk
        self._post_move([self.t1.id], self.target_season.id)
        # No new TeamScore created; the original was preserved (still all-zero).
        self.assertEqual(TeamScore.objects.filter(team_id=self.t1.pk).count(), 1)
        self.assertEqual(TeamScore.objects.get(team_id=self.t1.pk).pk, score_pk)

    # ---------------- blocker tests ----------------

    def _assert_move_blocked(self, team, expected_blocker_text):
        """POST a move and confirm it was blocked + team did not change season."""
        original_season_id = team.season_id
        response = self._post_move([team.id], self.target_season.id)
        self.assertEqual(response.status_code, 200)
        # Team did NOT move.
        team.refresh_from_db()
        self.assertEqual(team.season_id, original_season_id)
        # The blocker text is shown on the rendered page.
        self.assertContains(response, expected_blocker_text)
        # And the success banner is NOT.
        self.assertNotContains(response, "Successfully moved")

    def test_blocked_by_team_pairing(self):
        self.client.force_login(user=self.superuser)
        round1 = Round.objects.get(season=self.source_season, number=1)
        TeamPairing.objects.create(
            white_team=self.t1,
            black_team=self.t2,
            round=round1,
            pairing_order=1,
        )
        self._assert_move_blocked(self.t1, "team pairing")

    def test_blocked_by_team_bye(self):
        self.client.force_login(user=self.superuser)
        round1 = Round.objects.get(season=self.source_season, number=1)
        TeamBye.objects.create(round=round1, team=self.t1, type="full-point-bye")
        self._assert_move_blocked(self.t1, "team bye")

    def test_blocked_by_alternate_assignment(self):
        self.client.force_login(user=self.superuser)
        round1 = Round.objects.get(season=self.source_season, number=1)
        AlternateAssignment.objects.create(
            round=round1,
            team=self.t1,
            board_number=1,
            player=self.t1.teammember_set.first().player,
        )
        self._assert_move_blocked(self.t1, "alternate assignment")

    def test_blocked_by_alternate_search(self):
        self.client.force_login(user=self.superuser)
        round1 = Round.objects.get(season=self.source_season, number=1)
        AlternateSearch.objects.create(round=round1, team=self.t1, board_number=1)
        self._assert_move_blocked(self.t1, "alternate search")

    def test_blocked_by_knockout_seeding(self):
        self.client.force_login(user=self.superuser)
        bracket = KnockoutBracket.objects.create(
            season=self.source_season, bracket_size=4
        )
        KnockoutSeeding.objects.create(bracket=bracket, team=self.t1, seed_number=1)
        self._assert_move_blocked(self.t1, "knockout seeding")

    def test_blocked_by_knockout_advancement(self):
        self.client.force_login(user=self.superuser)
        bracket = KnockoutBracket.objects.create(
            season=self.source_season, bracket_size=4
        )
        round1 = Round.objects.get(season=self.source_season, number=1)
        # Pairing between OTHER teams so t1 has no pairings.
        other_pairing = TeamPairing.objects.create(
            white_team=self.t3,
            black_team=self.t4,
            round=round1,
            pairing_order=1,
        )
        KnockoutAdvancement.objects.create(
            bracket=bracket,
            team=self.t1,
            from_stage="quarterfinals",
            to_stage="semifinals",
            source_pairing=other_pairing,
        )
        self._assert_move_blocked(self.t1, "knockout advancement")

    def test_blocked_by_team_multi_match_progress(self):
        self.client.force_login(user=self.superuser)
        bracket = KnockoutBracket.objects.create(
            season=self.source_season, bracket_size=4
        )
        TeamMultiMatchProgress.objects.create(
            bracket=bracket,
            team=self.t1,
            round_number=1,
            stage_name="semifinals",
            opponent_team=self.t2,
            original_pairing_order=1,
            total_matches_required=2,
        )
        self._assert_move_blocked(self.t1, "multi-match progress")

    def test_invite_codes_follow_team_on_move(self):
        """Team invite codes should be repointed to the target season/league,
        not block the move and not stay tied to the source season."""
        self.client.force_login(user=self.superuser)
        unused = InviteCode.objects.create(
            league=self.source_league,
            season=self.source_season,
            code="MOVE-TEST-CODE-UNUSED",
            code_type="team_member",
            team=self.t1,
            created_by=self.superuser,
        )
        used_player = Player.objects.create(lichess_username="invitee1")
        used = InviteCode.objects.create(
            league=self.source_league,
            season=self.source_season,
            code="MOVE-TEST-CODE-USED",
            code_type="team_member",
            team=self.t1,
            created_by=self.superuser,
            used_by=used_player,
        )

        response = self._post_move([self.t1.id], self.target_season.id)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Successfully moved 1 teams")

        for code in (unused, used):
            code.refresh_from_db()
            self.assertEqual(code.team_id, self.t1.pk)
            self.assertEqual(code.season_id, self.target_season.id)
            self.assertEqual(code.league_id, self.target_league.id)
        # The "used_by" pointer is preserved.
        used.refresh_from_db()
        self.assertEqual(used.used_by_id, used_player.pk)

    def test_invite_codes_unrelated_to_moved_team_untouched(self):
        """Codes for OTHER teams or with no team must not be touched by the move."""
        self.client.force_login(user=self.superuser)
        # team_member code for a different team in the source season
        other_team_code = InviteCode.objects.create(
            league=self.source_league,
            season=self.source_season,
            code="OTHER-TEAM-CODE",
            code_type="team_member",
            team=self.t2,
            created_by=self.superuser,
        )
        # captain code (team is null) for the source season
        captain_code = InviteCode.objects.create(
            league=self.source_league,
            season=self.source_season,
            code="CAPTAIN-CODE",
            code_type="captain",
            team=None,
            created_by=self.superuser,
        )

        self._post_move([self.t1.id], self.target_season.id)

        other_team_code.refresh_from_db()
        captain_code.refresh_from_db()
        self.assertEqual(other_team_code.season_id, self.source_season.id)
        self.assertEqual(other_team_code.league_id, self.source_league.id)
        self.assertEqual(captain_code.season_id, self.source_season.id)
        self.assertEqual(captain_code.league_id, self.source_league.id)
        self.assertIsNone(captain_code.team_id)

    def test_blocked_by_nonzero_teamscore(self):
        self.client.force_login(user=self.superuser)
        score = self.t1.teamscore
        score.match_points = 3
        score.save()
        self._assert_move_blocked(self.t1, "non-zero team score")

    def test_blocked_by_nonzero_game_points(self):
        self.client.force_login(user=self.superuser)
        score = self.t1.teamscore
        score.game_points = 1.5
        score.save()
        self._assert_move_blocked(self.t1, "non-zero team score")

    def test_atomic_rollback_when_one_team_blocked(self):
        """If any selected team is blocked, none are moved."""
        self.client.force_login(user=self.superuser)
        round1 = Round.objects.get(season=self.source_season, number=1)
        # t2 has a bye (blocker); t1 is clean.
        TeamBye.objects.create(round=round1, team=self.t2, type="full-point-bye")

        response = self._post_move([self.t1.id, self.t2.id], self.target_season.id)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Successfully moved")

        self.t1.refresh_from_db()
        self.t2.refresh_from_db()
        self.assertEqual(self.t1.season_id, self.source_season.id)
        self.assertEqual(self.t2.season_id, self.source_season.id)

    def test_blocker_status_shown_on_form_get(self):
        self.client.force_login(user=self.superuser)
        round1 = Round.objects.get(season=self.source_season, number=1)
        TeamBye.objects.create(round=round1, team=self.t1, type="full-point-bye")
        ids = f"{self.t1.id},{self.t2.id}"
        response = self.client.get(f"{self.MOVE_URL}?team_ids={ids}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Blocked:")
        self.assertContains(response, "team bye")
        # Form is suppressed because at least one team is blocked.
        self.assertNotContains(response, 'name="target_season"')

    # ---------------- error paths ----------------

    def test_post_no_target_season(self):
        self.client.force_login(user=self.superuser)
        response = self.client.post(
            f"{self.MOVE_URL}?team_ids={self.t1.id}",
            data={"target_season": ""},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please select a target season")
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.season_id, self.source_season.id)

    def test_post_invalid_target_season(self):
        self.client.force_login(user=self.superuser)
        response = self._post_move([self.t1.id], 999999)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid target season")
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.season_id, self.source_season.id)

    def test_post_target_with_different_boards_rejected(self):
        self.client.force_login(user=self.superuser)
        response = self._post_move([self.t1.id], self.incompatible_season.id)
        self.assertEqual(response.status_code, 200)
        # The Season.objects.get() narrows on boards=source_boards, so the
        # incompatible season is treated as "not found".
        self.assertContains(response, "Invalid target season")
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.season_id, self.source_season.id)

    def test_post_target_equals_source_rejected(self):
        self.client.force_login(user=self.superuser)
        # Posting source_season.id directly bypasses the dropdown filter.
        response = self._post_move([self.t1.id], self.source_season.id)
        self.assertEqual(response.status_code, 200)
        # Should hit the explicit "must differ" guard.
        self.assertContains(response, "must differ")
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.season_id, self.source_season.id)

    def test_permission_denied_for_non_superuser(self):
        regular = User.objects.create(
            username="regular", password="password", is_staff=True
        )
        self.client.force_login(user=regular)
        response = self._post_move([self.t1.id], self.target_season.id)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Successfully moved")
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.season_id, self.source_season.id)

    # ---------------- post-move tournament wiring ----------------

    def test_pairing_in_target_season_after_move(self):
        """After moving teams, TeamPairings can be created against the target
        season's rounds and resolve back to the moved teams correctly."""
        self.client.force_login(user=self.superuser)
        self._post_move([self.t1.id, self.t2.id], self.target_season.id)

        moved_t1 = Team.objects.get(pk=self.t1.pk)
        moved_t2 = Team.objects.get(pk=self.t2.pk)
        target_round1 = Round.objects.get(season=self.target_season, number=1)

        pairing = TeamPairing.objects.create(
            white_team=moved_t1,
            black_team=moved_t2,
            round=target_round1,
            pairing_order=1,
        )

        # Lookup helpers on Team work as expected.
        self.assertEqual(moved_t1.get_teampairing(target_round1), pairing)
        self.assertEqual(moved_t1.get_opponent(target_round1), moved_t2)
        self.assertEqual(moved_t2.get_opponent(target_round1), moved_t1)
        # Source season has no pairings for these teams.
        self.assertEqual(
            TeamPairing.objects.filter(round__season=self.source_season).count(),
            0,
        )

    def test_board_pairings_after_move(self):
        """Per-board TeamPlayerPairings can be created using the moved team's
        members in the new season."""
        self.client.force_login(user=self.superuser)
        self._post_move([self.t1.id, self.t2.id], self.target_season.id)

        moved_t1 = Team.objects.get(pk=self.t1.pk)
        moved_t2 = Team.objects.get(pk=self.t2.pk)
        target_round1 = Round.objects.get(season=self.target_season, number=1)
        team_pairing = TeamPairing.objects.create(
            white_team=moved_t1,
            black_team=moved_t2,
            round=target_round1,
            pairing_order=1,
        )

        # Board 1: t1.player1 (white) vs t2.player1 (black)
        # Board 2: t2.player2 (white) vs t1.player2 (black)  (alternation)
        t1_b1 = moved_t1.teammember_set.get(board_number=1).player
        t1_b2 = moved_t1.teammember_set.get(board_number=2).player
        t2_b1 = moved_t2.teammember_set.get(board_number=1).player
        t2_b2 = moved_t2.teammember_set.get(board_number=2).player

        bp1 = TeamPlayerPairing.objects.create(
            team_pairing=team_pairing,
            board_number=1,
            white=t1_b1,
            black=t2_b1,
        )
        bp2 = TeamPlayerPairing.objects.create(
            team_pairing=team_pairing,
            board_number=2,
            white=t2_b2,
            black=t1_b2,
        )

        self.assertEqual(team_pairing.teamplayerpairing_set.count(), 2)
        self.assertEqual({bp.board_number for bp in [bp1, bp2]}, {1, 2})
        # The players on the moved teams are still the same Player objects.
        self.assertIn(
            t1_b1.id,
            list(moved_t1.teammember_set.values_list("player_id", flat=True)),
        )

    def test_multi_team_round_robin_after_move(self):
        """Move all four teams to a fresh season, then run a complete round
        with two pairings — exercises the moved teams as a group."""
        self.client.force_login(user=self.superuser)
        self._post_move(
            [self.t1.id, self.t2.id, self.t3.id, self.t4.id],
            self.target_season.id,
        )

        # All four teams now live in target_season.
        self.assertEqual(
            Team.objects.filter(season=self.target_season).count(), 4
        )
        # Source season is empty of teams.
        self.assertEqual(
            Team.objects.filter(season=self.source_season).count(), 0
        )

        target_round1 = Round.objects.get(season=self.target_season, number=1)
        m_t1 = Team.objects.get(pk=self.t1.pk)
        m_t2 = Team.objects.get(pk=self.t2.pk)
        m_t3 = Team.objects.get(pk=self.t3.pk)
        m_t4 = Team.objects.get(pk=self.t4.pk)

        TeamPairing.objects.create(
            white_team=m_t1,
            black_team=m_t2,
            round=target_round1,
            pairing_order=1,
        )
        TeamPairing.objects.create(
            white_team=m_t3,
            black_team=m_t4,
            round=target_round1,
            pairing_order=2,
        )

        self.assertEqual(
            TeamPairing.objects.filter(round=target_round1).count(), 2
        )
        # Each moved team is involved in exactly one pairing for round 1.
        for team in (m_t1, m_t2, m_t3, m_t4):
            self.assertIsNotNone(team.get_teampairing(target_round1))

    def test_after_move_team_admin_change_view_loads(self):
        """After a move, the moved team is still editable through the admin."""
        self.client.force_login(user=self.superuser)
        self._post_move([self.t1.id], self.target_season.id)
        response = self.client.get(
            reverse("admin:tournament_team_change", args=[self.t1.pk])
        )
        self.assertEqual(response.status_code, 200)
