"""
Tests for multi-match knockout tournaments.

Tests the core logic for knockout tournaments where each stage consists of
multiple matches between the same competitors (e.g., return matches with
color switching).
"""

import unittest
from heltour.tournament_core.multi_match import (
    get_match_number_from_pairing_order,
    get_original_pairing_order,
    get_pairing_order_for_match,
    can_generate_next_match_set,
    generate_next_match_set,
    calculate_multi_match_winners,
    is_multi_match_stage_complete,
    get_multi_match_stage_status,
)
from heltour.tournament_core.structure import Tournament, Round, Match, Game, Player, GameResult, TournamentFormat
from heltour.tournament_core.knockout import create_knockout_tournament
from heltour.tournament_core.builder import TournamentBuilder
from heltour.tournament_core.assertions import assert_tournament


class TestPairingOrderArithmetic(unittest.TestCase):
    """Test the modular arithmetic functions for pairing order calculation."""

    def test_match_number_calculation(self):
        """Test calculating match number from pairing order."""
        # 4 team pairs example
        total_pairs = 4
        
        # Match 1: pairing orders 1-4
        self.assertEqual(get_match_number_from_pairing_order(1, total_pairs), 1)
        self.assertEqual(get_match_number_from_pairing_order(2, total_pairs), 1)
        self.assertEqual(get_match_number_from_pairing_order(3, total_pairs), 1)
        self.assertEqual(get_match_number_from_pairing_order(4, total_pairs), 1)
        
        # Match 2: pairing orders 5-8
        self.assertEqual(get_match_number_from_pairing_order(5, total_pairs), 2)
        self.assertEqual(get_match_number_from_pairing_order(6, total_pairs), 2)
        self.assertEqual(get_match_number_from_pairing_order(7, total_pairs), 2)
        self.assertEqual(get_match_number_from_pairing_order(8, total_pairs), 2)
        
        # Match 3: pairing orders 9-12
        self.assertEqual(get_match_number_from_pairing_order(9, total_pairs), 3)
        self.assertEqual(get_match_number_from_pairing_order(12, total_pairs), 3)

    def test_original_pairing_order_calculation(self):
        """Test finding original pairing order from return match."""
        total_pairs = 4
        
        # Match 1 (original) maps to itself
        self.assertEqual(get_original_pairing_order(1, total_pairs), 1)
        self.assertEqual(get_original_pairing_order(2, total_pairs), 2)
        self.assertEqual(get_original_pairing_order(3, total_pairs), 3)
        self.assertEqual(get_original_pairing_order(4, total_pairs), 4)
        
        # Match 2 (return) maps back to match 1
        self.assertEqual(get_original_pairing_order(5, total_pairs), 1)
        self.assertEqual(get_original_pairing_order(6, total_pairs), 2)
        self.assertEqual(get_original_pairing_order(7, total_pairs), 3)
        self.assertEqual(get_original_pairing_order(8, total_pairs), 4)

    def test_pairing_order_for_match_calculation(self):
        """Test calculating pairing order for specific match number."""
        total_pairs = 4
        
        # Original match (match 1)
        self.assertEqual(get_pairing_order_for_match(1, 1, total_pairs), 1)
        self.assertEqual(get_pairing_order_for_match(2, 1, total_pairs), 2)
        self.assertEqual(get_pairing_order_for_match(3, 1, total_pairs), 3)
        self.assertEqual(get_pairing_order_for_match(4, 1, total_pairs), 4)
        
        # Return match (match 2)
        self.assertEqual(get_pairing_order_for_match(1, 2, total_pairs), 5)
        self.assertEqual(get_pairing_order_for_match(2, 2, total_pairs), 6)
        self.assertEqual(get_pairing_order_for_match(3, 2, total_pairs), 7)
        self.assertEqual(get_pairing_order_for_match(4, 2, total_pairs), 8)

    def test_invalid_inputs(self):
        """Test error handling for invalid inputs."""
        with self.assertRaises(ValueError):
            get_match_number_from_pairing_order(0, 4)  # pairing_order < 1
            
        with self.assertRaises(ValueError):
            get_match_number_from_pairing_order(1, 0)  # total_pairs < 1
            
        with self.assertRaises(ValueError):
            get_original_pairing_order(0, 4)  # pairing_order < 1
            
        with self.assertRaises(ValueError):
            get_pairing_order_for_match(5, 1, 4)  # original_pairing_order > total_pairs


