"""
Test TRF file generation for JavaFo pairing system.

These tests verify the TRF file format that JavaFo uses for pairings.
"""

from django.test import TestCase
from heltour.tournament.pairinggen import (
    JavafoPlayer,
    JavafoPairing,
    generate_trf_content,
)


class JavafoTRFTests(TestCase):
    """Test TRF file format generation for JavaFo."""

    def test_simple_trf_generation(self):
        """Test basic TRF file generation with 4 players."""
        # Create test players
        players = [
            JavafoPlayer("Player1", 0, []),
            JavafoPlayer("Player2", 0, []),
            JavafoPlayer("Player3", 0, []),
            JavafoPlayer("Player4", 0, []),
        ]

        # Generate TRF content
        trf_content = generate_trf_content(total_round_count=3, players=players)
        lines = trf_content.strip().split("\n")

        # Check header
        self.assertEqual(lines[0], "XXR 3")

        # Check player lines
        self.assertEqual(len(lines), 5)  # Header + 4 players

        # Check player line format
        for i in range(1, 5):
            self.assertTrue(lines[i].startswith("001"))
            self.assertIn("  0.0", lines[i])  # Score

    def test_trf_with_pairings(self):
        """Test TRF generation with actual pairings."""
        # Create players with pairings from round 1
        player1 = JavafoPlayer("Player1", 1.0, [JavafoPairing("Player2", "white", 1.0)])
        player2 = JavafoPlayer("Player2", 0.0, [JavafoPairing("Player1", "black", 0.0)])
        player3 = JavafoPlayer("Player3", 0.5, [JavafoPairing("Player4", "white", 0.5)])
        player4 = JavafoPlayer("Player4", 0.5, [JavafoPairing("Player3", "black", 0.5)])

        players = [player1, player2, player3, player4]

        # Generate TRF content
        trf_content = generate_trf_content(total_round_count=3, players=players)
        lines = trf_content.strip().split("\n")

        # Check header
        self.assertEqual(lines[0], "XXR 3")

        # Check player 1's line
        self.assertIn("001    1", lines[1])  # Player 1
        self.assertIn("  1.0", lines[1])  # Score 1.0
        self.assertIn("     2 w 1", lines[1])  # Played #2 as white, won

        # Check player 2's line
        self.assertIn("001    2", lines[2])  # Player 2
        self.assertIn("  0.0", lines[2])  # Score 0.0
        self.assertIn("     1 b 0", lines[2])  # Played #1 as black, lost

        # Check player 3's line
        self.assertIn("001    3", lines[3])  # Player 3
        self.assertIn("  0.5", lines[3])  # Score 0.5
        self.assertIn("     4 w =", lines[3])  # Played #4 as white, drew

        # Check player 4's line
        self.assertIn("001    4", lines[4])  # Player 4
        self.assertIn("  0.5", lines[4])  # Score 0.5
        self.assertIn("     3 b =", lines[4])  # Played #3 as black, drew

    def test_trf_with_bye(self):
        """Test TRF generation with a bye."""
        # Player 1 had a bye in round 1
        player1 = JavafoPlayer(
            "Player1", 1.0, [JavafoPairing(None, None, 1.0, forfeit=True)]
        )

        players = [player1]

        # Generate TRF content
        trf_content = generate_trf_content(total_round_count=1, players=players)
        lines = trf_content.strip().split("\n")

        # Check header
        self.assertEqual(lines[0], "XXR 1")

        # Check player line with bye
        self.assertIn("001    1", lines[1])  # Player 1
        self.assertIn("  1.0", lines[1])  # Score 1.0
        self.assertIn("  0000 - +", lines[1])  # Bye notation

    def test_trf_odd_players(self):
        """Test TRF with odd number of players (one gets bye)."""
        # 3 players, player 3 gets a bye
        players = [
            JavafoPlayer("Player1", 1.0, [JavafoPairing("Player2", "white", 1.0)]),
            JavafoPlayer("Player2", 0.0, [JavafoPairing("Player1", "black", 0.0)]),
            JavafoPlayer(
                "Player3", 1.0, [JavafoPairing(None, None, 1.0, forfeit=True)]
            ),
        ]

        # Generate TRF content
        trf_content = generate_trf_content(total_round_count=1, players=players)
        lines = trf_content.strip().split("\n")

        # Check header
        self.assertEqual(lines[0], "XXR 1")

        # Verify we have 3 player lines
        self.assertEqual(len(lines), 4)  # Header + 3 players

        # Check player 3's bye
        self.assertIn("001    3", lines[3])  # Player 3
        self.assertIn("  1.0", lines[3])  # Player 3 has bye point
        self.assertIn("  0000 - +", lines[3])  # Player 3's bye notation

    def test_trf_with_acceleration_scores(self):
        """Test TRF generation with acceleration scores."""
        # Create players with acceleration scores
        player1 = JavafoPlayer("Player1", 0, [])
        player1.acceleration_scores = [1.0, 0.5]

        player2 = JavafoPlayer("Player2", 0, [])
        player2.acceleration_scores = [0.5, 1.0]

        players = [player1, player2]

        # Generate TRF content
        trf_content = generate_trf_content(total_round_count=2, players=players)
        lines = trf_content.strip().split("\n")

        # Check header
        self.assertEqual(lines[0], "XXR 2")

        # Check player lines
        self.assertEqual(lines[1].startswith("001    1"), True)
        self.assertEqual(lines[2].startswith("001    2"), True)

        # Check acceleration score lines
        self.assertEqual(lines[3], "XXA    1  1.0  0.5")
        self.assertEqual(lines[4], "XXA    2  0.5  1.0")

    def test_trf_player_not_included(self):
        """Test TRF generation with a player marked as not included."""
        # Create a player not included in pairing
        player1 = JavafoPlayer("Player1", 0, [])
        player1.include = False

        players = [player1]

        # Generate TRF content
        trf_content = generate_trf_content(total_round_count=1, players=players)
        lines = trf_content.strip().split("\n")

        # Check that player has the "not included" marker
        self.assertIn("  0000 - -", lines[1])  # Not included notation
