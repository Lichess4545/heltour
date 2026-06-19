"""
Database integration tests for multi-match knockout tournaments.

These tests verify that the database models work correctly with the tournament_core
multi-match logic and that round-trip conversions maintain tournament state.
"""

import unittest
from django.test import TestCase
from django.core.exceptions import ValidationError

from heltour.tournament.models import (
    League, Season, Round, Team, TeamMember, Player, TeamPairing, 
    KnockoutBracket, KnockoutSeeding, TeamMultiMatchProgress
)
from heltour.tournament.db_to_structure import (
    season_to_tournament_structure, 
    knockout_bracket_to_structure
)
from heltour.tournament_core.multi_match import (
    can_generate_next_match_set,
    generate_next_match_set,
    is_multi_match_stage_complete,
    calculate_multi_match_winners
)
from heltour.tournament_core.structure import TournamentFormat


class MultiMatchDatabaseModelsTest(TestCase):
    """Test the new database models for multi-match knockout tournaments."""
    
    def setUp(self):
        """Set up test data for database model tests."""
        # Create league and season
        self.league = League.objects.create(
            name="Test League",
            tag="TL",
            competitor_type="team",
            pairing_type="knockout"
        )
        
        self.season = Season.objects.create(
            name="Test Season",
            league=self.league,
            is_active=True,
            registration_open=True,
            rounds=3  # Add required rounds field
        )
        
        # Create teams
        self.team_a = Team.objects.create(
            name="Team A",
            season=self.season,
            number=1
        )
        
        self.team_b = Team.objects.create(
            name="Team B", 
            season=self.season,
            number=2
        )
        
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
    
    def test_knockout_bracket_with_matches_per_stage(self):
        """Test KnockoutBracket model with matches_per_stage field."""
        bracket = KnockoutBracket.objects.create(
            season=self.season,
            bracket_size=2,
            seeding_style="adjacent", 
            matches_per_stage=2,  # Return matches
            games_per_match=1
        )
        
        self.assertEqual(bracket.matches_per_stage, 2)
        self.assertEqual(bracket.games_per_match, 1)
        self.assertEqual(bracket.seeding_style, "adjacent")
    
    def test_team_multi_match_progress_model(self):
        """Test TeamMultiMatchProgress model creation and properties."""
        bracket = KnockoutBracket.objects.create(
            season=self.season,
            bracket_size=2,
            matches_per_stage=2
        )
        
        progress = TeamMultiMatchProgress.objects.create(
            bracket=bracket,
            team=self.team_a,
            round_number=1,
            stage_name="finals",
            opponent_team=self.team_b,
            original_pairing_order=1,
            matches_completed=1,
            total_matches_required=2
        )
        
        self.assertEqual(progress.team, self.team_a)
        self.assertEqual(progress.opponent_team, self.team_b) 
        self.assertEqual(progress.matches_completed, 1)
        self.assertEqual(progress.total_matches_required, 2)
        self.assertFalse(progress.is_stage_complete_for_pair)
        self.assertEqual(progress.current_match_number, 2)
        
        # Test completion
        progress.matches_completed = 2
        progress.save()
        self.assertTrue(progress.is_stage_complete_for_pair)
        self.assertEqual(progress.current_match_number, 2)
    
    def test_team_multi_match_progress_unique_constraints(self):
        """Test that unique constraints work properly."""
        bracket = KnockoutBracket.objects.create(
            season=self.season,
            bracket_size=2,
            matches_per_stage=2
        )
        
        # Create first progress record
        TeamMultiMatchProgress.objects.create(
            bracket=bracket,
            team=self.team_a,
            round_number=1,
            stage_name="finals",
            opponent_team=self.team_b,
            original_pairing_order=1,
            matches_completed=1,
            total_matches_required=2
        )
        
        # Attempting to create duplicate should fail
        with self.assertRaises(Exception):  # IntegrityError
            TeamMultiMatchProgress.objects.create(
                bracket=bracket,
                team=self.team_a,
                round_number=1,  # Same bracket, team, round_number
                stage_name="finals",
                opponent_team=self.team_b,
                original_pairing_order=1,
                matches_completed=0,
                total_matches_required=2
            )