class TestGlobalSynchronization(unittest.TestCase):
    """Test that next match sets can only be generated when ALL teams complete current match."""

    def test_cannot_generate_when_partial_complete(self):
        """Test that next match set cannot be generated when only some teams completed."""
        builder = TournamentBuilder()
        tournament = (builder
            .multi_match_knockout(matches_per_stage=2)
            .team("Team A", ("Alice", 2000), ("Bob", 1900))
            .team("Team B", ("Charlie", 1950), ("David", 1850))
            .team("Team C", ("Eve", 1920), ("Frank", 1880))
            .team("Team D", ("Grace", 1970), ("Henry", 1840))
            .round(1)
            .bracket_seeding(["Team A", "Team B", "Team C", "Team D"], "adjacent")
            .match("Team A", "Team B", "1-0")  # Team A beats Team B
            # Team C vs Team D not yet complete
            .build())
        
        # Should not be able to generate next match set
        self.assertFalse(can_generate_next_match_set(tournament, round_number=1))

    def test_can_generate_when_all_complete(self):
        """Test that next match set can be generated when ALL teams completed."""
        builder = TournamentBuilder()
        tournament = (builder
            .multi_match_knockout(matches_per_stage=2)
            .team("Team A", ("Alice", 2000), ("Bob", 1900))
            .team("Team B", ("Charlie", 1950), ("David", 1850))
            .team("Team C", ("Eve", 1920), ("Frank", 1880))
            .team("Team D", ("Grace", 1970), ("Henry", 1840))
            .round(1)
            .bracket_seeding(["Team A", "Team B", "Team C", "Team D"], "adjacent")
            .match("Team A", "Team B", "1-0")  # Team A beats Team B
            .match("Team C", "Team D", "1-0")  # Team C beats Team D
            .build())
        
        # Should be able to generate next match set
        self.assertTrue(can_generate_next_match_set(tournament, round_number=1))

    def test_cannot_generate_beyond_max_matches(self):
        """Test that next match set cannot be generated beyond max matches per stage."""
        builder = TournamentBuilder()
        tournament = (builder
            .multi_match_knockout(matches_per_stage=2)
            .team("Team A", ("Alice", 2000), ("Bob", 1900))
            .team("Team B", ("Charlie", 1950), ("David", 1850))
            .team("Team C", ("Eve", 1920), ("Frank", 1880))
            .team("Team D", ("Grace", 1970), ("Henry", 1840))
            .round(1)
            .bracket_seeding(["Team A", "Team B", "Team C", "Team D"], "adjacent")
            .match("Team A", "Team B", "1-0")
            .match("Team C", "Team D", "1-0")
            .generate_next_match_set()  # Generate match 2
            .match("Team B", "Team A", "0-1")  # Team A wins return match as black
            .match("Team D", "Team C", "0-1")  # Team C wins return match as black
            .build())
        
        # Already at max matches (2), cannot generate more
        self.assertFalse(can_generate_next_match_set(tournament, round_number=1))


