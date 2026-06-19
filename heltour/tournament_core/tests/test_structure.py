"""
Tests for tournament utilities and tiebreak calculations using clean tournament representation.
"""

import unittest

from heltour.tournament_core.structure import (
    Game,
    GameResult,
    Player,
    Round,
    Tournament,
    create_single_game_match,
    create_bye_match,
    create_team_match,
    create_tournament_from_matches,
)
from heltour.tournament_core.tiebreaks import (
    calculate_sonneborn_berger,
    calculate_buchholz,
    calculate_head_to_head,
)
from heltour.tournament_core.scoring import STANDARD_SCORING, THREE_ONE_ZERO_SCORING


class TournamentUtilsTests(unittest.TestCase):
    """Test tournament representation and calculations."""

    def test_game_creation_without_round_number(self):
        """Test that Game no longer requires round_number."""
        # Game now uses Player objects
        player1 = Player(1, 1)  # player_id=1, competitor_id=1
        player2 = Player(2, 2)  # player_id=2, competitor_id=2
        game = Game(player1, player2, GameResult.P1_WIN)
        self.assertEqual(game.player1.player_id, 1)
        self.assertEqual(game.player2.player_id, 2)
        self.assertEqual(game.result, GameResult.P1_WIN)

        # Test points calculation
        p1_pts, p2_pts = game.points()
        self.assertEqual(p1_pts, 1.0)
        self.assertEqual(p2_pts, 0.0)

    def test_simple_round_robin(self):
        """Test a simple 3-player round robin tournament."""
        # Define the tournament structure
        players = [1, 2, 3]
        matches_with_rounds = [
            # Round 1: P1 beats P2, P3 gets bye
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),
            (1, create_bye_match(3)),
            # Round 2: P1 draws P3, P2 gets bye
            (2, create_single_game_match(1, 3, GameResult.DRAW)),
            (2, create_bye_match(2)),
            # Round 3: P2 beats P3, P1 gets bye
            (3, create_single_game_match(2, 3, GameResult.P1_WIN)),
            (3, create_bye_match(1)),
        ]

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        # Verify match points
        self.assertEqual(results[1].match_points, 4)  # Win + Draw + Bye = 2+1+1
        self.assertEqual(results[2].match_points, 3)  # Loss + Bye + Win = 0+1+2
        self.assertEqual(results[3].match_points, 2)  # Bye + Draw + Loss = 1+1+0

        # Verify game points
        self.assertEqual(results[1].game_points, 2.0)  # 1 + 0.5 + 0.5
        self.assertEqual(results[2].game_points, 1.5)  # 0 + 0.5 + 1
        self.assertEqual(results[3].game_points, 1.0)  # 0.5 + 0.5 + 0

        # Test Sonneborn-Berger
        sb1 = calculate_sonneborn_berger(results[1], results)
        # P1: Beat P2 (3 MP) = 3, Drew P3 (2 MP) = 1, Total = 4
        self.assertEqual(sb1, 4.0)

        # Test Buchholz
        bh1 = calculate_buchholz(results[1], results)
        # P1: Opponents P2 (3 MP) + P3 (2 MP) + Virtual opponent from bye (4 MP) = 9
        # Per FIDE 16.4: virtual opponent has same MP as participant (P1 has 4 MP)
        self.assertEqual(bh1, 9.0)

    def test_team_tournament(self):
        """Test a team tournament with multiple boards per match."""
        teams = [1, 2, 3, 4]
        matches_with_rounds = [
            # Round 1: Team 1 vs Team 2 (4 boards)
            (
                1,
                create_team_match(
                    1,
                    2,
                    [
                        (101, 201, GameResult.P1_WIN),  # Board 1: T1 wins
                        (102, 202, GameResult.DRAW),  # Board 2: Draw
                        (103, 203, GameResult.P1_WIN),  # Board 3: T1 wins
                        (104, 204, GameResult.P2_WIN),  # Board 4: T2 wins
                    ],
                ),
            ),
            # Team 3 vs Team 4
            (
                1,
                create_team_match(
                    3,
                    4,
                    [
                        (301, 401, GameResult.DRAW),  # Board 1: Draw
                        (302, 402, GameResult.DRAW),  # Board 2: Draw
                        (303, 403, GameResult.DRAW),  # Board 3: Draw
                        (304, 404, GameResult.DRAW),  # Board 4: Draw
                    ],
                ),
            ),
        ]

        tournament = create_tournament_from_matches(
            teams, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        # Team 1: 2.5-1.5 win = 2 match points
        self.assertEqual(results[1].match_points, 2)
        self.assertEqual(results[1].game_points, 2.5)
        self.assertEqual(results[1].match_results[0].games_won, 2)

        # Team 2: 1.5-2.5 loss = 0 match points
        self.assertEqual(results[2].match_points, 0)
        self.assertEqual(results[2].game_points, 1.5)
        self.assertEqual(results[2].match_results[0].games_won, 1)

        # Teams 3 & 4: 2-2 draw = 1 match point each
        self.assertEqual(results[3].match_points, 1)
        self.assertEqual(results[3].game_points, 2.0)
        self.assertEqual(results[4].match_points, 1)
        self.assertEqual(results[4].game_points, 2.0)

    def test_three_point_system(self):
        """Test tournament with 3-1-0 point system."""
        players = [1, 2]
        matches_with_rounds = [
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),
        ]

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, THREE_ONE_ZERO_SCORING
        )
        results = tournament.calculate_results()

        # Winner gets 3 points instead of 2
        self.assertEqual(results[1].match_points, 3)
        self.assertEqual(results[2].match_points, 0)

    def test_complex_tiebreak_scenario(self):
        """Test a scenario where multiple tiebreaks are needed."""
        # 4 players in a round-robin where they all finish with same points
        players = [1, 2, 3, 4]
        matches_with_rounds = [
            # Round 1
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),  # P1 beats P2
            (1, create_single_game_match(3, 4, GameResult.P1_WIN)),  # P3 beats P4
            # Round 2
            (2, create_single_game_match(1, 3, GameResult.P2_WIN)),  # P3 beats P1
            (2, create_single_game_match(2, 4, GameResult.P1_WIN)),  # P2 beats P4
            # Round 3
            (3, create_single_game_match(1, 4, GameResult.P2_WIN)),  # P4 beats P1
            (3, create_single_game_match(2, 3, GameResult.P2_WIN)),  # P3 beats P2
        ]

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        # Let's trace through each player's results:
        # P1: Beat P2, Lost to P3, Lost to P4 = 1 win, 2 losses = 2 MP
        # P2: Lost to P1, Beat P4, Lost to P3 = 1 win, 2 losses = 2 MP
        # P3: Beat P4, Beat P1, Beat P2 = 3 wins, 0 losses = 6 MP
        # P4: Lost to P3, Lost to P2, Beat P1 = 1 win, 2 losses = 2 MP

        self.assertEqual(results[1].match_points, 2)
        self.assertEqual(results[2].match_points, 2)
        self.assertEqual(results[3].match_points, 6)  # P3 won all their games!
        self.assertEqual(results[4].match_points, 2)

        # Three players (1, 2, 4) are tied at 2 match points
        # Calculate their tiebreaks
        tied_players = [1, 2, 4]

        # Sonneborn-Berger scores for tied players
        sb_scores = {
            p: calculate_sonneborn_berger(results[p], results) for p in tied_players
        }

        # P1 SB: Beat P2 (2 MP) = 2, Lost to P3 (6 MP) = 0, Lost to P4 (2 MP) = 0, Total = 2
        # P2 SB: Lost to P1 (2 MP) = 0, Beat P4 (2 MP) = 2, Lost to P3 (6 MP) = 0, Total = 2
        # P4 SB: Lost to P3 (6 MP) = 0, Lost to P2 (2 MP) = 0, Beat P1 (2 MP) = 2, Total = 2

        self.assertEqual(sb_scores[1], 2.0)
        self.assertEqual(sb_scores[2], 2.0)
        self.assertEqual(sb_scores[4], 2.0)

        # All tied players have the same SB score too!
        # This shows why multiple tiebreak systems are sometimes needed

    def test_head_to_head_in_tied_group(self):
        """Test head-to-head calculation among tied players."""
        # Create a scenario where 3 players are tied on points
        # but have different head-to-head records
        players = [1, 2, 3, 4, 5]
        matches_with_rounds = [
            # Players 2, 3, 4 will all end with 4 match points
            # P2 beats P3, P3 beats P4, P4 beats P2 (rock-paper-scissors)
            (1, create_single_game_match(2, 3, GameResult.P1_WIN)),
            (2, create_single_game_match(3, 4, GameResult.P1_WIN)),
            (3, create_single_game_match(4, 2, GameResult.P1_WIN)),
            # They all beat P5
            (4, create_single_game_match(2, 5, GameResult.P1_WIN)),
            (5, create_single_game_match(3, 5, GameResult.P1_WIN)),
            (6, create_single_game_match(4, 5, GameResult.P1_WIN)),
            # And all lose to P1
            (7, create_single_game_match(1, 2, GameResult.P1_WIN)),
            (8, create_single_game_match(1, 3, GameResult.P1_WIN)),
            (9, create_single_game_match(1, 4, GameResult.P1_WIN)),
        ]

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        # P2, P3, P4 should all have 4 match points (2 wins, 1 loss each)
        for p in [2, 3, 4]:
            self.assertEqual(results[p].match_points, 4)

        # They're tied, so calculate head-to-head among them
        tied_set = {2, 3, 4}
        h2h_2 = calculate_head_to_head(results[2], tied_set, results)
        h2h_3 = calculate_head_to_head(results[3], tied_set, results)
        h2h_4 = calculate_head_to_head(results[4], tied_set, results)

        # Each won one game against the others in the tied set
        self.assertEqual(h2h_2, 2)  # Beat P3
        self.assertEqual(h2h_3, 2)  # Beat P4
        self.assertEqual(h2h_4, 2)  # Beat P2

        # So head-to-head doesn't break the tie in this case!

    def test_tournament_rounds(self):
        """Test that tournament properly organizes matches into rounds."""
        players = [1, 2, 3, 4]

        # Create rounds directly
        round1 = Round(
            1,
            [
                create_single_game_match(1, 2, GameResult.P1_WIN),
                create_single_game_match(3, 4, GameResult.P1_WIN),
            ],
        )
        round2 = Round(
            2,
            [
                create_single_game_match(1, 3, GameResult.P1_WIN),
                create_single_game_match(2, 4, GameResult.P1_WIN),
            ],
        )
        round3 = Round(
            3,
            [
                create_single_game_match(1, 4, GameResult.P1_WIN),
                create_single_game_match(2, 3, GameResult.P1_WIN),
            ],
        )

        tournament = Tournament(players, [round1, round2, round3], STANDARD_SCORING)

        # Test num_rounds property
        self.assertEqual(tournament.num_rounds, 3)

        # Test direct round access
        rounds = tournament.rounds
        self.assertEqual(len(rounds), 3)

        # Check round 1
        self.assertEqual(rounds[0].number, 1)
        self.assertEqual(len(rounds[0].matches), 2)
        self.assertIn(
            (1, 2), [(m.competitor1_id, m.competitor2_id) for m in rounds[0].matches]
        )
        self.assertIn(
            (3, 4), [(m.competitor1_id, m.competitor2_id) for m in rounds[0].matches]
        )

        # Check round 2
        self.assertEqual(rounds[1].number, 2)
        self.assertEqual(len(rounds[1].matches), 2)

        # Check round 3
        self.assertEqual(rounds[2].number, 3)
        self.assertEqual(len(rounds[2].matches), 2)


if __name__ == "__main__":
    unittest.main()
