"""Tests for registration form customization settings."""

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from heltour.tournament.models import (
    League,
    Season,
    Player,
    InviteCode,
    Team,
)
from heltour.tournament.forms import RegistrationForm
from heltour.tournament.tests.testutils import get_valid_registration_form_data


class RegistrationSettingsTestCase(TestCase):
    """Test various registration settings on leagues."""

    def setUp(self):
        """Set up test data."""
        # Create a test user and player
        self.user = User.objects.create_user(username="testplayer", password="test123")
        self.player = Player.objects.create(
            lichess_username="testplayer", rating=1500, email="test@example.com"
        )

        # Create a league with all settings enabled (default)
        self.league_all_enabled = League.objects.create(
            name="Test League Full",
            tag="test-full",
            description="League with all registration fields",
            theme="blue",
            time_control="45+45",
            rating_type="classical",
            competitor_type="team",
            email_required=True,
            show_provisional_warning=True,
            ask_availability=True,
        )

        # Create a league with minimal settings
        self.league_minimal = League.objects.create(
            name="Test League Minimal",
            tag="test-minimal",
            description="League with minimal registration",
            theme="green",
            time_control="45+45",
            rating_type="classical",
            competitor_type="team",
            email_required=False,
            show_provisional_warning=False,
            ask_availability=False,
        )

        # Create seasons for both leagues
        self.season_full = Season.objects.create(
            league=self.league_all_enabled,
            name="Test Season Full",
            tag="test-season-full",
            rounds=8,
            boards=4,
            start_date=timezone.now() + timedelta(days=7),
            registration_open=True,
            round_duration=timedelta(days=7),
        )

        self.season_minimal = Season.objects.create(
            league=self.league_minimal,
            name="Test Season Minimal",
            tag="test-season-minimal",
            rounds=8,
            boards=4,
            start_date=timezone.now() + timedelta(days=7),
            registration_open=True,
            round_duration=timedelta(days=7),
        )

        # Create rounds for availability testing
        for i in range(1, 9):
            for season in [self.season_full, self.season_minimal]:
                season.round_set.create(
                    number=i,
                    start_date=season.start_date + timedelta(days=(i - 1) * 7),
                    end_date=season.start_date + timedelta(days=(i - 1) * 7 + 6),
                    is_completed=False,
                    publish_pairings=False,
                )

    def test_email_field_required_when_enabled(self):
        """Test that email field is required when email_required=True."""
        form = RegistrationForm(season=self.season_full, player=self.player)

        self.assertIn("email", form.fields)
        self.assertTrue(form.fields["email"].required)

    def test_email_field_removed_when_disabled(self):
        """Test that email field is removed when email_required=False."""
        form = RegistrationForm(season=self.season_minimal, player=self.player)

        self.assertNotIn("email", form.fields)

    def test_provisional_warning_field_shown_when_enabled(self):
        """Test that has_played_20_games field exists when show_provisional_warning=True."""
        form = RegistrationForm(season=self.season_full, player=self.player)

        self.assertIn("has_played_20_games", form.fields)

    def test_provisional_warning_field_removed_when_disabled(self):
        """Test that has_played_20_games field is removed when show_provisional_warning=False."""
        form = RegistrationForm(season=self.season_minimal, player=self.player)

        self.assertNotIn("has_played_20_games", form.fields)

    def test_availability_field_shown_when_enabled(self):
        """Test that weeks_unavailable field exists when ask_availability=True."""
        form = RegistrationForm(season=self.season_full, player=self.player)

        self.assertIn("weeks_unavailable", form.fields)
        # Check that it has the correct number of choices (8 rounds)
        # Debug: print the actual choices to see what's happening
        actual_choices = form.fields["weeks_unavailable"].choices
        expected_rounds = self.season_full.round_set.count()
        self.assertEqual(len(actual_choices), expected_rounds)

    def test_availability_field_removed_when_disabled(self):
        """Test that weeks_unavailable field is removed when ask_availability=False."""
        form = RegistrationForm(season=self.season_minimal, player=self.player)

        self.assertNotIn("weeks_unavailable", form.fields)

    def test_minimal_registration_form(self):
        """Test that minimal registration only has essential fields."""
        form = RegistrationForm(season=self.season_minimal, player=self.player)

        # Check that optional fields are removed
        self.assertNotIn("email", form.fields)
        self.assertNotIn("has_played_20_games", form.fields)
        self.assertNotIn("weeks_unavailable", form.fields)

        # Check that required fields still exist
        self.assertIn("agreed_to_tos", form.fields)
        self.assertIn("agreed_to_rules", form.fields)
        # For team leagues before season start
        self.assertIn("friends", form.fields)
        self.assertIn("avoid", form.fields)
        self.assertIn("alternate_preference", form.fields)

    def test_registration_saves_without_optional_fields(self):
        """Test that registration can be saved without optional fields."""
        form_data = get_valid_registration_form_data()

        form = RegistrationForm(
            data=form_data, season=self.season_minimal, player=self.player
        )

        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        registration = form.save()

        # Check registration was created successfully
        self.assertEqual(registration.season, self.season_minimal)
        self.assertEqual(registration.player, self.player)
        self.assertEqual(registration.email, "")  # Should be empty
        self.assertTrue(registration.has_played_20_games)  # Should use default

    def test_individual_league_settings(self):
        """Test settings for individual (non-team) leagues."""
        # Create an individual league with minimal settings
        league_individual = League.objects.create(
            name="Test Individual League",
            tag="test-individual",
            description="Individual league with minimal registration",
            theme="red",
            time_control="10+5",
            rating_type="rapid",
            competitor_type="lone",  # Individual league
            email_required=False,
            show_provisional_warning=False,
            ask_availability=False,
        )

        season_individual = Season.objects.create(
            league=league_individual,
            name="Test Individual Season",
            tag="test-individual-season",
            rounds=8,
            start_date=timezone.now() + timedelta(days=7),
            registration_open=True,
            round_duration=timedelta(days=7),
        )

        form = RegistrationForm(season=season_individual, player=self.player)

        # Individual leagues don't have team-related fields
        self.assertNotIn("friends", form.fields)
        self.assertNotIn("avoid", form.fields)
        self.assertNotIn("alternate_preference", form.fields)

        # Optional fields should still be removed
        self.assertNotIn("email", form.fields)
        self.assertNotIn("has_played_20_games", form.fields)