class TestColorSwitching(unittest.TestCase):
    """Test that return matches correctly flip colors from original matches."""

    def test_color_switching_in_return_matches(self):
        """Test that return matches have flipped colors."""
        builder = TournamentBuilder()
        tournament = (builder
            .multi_match_knockout(matches_per_stage=2)
            .team("Team A", ("Alice", 2000), ("Bob", 1900))
            .team("Team B", ("Charlie", 1950), ("David", 1850))
            .round(1)
            .bracket_seeding(["Team A", "Team B"], "adjacent")
            .match("Team A", "Team B", "1-0")  # Team A (white) beats Team B (black)
            .generate_next_match_set()  # Generate return match
            .build())
        
        round_obj = tournament.rounds[0]
        
        # Should have 2 matches total
        self.assertEqual(len(round_obj.matches), 2)
        
        # First match: Team A vs Team B (Team A white)
        first_match = round_obj.matches[0]
        team_a_id = builder.metadata.teams["Team A"]["id"]
        team_b_id = builder.metadata.teams["Team B"]["id"]
        
        self.assertEqual(first_match.competitor1_id, team_a_id)  # Team A white
        self.assertEqual(first_match.competitor2_id, team_b_id)  # Team B black
        
        # Second match: Team B vs Team A (colors flipped)
        second_match = round_obj.matches[1]
        self.assertEqual(second_match.competitor1_id, team_b_id)  # Team B white (flipped)
        self.assertEqual(second_match.competitor2_id, team_a_id)  # Team A black (flipped)

    def test_multiple_pair_color_switching(self):
        """Test color switching with multiple team pairs."""
        builder = TournamentBuilder()
        tournament = (builder
            .multi_match_knockout(matches_per_stage=2)
            .team("Team A", ("Alice", 2000), ("Bob", 1900))
            .team("Team B", ("Charlie", 1950), ("David", 1850))
            .team("Team C", ("Eve", 1920), ("Frank", 1880))
            .team("Team D", ("Grace", 1970), ("Henry", 1840))
            .round(1)
            .bracket_seeding(["Team A", "Team B", "Team C", "Team D"], "adjacent")
            .match("Team A", "Team B", "1-0")
            .match("Team C", "Team D", "1-0")
            .generate_next_match_set()
            .build())
        
        round_obj = tournament.rounds[0]
        
        # Should have 4 matches total (2 original + 2 return)
        self.assertEqual(len(round_obj.matches), 4)
        
        # Get team IDs
        team_a_id = builder.metadata.teams["Team A"]["id"]
        team_b_id = builder.metadata.teams["Team B"]["id"]
        team_c_id = builder.metadata.teams["Team C"]["id"]
        team_d_id = builder.metadata.teams["Team D"]["id"]
        
        # Check original matches
        self.assertEqual(round_obj.matches[0].competitor1_id, team_a_id)  # Team A white
        self.assertEqual(round_obj.matches[0].competitor2_id, team_b_id)  # Team B black
        self.assertEqual(round_obj.matches[1].competitor1_id, team_c_id)  # Team C white
        self.assertEqual(round_obj.matches[1].competitor2_id, team_d_id)  # Team D black
        
        # Check return matches (colors flipped)
        self.assertEqual(round_obj.matches[2].competitor1_id, team_b_id)  # Team B white (flipped)
        self.assertEqual(round_obj.matches[2].competitor2_id, team_a_id)  # Team A black (flipped)
        self.assertEqual(round_obj.matches[3].competitor1_id, team_d_id)  # Team D white (flipped)
        self.assertEqual(round_obj.matches[3].competitor2_id, team_c_id)  # Team C black (flipped)


class TestBasicMultiMatchWinnerCalculation(unittest.TestCase):
    """Test calculating winners from multiple matches between same competitors."""

    def test_simple_two_match_winner(self):
        """Test winner calculation with clear 2-0 result."""
        builder = TournamentBuilder()
        tournament = (builder
            .multi_match_knockout(matches_per_stage=2)
            .team("Team A", ("Alice", 2000), ("Bob", 1900))
            .team("Team B", ("Charlie", 1950), ("David", 1850))
            .round(1)
            .bracket_seeding(["Team A", "Team B"], "adjacent")
            .match("Team A", "Team B", "1-0")  # Team A wins match 1
            .generate_next_match_set()
            .match("Team B", "Team A", "0-1")  # Team A wins match 2 (as black)
            .build())
        
        round_obj = tournament.rounds[0]
        winners = calculate_multi_match_winners(round_obj.matches, 1, 2, tournament.scoring)
        
        team_a_id = builder.metadata.teams["Team A"]["id"]
        self.assertEqual(winners, [team_a_id])  # Team A won both matches