class MultiMatchDbToStructureTest(TestCase):
    """Test conversion from database models to tournament_core structures."""
    
    def setUp(self):
        """Set up test data for db-to-structure tests."""
        # Create league and season
        self.league = League.objects.create(
            name="Test League",
            tag="TL", 
            competitor_type="team",
            pairing_type="knockout"
        )
        
        self.season = Season.objects.create(
            name="Test Season",
            league=self.league,
            is_active=True,
            registration_open=True,
            rounds=3  # Add required rounds field
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
    
    def test_knockout_bracket_to_structure_with_multi_match(self):
        """Test conversion of KnockoutBracket with matches_per_stage to tournament structure."""
        tournament = knockout_bracket_to_structure(self.bracket)
        
        self.assertEqual(tournament.format, TournamentFormat.KNOCKOUT)
        self.assertEqual(tournament.matches_per_stage, 2)
        self.assertEqual(tournament.current_match_number, 1)  # No matches yet
        self.assertEqual(len(tournament.competitors), 2)
        self.assertIn(self.team_a.id, tournament.competitors)
        self.assertIn(self.team_b.id, tournament.competitors)
    
    def test_season_to_tournament_structure_basic(self):
        """Test basic conversion of season to tournament structure."""
        tournament = season_to_tournament_structure(self.season)
        
        # Should have correct competitors
        self.assertEqual(len(tournament.competitors), 2)
        self.assertIn(self.team_a.id, tournament.competitors)
        self.assertIn(self.team_b.id, tournament.competitors)


class MultiMatchRoundTripTest(TestCase):
    """Test round-trip conversion: database -> tournament_core -> database."""
    
    def setUp(self):
        """Set up test data for round-trip tests."""
        # Create league and season
        self.league = League.objects.create(
            name="Test League", 
            tag="TL",
            competitor_type="team",
            pairing_type="knockout"
        )
        
        self.season = Season.objects.create(
            name="Test Season",
            league=self.league,
            is_active=True,
            registration_open=True,
            rounds=3  # Add required rounds field
        )
        
        # Create teams
        self.team_a = Team.objects.create(name="Team A", season=self.season, number=1)
        self.team_b = Team.objects.create(name="Team B", season=self.season, number=2)
        
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
    
    def test_empty_tournament_conversion(self):
        """Test conversion of tournament with no matches."""
        tournament = knockout_bracket_to_structure(self.bracket)
        
        self.assertEqual(tournament.matches_per_stage, 2)
        self.assertEqual(tournament.current_match_number, 1)
        self.assertEqual(len(tournament.rounds), 0)  # No rounds yet in empty bracket
    
    def test_multi_match_integration_with_core_logic(self):
        """Test integration between database models and tournament_core multi-match logic."""
        # Convert to tournament structure
        tournament = knockout_bracket_to_structure(self.bracket)
        
        # Test that core multi-match functions work with converted tournament
        self.assertFalse(can_generate_next_match_set(tournament, 1))  # No matches yet
        
        # The tournament should have the correct multi-match configuration
        self.assertEqual(tournament.matches_per_stage, 2)
        self.assertEqual(tournament.format, TournamentFormat.KNOCKOUT)


class MultiMatchProgressTrackingTest(TestCase):
    """Test tracking progress through multi-match knockout stages."""
    
    def setUp(self):
        """Set up test data for progress tracking tests."""
        # Create league and season
        self.league = League.objects.create(
            name="Test League",
            tag="TL",
            competitor_type="team", 
            pairing_type="knockout"
        )
        
        self.season = Season.objects.create(
            name="Test Season",
            league=self.league,
            is_active=True,
            registration_open=True,
            rounds=3  # Add required rounds field
        )
        
        # Create teams
        self.team_a = Team.objects.create(name="Team A", season=self.season, number=1)
        self.team_b = Team.objects.create(name="Team B", season=self.season, number=2)
        
        # Create knockout bracket
        self.bracket = KnockoutBracket.objects.create(
            season=self.season,
            bracket_size=2,
            seeding_style="adjacent",
            matches_per_stage=3,  # Best of 3
            games_per_match=1
        )
    
    def test_progress_tracking_workflow(self):
        """Test the complete workflow of tracking progress through multiple matches."""
        # Create initial progress records
        progress_a = TeamMultiMatchProgress.objects.create(
            bracket=self.bracket,
            team=self.team_a,
            round_number=1,
            stage_name="finals",
            opponent_team=self.team_b,
            original_pairing_order=1,
            matches_completed=0,
            total_matches_required=3
        )
        
        progress_b = TeamMultiMatchProgress.objects.create(
            bracket=self.bracket,
            team=self.team_b,
            round_number=1,
            stage_name="finals", 
            opponent_team=self.team_a,
            original_pairing_order=1,
            matches_completed=0,
            total_matches_required=3
        )
        
        # Initially no matches completed
        self.assertEqual(progress_a.current_match_number, 1)
        self.assertFalse(progress_a.is_stage_complete_for_pair)
        
        # Complete first match
        progress_a.matches_completed = 1
        progress_b.matches_completed = 1
        progress_a.save()
        progress_b.save()
        
        self.assertEqual(progress_a.current_match_number, 2)
        self.assertFalse(progress_a.is_stage_complete_for_pair)
        
        # Complete second match
        progress_a.matches_completed = 2  
        progress_b.matches_completed = 2
        progress_a.save()
        progress_b.save()
        
        self.assertEqual(progress_a.current_match_number, 3)
        self.assertFalse(progress_a.is_stage_complete_for_pair)
        
        # Complete third match
        progress_a.matches_completed = 3
        progress_b.matches_completed = 3
        progress_a.save()
        progress_b.save()
        
        self.assertEqual(progress_a.current_match_number, 3)
        self.assertTrue(progress_a.is_stage_complete_for_pair)
    
    def test_bulk_progress_query(self):
        """Test querying progress for multiple teams efficiently."""
        # Create progress for multiple team pairs
        TeamMultiMatchProgress.objects.create(
            bracket=self.bracket,
            team=self.team_a,
            round_number=1,
            stage_name="finals",
            opponent_team=self.team_b,
            original_pairing_order=1,
            matches_completed=1,
            total_matches_required=3
        )
        
        # Query all progress for a round
        round_progress = TeamMultiMatchProgress.objects.filter(
            bracket=self.bracket,
            round_number=1
        ).select_related('team', 'opponent_team')
        
        self.assertEqual(len(round_progress), 1)
        self.assertEqual(round_progress[0].matches_completed, 1)
        
        # Test index usage for common queries
        bracket_progress = TeamMultiMatchProgress.objects.filter(
            bracket=self.bracket,
            round_number=1,
            matches_completed__lt=3
        )
        
        self.assertEqual(len(bracket_progress), 1)


class MultiMatchRoundTripConversionTest(TestCase):
    """Test complete round-trip: database -> tournament_core -> database."""
    
    def setUp(self):
        """Set up test data for round-trip conversion tests."""
        # Create league and season
        self.league = League.objects.create(
            name="Test League",
            tag="TL",
            competitor_type="team",
            pairing_type="knockout"
        )
        
        self.season = Season.objects.create(
            name="Test Season",
            league=self.league,
            is_active=True,
            registration_open=True,
            rounds=3  # Add required rounds field
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
    
    def test_round_trip_conversion_preservation(self):
        """Test that converting db -> structure -> db preserves multi-match settings."""
        from heltour.tournament.db_to_structure import update_multi_match_progress_from_tournament
        
        # Convert database to structure
        tournament = knockout_bracket_to_structure(self.bracket)
        
        # Verify structure has correct multi-match settings
        self.assertEqual(tournament.matches_per_stage, 2)
        self.assertEqual(tournament.format, TournamentFormat.KNOCKOUT)
        
        # Convert structure back to database (progress tracking)
        records_created = update_multi_match_progress_from_tournament(tournament, self.bracket)
        
        # Should create no progress records for empty tournament
        self.assertEqual(records_created, 0)
        
        # Verify bracket settings are preserved
        self.bracket.refresh_from_db()
        self.assertEqual(self.bracket.matches_per_stage, 2)
        self.assertEqual(self.bracket.bracket_size, 2)
    
    def test_structure_to_db_progress_creation(self):
        """Test creating progress records from tournament structure."""
        from heltour.tournament.db_to_structure import update_multi_match_progress_from_tournament
        from heltour.tournament_core.builder import TournamentBuilder
        from heltour.tournament_core.structure import Tournament, Round, Match
        
        # Create a tournament structure with matches
        tournament = Tournament(
            competitors=[self.team_a.id, self.team_b.id],
            rounds=[
                Round(
                    number=1,
                    matches=[
                        Match(
                            competitor1_id=self.team_a.id,
                            competitor2_id=self.team_b.id,
                            games=[],  # No games yet
                            games_per_match=1
                        )
                    ],
                    knockout_stage="finals"
                )
            ],
            format=TournamentFormat.KNOCKOUT,
            matches_per_stage=2,
            current_match_number=1
        )
        
        # Convert to database progress records
        records_created = update_multi_match_progress_from_tournament(tournament, self.bracket)
        
        # Should create progress records for both teams
        self.assertEqual(records_created, 2)
        
        # Verify progress records were created correctly
        progress_records = TeamMultiMatchProgress.objects.filter(bracket=self.bracket)
        self.assertEqual(len(progress_records), 2)
        
        # Check specific progress details
        progress_a = TeamMultiMatchProgress.objects.get(bracket=self.bracket, team=self.team_a)
        self.assertEqual(progress_a.opponent_team, self.team_b)
        self.assertEqual(progress_a.round_number, 1)
        self.assertEqual(progress_a.stage_name, "finals")
        self.assertEqual(progress_a.original_pairing_order, 1)
        self.assertEqual(progress_a.total_matches_required, 2)
        self.assertEqual(progress_a.matches_completed, 0)  # No completed matches yet