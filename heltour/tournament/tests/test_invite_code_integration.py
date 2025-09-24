from datetime import timedelta
from unittest.mock import Mock

from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory
from django.utils import timezone

from heltour.tournament.forms import GenerateTeamInviteCodeForm, RegistrationForm
from heltour.tournament.models import (
    InviteCode,
    League,
    Player,
    Registration,
    RegistrationMode,
    Round,
    Season,
    SeasonPlayer,
    Team,
    TeamMember,
)
from heltour.tournament.workflows import ApproveRegistrationWorkflow
from heltour.tournament.tests.testutils import Shush, get_valid_registration_form_data


class InviteCodeIntegrationTestCase(TestCase):
    """Integration tests for the complete invite code registration workflow"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for integration tests"""
        cls.admin_user = User.objects.create(
            username="admin", password="password", is_superuser=True, is_staff=True
        )

        # Create system user for auto-approvals
        cls.system_user = User.objects.create(
            username="system", first_name="System", last_name="Auto-Approval"
        )

        # Create invite-only team league
        cls.league = League.objects.create(
            name="Integration Test League",
            tag="inttest",
            competitor_type="team",
            rating_type="classical",
            registration_mode=RegistrationMode.INVITE_ONLY,
        )
        cls.season = Season.objects.create(
            league=cls.league,
            name="Integration Season",
            tag="intseason",
            rounds=8,
            boards=4,
        )

        cls.rf = RequestFactory()

        # Create rounds with start dates
        start_date = timezone.now()
        for i in range(1, 9):
            Round.objects.create(
                season=cls.season,
                number=i,
                start_date=start_date + timedelta(weeks=i - 1),
                end_date=start_date + timedelta(weeks=i),
                publish_pairings=False,
                is_completed=False,
            )

    def test_complete_team_formation_workflow(self):
        """Test the complete workflow from captain registration to full team"""
        # Step 1: Admin generates captain codes
        captain_codes = InviteCode.create_batch(
            league=self.league,
            season=self.season,
            count=2,
            created_by=self.admin_user,
            code_type="captain",
        )

        self.assertEqual(len(captain_codes), 2)

        # Step 2: First captain registers
        captain1 = Player.objects.create(lichess_username="captain1", rating=1800)

        form_data = get_valid_registration_form_data()
        form_data["email"] = "captain1@example.com"
        form_data["first_name"] = "Captain"
        form_data["last_name"] = "One"
        form_data["corporate_email"] = "captain1@company.com"
        form_data["invite_code"] = captain_codes[0].code

        form = RegistrationForm(data=form_data, season=self.season, player=captain1)
        self.assertTrue(form.is_valid())

        with Shush():
            reg1 = form.save()

        # Step 3: Verify captain registration was auto-approved
        reg1.refresh_from_db()
        self.assertEqual(reg1.status, "approved")

        # In new flow, team is NOT created automatically
        # Captain must create team manually
        from heltour.tournament.forms import TeamCreateForm
        team_form = TeamCreateForm(
            data={
                'team_name': 'Team captain1',
                'company_name': 'Company 1',
                'company_address': '123 Main St',
                'team_contact_email': 'team1@example.com',
                'team_contact_number_0': 'US',
                'team_contact_number_1': '2345678900',
            },
            season=self.season,
            player=captain1
        )
        self.assertTrue(team_form.is_valid())
        team1 = team_form.save()
        
        # Now verify team 1 was created
        self.assertEqual(team1.name, "Team captain1")
        self.assertTrue(
            TeamMember.objects.filter(
                team=team1, player=captain1, is_captain=True
            ).exists()
        )

        # Step 4: Captain generates team member codes
        member_codes = InviteCode.create_batch(
            league=self.league,
            season=self.season,
            count=3,
            created_by=self.admin_user,  # In practice, would be captain
            code_type="team_member",
            team=team1,
        )

        # Step 5: Team members register
        members = []
        for i, code in enumerate(member_codes):
            member = Player.objects.create(
                lichess_username=f"member1_{i+1}", rating=1600 + (i * 50)
            )
            members.append(member)

            form_data = get_valid_registration_form_data()
            form_data["email"] = f"member1_{i+1}@example.com"
            form_data["first_name"] = "Member"
            form_data["last_name"] = f"{i+1}"
            form_data["gender"] = "female" if i % 2 == 0 else "male"
            form_data["date_of_birth"] = "1992-03-15"
            form_data["nationality"] = "CA"
            form_data["corporate_email"] = f"member1_{i+1}@company.com"
            form_data["invite_code"] = code.code

            form = RegistrationForm(data=form_data, season=self.season, player=member)
            self.assertTrue(form.is_valid())

            with Shush():
                reg = form.save()

            # Verify member registration was auto-approved
            reg.refresh_from_db()
            self.assertEqual(reg.status, "approved")

        # Step 6: Verify team composition
        team1.refresh_from_db()
        team_members = TeamMember.objects.filter(team=team1).order_by("board_number")
        # Debug: print actual count and members
        if team_members.count() != 4:
            print(f"Expected 4 team members, got {team_members.count()}")
            for tm in team_members:
                print(f"  - Board {tm.board_number}: {tm.player.lichess_username} (Captain: {tm.is_captain})")
        self.assertEqual(team_members.count(), 4)  # Captain + 3 members

        # Verify board assignments
        self.assertEqual(team_members[0].player, captain1)
        self.assertTrue(team_members[0].is_captain)
        self.assertEqual(team_members[0].board_number, 1)

        for i, member in enumerate(members):
            self.assertEqual(team_members[i + 1].player, member)
            self.assertFalse(team_members[i + 1].is_captain)
            self.assertEqual(team_members[i + 1].board_number, i + 2)

        # Step 7: Second captain creates second team
        captain2 = Player.objects.create(lichess_username="captain2", rating=1900)

        form_data = get_valid_registration_form_data()
        form_data["email"] = "captain2@example.com"
        form_data["first_name"] = "Captain"
        form_data["last_name"] = "Two"
        form_data["gender"] = "female"
        form_data["date_of_birth"] = "1988-05-20"
        form_data["nationality"] = "GB"
        form_data["corporate_email"] = "captain2@company.com"
        form_data["invite_code"] = captain_codes[1].code

        form = RegistrationForm(data=form_data, season=self.season, player=captain2)
        self.assertTrue(form.is_valid())

        with Shush():
            reg2 = form.save()

        # Verify captain2 registration was auto-approved
        reg2.refresh_from_db()
        self.assertEqual(reg2.status, "approved")

        # In new flow, captain2 must also create their team manually
        from heltour.tournament.forms import TeamCreateForm
        team2_form = TeamCreateForm(
            data={
                'team_name': 'Team captain2',
                'company_name': 'Company 2',
                'company_address': '456 Second St',
                'team_contact_email': 'team2@example.com',
                'team_contact_number_0': 'US',
                'team_contact_number_1': '2345678900',
            },
            season=self.season,
            player=captain2
        )
        self.assertTrue(team2_form.is_valid())
        team2 = team2_form.save()
        
        # Verify team 2 was created
        self.assertEqual(team2.name, "Team captain2")
        self.assertEqual(team2.number, 2)

        # Verify we have two teams total
        self.assertEqual(Team.objects.filter(season=self.season).count(), 2)

        # Step 8: Verify all codes are properly marked as used
        for code in captain_codes:
            code.refresh_from_db()
            self.assertIsNotNone(code.used_by)
            self.assertIsNotNone(code.used_at)

        for code in member_codes:
            code.refresh_from_db()
            self.assertIsNotNone(code.used_by)
            self.assertIsNotNone(code.used_at)

        # Step 9: Verify season players were created
        season_players = SeasonPlayer.objects.filter(season=self.season)
        self.assertEqual(season_players.count(), 5)  # 2 captains + 3 members

        for sp in season_players:
            self.assertTrue(sp.is_active)
            self.assertIsNotNone(sp.registration)

    def test_mixed_registration_scenarios(self):
        """Test various edge cases and mixed scenarios"""
        # Create a captain code and a team
        captain_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="EDGE-CAPTAIN-001",
            code_type="captain",
            created_by=self.admin_user,
        )

        captain = Player.objects.create(lichess_username="edgecaptain", rating=1750)

        # Register and approve captain
        form_data = get_valid_registration_form_data()
        form_data["email"] = "edge@example.com"
        form_data["first_name"] = "Edge"
        form_data["last_name"] = "Captain"
        form_data["gender"] = "non-binary"
        form_data["date_of_birth"] = "1995-11-30"
        form_data["nationality"] = "DE"
        form_data["corporate_email"] = "edge@company.com"
        form_data["invite_code"] = captain_code.code

        form = RegistrationForm(data=form_data, season=self.season, player=captain)
        self.assertTrue(form.is_valid())

        with Shush():
            reg = form.save()

        # Verify auto-approval
        reg.refresh_from_db()
        self.assertEqual(reg.status, "approved")

        # In new flow, team is NOT created automatically
        # Captain must create team manually
        from heltour.tournament.forms import TeamCreateForm
        team_form = TeamCreateForm(
            data={
                'team_name': 'Team edgecaptain',
                'company_name': 'Edge Company',
                'company_address': '789 Edge St',
                'team_contact_email': 'edge@example.com',
                'team_contact_number_0': 'US',
                'team_contact_number_1': '2345678900',
            },
            season=self.season,
            player=captain
        )
        self.assertTrue(team_form.is_valid())
        team = team_form.save()

        # Test: Try to register another player with the same captain code
        another_player = Player.objects.create(lichess_username="another", rating=1600)
        form_data["email"] = "another@example.com"

        form = RegistrationForm(
            data=form_data, season=self.season, player=another_player
        )
        self.assertFalse(form.is_valid())
        self.assertIn("already been used", str(form.errors["invite_code"]))

        # Test: Create member code but try to use it before team exists
        # (This is prevented by the workflow since team is created first)

        # Test: Maximum team size enforcement
        # Generate exactly enough codes to fill the team
        max_members = self.season.boards - 1  # -1 for captain
        member_codes = InviteCode.create_batch(
            league=self.league,
            season=self.season,
            count=max_members,
            created_by=self.admin_user,
            code_type="team_member",
            team=team,
        )

        # Fill the team
        for i, code in enumerate(member_codes):
            member = Player.objects.create(
                lichess_username=f"fullmember{i}", rating=1500 + (i * 25)
            )

            form_data = get_valid_registration_form_data()
            form_data["email"] = f"full{i}@example.com"
            form_data["first_name"] = "Full"
            form_data["last_name"] = f"Member {i}"
            form_data["gender"] = "male"
            form_data["date_of_birth"] = "1993-07-10"
            form_data["nationality"] = "FR"
            form_data["corporate_email"] = f"full{i}@company.com"
            form_data["invite_code"] = code.code

            form = RegistrationForm(data=form_data, season=self.season, player=member)
            self.assertTrue(form.is_valid())

            with Shush():
                reg = form.save()

            # Verify auto-approval
            reg.refresh_from_db()
            self.assertEqual(reg.status, "approved")

        # Verify team is full
        self.assertEqual(
            TeamMember.objects.filter(team=team).count(), self.season.boards
        )

        # Test: Player changes their username after registration
        original_member = TeamMember.objects.filter(team=team, is_captain=False).first()
        original_player = original_member.player
        original_username = original_player.lichess_username

        # Simulate username change
        original_player.lichess_username = "changed_username"
        original_player.save()

        # Verify team member relationship is maintained
        original_member.refresh_from_db()
        self.assertEqual(original_member.player.lichess_username, "changed_username")
        self.assertEqual(original_member.team, team)

    def test_auto_approval_with_valid_invite_codes(self):
        """Test that registrations with valid invite codes are automatically approved"""
        # Step 1: Create captain code
        captain_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="AUTO-CAPTAIN-001",
            code_type="captain",
            created_by=self.admin_user,
        )

        # Step 2: Register with captain code - should be auto-approved
        captain = Player.objects.create(lichess_username="autocaptain", rating=1850)

        form_data = get_valid_registration_form_data()
        form_data["email"] = "autocaptain@example.com"
        form_data["first_name"] = "Auto"
        form_data["last_name"] = "Captain"
        form_data["gender"] = "male"
        form_data["date_of_birth"] = "1990-01-01"
        form_data["nationality"] = "US"
        form_data["corporate_email"] = "autocaptain@company.com"
        form_data["invite_code"] = captain_code.code

        form = RegistrationForm(data=form_data, season=self.season, player=captain)
        self.assertTrue(form.is_valid())

        with Shush():
            reg = form.save()

        # Verify registration was auto-approved
        reg.refresh_from_db()
        self.assertEqual(reg.status, "approved")

        # In new flow, team is NOT created automatically - captain must create it
        # Verify NO team exists yet
        self.assertEqual(Team.objects.filter(season=self.season).count(), 0)
        
        # Verify NO TeamMember exists yet
        self.assertEqual(TeamMember.objects.filter(player=captain).count(), 0)

        # Verify SeasonPlayer was created
        self.assertTrue(
            SeasonPlayer.objects.filter(
                season=self.season, player=captain, is_active=True
            ).exists()
        )

        # Now simulate captain creating their team using TeamCreateForm
        from heltour.tournament.forms import TeamCreateForm
        team_form = TeamCreateForm(
            data={
                'team_name': 'Team autocaptain',
                'company_name': 'Test Company',
                'company_address': '123 Test St',
                'team_contact_email': 'team@example.com',
                'team_contact_number_0': 'US',
                'team_contact_number_1': '2345678900',
            },
            season=self.season,
            player=captain
        )
        self.assertTrue(team_form.is_valid())
        team = team_form.save()
        
        # Now verify team was created with captain
        self.assertEqual(team.name, "Team autocaptain")
        self.assertTrue(
            TeamMember.objects.filter(
                team=team, player=captain, is_captain=True, board_number=1
            ).exists()
        )

        # Step 3: Create team member code
        member_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="AUTO-MEMBER-001",
            code_type="team_member",
            team=team,
            created_by=self.admin_user,
        )

        # Step 4: Register team member - should be auto-approved
        member = Player.objects.create(lichess_username="automember", rating=1700)

        form_data = get_valid_registration_form_data()
        form_data["email"] = "automember@example.com"
        form_data["first_name"] = "Auto"
        form_data["last_name"] = "Member"
        form_data["gender"] = "male"
        form_data["date_of_birth"] = "1991-06-15"
        form_data["nationality"] = "ES"
        form_data["corporate_email"] = "automember@company.com"
        form_data["invite_code"] = member_code.code

        form = RegistrationForm(data=form_data, season=self.season, player=member)
        self.assertTrue(form.is_valid())

        with Shush():
            reg2 = form.save()

        # Verify member registration was auto-approved
        reg2.refresh_from_db()
        self.assertEqual(reg2.status, "approved")

        # Verify member was added to team
        self.assertTrue(
            TeamMember.objects.filter(
                team=team, player=member, is_captain=False, board_number=2
            ).exists()
        )

        # Verify SeasonPlayer was created for member
        self.assertTrue(
            SeasonPlayer.objects.filter(
                season=self.season, player=member, is_active=True
            ).exists()
        )

        # Step 5: Verify codes are marked as used
        captain_code.refresh_from_db()
        self.assertEqual(captain_code.used_by, captain)
        self.assertIsNotNone(captain_code.used_at)

        member_code.refresh_from_db()
        self.assertEqual(member_code.used_by, member)
        self.assertIsNotNone(member_code.used_at)

    def test_no_auto_approval_without_invite_code(self):
        """Test that registrations without invite codes remain pending"""
        # Test 1: Registration in a non-invite-only league
        open_league = League.objects.create(
            name="Open League",
            tag="open",
            competitor_type="team",
            rating_type="classical",
            registration_mode=RegistrationMode.OPEN,
        )
        open_season = Season.objects.create(
            league=open_league, name="Open Season", tag="openseason", rounds=8, boards=4
        )

        player = Player.objects.create(lichess_username="openplayer", rating=1600)

        form_data = get_valid_registration_form_data()
        form_data["email"] = "open@example.com"
        form_data["first_name"] = "Open"
        form_data["last_name"] = "Player"
        form_data["gender"] = "female"
        form_data["date_of_birth"] = "1994-02-28"
        form_data["nationality"] = "AU"
        form_data["corporate_email"] = "open@company.com"

        form = RegistrationForm(data=form_data, season=open_season, player=player)
        self.assertTrue(form.is_valid())

        with Shush():
            reg = form.save()

        # Verify registration remains pending (no auto-approval without invite code)
        reg.refresh_from_db()
        self.assertEqual(reg.status, "pending")

        # Verify no team was created
        self.assertEqual(Team.objects.filter(season=open_season).count(), 0)

        # Verify no SeasonPlayer was created
        self.assertFalse(
            SeasonPlayer.objects.filter(season=open_season, player=player).exists()
        )

    def test_captain_workflow_with_code_management(self):
        """Test complete captain workflow including code creation and management"""
        # Step 1: Create captain code and register captain
        captain_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="CAPTAIN-WORKFLOW-001",
            code_type="captain",
            created_by=self.admin_user,
        )

        captain = Player.objects.create(
            lichess_username="workflow_captain", rating=1900
        )

        form_data = get_valid_registration_form_data()
        form_data["email"] = "workflow_captain@example.com"
        form_data["first_name"] = "Workflow"
        form_data["last_name"] = "Captain"
        form_data["gender"] = "prefer-not-disclose"
        form_data["date_of_birth"] = "1987-09-12"
        form_data["nationality"] = "BR"
        form_data["corporate_email"] = "workflow@company.com"
        form_data["invite_code"] = captain_code.code

        form = RegistrationForm(data=form_data, season=self.season, player=captain)
        self.assertTrue(form.is_valid())

        with Shush():
            reg = form.save()

        # Verify captain registration was auto-approved
        reg.refresh_from_db()
        self.assertEqual(reg.status, "approved")

        # In new flow, team is NOT created automatically
        # Captain must create team manually
        from heltour.tournament.forms import TeamCreateForm
        team_form = TeamCreateForm(
            data={
                'team_name': f'Team {captain.lichess_username}',
                'company_name': 'Workflow Company',
                'company_address': '456 Test Ave',
                'team_contact_email': 'workflow@example.com',
                'team_contact_number_0': 'US',
                'team_contact_number_1': '2345678900',
            },
            season=self.season,
            player=captain
        )
        self.assertTrue(team_form.is_valid())
        team = team_form.save()
        
        self.assertEqual(team.name, f"Team {captain.lichess_username}")

        # Step 2: Captain creates invite codes for team members
        # Simulate captain creating codes (normally done through the view)
        codes = []
        for i in range(3):
            code = InviteCode.objects.create(
                league=self.league,
                season=self.season,
                code=f"TEAM-{team.number}-MEMBER-{i+1}",
                code_type="team_member",
                team=team,
                created_by_captain=captain,
                notes=f"Created by captain for team {team.name}",
            )
            codes.append(code)

        # Verify codes are properly linked
        team_codes = InviteCode.objects.filter(team=team, created_by_captain=captain)
        self.assertEqual(team_codes.count(), 3)

        # Step 3: Team members join using captain's codes
        members = []
        for i, code in enumerate(codes[:2]):  # Only use 2 of 3 codes
            member = Player.objects.create(
                lichess_username=f"team_member_{i+1}", rating=1700 + i * 50
            )

            form_data = get_valid_registration_form_data()
            form_data["email"] = f"member{i+1}@example.com"
            form_data["first_name"] = "Team"
            form_data["last_name"] = f"Member {i+1}"
            form_data["gender"] = "female" if i == 0 else "male"
            form_data["date_of_birth"] = "1990-12-25"
            form_data["nationality"] = "JP"
            form_data["corporate_email"] = f"member{i+1}@company.com"
            form_data["invite_code"] = code.code

            form = RegistrationForm(data=form_data, season=self.season, player=member)
            self.assertTrue(form.is_valid())

            with Shush():
                member_reg = form.save()

            # Verify auto-approval
            member_reg.refresh_from_db()
            self.assertEqual(member_reg.status, "approved")

            members.append(member)

        # Step 4: Verify team composition
        team.refresh_from_db()
        team_members = TeamMember.objects.filter(team=team).order_by("board_number")

        self.assertEqual(team_members.count(), 3)  # Captain + 2 members

        # Verify captain is board 1
        self.assertEqual(team_members[0].player, captain)
        self.assertTrue(team_members[0].is_captain)
        self.assertEqual(team_members[0].board_number, 1)

        # Verify members
        self.assertEqual(team_members[1].player, members[0])
        self.assertEqual(team_members[1].board_number, 2)
        self.assertEqual(team_members[2].player, members[1])
        self.assertEqual(team_members[2].board_number, 3)

        # Step 5: Verify code usage tracking
        for i, code in enumerate(codes[:2]):
            code.refresh_from_db()
            self.assertFalse(code.is_available())
            self.assertEqual(code.used_by, members[i])
            self.assertIsNotNone(code.used_at)

        # Verify unused code remains available
        codes[2].refresh_from_db()
        self.assertTrue(codes[2].is_available())
        self.assertIsNone(codes[2].used_by)

        # Step 6: Test captain code limit enforcement
        self.season.codes_per_captain_limit = 5
        self.season.save()

        # Captain has created 3 codes, should be able to create 2 more
        remaining_codes = self.season.codes_per_captain_limit - team_codes.count()
        self.assertEqual(remaining_codes, 2)

        # Try to create more codes within limit
        form = GenerateTeamInviteCodeForm(
            data={"count": 2}, team=team, season=self.season, player=captain
        )
        self.assertTrue(form.is_valid())

        # Try to exceed limit
        form = GenerateTeamInviteCodeForm(
            data={"count": 3}, team=team, season=self.season, player=captain
        )
        self.assertFalse(form.is_valid())
        self.assertIn("You can only create 2 more invite codes", str(form.errors))
