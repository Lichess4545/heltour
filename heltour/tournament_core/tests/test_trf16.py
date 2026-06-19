"""
Tests for TRF16 parser.
"""

import unittest
from datetime import datetime
from heltour.tournament_core.trf16 import (
    TRF16Parser,
)


class TestTRF16Parser(unittest.TestCase):
    """Test TRF16 parser functionality."""

    def setUp(self):
        """Set up test data."""
        # Sample TRF16 content (simplified version)
        self.sample_trf16 = """012 Test Team Tournament
022 Test City
032 GRE
042 2024/11/23
052 2024/11/24
062 12 (10)
072 10
082 3
092 Team Swiss System
102 Test Arbiter
112 Assistant One, Assistant Two
122 15 minutes plus 10 sec per move
142 3
132                                                                                        24/11/23  24/11/23  24/11/24

001    1 m    Player One                        1500 GRE    12345678 2000/01/01  2.5   4  0000 - -     7 w 1     9 b 0
001    2 m    Player Two                        1450 GRE    12345679 2001/01/01  1.5   6  0000 - -     8 b 0    10 w 1
001    3 m    Player Three                      1400 GRE    12345680 2002/01/01  2.0   5  0000 - -     9 w 1    11 b 0
001    4 m    Player Four                       1350 GRE    12345681 2003/01/01  1.0   8  0000 - -    10 b 0    12 w 0
001    5 m    Player Five                       1600 GRE    12345682 1999/01/01  2.5   3     1 w 1     9 b 1  0000 - -
001    6 m    Player Six                        1550 GRE    12345683 1998/01/01  1.5   7     2 b 1    10 w 0  0000 - -
001    7 m    Player Seven                      1700 GRE    12345684 1997/01/01  2.0   2     1 b 0    11 w 1  0000 - -
001    8 m    Player Eight                      1650 GRE    12345685 1996/01/01  3.0   1     2 w 1    12 b 1  0000 - -
001    9 m    Player Nine                       1300 GRE    12345686 2004/01/01  0.5  11     3 b 0     1 w 1     5 w 0
001   10 m    Player Ten                        1250 GRE    12345687 2005/01/01  1.5   9     4 w 1     2 b 0     6 b 1
001   11 m    Player Eleven                     1200 GRE    12345688 2006/01/01  1.0  10  0000 - -     3 w 1     7 b 0
001   12 m    Player Twelve                     1150 GRE    12345689 2007/01/01  0.0  12  0000 - -     4 b 1     8 w 0

013 Team Alpha                           1    2    3    4
013 Team Beta                            5    6    7    8
013 Team Gamma                           9   10   11   12"""

        self.parser = TRF16Parser(self.sample_trf16)

    def test_parse_header(self):
        """Test header parsing."""
        header = self.parser.parse_header()

        self.assertEqual(header.tournament_name, "Test Team Tournament")
        self.assertEqual(header.city, "Test City")
        self.assertEqual(header.federation, "GRE")
        self.assertEqual(header.start_date, datetime(2024, 11, 23))
        self.assertEqual(header.end_date, datetime(2024, 11, 24))
        self.assertEqual(header.num_players, 12)
        self.assertEqual(header.num_rated_players, 10)
        self.assertEqual(header.num_teams, 3)
        self.assertEqual(header.tournament_type, "Team Swiss System")
        self.assertEqual(header.chief_arbiter, "Test Arbiter")
        self.assertEqual(header.deputy_arbiters, ["Assistant One", "Assistant Two"])
        self.assertEqual(header.time_control, "15 minutes plus 10 sec per move")
        self.assertEqual(header.num_rounds, 3)

    def test_parse_players(self):
        """Test player parsing."""
        players = self.parser.parse_players()

        # Check we have all 12 players
        self.assertEqual(len(players), 12)

        # Check specific player details
        # Player on line 17 (1-based counting includes header lines)
        player1_line = 17  # Approximate line number
        player1 = None
        for line_num, player in players.items():
            if player.name == "Player One":
                player1 = player
                break

        self.assertIsNotNone(player1)
        self.assertEqual(player1.name, "Player One")
        self.assertEqual(player1.rating, 1500)
        self.assertEqual(player1.federation, "GRE")
        self.assertEqual(player1.fide_id, "12345678")
        self.assertEqual(player1.birth_year, 2000)
        self.assertEqual(player1.points, 2.5)
        self.assertEqual(player1.rank, 4)

        # Check results parsing
        self.assertEqual(len(player1.results), 3)  # Should have 3 round results
        self.assertEqual(player1.results[0], (None, "-", "-"))  # Round 1: bye
        self.assertEqual(player1.results[1][1], "w")  # Round 2: white
        self.assertEqual(player1.results[1][2], "1")  # Round 2: win
        self.assertEqual(player1.results[2][1], "b")  # Round 3: black
        self.assertEqual(player1.results[2][2], "0")  # Round 3: loss

    def test_parse_teams(self):
        """Test team parsing."""
        teams = self.parser.parse_teams()

        self.assertEqual(len(teams), 3)
        self.assertIn("Team Alpha", teams)
        self.assertIn("Team Beta", teams)
        self.assertIn("Team Gamma", teams)

        # Check Team Alpha
        alpha = teams["Team Alpha"]
        self.assertEqual(alpha.name, "Team Alpha")
        self.assertEqual(alpha.player_ids, [1, 2, 3, 4])

        # Check Team Beta
        beta = teams["Team Beta"]
        self.assertEqual(beta.name, "Team Beta")
        self.assertEqual(beta.player_ids, [5, 6, 7, 8])

    def test_update_board_numbers(self):
        """Test board number assignment."""
        self.parser.parse_players()
        self.parser.parse_teams()
        self.parser.update_board_numbers()

        # Check that players have correct board numbers
        for player_id, player in self.parser.players.items():
            if player.team_number == 1:  # Team Alpha
                self.assertIn(player.board_number, [1, 2, 3, 4])

    def test_parse_round_pairings(self):
        """Test round pairing extraction."""
        self.parser.parse_players()

        # Get round 2 pairings
        round2_pairings = self.parser.parse_round_pairings(2)

        # Should have pairings from white's perspective
        self.assertGreater(len(round2_pairings), 0)

        # Check a specific pairing
        found_pairing = False
        for pairing in round2_pairings:
            if pairing.white_player_id and pairing.black_player_id:
                white_player = self.parser.players.get(pairing.white_player_id)
                black_player = self.parser.players.get(pairing.black_player_id)
                if white_player and black_player:
                    if (
                        white_player.name == "Player One"
                        and black_player.name == "Player Seven"
                    ):
                        found_pairing = True
                        self.assertEqual(pairing.result, "1-0")

        self.assertTrue(found_pairing, "Expected pairing not found")

    def test_full_trf16_parsing(self):
        """Test parsing with the full TRF16 content from the user."""
        # This would use the actual TRF16 content provided
        # For now, we'll use our simplified test data
        header, players, teams = self.parser.parse_all()

        self.assertIsNotNone(header)
        self.assertGreater(len(players), 0)
        self.assertGreater(len(teams), 0)


class TestTRF16Integration(unittest.TestCase):
    """Test integration with tournament builder."""

    def test_trf16_to_tournament_structure(self):
        """Test converting TRF16 data to tournament structure."""
        # This test would demonstrate how to use parsed TRF16 data
        # with the TournamentBuilder
        pass  # Implementation to follow


if __name__ == "__main__":
    unittest.main()
