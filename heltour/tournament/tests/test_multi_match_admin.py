"""
Admin interface tests for multi-match knockout tournaments.

These tests verify that the admin interface correctly handles multi-match tournaments,
including creating brackets, generating next match sets, and tracking progress.
"""

from django.test import TestCase
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpRequest
from unittest.mock import Mock

from heltour.tournament.models import (
    League, Season, Round, Team, TeamMember, Player, TeamPairing,
    KnockoutBracket, KnockoutSeeding, TeamMultiMatchProgress
)
from heltour.tournament.admin import KnockoutBracketAdmin, TeamMultiMatchProgressAdmin


class MockRequest:
    """Mock request object for admin testing."""
    
    def __init__(self, user=None):
        self.user = user or User()
        self.session = {}
        self._messages = FallbackStorage(self)
    
    def _get_messages(self):
        return getattr(self._messages, '_queued_messages', [])
    
    def _add_message(self, level, message, extra_tags=''):
        if not hasattr(self._messages, '_queued_messages'):
            self._messages._queued_messages = []
        self._messages._queued_messages.append({
            'level': level,
            'message': message,
            'extra_tags': extra_tags
        })


class MultiMatchKnockoutBracketAdminTest(TestCase):
    """Test the KnockoutBracket admin interface for multi-match tournaments."""
    
    def setUp(self):
        """Set up test data for admin tests."""
        # Create league and season
        self.league = League.objects.create(
            name="Test League",
            tag="TL",
            competitor_type="team",
            pairing_type="knockout"
        )
        
        self.season = Season.objects.create(
            name="Test Season",
            tag="TS1",
            league=self.league,
            is_active=True,
            registration_open=True,
            rounds=3
        )
        
        # Create teams
        self.team_a = Team.objects.create(name="Team A", season=self.season, number=1)
        self.team_b = Team.objects.create(name="Team B", season=self.season, number=2)
        self.team_c = Team.objects.create(name="Team C", season=self.season, number=3)
        self.team_d = Team.objects.create(name="Team D", season=self.season, number=4)
        
        # Create players
        self.player_a1 = Player.objects.create(lichess_username="alice")
        self.player_a2 = Player.objects.create(lichess_username="bob")
        self.player_b1 = Player.objects.create(lichess_username="charlie")
        self.player_b2 = Player.objects.create(lichess_username="david")
        
        # Create team members
        TeamMember.objects.create(team=self.team_a, player=self.player_a1, board_number=1)
        TeamMember.objects.create(team=self.team_a, player=self.player_a2, board_number=2)
        TeamMember.objects.create(team=self.team_b, player=self.player_b1, board_number=1)
        TeamMember.objects.create(team=self.team_b, player=self.player_b2, board_number=2)
        
        # Create admin site and admin
        self.site = AdminSite()
        self.admin = KnockoutBracketAdmin(KnockoutBracket, self.site)
        
        # Create user and request
        self.user = User.objects.create_user('admin', 'admin@test.com', 'password')
        self.request = MockRequest(self.user)
        
        # Create round
        self.round = Round.objects.create(
            season=self.season,
            number=1,
            is_completed=False,
            knockout_stage="semifinals"
        )
    
    def test_tournament_type_display(self):
        """Test that tournament_type method displays correctly."""
        # Create separate seasons for each bracket (OneToOneField constraint)
        season2 = Season.objects.create(
            name="Test Season 2",
            tag="TS2",
            league=self.league,
            is_active=True,
            registration_open=True,
            rounds=3
        )
        
        season3 = Season.objects.create(
            name="Test Season 3",
            tag="TS3",
            league=self.league,
            is_active=True,
            registration_open=True,
            rounds=3
        )
        
        # Single elimination
        bracket_single = KnockoutBracket.objects.create(
            season=self.season,
            bracket_size=4,
            matches_per_stage=1
        )
        
        # Return matches  
        bracket_return = KnockoutBracket.objects.create(
            season=season2,
            bracket_size=4,
            matches_per_stage=2
        )
        
        # Triple matches
        bracket_triple = KnockoutBracket.objects.create(
            season=season3,
            bracket_size=4,
            matches_per_stage=3
        )
        
        self.assertEqual(self.admin.tournament_type(bracket_single), "Single Elimination")
        self.assertEqual(self.admin.tournament_type(bracket_return), "Return Matches")
        self.assertEqual(self.admin.tournament_type(bracket_triple), "3-Match Stages")
    
    def test_generate_next_match_set_action_validation(self):
        """Test validation in generate_next_match_set_action."""
        bracket = KnockoutBracket.objects.create(
            season=self.season,
            bracket_size=4,
            matches_per_stage=1  # Single elimination
        )
        
        # Test with single elimination (should fail)
        queryset = KnockoutBracket.objects.filter(id=bracket.id)
        self.admin.generate_next_match_set_action(self.request, queryset)
        
        # Check that error message was added  
        messages = self.request._get_messages()
        self.assertTrue(len(messages) > 0)
        # Access message content properly
        first_message = messages[0]
        if hasattr(first_message, 'message'):
            message_text = str(first_message.message)
        elif 'message' in first_message:
            message_text = str(first_message['message'])
        else:
            message_text = str(first_message)
        
        self.assertIn("not a multi-match tournament", message_text)
    
    def test_generate_next_match_set_action_multiple_selection(self):
        """Test that action fails with multiple brackets selected."""
        # Create separate season for second bracket
        season2 = Season.objects.create(
            name="Test Season 2",
            tag="TS2B",
            league=self.league,
            is_active=True,
            registration_open=True,
            rounds=3
        )
        
        bracket1 = KnockoutBracket.objects.create(
            season=self.season,
            bracket_size=4,
            matches_per_stage=2
        )
        
        bracket2 = KnockoutBracket.objects.create(
            season=season2,
            bracket_size=4,
            matches_per_stage=2
        )
        
        queryset = KnockoutBracket.objects.filter(id__in=[bracket1.id, bracket2.id])
        self.admin.generate_next_match_set_action(self.request, queryset)
        
        # Check that error message was added
        messages = self.request._get_messages()
        self.assertTrue(len(messages) > 0)
        # Access message content properly
        first_message = messages[0]
        if hasattr(first_message, 'message'):
            message_text = str(first_message.message)
        elif 'message' in first_message:
            message_text = str(first_message['message'])
        else:
            message_text = str(first_message)
        self.assertIn("exactly one bracket", message_text)
    
    def test_list_display_fields(self):
        """Test that all list_display fields work correctly."""
        bracket = KnockoutBracket.objects.create(
            season=self.season,
            bracket_size=4,
            seeding_style="adjacent",
            games_per_match=1,
            matches_per_stage=2,
            is_completed=False
        )
        
        # Test each field in list_display
        self.assertEqual(str(bracket.season), str(self.season))
        self.assertEqual(bracket.bracket_size, 4)
        self.assertEqual(bracket.seeding_style, "adjacent")
        self.assertEqual(bracket.games_per_match, 1)
        self.assertEqual(bracket.matches_per_stage, 2)
        self.assertEqual(self.admin.tournament_type(bracket), "Return Matches")
        self.assertEqual(bracket.is_completed, False)


