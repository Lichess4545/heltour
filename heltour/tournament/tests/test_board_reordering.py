import logging
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from heltour.tournament.forms import BoardOrderForm
from heltour.tournament.models import (
    League,
    LeagueSetting,
    Player,
    RegistrationMode,
    Round,
    Season,
    Team,
    TeamMember,
)


class BoardReorderingTestCase(TestCase):
    """Test cases for team board reordering functionality"""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests in this class"""

        # Create admin user
        cls.admin_user = User.objects.create_user(
            username="admin", password="admin123", is_staff=True
        )

        # Create captain user with matching username
        cls.captain_user = User.objects.create_user(
            username="captain_user", password="captain123"
        )
        cls.captain_player = Player.objects.create(
            lichess_username="captain_user",  # Must match User.username
            rating=1900,
        )

        # Create regular member user
        cls.member_user = User.objects.create_user(
            username="member_user", password="member123"
        )
        cls.member_player = Player.objects.create(
            lichess_username="member_user", rating=1800
        )

        # Create league with settings
        cls.league = League.objects.create(
            name="Test League",
            tag="test",
            competitor_type="team",
            rating_type="classical",
        )

        cls.league_setting = LeagueSetting.objects.create(
            league=cls.league, board_update_deadline_minutes=30
        )

        cls.season = Season.objects.create(
            league=cls.league, name="Test Season", tag="testseason", rounds=8, boards=4
        )

        # Create team with members
        cls.team = Team.objects.create(
            season=cls.season, number=1, name="Test Team", is_active=True
        )

        # Create team members
        cls.members = []
        for i in range(4):
            player = Player.objects.create(
                lichess_username=f"player{i+1}", rating=1700 - i * 50
            )
            member = TeamMember.objects.create(
                team=cls.team,
                player=player if i > 0 else cls.captain_player,
                board_number=i + 1,
                is_captain=(i == 0),
            )
            cls.members.append(member)

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

    def test_board_update_deadline_calculation(self):
        """Test that board update deadline is calculated correctly"""
        # Create round starting in 2 hours
        start_time = timezone.now() + timedelta(hours=2)
        round = Round.objects.create(
            season=self.season,
            number=1,
            start_date=start_time,
            end_date=start_time + timedelta(days=7),
        )

        deadline = round.get_board_update_deadline()
        expected_deadline = start_time - timedelta(minutes=30)

        self.assertEqual(deadline, expected_deadline)
        self.assertTrue(round.is_board_update_allowed())

    def test_board_update_blocked_after_deadline(self):
        """Test that board updates are blocked after deadline"""
        # Create round that already started
        start_time = timezone.now() - timedelta(hours=1)
        round = Round.objects.create(
            season=self.season,
            number=1,
            start_date=start_time,
            end_date=start_time + timedelta(days=7),
        )

        self.assertFalse(round.is_board_update_allowed())

    def test_board_order_form_validation(self):
        """Test BoardOrderForm validation"""
        # Valid form - use actual player IDs
        form_data = {}
        for i, member in enumerate(self.members):
            # Swap boards 1 and 2
            if i == 0:
                form_data[f"player_{member.player.id}"] = 2
            elif i == 1:
                form_data[f"player_{member.player.id}"] = 1
            else:
                form_data[f"player_{member.player.id}"] = member.board_number

        form = BoardOrderForm(
            data=form_data, team=self.team, user=self.captain_user, upcoming_round=None
        )

        self.assertTrue(form.is_valid())

    def test_board_order_form_duplicate_validation(self):
        """Test that duplicate board numbers are rejected"""
        form_data = {}
        for i, member in enumerate(self.members):
            # Set all to board 1 to create duplicates
            form_data[f"player_{member.player.id}"] = 1

        form = BoardOrderForm(
            data=form_data, team=self.team, user=self.captain_user, upcoming_round=None
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Each board number must be unique", str(form.errors))

    def test_board_order_form_gap_validation(self):
        """Test that gaps in board numbers are rejected"""
        form_data = {}
        for i, member in enumerate(self.members):
            # Create a gap by skipping board 3
            if i < 2:
                form_data[f"player_{member.player.id}"] = i + 1
            else:
                form_data[f"player_{member.player.id}"] = i + 2  # Skip board 3

        form = BoardOrderForm(
            data=form_data, team=self.team, user=self.captain_user, upcoming_round=None
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Board numbers must be continuous", str(form.errors))

    def test_board_order_form_deadline_enforcement(self):
        """Test that form enforces deadline for non-admin users"""
        # Create round with passed deadline
        round = Round.objects.create(
            season=self.season,
            number=1,
            start_date=timezone.now() - timedelta(minutes=10),
            end_date=timezone.now() + timedelta(days=7),
        )

        form_data = {}
        for member in self.members:
            form_data[f"player_{member.player.id}"] = member.board_number

        # Captain should be blocked
        form = BoardOrderForm(
            data=form_data, team=self.team, user=self.captain_user, upcoming_round=round
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Board assignments are locked", str(form.errors))

        # Admin should be allowed
        form = BoardOrderForm(
            data=form_data, team=self.team, user=self.admin_user, upcoming_round=round
        )

        # Admin should bypass deadline check
        if not form.is_valid():
            print(f"Admin form errors: {form.errors}")
        self.assertTrue(form.is_valid())

    def test_captain_can_update_board_order(self):
        """Test that team captain can update board order"""
        self.client.login(username="captain_user", password="captain123")

        # Create upcoming round
        Round.objects.create(
            season=self.season,
            number=1,
            start_date=timezone.now() + timedelta(hours=2),
            end_date=timezone.now() + timedelta(days=7),
        )

        # Update board order - use actual player IDs
        post_data = {"action": "update_boards"}
        post_data[f"player_{self.members[0].player.id}"] = "2"
        post_data[f"player_{self.members[1].player.id}"] = "1"
        post_data[f"player_{self.members[2].player.id}"] = "3"
        post_data[f"player_{self.members[3].player.id}"] = "4"

        response = self.client.post(self.manage_url, post_data)

        self.assertEqual(response.status_code, 302)

        # Verify changes
        self.members[0].refresh_from_db()
        self.members[1].refresh_from_db()
        self.assertEqual(self.members[0].board_number, 2)
        self.assertEqual(self.members[1].board_number, 1)

    def test_captain_blocked_after_deadline(self):
        """Test that captain cannot update boards after deadline"""
        self.client.login(username="captain_user", password="captain123")

        # Create round with passed deadline
        round = Round.objects.create(
            season=self.season,
            number=1,
            start_date=timezone.now() - timedelta(minutes=10),
            end_date=timezone.now() + timedelta(days=7),
        )

        # Verify that board updates should be blocked
        self.assertFalse(round.is_board_update_allowed())

        # Try to update board order - use actual player IDs
        post_data = {"action": "update_boards"}
        post_data[f"player_{self.members[0].player.id}"] = "2"
        post_data[f"player_{self.members[1].player.id}"] = "1"
        post_data[f"player_{self.members[2].player.id}"] = "3"
        post_data[f"player_{self.members[3].player.id}"] = "4"

        response = self.client.post(self.manage_url, post_data)

        # Should stay on page with form errors
        self.assertEqual(response.status_code, 200)

        # Check for error message - the form error might have different text
        content = response.content.decode()
        self.assertIn(
            "deadline",
            content.lower(),
            f"Expected deadline-related error message but got: {content[:1000]}",
        )

        # Verify no changes
        self.members[0].refresh_from_db()
        self.members[1].refresh_from_db()
        self.assertEqual(self.members[0].board_number, 1)
        self.assertEqual(self.members[1].board_number, 2)

    def test_admin_can_always_update_boards(self):
        """Test that admin can update boards even after deadline"""
        self.client.login(username="admin", password="admin123")

        # Create round with passed deadline
        Round.objects.create(
            season=self.season,
            number=1,
            start_date=timezone.now() - timedelta(minutes=10),
            end_date=timezone.now() + timedelta(days=7),
        )

        # Update board order - use actual player IDs
        post_data = {"action": "update_boards"}
        post_data[f"player_{self.members[0].player.id}"] = "4"
        post_data[f"player_{self.members[1].player.id}"] = "3"
        post_data[f"player_{self.members[2].player.id}"] = "2"
        post_data[f"player_{self.members[3].player.id}"] = "1"

        response = self.client.post(self.manage_url, post_data)

        self.assertEqual(response.status_code, 302)

        # Verify changes
        for i, member in enumerate(self.members):
            member.refresh_from_db()
            self.assertEqual(member.board_number, 4 - i)

    def test_regular_member_cannot_update_boards(self):
        """Test that regular team members cannot update board order"""
        self.client.login(username="member_user", password="member123")

        # Temporarily disable django.request logger to avoid 404 warning
        logging.disable(logging.WARNING)

        response = self.client.post(
            self.manage_url,
            {
                "action": "update_boards",
                "player_1": "2",
                "player_2": "1",
                "player_3": "3",
                "player_4": "4",
            },
        )

        # Re-enable logging
        logging.disable(logging.NOTSET)

        # Should get 404 (no access to manage page)
        self.assertEqual(response.status_code, 404)

    def test_board_order_page_display(self):
        """Test that board order interface is displayed correctly"""
        self.client.login(username="captain_user", password="captain123")

        # Create upcoming round
        round = Round.objects.create(
            season=self.season,
            number=1,
            start_date=timezone.now() + timedelta(hours=2),
            end_date=timezone.now() + timedelta(days=7),
        )

        response = self.client.get(self.manage_url)
        self.assertEqual(response.status_code, 200)

        # Check for board ordering elements
        self.assertContains(response, "Team Roster & Board Order")
        self.assertContains(response, "Edit Board Order")
        self.assertContains(response, "Board Update Deadline")
        self.assertContains(response, "Round 1 starts")

        # Check form is included
        self.assertContains(response, "board-order-form")
        self.assertContains(response, "sortable-boards")

    def test_board_order_locked_display(self):
        """Test display when board order is locked"""
        self.client.login(username="captain_user", password="captain123")

        # Create round with passed deadline
        Round.objects.create(
            season=self.season,
            number=1,
            start_date=timezone.now() - timedelta(minutes=10),
            end_date=timezone.now() + timedelta(days=7),
        )

        response = self.client.get(self.manage_url)
        self.assertEqual(response.status_code, 200)

        # Should show locked message
        self.assertContains(response, "Board order locked")
        self.assertNotContains(response, "Edit Board Order")

    def test_form_save_updates_board_numbers(self):
        """Test that form save correctly updates board numbers"""
        # Set up form data switching boards 1 and 4 - use actual player IDs
        form_data = {}
        form_data[f"player_{self.members[0].player.id}"] = 4
        form_data[f"player_{self.members[1].player.id}"] = 2
        form_data[f"player_{self.members[2].player.id}"] = 3
        form_data[f"player_{self.members[3].player.id}"] = 1

        form = BoardOrderForm(
            data=form_data, team=self.team, user=self.admin_user, upcoming_round=None
        )

        self.assertTrue(form.is_valid())
        form.save()

        # Verify changes
        self.members[0].refresh_from_db()
        self.members[3].refresh_from_db()
        self.assertEqual(self.members[0].board_number, 4)
        self.assertEqual(self.members[3].board_number, 1)

        # Verify unchanged boards
        self.members[1].refresh_from_db()
        self.members[2].refresh_from_db()
        self.assertEqual(self.members[1].board_number, 2)
        self.assertEqual(self.members[2].board_number, 3)


class BoardReorderingIntegrationTestCase(TestCase):
    """Integration tests for board reordering with pairing generation"""

    def test_pairing_generation_uses_updated_boards(self):
        """Test that pairing generation respects updated board order"""
        # This would test integration with the pairing generation system
        # Implementation depends on how pairings are generated in the system
        pass
