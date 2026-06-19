from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import TestCase, RequestFactory
from django.urls import reverse

from heltour.tournament.admin import InviteCodeAdmin, SeasonAdmin, TeamAdmin
from heltour.tournament.models import (
    InviteCode,
    League,
    Player,
    RegistrationMode,
    Season,
    Team,
    TeamMember,
)


from django.contrib.messages.storage.base import Message
from django.contrib.messages.storage.fallback import FallbackStorage


class MockRequest:
    """Mock request object for admin tests"""

    def __init__(self, user):
        self.user = user
        self.META = {}
        self.session = {}
        self._messages = FallbackStorage(self)

    @property
    def method(self):
        return "GET"


class InviteCodeAdminTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        """Set up test data for admin tests"""
        # Create test users
        cls.superuser = User.objects.create(
            username="admin", password="password", is_superuser=True, is_staff=True
        )
        cls.captain_user = User.objects.create(
            username="captain", password="password", is_staff=True
        )

        # Create invite-only league and season
        cls.league = League.objects.create(
            name="Admin Test League",
            tag="admintest",
            competitor_type="team",
            rating_type="classical",
            registration_mode=RegistrationMode.INVITE_ONLY,
        )
        cls.season = Season.objects.create(
            league=cls.league,
            name="Admin Test Season",
            tag="adminseason",
            rounds=6,
            boards=4,
        )

        # Create a team with captain
        cls.captain_player = Player.objects.create(
            lichess_username="captain", rating=1700
        )
        cls.team = Team.objects.create(
            season=cls.season, number=1, name="Captain Team", is_active=True
        )
        TeamMember.objects.create(
            team=cls.team, player=cls.captain_player, board_number=1, is_captain=True
        )

        cls.site = AdminSite()
        cls.rf = RequestFactory()

    def test_season_admin_generate_invite_codes_action(self):
        """Test the generate_invite_codes action in SeasonAdmin"""
        admin = SeasonAdmin(Season, self.site)
        request = MockRequest(self.superuser)

        # Test with non-invite-only league
        open_league = League.objects.create(
            name="Open League",
            tag="open",
            competitor_type="team",
            rating_type="classical",
            registration_mode=RegistrationMode.OPEN,
        )
        open_season = Season.objects.create(
            league=open_league, name="Open Season", tag="openseason", rounds=6, boards=4
        )

        # Should show error for open registration league
        result = admin.generate_invite_codes(
            request, Season.objects.filter(pk=open_season.pk)
        )
        self.assertIsNone(result)  # Action returns None when showing error

        # Test with invite-only league
        result = admin.generate_invite_codes(
            request, Season.objects.filter(pk=self.season.pk)
        )
        self.assertEqual(result.status_code, 302)  # Should redirect
        self.assertIn("generate_invite_codes", result.url)

    def test_team_admin_generate_invite_codes_action(self):
        """Test the generate_invite_codes action in TeamAdmin"""
        admin = TeamAdmin(Team, self.site)
        request = MockRequest(self.superuser)

        # Test the action
        result = admin.generate_team_invite_codes(
            request, Team.objects.filter(pk=self.team.pk)
        )
        self.assertEqual(result.status_code, 302)  # Should redirect
        self.assertIn("generate_team_invite_codes", result.url)

    def test_invite_code_admin_export_codes(self):
        """Test the export_codes action in InviteCodeAdmin"""
        # Create some test codes
        codes = []
        for i in range(3):
            code = InviteCode.objects.create(
                league=self.league,
                season=self.season,
                code=f"TEST-CODE-{i}",
                code_type="captain" if i == 0 else "team_member",
                team=self.team if i > 0 else None,
                created_by=self.superuser,
            )
            codes.append(code)

        # Use the first code
        player = Player.objects.create(lichess_username="usedplayer", rating=1500)
        codes[0].mark_used(player)

        admin = InviteCodeAdmin(InviteCode, self.site)
        request = self.rf.get("/")
        request.user = self.superuser

        # Export codes
        response = admin.export_codes(request, InviteCode.objects.all())

        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn(
            'attachment; filename="invite_codes.csv"', response["Content-Disposition"]
        )

        # Check CSV content
        content = response.content.decode("utf-8")
        lines = content.strip().split("\n")

        # Header
        self.assertIn("Code,Type,League,Season,Team,Status", lines[0])

        # Check that all codes are in the export
        for code in codes:
            self.assertIn(code.code, content)

    def test_invite_code_admin_permissions(self):
        """Test InviteCodeAdmin permissions"""
        admin = InviteCodeAdmin(InviteCode, self.site)
        request = MockRequest(self.superuser)

        # Should not allow direct creation
        self.assertFalse(admin.has_add_permission(request))

        # Should have readonly fields for existing codes
        code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="READONLY-TEST",
            code_type="captain",
            created_by=self.superuser,
        )

        readonly_fields = admin.get_readonly_fields(request, obj=code)
        self.assertIn("code", readonly_fields)
        self.assertIn("used_by", readonly_fields)
        self.assertIn("used_at", readonly_fields)

    def test_batch_code_generation(self):
        """Test batch generation of invite codes"""
        # Test captain code generation
        captain_codes = InviteCode.create_batch(
            league=self.league,
            season=self.season,
            count=5,
            created_by=self.superuser,
            code_type="captain",
        )

        self.assertEqual(len(captain_codes), 5)
        for code in captain_codes:
            self.assertEqual(code.code_type, "captain")
            self.assertIsNone(code.team)
            self.assertTrue(code.is_available())
            # Check code format
            parts = code.code.split("-")
            self.assertEqual(len(parts), 3)
            self.assertEqual(len(parts[2]), 8)  # Random suffix length

        # Test team member code generation
        member_codes = InviteCode.create_batch(
            league=self.league,
            season=self.season,
            count=3,
            created_by=self.superuser,
            code_type="team_member",
            team=self.team,
        )

        self.assertEqual(len(member_codes), 3)
        for code in member_codes:
            self.assertEqual(code.code_type, "team_member")
            self.assertEqual(code.team, self.team)
            self.assertTrue(code.is_available())

    def test_code_uniqueness(self):
        """Test that generated codes are unique"""
        # Generate a large batch to test uniqueness
        codes = InviteCode.create_batch(
            league=self.league,
            season=self.season,
            count=50,
            created_by=self.superuser,
            code_type="captain",
        )

        code_values = [c.code for c in codes]
        # Check all codes are unique
        self.assertEqual(len(code_values), len(set(code_values)))

    def test_invalid_team_member_code_without_team(self):
        """Test that team member codes require a team"""
        with self.assertRaises(ValidationError):
            code = InviteCode(
                league=self.league,
                season=self.season,
                code="INVALID-MEMBER-CODE",
                code_type="team_member",
                team=None,  # Missing team
                created_by=self.superuser,
            )
            code.save()