class MultiMatchProgressAdminTest(TestCase):
    """Test the TeamMultiMatchProgress admin interface."""
    
    def setUp(self):
        """Set up test data for progress admin tests."""
        # Create league and season
        self.league = League.objects.create(
            name="Test League",
            tag="TL",
            competitor_type="team",
            pairing_type="knockout"
        )
        
        self.season = Season.objects.create(
            name="Test Season",
            tag="TS1",
            league=self.league,
            is_active=True,
            registration_open=True,
            rounds=3
        )
        
        # Create teams
        self.team_a = Team.objects.create(name="Team A", season=self.season, number=1)
        self.team_b = Team.objects.create(name="Team B", season=self.season, number=2)
        
        # Create knockout bracket
        self.bracket = KnockoutBracket.objects.create(
            season=self.season,
            bracket_size=2,
            matches_per_stage=3
        )
        
        # Create admin
        self.site = AdminSite()
        self.admin = TeamMultiMatchProgressAdmin(TeamMultiMatchProgress, self.site)
    
    def test_progress_percentage_display(self):
        """Test that progress_percentage method calculates correctly."""
        # Create progress record
        progress = TeamMultiMatchProgress.objects.create(
            bracket=self.bracket,
            team=self.team_a,
            round_number=1,
            stage_name="finals",
            opponent_team=self.team_b,
            original_pairing_order=1,
            matches_completed=2,
            total_matches_required=3
        )
        
        result = self.admin.progress_percentage(progress)
        self.assertEqual(result, "67%")
    
    def test_progress_percentage_zero_total(self):
        """Test progress_percentage with zero total matches."""
        progress = TeamMultiMatchProgress.objects.create(
            bracket=self.bracket,
            team=self.team_a,
            round_number=1,
            stage_name="finals",
            opponent_team=self.team_b,
            original_pairing_order=1,
            matches_completed=0,
            total_matches_required=0
        )
        
        result = self.admin.progress_percentage(progress)
        self.assertEqual(result, "0%")
    
    def test_current_match_status_incomplete(self):
        """Test current_match_status for incomplete stage."""
        progress = TeamMultiMatchProgress.objects.create(
            bracket=self.bracket,
            team=self.team_a,
            round_number=1,
            stage_name="finals",
            opponent_team=self.team_b,
            original_pairing_order=1,
            matches_completed=1,
            total_matches_required=3
        )
        
        result = self.admin.current_match_status(progress)
        self.assertEqual(result, "🔄 Match 2 of 3")
    
    def test_current_match_status_complete(self):
        """Test current_match_status for complete stage."""
        progress = TeamMultiMatchProgress.objects.create(
            bracket=self.bracket,
            team=self.team_a,
            round_number=1,
            stage_name="finals",
            opponent_team=self.team_b,
            original_pairing_order=1,
            matches_completed=3,
            total_matches_required=3
        )
        
        result = self.admin.current_match_status(progress)
        self.assertEqual(result, "✅ Stage Complete")
    
    def test_list_display_fields(self):
        """Test that all list_display fields work correctly."""
        progress = TeamMultiMatchProgress.objects.create(
            bracket=self.bracket,
            team=self.team_a,
            round_number=1,
            stage_name="finals",
            opponent_team=self.team_b,
            original_pairing_order=1,
            matches_completed=2,
            total_matches_required=3
        )
        
        # Test each field in list_display
        self.assertEqual(progress.team, self.team_a)
        self.assertEqual(progress.opponent_team, self.team_b)
        self.assertEqual(progress.bracket, self.bracket)
        self.assertEqual(progress.round_number, 1)
        self.assertEqual(progress.stage_name, "finals")
        self.assertEqual(progress.matches_completed, 2)
        self.assertEqual(progress.total_matches_required, 3)
        self.assertEqual(self.admin.progress_percentage(progress), "67%")
        self.assertIsNotNone(progress.last_updated)