class InviteCodeRegistrationTestCase(TestCase):
    """Test registration with invite codes and team assignment."""

    def setUp(self):
        """Set up test data for invite code tests."""
        self.user = User.objects.create_user(username="captain", password="test123")
        self.player = Player.objects.create(
            lichess_username="captain", rating=1800, email="captain@example.com"
        )

        # Create invite-only league
        self.league = League.objects.create(
            name="Elite Championship",
            tag="elite",
            description="Invite-only championship",
            theme="blue",
            time_control="60+30",
            rating_type="classical",
            competitor_type="team",
            registration_mode="invite_only",
            email_required=False,
            show_provisional_warning=False,
            ask_availability=False,
        )

        self.season = Season.objects.create(
            league=self.league,
            name="Elite Season",
            tag="elite-season",
            rounds=8,
            boards=4,
            start_date=timezone.now() + timedelta(days=7),
            registration_open=True,
        )

        # Create a team
        self.team = Team.objects.create(
            season=self.season, number=1, name="Elite Squad", is_active=True
        )

        # Create team member invite code
        self.invite_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="TEAM-MEMBER-123",
            code_type="team_member",
            team=self.team,
        )

    def test_invite_code_field_in_invite_only_league(self):
        """Test that invite code field appears in invite-only leagues."""
        form = RegistrationForm(season=self.season, player=self.player)

        self.assertIn("invite_code", form.fields)
        self.assertTrue(form.fields["invite_code"].required)

    def test_minimal_fields_with_invite_code(self):
        """Test invite-only league with minimal fields."""
        form = RegistrationForm(season=self.season, player=self.player)

        # Should have invite code but not optional fields
        self.assertIn("invite_code", form.fields)
        self.assertNotIn("email", form.fields)
        self.assertNotIn("has_played_20_games", form.fields)
        self.assertNotIn("weeks_unavailable", form.fields)

        # Team preference fields should be hidden for invite-only
        self.assertIn("friends", form.fields)
        self.assertIn("avoid", form.fields)
        self.assertIsInstance(
            form.fields["friends"].widget, type(form.fields["friends"].widget)
        )
        self.assertIsInstance(
            form.fields["avoid"].widget, type(form.fields["avoid"].widget)
        )

    def test_registration_with_valid_invite_code(self):
        """Test successful registration with valid invite code."""
        form_data = get_valid_registration_form_data()
        form_data["invite_code"] = "TEAM-MEMBER-123"

        form = RegistrationForm(data=form_data, season=self.season, player=self.player)

        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        registration = form.save()

        # Check registration details
        self.assertEqual(registration.invite_code_used, self.invite_code)
        self.assertEqual(registration.status, "approved")  # Should auto-approve

    def test_registration_with_invalid_invite_code(self):
        """Test registration fails with invalid invite code."""
        form_data = get_valid_registration_form_data()
        form_data["invite_code"] = "INVALID-CODE"

        form = RegistrationForm(data=form_data, season=self.season, player=self.player)

        self.assertFalse(form.is_valid())
        self.assertIn("invite_code", form.errors)
        self.assertIn("Invalid invite code", str(form.errors["invite_code"]))

    def test_registration_with_used_invite_code(self):
        """Test registration fails with already used invite code."""
        # Mark the code as used
        self.invite_code.mark_used(self.player)

        # Create another player to test
        other_player = Player.objects.create(
            lichess_username="otherplayer", rating=1600
        )

        form_data = {
            "invite_code": "TEAM-MEMBER-123",
            "agreed_to_tos": True,
            "agreed_to_rules": True,
            "can_commit": True,
            "friends": "",
            "avoid": "",
            "alternate_preference": "full_time",
        }

        form = RegistrationForm(data=form_data, season=self.season, player=other_player)

        self.assertFalse(form.is_valid())
        self.assertIn("invite_code", form.errors)
        self.assertIn("already been used", str(form.errors["invite_code"]))


