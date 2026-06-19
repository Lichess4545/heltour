"""
Integration tests for TRF16 parser with tournament builder.
"""

import unittest
from heltour.tournament_core.trf16_converter import TRF16Converter
from heltour.tournament_core.assertions import assert_tournament


class TestTRF16Integration(unittest.TestCase):
    """Test TRF16 integration with tournament structures."""

    def setUp(self):
        """Set up test data with a more complete example."""
        # This is a simplified but complete TRF16 for a 2-round team tournament
        self.trf16_content = """012 Regional Team Championship
022 Athens
032 GRE
042 2024/03/01
052 2024/03/02
062 8 (8)
072 8
082 2
092 Team Swiss System
102 John Smith IA
112 Jane Doe FA
122 90 minutes plus 30 sec per move
142 2
132                                                                                        24/03/01  24/03/02

001    1 m    Board1 TeamA                      2100 GRE    10000001 1990/01/01  1.5   3     5 w 1     7 b =
001    2 m    Board2 TeamA                      2050 GRE    10000002 1991/01/01  1.0   5     6 b =     8 w =
001    3 m    Board1 TeamB                      2000 GRE    10000003 1992/01/01  2.0   1     7 w 1     5 b 1
001    4 m    Board2 TeamB                      1950 GRE    10000004 1993/01/01  0.0   8     8 b 0     6 w 0
001    5 m    Board1 TeamC                      2150 GRE    10000005 1988/01/01  0.5   6     1 b 0     3 w 0
001    6 m    Board2 TeamC                      2100 GRE    10000006 1989/01/01  1.5   4     2 w =     4 b 1
001    7 m    Board1 TeamD                      1900 GRE    10000007 1994/01/01  0.5   7     3 b 0     1 w =
001    8 m    Board2 TeamD                      1850 GRE    10000008 1995/01/01  1.0   2     4 w 1     2 b =

013 Team Alpha                           1    2
013 Team Beta                            3    4
013 Team Gamma                           5    6
013 Team Delta                           7    8"""

    def test_create_tournament_from_trf16(self):
        """Test creating a tournament structure from TRF16 data."""
        converter = TRF16Converter(self.trf16_content)
        converter.parse()

        # Create tournament builder with teams
        builder = converter.create_tournament_builder()

        # Add all rounds
        converter.add_rounds_to_builder(builder)

        # Build tournament
        tournament = builder.build()

        # Verify tournament structure
        self.assertEqual(len(tournament.competitors), 4)  # 4 teams
        self.assertEqual(len(tournament.rounds), 2)  # 2 rounds

        # Test team standings
        # Round 1: Alpha vs Gamma (1.5-0.5), Beta vs Delta (1-1)
        # Round 2: Alpha vs Delta (1-1), Beta vs Gamma (1-1)
        # Final: Alpha 3 pts (1W 1D), Beta 2 pts (1D 1D), Delta 2 pts (1D 1D), Gamma 1 pt (1L 1D)

        assert_tournament(tournament).team("Team Alpha").assert_().match_points(3)
        assert_tournament(tournament).team("Team Beta").assert_().match_points(2)
        assert_tournament(tournament).team("Team Delta").assert_().match_points(2)
        assert_tournament(tournament).team("Team Gamma").assert_().match_points(1)

    def test_partial_round_import(self):
        """Test importing only specific rounds from TRF16."""
        converter = TRF16Converter(self.trf16_content)
        converter.parse()

        builder = converter.create_tournament_builder()

        # Add only round 1
        converter.add_rounds_to_builder_v2(builder, rounds_to_add=[1])

        tournament = builder.build()

        # Should have only 1 round
        self.assertEqual(len(tournament.rounds), 1)

        # Check round 1 results
        round1 = tournament.rounds[0]
        self.assertEqual(
            len(round1.matches), 2
        )  # 2 team matches (not 4 individual games)

    def test_team_and_player_creation(self):
        """Test that teams and players are created correctly."""
        converter = TRF16Converter(self.trf16_content)
        converter.parse()

        # Check parsed data
        self.assertEqual(len(converter.teams), 4)
        self.assertEqual(len(converter.players), 8)

        # Check team composition
        team_alpha = converter.teams["Team Alpha"]
        self.assertEqual(len(team_alpha.player_ids), 2)

        # Check player details - player 1 is the first player
        player1 = converter.players[1]  # Player with start number 1
        self.assertEqual(player1.name, "Board1 TeamA")
        self.assertEqual(player1.rating, 2100)
        self.assertEqual(player1.board_number, 1)

    def test_pairing_extraction(self):
        """Test extracting pairings for validation."""
        converter = TRF16Converter(self.trf16_content)
        converter.parse()

        # Get round 1 pairings
        round1_pairings = converter.parser.parse_round_pairings(1)

        # Should have 4 pairings (one per board)
        self.assertEqual(len(round1_pairings), 4)

        # Check specific pairing
        pairing_found = False
        for pairing in round1_pairings:
            white = converter.players.get(pairing.white_player_id)
            black = converter.players.get(pairing.black_player_id)
            if white and black:
                if white.name == "Board1 TeamA" and black.name == "Board1 TeamC":
                    pairing_found = True
                    self.assertEqual(pairing.result, "1-0")

        self.assertTrue(pairing_found, "Expected pairing not found")

    def test_round_by_round_validation(self):
        """Test that we can validate pairings round by round."""
        converter = TRF16Converter(self.trf16_content)
        converter.parse()

        builder = converter.create_tournament_builder()

        # Add round 1
        converter.add_rounds_to_builder(builder, rounds_to_add=[1])
        tournament_r1 = builder.build()

        # Validate round 1 standings
        results_r1 = tournament_r1.calculate_results()

        # After round 1: Alpha beat Gamma 1.5-0.5, Beta beat Delta 2-0
        # So: Alpha 2 match pts, Beta 2 match pts, Delta 0, Gamma 0
        # Note: We need team IDs, not names for the results dict

        # Get team IDs from builder metadata
        team_name_to_id = builder.metadata.teams
        alpha_id = team_name_to_id["Team Alpha"]["id"]
        beta_id = team_name_to_id["Team Beta"]["id"]
        gamma_id = team_name_to_id["Team Gamma"]["id"]
        delta_id = team_name_to_id["Team Delta"]["id"]

        self.assertEqual(
            results_r1[alpha_id].match_points, 2
        )  # Alpha beats Gamma 1.5-0.5
        self.assertEqual(results_r1[beta_id].match_points, 1)  # Beta draws Delta 1-1
        self.assertEqual(
            results_r1[gamma_id].match_points, 0
        )  # Gamma loses to Alpha 0.5-1.5
        self.assertEqual(results_r1[delta_id].match_points, 1)  # Delta draws Beta 1-1


if __name__ == "__main__":
    unittest.main()
