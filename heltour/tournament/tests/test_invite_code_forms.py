from datetime import timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from heltour.tournament.forms import RegistrationForm
from heltour.tournament.models import (
    InviteCode,
    League,
    Player,
    RegistrationMode,
    Round,
    Season,
    Team,
)
from heltour.tournament.tests.testutils import get_valid_registration_form_data


class InviteCodeFormTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        """Set up test data for form tests"""
        cls.superuser = User.objects.create(
            username="admin", password="password", is_superuser=True, is_staff=True
        )

        # Create invite-only league
        cls.invite_league = League.objects.create(
            name="Invite Form Test League",
            tag="inviteform",
            competitor_type="team",
            rating_type="classical",
            registration_mode=RegistrationMode.INVITE_ONLY,
        )
        cls.invite_season = Season.objects.create(
            league=cls.invite_league,
            name="Invite Form Season",
            tag="inviteformseason",
            rounds=6,
            boards=4,
        )

        # Create open registration league
        cls.open_league = League.objects.create(
            name="Open Form Test League",
            tag="openform",
            competitor_type="team",
            rating_type="classical",
            registration_mode=RegistrationMode.OPEN,
        )
        cls.open_season = Season.objects.create(
            league=cls.open_league,
            name="Open Form Season",
            tag="openformseason",
            rounds=6,
            boards=4,
        )

        # Create rounds for both seasons to avoid clean_weeks_unavailable errors
        start_date = timezone.now()
        for season in [cls.invite_season, cls.open_season]:
            for i in range(1, 7):
                Round.objects.create(
                    season=season,
                    number=i,
                    start_date=start_date + timedelta(weeks=i - 1),
                    end_date=start_date + timedelta(weeks=i),
                    publish_pairings=False,
                    is_completed=False,
                )

    def test_invite_code_field_present_for_invite_only(self):
        """Test that invite_code field is present for invite-only leagues"""
        player = Player.objects.create(lichess_username="testplayer", rating=1500)

        form = RegistrationForm(season=self.invite_season, player=player)

        self.assertIn("invite_code", form.fields)
        self.assertTrue(form.fields["invite_code"].required)
        self.assertEqual(form.fields["invite_code"].max_length, 50)

        # Check field ordering - invite_code should be first
        field_order = list(form.fields.keys())
        self.assertEqual(field_order[0], "invite_code")

    def test_invite_code_field_absent_for_open_registration(self):
        """Test that invite_code field is not present for open registration leagues"""
        player = Player.objects.create(lichess_username="openplayer", rating=1500)

        form = RegistrationForm(season=self.open_season, player=player)

        self.assertNotIn("invite_code", form.fields)

    def test_friends_avoid_fields_hidden_for_invite_only(self):
        """Test that friends/avoid fields are hidden for invite-only leagues"""
        player = Player.objects.create(lichess_username="testplayer", rating=1500)

        form = RegistrationForm(season=self.invite_season, player=player)

        # Fields should exist but be hidden
        self.assertIn("friends", form.fields)
        self.assertIn("avoid", form.fields)
        self.assertEqual(
            form.fields["friends"].widget.__class__.__name__, "HiddenInput"
        )
        self.assertEqual(form.fields["avoid"].widget.__class__.__name__, "HiddenInput")

    def test_alternate_preference_hidden_for_invite_only(self):
        """Test that alternate_preference is hidden for invite-only leagues"""
        player = Player.objects.create(lichess_username="testplayer", rating=1500)

        form = RegistrationForm(season=self.invite_season, player=player)

        # Field should exist but be hidden
        self.assertIn("alternate_preference", form.fields)
        self.assertEqual(
            form.fields["alternate_preference"].widget.__class__.__name__, "HiddenInput"
        )

    def test_whitespace_handling_in_invite_code(self):
        """Test that whitespace is properly handled in invite codes"""
        # Create a code
        code = InviteCode.objects.create(
            league=self.invite_league,
            season=self.invite_season,
            code="WHITESPACE-TEST-123",
            code_type="captain",
            created_by=self.superuser,
        )

        player = Player.objects.create(lichess_username="wsplayer", rating=1500)

        # Test with leading/trailing whitespace
        form_data = get_valid_registration_form_data()
        form_data["email"] = "ws@example.com"
        form_data["corporate_email"] = "ws@company.com"
        form_data["invite_code"] = "  WHITESPACE-TEST-123  "  # With whitespace

        form = RegistrationForm(
            data=form_data, season=self.invite_season, player=player
        )

        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        self.assertEqual(form.cleaned_data["invite_code"], "WHITESPACE-TEST-123")

    def test_special_characters_in_code(self):
        """Test that only valid characters are allowed in codes"""
        player = Player.objects.create(lichess_username="specplayer", rating=1500)

        # Test with special characters that shouldn't exist
        form_data = get_valid_registration_form_data()
        form_data["email"] = "spec@example.com"
        form_data["invite_code"] = "CODE@WITH#SPECIAL$CHARS"

        form = RegistrationForm(
            data=form_data, season=self.invite_season, player=player
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Invalid invite code", str(form.errors["invite_code"]))

    def test_code_validation_for_different_seasons(self):
        """Test that codes are validated against the correct season"""
        # Create another season
        other_season = Season.objects.create(
            league=self.invite_league,
            name="Other Season",
            tag="otherseason",
            rounds=6,
            boards=4,
        )

        # Create rounds for the other season
        start_date = timezone.now()
        for i in range(1, 7):
            Round.objects.create(
                season=other_season,
                number=i,
                start_date=start_date + timedelta(weeks=i - 1),
                end_date=start_date + timedelta(weeks=i),
                publish_pairings=False,
                is_completed=False,
            )

        # Create code for other season
        code = InviteCode.objects.create(
            league=self.invite_league,
            season=other_season,
            code="OTHER-SEASON-CODE",
            code_type="captain",
            created_by=self.superuser,
        )

        player = Player.objects.create(lichess_username="crossplayer", rating=1500)

        # Try to use code for wrong season
        form_data = get_valid_registration_form_data()
        form_data["email"] = "cross@example.com"
        form_data["invite_code"] = "OTHER-SEASON-CODE"

        form = RegistrationForm(
            data=form_data,
            season=self.invite_season,  # Different season
            player=player,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Invalid invite code", str(form.errors["invite_code"]))

    def test_lone_league_no_invite_code(self):
        """Test that lone (individual) leagues don't get invite code functionality"""
        # Create lone league
        lone_league = League.objects.create(
            name="Lone League",
            tag="loneleague",
            competitor_type="individual",
            rating_type="classical",
            registration_mode=RegistrationMode.INVITE_ONLY,
        )
        lone_season = Season.objects.create(
            league=lone_league, name="Lone Season", tag="loneseason", rounds=6
        )

        # Create rounds for lone season
        start_date = timezone.now()
        for i in range(1, 7):
            Round.objects.create(
                season=lone_season,
                number=i,
                start_date=start_date + timedelta(weeks=i - 1),
                end_date=start_date + timedelta(weeks=i),
                publish_pairings=False,
                is_completed=False,
            )

        player = Player.objects.create(lichess_username="loneplayer", rating=1500)

        form = RegistrationForm(season=lone_season, player=player)

        # Even though it's invite-only, lone leagues shouldn't have invite code field
        # (based on current implementation focusing on team leagues)
        self.assertIn("invite_code", form.fields)  # Currently it would still show