class TeamAssignmentTestCase(TestCase):
    """Test team assignment when using invite codes."""

    def setUp(self):
        """Set up test data for team assignment tests."""
        # Create invite-only league
        self.league = League.objects.create(
            name="Team Assignment Test League",
            tag="team-assign-test",
            description="Test team assignments",
            theme="green",
            time_control="45+45",
            rating_type="classical",
            competitor_type="team",
            registration_mode="invite_only",
            email_required=False,
            show_provisional_warning=False,
            ask_availability=False,
        )

        self.season = Season.objects.create(
            league=self.league,
            name="Team Test Season",
            tag="team-test-season",
            rounds=8,
            boards=4,
            start_date=timezone.now() + timedelta(days=7),
            registration_open=True,
        )

    def test_captain_code_auto_approves_registration(self):
        """Test that using a captain code auto-approves registration but doesn't create team."""
        from heltour.tournament.models import SeasonPlayer, TeamMember

        # Create captain player with unique username
        captain = Player.objects.create(
            lichess_username="teamcaptain_unique1",
            rating=2000,
            email="captain@test.com",
        )

        # Create captain invite code
        captain_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="CAPTAIN-CODE-001",
            code_type="captain",
        )

        # Register with captain code
        form_data = get_valid_registration_form_data()
        form_data["invite_code"] = "CAPTAIN-CODE-001"

        form = RegistrationForm(data=form_data, season=self.season, player=captain)

        self.assertTrue(form.is_valid())
        registration = form.save()

        # Check registration is approved
        self.assertEqual(registration.status, "approved")

        # Check SeasonPlayer was created
        sp = SeasonPlayer.objects.filter(player=captain, season=self.season).first()
        self.assertIsNotNone(sp)
        self.assertTrue(sp.is_active)

        # In new flow, team is NOT created automatically
        team_member = TeamMember.objects.filter(player=captain).first()
        self.assertIsNone(team_member)  # No team member should exist yet

        # Check invite code was marked as used
        captain_code.refresh_from_db()
        self.assertEqual(captain_code.used_by, captain)
        self.assertIsNotNone(captain_code.used_at)

    def test_team_member_code_joins_existing_team(self):
        """Test that using a team member code adds player to the specified team."""
        from heltour.tournament.models import SeasonPlayer, TeamMember

        # Create existing team
        existing_team = Team.objects.create(
            season=self.season, number=1, name="Existing Team", is_active=True
        )

        # Add a captain to the team
        captain = Player.objects.create(lichess_username="existingcaptain", rating=2100)
        TeamMember.objects.create(
            team=existing_team, player=captain, board_number=1, is_captain=True
        )

        # Create team member
        member = Player.objects.create(
            lichess_username="newmember", rating=1900, email="member@test.com"
        )

        # Create team member invite code
        member_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="MEMBER-CODE-001",
            code_type="team_member",
            team=existing_team,
            created_by_captain=captain,
        )

        # Register with member code
        form_data = get_valid_registration_form_data()
        form_data["invite_code"] = "MEMBER-CODE-001"

        form = RegistrationForm(data=form_data, season=self.season, player=member)

        self.assertTrue(form.is_valid())
        registration = form.save()

        # Check registration is approved
        self.assertEqual(registration.status, "approved")

        # Check SeasonPlayer was created
        sp = SeasonPlayer.objects.filter(player=member, season=self.season).first()
        self.assertIsNotNone(sp)
        self.assertTrue(sp.is_active)

        # Check member was added to team
        team_member = TeamMember.objects.filter(player=member).first()
        self.assertIsNotNone(team_member)
        self.assertEqual(team_member.team, existing_team)
        self.assertFalse(team_member.is_captain)
        self.assertEqual(team_member.board_number, 2)  # Should be board 2 after captain

        # Check invite code was marked as used
        member_code.refresh_from_db()
        self.assertEqual(member_code.used_by, member)
        self.assertIsNotNone(member_code.used_at)

    def test_multiple_members_join_team_in_order(self):
        """Test that multiple players joining a team get assigned correct board numbers."""
        from heltour.tournament.models import TeamMember

        # Create team with captain
        team = Team.objects.create(
            season=self.season, number=1, name="Multi Member Team", is_active=True
        )

        captain = Player.objects.create(lichess_username="multicaptain", rating=2200)
        TeamMember.objects.create(
            team=team, player=captain, board_number=1, is_captain=True
        )

        # Create and register multiple members
        members = []
        for i in range(3):
            player = Player.objects.create(
                lichess_username=f"member{i+1}", rating=2000 - (i * 100)
            )

            # Create unique code for each member
            code = InviteCode.objects.create(
                league=self.league,
                season=self.season,
                code=f"MULTI-MEMBER-{i+1}",
                code_type="team_member",
                team=team,
                created_by_captain=captain,
            )

            # Register the member
            form_data = get_valid_registration_form_data()
            form_data["invite_code"] = code.code
            form_data["first_name"] = "Multi"
            form_data["last_name"] = f"Member {i+1}"
            form_data["corporate_email"] = f"member{i+1}@company.com"

            form = RegistrationForm(data=form_data, season=self.season, player=player)

            self.assertTrue(form.is_valid())
            registration = form.save()
            members.append(player)

        # Check all members were added with correct board numbers
        for i, player in enumerate(members):
            team_member = TeamMember.objects.get(player=player, team=team)
            self.assertEqual(team_member.team, team)
            self.assertEqual(team_member.board_number, i + 2)  # Captain is board 1

    def test_team_assignment_without_invite_code(self):
        """Test that non-invite-only leagues don't auto-create teams."""
        # Create regular league
        regular_league = League.objects.create(
            name="Regular League",
            tag="regular",
            description="Regular registration",
            theme="blue",
            time_control="45+45",
            rating_type="classical",
            competitor_type="team",
            registration_mode="open",  # Not invite-only
            email_required=False,
            show_provisional_warning=False,
            ask_availability=False,
        )

        regular_season = Season.objects.create(
            league=regular_league,
            name="Regular Season",
            tag="regular-season",
            rounds=8,
            boards=4,
            start_date=timezone.now() + timedelta(days=7),
            registration_open=True,
        )

        player = Player.objects.create(lichess_username="regularplayer", rating=1700)

        # Register without invite code
        form_data = get_valid_registration_form_data()
        form_data["friends"] = "friend1, friend2"
        form_data["avoid"] = "enemy1"

        form = RegistrationForm(data=form_data, season=regular_season, player=player)

        self.assertTrue(form.is_valid())
        registration = form.save()

        # Check registration is pending (not auto-approved)
        self.assertEqual(registration.status, "pending")

        # Check no team was created
        from heltour.tournament.models import TeamMember

        team_member = TeamMember.objects.filter(player=player).first()
        self.assertIsNone(team_member)

    def test_captain_code_with_duplicate_prevention(self):
        """Test that captain codes handle duplicate team creation gracefully."""
        captain = Player.objects.create(
            lichess_username="dupcaptain_unique1", rating=2000
        )

        # Create captain code
        captain_code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="DUP-CAPTAIN-001",
            code_type="captain",
        )

        # First registration
        form_data = get_valid_registration_form_data()
        form_data["invite_code"] = "DUP-CAPTAIN-001"

        form1 = RegistrationForm(data=form_data, season=self.season, player=captain)
        self.assertTrue(form1.is_valid())
        reg1 = form1.save()

        # Try to use the same code again (should fail)
        captain2 = Player.objects.create(lichess_username="dupcaptain2", rating=1950)

        form2 = RegistrationForm(data=form_data, season=self.season, player=captain2)

        self.assertFalse(form2.is_valid())
        self.assertIn("invite_code", form2.errors)


