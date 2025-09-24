from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from heltour.tournament.forms import GenerateTeamInviteCodeForm
from heltour.tournament.models import (
    InviteCode,
    League,
    Player,
    Registration,
    RegistrationMode,
    Round,
    Season,
    Team,
    TeamMember,
)
from heltour.tournament.tests.testutils import Shush


class TeamManagementViewTestCase(TestCase):
    """Test cases for the team management views"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests in this class"""

        # Create admin user
        cls.admin_user = User.objects.create_user(
            username="admin", password="admin123", is_staff=True
        )

        # Create captain user
        cls.captain_user = User.objects.create_user(
            username="captain_user", password="captain123"
        )
        cls.captain_player = Player.objects.create(
            lichess_username="captain_user", rating=1900
        )

        # Create vice captain user
        cls.vice_captain_user = User.objects.create_user(
            username="vice_captain", password="vice123"
        )
        cls.vice_captain_player = Player.objects.create(
            lichess_username="vice_captain", rating=1850
        )

        # Create regular member user
        cls.member_user = User.objects.create_user(
            username="member_user", password="member123"
        )
        cls.member_player = Player.objects.create(
            lichess_username="member_user", rating=1800
        )

        # Create non-member user
        cls.other_user = User.objects.create_user(
            username="other_user", password="other123"
        )
        cls.other_player = Player.objects.create(
            lichess_username="other_user", rating=1750
        )

        # Create league and season
        cls.league = League.objects.create(
            name="Test League",
            tag="test",
            competitor_type="team",
            rating_type="classical",
            registration_mode=RegistrationMode.INVITE_ONLY,
        )

        cls.season = Season.objects.create(
            league=cls.league,
            name="Test Season",
            tag="testseason",
            rounds=8,
            boards=4,
            is_active=True,
            registration_open=True,
            codes_per_captain_limit=10,
        )

        # Create rounds
        start_date = timezone.now()
        for i in range(cls.season.rounds):
            Round.objects.create(
                season=cls.season,
                number=i + 1,
                start_date=start_date + timedelta(weeks=i),
                end_date=start_date + timedelta(weeks=i, days=6),
                publish_pairings=False,
                is_completed=False,
            )

        # Create team with members
        cls.team = Team.objects.create(
            season=cls.season, number=1, name="Test Team", is_active=True
        )

        # Add team members
        TeamMember.objects.create(
            team=cls.team, player=cls.captain_player, board_number=1, is_captain=True
        )

        TeamMember.objects.create(
            team=cls.team,
            player=cls.vice_captain_player,
            board_number=2,
            is_vice_captain=True,
        )

        TeamMember.objects.create(
            team=cls.team, player=cls.member_player, board_number=3
        )

        # Create another team
        cls.other_team = Team.objects.create(
            season=cls.season, number=2, name="Other Team", is_active=True
        )

        # URL for team management
        cls.manage_url = reverse(
            "by_league:by_season:team_manage",
            kwargs={
                "league_tag": cls.league.tag,
                "season_tag": cls.season.tag,
                "team_number": cls.team.number,
            },
        )

    def setUp(self):
        """Set up per-test items"""
        self.client = Client()

    def test_anonymous_user_redirected(self):
        """Test that anonymous users are redirected to login"""
        response = self.client.get(self.manage_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_captain_can_access_manage_page(self):
        """Test that team captain can access the management page"""
        self.client.login(username="captain_user", password="captain123")
        response = self.client.get(self.manage_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage Test Team")
        self.assertContains(response, "Generate Invite Codes")

    def test_vice_captain_can_access_manage_page(self):
        """Test that vice captain can access the management page"""
        self.client.login(username="vice_captain", password="vice123")
        response = self.client.get(self.manage_url)
        self.assertEqual(response.status_code, 200)

    def test_regular_member_cannot_access_manage_page(self):
        """Test that regular team members cannot access the management page"""
        self.client.login(username="member_user", password="member123")
        with Shush():
            response = self.client.get(self.manage_url)
        self.assertEqual(response.status_code, 404)

    def test_non_member_cannot_access_manage_page(self):
        """Test that non-team members cannot access the management page"""
        self.client.login(username="other_user", password="other123")
        with Shush():
            response = self.client.get(self.manage_url)
        self.assertEqual(response.status_code, 404)

    def test_admin_can_access_any_team_manage_page(self):
        """Test that admins can access any team's management page"""
        self.client.login(username="admin", password="admin123")

        # Access own team
        response = self.client.get(self.manage_url)
        self.assertEqual(response.status_code, 200)

        # Access other team
        other_url = reverse(
            "by_league:by_season:team_manage",
            kwargs={
                "league_tag": self.league.tag,
                "season_tag": self.season.tag,
                "team_number": self.other_team.number,
            },
        )
        response = self.client.get(other_url)
        self.assertEqual(response.status_code, 200)

    def test_generate_invite_codes(self):
        """Test generating invite codes through the view"""
        self.client.login(username="captain_user", password="captain123")

        # Generate codes
        response = self.client.post(
            self.manage_url, {"action": "generate_codes", "count": "3"}
        )

        # Should redirect back to manage page
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.manage_url)

        # Verify codes were created
        codes = InviteCode.objects.filter(
            team=self.team, created_by_captain=self.captain_player
        )
        self.assertEqual(codes.count(), 3)

        for code in codes:
            self.assertEqual(code.code_type, "team_member")
            self.assertTrue(code.is_available())

    def test_captain_code_limit_enforcement(self):
        """Test that captain code limits are enforced"""
        self.client.login(username="captain_user", password="captain123")

        # Set a low limit
        self.season.codes_per_captain_limit = 2
        self.season.save()

        # Create 2 codes (at limit)
        response = self.client.post(
            self.manage_url, {"action": "generate_codes", "count": "2"}
        )
        self.assertEqual(response.status_code, 302)

        # Try to access the page again - should show limit reached message
        response = self.client.get(self.manage_url)
        self.assertEqual(response.status_code, 200)
        # Should show the static warning since can_create_codes is now False
        self.assertContains(
            response, "You have reached the maximum limit of 2 invite codes."
        )

        # Try to POST directly to create more codes (bypassing the UI)
        response = self.client.post(
            self.manage_url, {"action": "generate_codes", "count": "1"}
        )

        # Should get a 200 response (form validation will fail)
        self.assertEqual(response.status_code, 200)

        # Verify only 2 codes exist (no new codes created)
        codes = InviteCode.objects.filter(
            team=self.team, created_by_captain=self.captain_player
        )
        self.assertEqual(codes.count(), 2)

    def test_admin_no_code_limit(self):
        """Test that admins are not subject to code limits"""
        self.client.login(username="admin", password="admin123")

        # Set a low limit
        self.season.codes_per_captain_limit = 1
        self.season.save()

        # Admin should be able to create multiple codes
        response = self.client.post(
            self.manage_url, {"action": "generate_codes", "count": "5"}
        )
        self.assertEqual(response.status_code, 302)

        # Verify codes were created
        codes = InviteCode.objects.filter(team=self.team)
        self.assertEqual(codes.count(), 5)

    def test_delete_unused_code(self):
        """Test deleting an unused invite code"""
        self.client.login(username="captain_user", password="captain123")

        # Create a code
        code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="DELETE-TEST-001",
            code_type="team_member",
            team=self.team,
            created_by_captain=self.captain_player,
        )

        # Delete the code
        response = self.client.post(
            self.manage_url, {"action": "delete_code", "code_id": str(code.id)}
        )

        self.assertEqual(response.status_code, 302)

        # Verify code was deleted
        self.assertFalse(InviteCode.objects.filter(id=code.id).exists())

    def test_cannot_delete_used_code(self):
        """Test that used codes cannot be deleted"""
        self.client.login(username="captain_user", password="captain123")

        # Create and use a code
        user_player = Player.objects.create(lichess_username="code_user", rating=1700)
        code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="USED-TEST-001",
            code_type="team_member",
            team=self.team,
            created_by_captain=self.captain_player,
        )
        code.mark_used(user_player)

        # Try to delete the used code
        response = self.client.post(
            self.manage_url, {"action": "delete_code", "code_id": str(code.id)}
        )

        self.assertEqual(response.status_code, 302)

        # Verify code was NOT deleted
        self.assertTrue(InviteCode.objects.filter(id=code.id).exists())

    def test_team_roster_display(self):
        """Test that team roster is displayed correctly"""
        self.client.login(username="captain_user", password="captain123")
        response = self.client.get(self.manage_url)

        # Check team members are displayed
        self.assertContains(response, self.captain_player.lichess_username)
        self.assertContains(response, self.vice_captain_player.lichess_username)
        self.assertContains(response, self.member_player.lichess_username)

        # Check roles are displayed
        self.assertContains(response, "Captain")
        self.assertContains(response, "Vice Captain")

    def test_invite_codes_table_display(self):
        """Test that invite codes are displayed in the table"""
        self.client.login(username="captain_user", password="captain123")

        # Create some codes
        codes = []
        for i in range(3):
            code = InviteCode.objects.create(
                league=self.league,
                season=self.season,
                code=f"DISPLAY-TEST-{i}",
                code_type="team_member",
                team=self.team,
                created_by_captain=self.captain_player,
            )
            codes.append(code)

        # Use one code
        user_player = Player.objects.create(lichess_username="used_by", rating=1650)
        codes[0].mark_used(user_player)

        response = self.client.get(self.manage_url)

        # Check codes are displayed
        for code in codes:
            self.assertContains(response, code.code)

        # Check status indicators
        self.assertContains(response, "Available")
        self.assertContains(response, "Used")
        self.assertContains(response, "used_by")  # Username of player who used code

    def test_manage_team_button_visibility(self):
        """Test that Manage Team button is shown only to authorized users"""
        team_profile_url = reverse(
            "by_league:by_season:team_profile",
            kwargs={
                "league_tag": self.league.tag,
                "season_tag": self.season.tag,
                "team_number": self.team.number,
            },
        )

        # Captain should see button
        self.client.login(username="captain_user", password="captain123")
        response = self.client.get(team_profile_url)
        self.assertContains(response, "Manage Team")

        # Regular member should not see button
        self.client.login(username="member_user", password="member123")
        response = self.client.get(team_profile_url)
        self.assertNotContains(response, "Manage Team")

        # Admin should see button
        self.client.login(username="admin", password="admin123")
        response = self.client.get(team_profile_url)
        self.assertContains(response, "Manage Team")
