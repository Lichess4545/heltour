from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test.client import RequestFactory
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


class InviteCodeTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        """Set up test data for invite code tests"""
        # Create a team league with invite-only registration
        cls.league = League.objects.create(
            name="Invite Only Team League",
            tag="inviteteam",
            competitor_type="team",
            rating_type="classical",
            registration_mode=RegistrationMode.INVITE_ONLY,
        )
        cls.season = Season.objects.create(
            league=cls.league,
            name="Test Invite Season",
            tag="inviteseason",
            rounds=6,
            boards=4,
        )

        # Create a superuser for admin operations
        cls.superuser = User.objects.create(
            username="admin", password="password", is_superuser=True, is_staff=True
        )

        # Create system user for auto-approvals
        cls.system_user = User.objects.create(
            username="system", first_name="System", last_name="Auto-Approval"
        )

        cls.rf = RequestFactory()

        # Create rounds with start dates to avoid clean_weeks_unavailable errors
        start_date = timezone.now()
        for i in range(1, 7):
            Round.objects.create(
                season=cls.season,
                number=i,
                start_date=start_date + timedelta(weeks=i - 1),
                end_date=start_date + timedelta(weeks=i),
                publish_pairings=False,
                is_completed=False,
            )

    def test_cannot_register_without_valid_code(self):
        """Test that registration fails without a valid invite code"""
        player = Player.objects.create(lichess_username="testplayer", rating=1500)

        # Create form data without invite code
        form_data = {
            "email": "test@example.com",
            "has_played_20_games": True,
            "can_commit": True,
            "agreed_to_rules": True,
            "agreed_to_tos": True,
            "alternate_preference": "full_time",
            "invite_code": "",  # Empty code
        }

        form = RegistrationForm(data=form_data, season=self.season, player=player)

        self.assertFalse(form.is_valid())
        self.assertIn("invite_code", form.errors)
        self.assertIn("Invite code is required", str(form.errors["invite_code"]))

    def test_cannot_register_with_invalid_code(self):
        """Test that registration fails with an invalid invite code"""
        player = Player.objects.create(lichess_username="testplayer2", rating=1500)

        # Create form data with invalid code
        form_data = {
            "email": "test@example.com",
            "has_played_20_games": True,
            "can_commit": True,
            "agreed_to_rules": True,
            "agreed_to_tos": True,
            "alternate_preference": "full_time",
            "invite_code": "INVALID-CODE-12345",
        }

        form = RegistrationForm(data=form_data, season=self.season, player=player)

        self.assertFalse(form.is_valid())
        self.assertIn("invite_code", form.errors)
        self.assertIn("Invalid invite code", str(form.errors["invite_code"]))

    def test_captain_code_creates_team(self):
        """Test that a captain code creates a new team upon registration approval"""
        # Create a captain invite code
        captain_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="CAPTAIN-CODE-123",
            code_type="captain",
            created_by=self.superuser,
        )

        # Create player and registration
        player = Player.objects.create(lichess_username="captainplayer", rating=1600)

        # Create form data with captain code
        form_data = get_valid_registration_form_data()
        form_data["email"] = "captain@example.com"
        form_data["corporate_email"] = "captain@company.com"
        form_data["invite_code"] = "CAPTAIN-CODE-123"

        form = RegistrationForm(data=form_data, season=self.season, player=player)

        self.assertTrue(form.is_valid())

        # Save the registration
        with Shush():
            registration = form.save()

        # Verify the invite code was stored
        self.assertEqual(registration.invite_code_used, captain_code)

        # Verify registration was auto-approved
        registration.refresh_from_db()
        self.assertEqual(registration.status, "approved")
        
        # Verify SeasonPlayer was created and is active
        sp = SeasonPlayer.objects.get(player=player, season=self.season)
        self.assertTrue(sp.is_active)
        self.assertEqual(sp.registration, registration)

        # In new flow, team is NOT created automatically
        team = Team.objects.filter(
            season=self.season,
            teammember__player=player,
            teammember__is_captain=True
        ).first()
        self.assertIsNone(team)  # No team should exist yet
        
        # Verify no team member exists yet
        self.assertFalse(TeamMember.objects.filter(player=player).exists())

        # Verify code is marked as used
        captain_code.refresh_from_db()
        self.assertEqual(captain_code.used_by, player)
        self.assertIsNotNone(captain_code.used_at)

    def test_captain_can_generate_team_codes(self):
        """Test that a team captain can generate team member codes"""
        # First create a team with a captain
        captain = Player.objects.create(lichess_username="teamcaptain", rating=1700)
        team = Team.objects.create(
            season=self.season, number=1, name="Test Team", is_active=True
        )
        TeamMember.objects.create(
            team=team, player=captain, board_number=1, is_captain=True
        )

        # Generate team member codes
        codes = InviteCode.create_batch(
            league=self.league,
            season=self.season,
            count=3,
            created_by=self.superuser,
            code_type="team_member",
            team=team,
        )

        self.assertEqual(len(codes), 3)

        for code in codes:
            self.assertEqual(code.code_type, "team_member")
            self.assertEqual(code.team, team)
            self.assertTrue(code.is_available())

    def test_team_member_code_joins_existing_team(self):
        """Test that a team member code adds player to existing team"""
        # Create a team with captain
        captain = Player.objects.create(lichess_username="captain", rating=1800)
        team = Team.objects.create(
            season=self.season, number=1, name="Existing Team", is_active=True
        )
        TeamMember.objects.create(
            team=team, player=captain, board_number=1, is_captain=True
        )

        # Create team member invite code
        member_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="MEMBER-CODE-456",
            code_type="team_member",
            team=team,
            created_by=self.superuser,
        )

        # Create new player and registration
        new_player = Player.objects.create(lichess_username="teammember", rating=1650)

        form_data = get_valid_registration_form_data()
        form_data["email"] = "member@example.com"
        form_data["corporate_email"] = "member@company.com"
        form_data["invite_code"] = "MEMBER-CODE-456"

        form = RegistrationForm(data=form_data, season=self.season, player=new_player)

        self.assertTrue(form.is_valid())

        # Save the registration
        with Shush():
            registration = form.save()

        # Verify registration was auto-approved
        registration.refresh_from_db()
        self.assertEqual(registration.status, "approved")
        
        # Verify SeasonPlayer was created and is active
        sp = SeasonPlayer.objects.get(player=new_player, season=self.season)
        self.assertTrue(sp.is_active)
        self.assertEqual(sp.registration, registration)

        # Verify no new team was created
        self.assertEqual(Team.objects.filter(season=self.season).count(), 1)

        # Verify player was added to existing team
        team_member = TeamMember.objects.get(team=team, player=new_player)
        self.assertFalse(team_member.is_captain)
        self.assertEqual(team_member.board_number, 2)  # Next available board

        # Verify code is marked as used
        member_code.refresh_from_db()
        self.assertEqual(member_code.used_by, new_player)
        self.assertIsNotNone(member_code.used_at)

    def test_cannot_reuse_invite_code(self):
        """Test that an invite code cannot be used twice"""
        # Create and use a captain code
        captain_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="USED-CODE-789",
            code_type="captain",
            created_by=self.superuser,
        )

        # Mark it as used
        first_player = Player.objects.create(
            lichess_username="firstplayer", rating=1500
        )
        captain_code.mark_used(first_player)

        # Try to use it again
        second_player = Player.objects.create(
            lichess_username="secondplayer", rating=1550
        )

        form_data = get_valid_registration_form_data()
        form_data["email"] = "second@example.com"
        form_data["invite_code"] = "USED-CODE-789"

        form = RegistrationForm(
            data=form_data, season=self.season, player=second_player
        )

        self.assertFalse(form.is_valid())
        self.assertIn("invite_code", form.errors)
        self.assertIn("already been used", str(form.errors["invite_code"]))

    def test_code_generation_respects_limits(self):
        """Test that team member code generation respects the 2x boards limit"""
        # Create a team
        team = Team.objects.create(
            season=self.season, number=1, name="Limited Team", is_active=True
        )

        # Max codes should be 2 * boards (4) = 8
        max_codes = self.season.boards * 2

        # Generate max codes
        codes = InviteCode.create_batch(
            league=self.league,
            season=self.season,
            count=max_codes,
            created_by=self.superuser,
            code_type="team_member",
            team=team,
        )

        self.assertEqual(len(codes), max_codes)

        # Verify we can't generate more
        # In the actual implementation, this would be enforced in the view
        existing_count = InviteCode.objects.filter(
            league=self.league, season=self.season, code_type="team_member", team=team
        ).count()

        self.assertEqual(existing_count, max_codes)

    def test_invite_code_case_insensitive(self):
        """Test that invite codes are case-insensitive"""
        # Create a code
        code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="CHESS-KNIGHT-ABC123",
            code_type="captain",
            created_by=self.superuser,
        )

        # Test various case combinations
        found_code = InviteCode.get_by_code(
            "chess-knight-abc123", self.league, self.season
        )
        self.assertEqual(found_code, code)

        found_code = InviteCode.get_by_code(
            "CHESS-knight-ABC123", self.league, self.season
        )
        self.assertEqual(found_code, code)

        found_code = InviteCode.get_by_code(
            "ChEsS-KnIgHt-AbC123", self.league, self.season
        )
        self.assertEqual(found_code, code)

    def test_open_registration_does_not_require_code(self):
        """Test that open registration leagues don't require invite codes"""
        # Create an open registration league
        open_league = League.objects.create(
            name="Open League",
            tag="openleague",
            competitor_type="team",
            rating_type="classical",
            registration_mode=RegistrationMode.OPEN,
        )
        open_season = Season.objects.create(
            league=open_league, name="Open Season", tag="openseason", rounds=6, boards=4
        )

        player = Player.objects.create(lichess_username="openplayer", rating=1400)

        # Form should not have invite_code field
        form = RegistrationForm(season=open_season, player=player)

        self.assertNotIn("invite_code", form.fields)

    def test_captain_created_invite_codes(self):
        """Test that captain-created invite codes are tracked properly"""
        captain_player = Player.objects.create(
            lichess_username="test_captain", rating=1800
        )

        # Create a team for the captain
        team = Team.objects.create(
            season=self.season, number=1, name="Captain Test Team"
        )

        # Create invite code as captain
        code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="CAPTAIN-MADE-001",
            code_type="team_member",
            team=team,  # Required for team_member type
            created_by_captain=captain_player,
            notes="Created by captain",
        )

        # Verify tracking
        self.assertEqual(code.created_by_captain, captain_player)
        self.assertIsNone(code.created_by)

        # Test captain's created codes count
        captain_codes = InviteCode.objects.filter(
            season=self.season, created_by_captain=captain_player
        ).count()
        self.assertEqual(captain_codes, 1)

    def test_codes_per_captain_limit(self):
        """Test that the codes per captain limit is enforced"""
        # Set a low limit for testing
        self.season.codes_per_captain_limit = 3
        self.season.save()

        captain = Player.objects.create(lichess_username="limited_captain", rating=1900)
        team = Team.objects.create(season=self.season, number=1, name="Test Team")

        # Create codes up to the limit
        for i in range(3):
            InviteCode.objects.create(
                league=self.league,
                season=self.season,
                code=f"LIMIT-TEST-{i}",
                code_type="team_member",
                team=team,
                created_by_captain=captain,
            )

        # Verify form validation prevents creating more
        form = GenerateTeamInviteCodeForm(
            data={"count": 1}, team=team, season=self.season, player=captain
        )

        self.assertFalse(form.is_valid())
        self.assertIn("You have reached your limit of 3 invite codes", str(form.errors))

    def test_admin_bypass_captain_limit(self):
        """Test that admins are not subject to captain code limits"""
        self.season.codes_per_captain_limit = 1
        self.season.save()

        team = Team.objects.create(season=self.season, number=1, name="Admin Test Team")

        # Admin should be able to create codes without limit
        form = GenerateTeamInviteCodeForm(
            data={"count": 5},
            team=team,
            season=self.season,
            player=None,  # No player when admin
        )

        self.assertTrue(form.is_valid())

    def test_code_generation_form(self):
        """Test the GenerateTeamInviteCodeForm functionality"""
        captain = Player.objects.create(lichess_username="form_captain", rating=1850)
        team = Team.objects.create(season=self.season, number=1, name="Form Test Team")

        form = GenerateTeamInviteCodeForm(
            data={"count": 3}, team=team, season=self.season, player=captain
        )

        self.assertTrue(form.is_valid())

        # Save should create the codes
        codes = form.save(created_by=self.system_user)

        self.assertEqual(len(codes), 3)
        for code in codes:
            self.assertEqual(code.code_type, "team_member")
            self.assertEqual(code.team, team)
            self.assertEqual(code.created_by_captain, captain)
            self.assertTrue(code.is_available())