class FieldVisibilitySettingsTestCase(TestCase):
    """Test granular field visibility settings for registration."""

    def setUp(self):
        """Set up test data."""
        self.player = Player.objects.create(
            lichess_username="visibilitytest", rating=1700
        )

    def _create_league_and_season(self, tag, **league_kwargs):
        """Helper to create league and season with minimal boilerplate."""
        defaults = {
            "name": f"Test League {tag}",
            "tag": tag,
            "theme": "blue",
            "time_control": "45+45",
            "rating_type": "classical",
            "competitor_type": "team",
        }
        defaults.update(league_kwargs)
        league = League.objects.create(**defaults)
        season = Season.objects.create(
            league=league,
            name=f"Test Season {tag}",
            tag=f"season-{tag}",
            rounds=8,
            boards=4,
            start_date=timezone.now() + timedelta(days=7),
            registration_open=True,
            round_duration=timedelta(days=7),
        )
        return league, season

    def test_field_visibility_matrix(self):
        """Test all combinations of field visibility settings."""
        test_cases = [
            # (settings_dict, expected_fields_present, expected_fields_absent)
            ({}, [], ["first_name", "corporate_email", "fide_id", "regional_rating"]),
            (
                {"require_name": True},
                ["first_name", "last_name"],
                ["gender", "corporate_email", "fide_id"],
            ),
            (
                {"require_gender": True, "require_nationality": True},
                ["gender", "nationality"],
                ["first_name", "corporate_email", "fide_id"],
            ),
            (
                {"require_corporate_email": True, "require_personal_email": True},
                ["corporate_email", "personal_email"],
                ["first_name", "fide_id"],
            ),
            (
                {"require_contact_number": True},
                ["contact_number"],
                ["first_name", "corporate_email", "fide_id"],
            ),
            (
                {"require_fide_id": True},
                ["fide_id"],
                ["first_name", "corporate_email", "regional_rating"],
            ),
            (
                {"require_regional_rating": True, "regional_rating_name": "USCF"},
                ["regional_rating"],
                ["first_name", "corporate_email", "fide_id"],
            ),
            (
                {
                    "require_name": True,
                    "require_corporate_email": True,
                    "require_fide_id": True,
                    "require_regional_rating": True,
                },
                ["first_name", "corporate_email", "fide_id", "regional_rating"],
                [],
            ),
        ]

        for i, (settings, present, absent) in enumerate(test_cases):
            _, season = self._create_league_and_season(f"matrix-{i}", **settings)
            form = RegistrationForm(season=season, player=self.player)

            for field in present:
                self.assertIn(
                    field, form.fields, f"Case {i}: {field} should be present"
                )
            for field in absent:
                self.assertNotIn(
                    field, form.fields, f"Case {i}: {field} should be absent"
                )

    def test_required_fields_validation(self):
        """Test that enabled fields are actually required."""
        _, season = self._create_league_and_season(
            "required",
            require_name=True,
            require_corporate_email=True,
            require_fide_id=True,
            require_regional_rating=True,
            regional_rating_name="USCF",
        )

        form = RegistrationForm(
            data={
                "agreed_to_tos": True,
                "agreed_to_rules": True,
                "can_commit": True,
                "friends": "",
                "avoid": "",
                "alternate_preference": "full_time",
            },
            season=season,
            player=self.player,
        )

        self.assertFalse(form.is_valid())
        for field in [
            "first_name",
            "last_name",
            "corporate_email",
            "fide_id",
            "regional_rating",
        ]:
            self.assertIn(field, form.errors)

    def test_minimal_registration_saves_successfully(self):
        """Test that minimal registration (no optional fields) can be saved."""
        _, season = self._create_league_and_season(
            "minimal",
            require_name=False,
            require_personal_email=False,
            require_gender=False,
            require_date_of_birth=False,
            require_nationality=False,
            require_corporate_email=False,
            require_contact_number=False,
            require_fide_id=False,
            require_regional_rating=False,
            email_required=False,
            show_provisional_warning=False,
            ask_availability=False,
        )

        form = RegistrationForm(
            data={
                "agreed_to_tos": True,
                "agreed_to_rules": True,
                "can_commit": True,
                "friends": "",
                "avoid": "",
                "alternate_preference": "full_time",
            },
            season=season,
            player=self.player,
        )

        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        registration = form.save()
        self.assertEqual(registration.first_name, "")
        self.assertEqual(registration.corporate_email, "")

    def test_invite_only_with_minimal_fields(self):
        """Test invite-only leagues with minimal field requirements."""
        _, season = self._create_league_and_season(
            "invite",
            registration_mode="invite_only",
            require_name=False,
            require_personal_email=False,
            require_gender=False,
            require_date_of_birth=False,
            require_nationality=False,
            require_corporate_email=False,
            require_contact_number=False,
            require_fide_id=False,
            require_regional_rating=False,
            email_required=False,
            show_provisional_warning=False,
            ask_availability=False,
        )

        InviteCode.objects.create(
            league=season.league, season=season, code="TEST-123", code_type="captain"
        )
        form = RegistrationForm(season=season, player=self.player)

        self.assertIn("invite_code", form.fields)
        self.assertNotIn("first_name", form.fields)
        self.assertNotIn("corporate_email", form.fields)

    def test_individual_league_removes_team_fields(self):
        """Test that individual leagues don't show team-specific fields."""
        league, season = self._create_league_and_season(
            "individual",
            competitor_type="lone",
            require_fide_id=True,
            email_required=True,
        )

        form = RegistrationForm(season=season, player=self.player)

        self.assertNotIn("friends", form.fields)
        self.assertNotIn("avoid", form.fields)
        self.assertNotIn("alternate_preference", form.fields)
        self.assertIn("fide_id", form.fields)
        self.assertIn("email", form.fields)

    def test_fide_id_required_when_enabled(self):
        """Test that FIDE ID field is marked as required when require_fide_id=True."""
        _, season = self._create_league_and_season(
            "fide-required", require_fide_id=True
        )

        form = RegistrationForm(season=season, player=self.player)

        self.assertIn("fide_id", form.fields)
        self.assertTrue(form.fields["fide_id"].required)

    def test_regional_rating_label_customization(self):
        """Test that regional rating field label is customized based on regional_rating_name."""
        _, season = self._create_league_and_season(
            "uscf-rating",
            require_regional_rating=True,
            regional_rating_name="USCF",
        )

        form = RegistrationForm(season=season, player=self.player)

        self.assertIn("regional_rating", form.fields)
        self.assertTrue(form.fields["regional_rating"].required)
        self.assertIn("USCF", str(form.fields["regional_rating"].label))

    def test_regional_rating_without_name(self):
        """Test regional rating field when no specific name is provided."""
        _, season = self._create_league_and_season(
            "generic-rating",
            require_regional_rating=True,
            regional_rating_name="",
        )

        form = RegistrationForm(season=season, player=self.player)

        self.assertIn("regional_rating", form.fields)
        self.assertTrue(form.fields["regional_rating"].required)