class MultiMatchAdminIntegrationTest(TestCase):
    """Integration tests for multi-match admin functionality."""
    
    def setUp(self):
        """Set up test data for integration tests."""
        # Create league and season
        self.league = League.objects.create(
            name="Test League",
            tag="TL",
            competitor_type="team",
            pairing_type="knockout"
        )
        
        self.season = Season.objects.create(
            name="Test Season",
            tag="TS1",
            league=self.league,
            is_active=True,
            registration_open=True,
            rounds=3
        )
        
        # Create teams
        self.team_a = Team.objects.create(name="Team A", season=self.season, number=1)
        self.team_b = Team.objects.create(name="Team B", season=self.season, number=2)
        
        # Create knockout bracket
        self.bracket = KnockoutBracket.objects.create(
            season=self.season,
            bracket_size=2,
            seeding_style="adjacent",
            matches_per_stage=2,
            games_per_match=1
        )
        
        # Create seedings
        KnockoutSeeding.objects.create(bracket=self.bracket, team=self.team_a, seed_number=1)
        KnockoutSeeding.objects.create(bracket=self.bracket, team=self.team_b, seed_number=2)
        
        # Create round
        self.round = Round.objects.create(
            season=self.season,
            number=1,
            is_completed=False,
            knockout_stage="finals"
        )
        
        # Create initial pairing
        self.pairing = TeamPairing.objects.create(
            white_team=self.team_a,
            black_team=self.team_b,
            round=self.round,
            pairing_order=1
        )
        
        # Create admin
        self.site = AdminSite()
        self.admin = KnockoutBracketAdmin(KnockoutBracket, self.site)
        self.user = User.objects.create_user('admin', 'admin@test.com', 'password')
        self.request = MockRequest(self.user)
    
    def test_create_next_match_pairings_helper(self):
        """Test that _create_next_match_pairings creates correct database objects."""
        from heltour.tournament_core.structure import Tournament, Round, Match, TournamentFormat
        
        # Create a tournament structure with return matches
        tournament = Tournament(
            competitors=[self.team_a.id, self.team_b.id],
            rounds=[
                Round(
                    number=1,
                    matches=[
                        # Original match
                        Match(
                            competitor1_id=self.team_a.id,
                            competitor2_id=self.team_b.id,
                            games=[],
                            games_per_match=1
                        ),
                        # Return match (colors flipped)
                        Match(
                            competitor1_id=self.team_b.id,  # Flipped
                            competitor2_id=self.team_a.id,
                            games=[],
                            games_per_match=1
                        )
                    ],
                    knockout_stage="finals"
                )
            ],
            format=TournamentFormat.KNOCKOUT,
            matches_per_stage=2,
            current_match_number=2
        )
        
        # Should have 1 pairing before
        initial_count = TeamPairing.objects.filter(round=self.round).count()
        self.assertEqual(initial_count, 1)
        
        # Call the helper method
        self.admin._create_next_match_pairings(tournament, self.bracket, 1)
        
        # Should have 2 pairings after (original + return match)
        final_count = TeamPairing.objects.filter(round=self.round).count()
        self.assertEqual(final_count, 2)
        
        # Check the return match has flipped colors
        return_pairing = TeamPairing.objects.filter(round=self.round, pairing_order=2).first()
        self.assertIsNotNone(return_pairing)
        self.assertEqual(return_pairing.white_team, self.team_b)  # Flipped
        self.assertEqual(return_pairing.black_team, self.team_a)
        
    def test_admin_queryset_optimization(self):
        """Test that admin querysets are optimized with select_related."""
        # Create progress record
        progress = TeamMultiMatchProgress.objects.create(
            bracket=self.bracket,
            team=self.team_a,
            round_number=1,
            stage_name="finals",
            opponent_team=self.team_b,
            original_pairing_order=1,
            matches_completed=1,
            total_matches_required=2
        )
        
        # Test KnockoutBracket admin queryset
        bracket_queryset = self.admin.get_queryset(self.request)
        self.assertTrue(hasattr(bracket_queryset, 'query'))
        
        # Test TeamMultiMatchProgress admin queryset
        progress_admin = TeamMultiMatchProgressAdmin(TeamMultiMatchProgress, self.site)
        progress_queryset = progress_admin.get_queryset(self.request)
        self.assertTrue(hasattr(progress_queryset, 'query'))
    
    def test_admin_field_validation(self):
        """Test that admin fieldsets contain all expected fields."""
        # Test KnockoutBracket fieldsets
        expected_fields = {
            "season", "bracket_size", "seeding_style", 
            "games_per_match", "matches_per_stage", "is_completed"
        }
        
        all_fields = set()
        for fieldset in self.admin.fieldsets:
            for field in fieldset[1]['fields']:
                all_fields.add(field)
        
        self.assertTrue(expected_fields.issubset(all_fields))
        
        # Test TeamMultiMatchProgress fieldsets
        progress_admin = TeamMultiMatchProgressAdmin(TeamMultiMatchProgress, self.site)
        expected_progress_fields = {
            "bracket", "team", "opponent_team", "round_number", "stage_name",
            "original_pairing_order", "matches_completed", "total_matches_required"
        }
        
        all_progress_fields = set()
        for fieldset in progress_admin.fieldsets:
            for field in fieldset[1]['fields']:
                all_progress_fields.add(field)
        
        self.assertTrue(expected_progress_fields.issubset(all_progress_fields))