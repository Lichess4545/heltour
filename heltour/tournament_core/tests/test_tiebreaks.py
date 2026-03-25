"""
Simple unit tests for tiebreak calculation functions.
No database, no Django models - just pure function tests.
"""

import unittest
from heltour.tournament_core.structure import (
    Game,
    GameResult,
    Match,
    Player,
    create_single_game_match,
    create_bye_match,
    create_scored_bye_match,
    create_team_match,
    create_tournament_from_matches,
)
from heltour.tournament_core.tiebreaks import (
    calculate_sonneborn_berger,
    calculate_buchholz,
    calculate_buchholz_cut1,
    calculate_head_to_head,
    calculate_games_won,
    calculate_all_tiebreaks,
)
from heltour.tournament_core.scoring import STANDARD_SCORING
from heltour.tournament_core.builder import TournamentBuilder
from heltour.tournament_core.assertions import assert_tournament


class SimpleTiebreakTests(unittest.TestCase):
    """Test tiebreak calculations with simple, clear scenarios."""

    def test_sonneborn_berger_basic(self):
        """Test SB calculation: sum of defeated opponents' scores + half of drawn opponents' scores."""
        # Define tournament with clear match results
        players = [1, 2, 3]
        matches_with_rounds = [
            # Round 1: Player 1 beats Player 2, Player 3 has bye
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),
            (1, create_bye_match(3)),
            # Round 2: Player 1 draws Player 3, Player 2 has bye
            (2, create_single_game_match(1, 3, GameResult.DRAW)),
            (2, create_bye_match(2)),
            # Round 3: Player 2 beats Player 3, Player 1 has bye
            (3, create_single_game_match(2, 3, GameResult.P1_WIN)),
            (3, create_bye_match(1)),
        ]

        # Create tournament and calculate results
        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        # Expected match points:
        # Player 1: Win(2) + Draw(1) + Bye(1) = 4 MP
        # Player 2: Loss(0) + Bye(1) + Win(2) = 3 MP
        # Player 3: Bye(1) + Draw(1) + Loss(0) = 2 MP

        # Calculate Sonneborn-Berger for each player
        # Player 1 SB: Beat P2 (3 MP) = 3, Drew P3 (2 MP) = 1, Total = 4
        self.assertEqual(calculate_sonneborn_berger(results[1], results), 4.0)

        # Player 2 SB: Lost to P1 (4 MP) = 0, Beat P3 (2 MP) = 2, Total = 2
        self.assertEqual(calculate_sonneborn_berger(results[2], results), 2.0)

        # Player 3 SB: Drew P1 (4 MP) = 2, Lost to P2 (3 MP) = 0, Total = 2
        self.assertEqual(calculate_sonneborn_berger(results[3], results), 2.0)

    def test_sonneborn_berger_with_bye(self):
        """Test SB calculation with byes (byes don't count)."""
        players = [1, 2]
        matches_with_rounds = [
            # Round 1: Player 1 has bye, Player 2 doesn't play
            (1, create_bye_match(1)),
            # Round 2: Player 1 beats Player 2
            (2, create_single_game_match(1, 2, GameResult.P1_WIN)),
        ]

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        # Player 1: Bye(1) + Win(2) = 3 MP
        # Player 2: Loss(0) = 0 MP

        # SB should only count the win against opponent (0 MP), not the bye
        self.assertEqual(calculate_sonneborn_berger(results[1], results), 0)

    def test_buchholz_basic(self):
        """Test Buchholz: sum of all opponents' match points."""
        players = [1, 2, 3]
        matches_with_rounds = [
            # Round 1: P1 beats P2, P3 has bye
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),
            (1, create_bye_match(3)),
            # Round 2: P1 draws P3, P2 has bye
            (2, create_single_game_match(1, 3, GameResult.DRAW)),
            (2, create_bye_match(2)),
        ]

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        # Player 1: Win(2) + Draw(1) = 3 MP
        # Player 2: Loss(0) + Bye(1) = 1 MP
        # Player 3: Bye(1) + Draw(1) = 2 MP

        # Player 1 Buchholz: Opponents P2 (1 MP) + P3 (2 MP) = 3
        self.assertEqual(calculate_buchholz(results[1], results), 3)

    def test_buchholz_missing_opponent(self):
        """Test Buchholz when opponent is not in scores (shouldn't crash)."""
        # Create a match with player 99 who isn't in the tournament
        # Need to include player 99 in the competitor list to avoid KeyError
        players = [1, 99]
        matches_with_rounds = [
            (1, Match(1, 99, [Game(Player(1, 1), Player(99, 99), GameResult.P1_WIN)])),
        ]

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        # Player 99 has 0 match points (lost), so Player 1's Buchholz is 0
        self.assertEqual(calculate_buchholz(results[1], results), 0)

    def test_head_to_head_basic(self):
        """Test head-to-head among tied competitors."""
        # Create a scenario where all players are tied
        players = [1, 2, 3]
        matches_with_rounds = [
            # Round 1: P1 beats P2
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),
            # Round 2: P2 beats P3
            (2, create_single_game_match(2, 3, GameResult.P1_WIN)),
            # Round 3: P3 beats P1
            (3, create_single_game_match(3, 1, GameResult.P1_WIN)),
        ]

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        # All three players have 2 MP (1 win, 1 loss each)
        tied_set = {1, 2, 3}

        # Each player beat one other in the tied set:
        # P1 beat P2, P2 beat P3, P3 beat P1
        self.assertEqual(calculate_head_to_head(results[1], tied_set, results), 2)
        self.assertEqual(calculate_head_to_head(results[2], tied_set, results), 2)
        self.assertEqual(calculate_head_to_head(results[3], tied_set, results), 2)

    def test_head_to_head_incomplete_pairings_individual(self):
        """H2H returns 0 when not all tied competitors have played each other."""
        # A(1), B(2), C(3) are tied at 2 MP, 1.0 GP
        # A played B (won) and C (lost) — but B and C never played each other
        # H2H should NOT apply for any of them
        players = [1, 2, 3, 4, 5]
        matches_with_rounds = [
            # A beats B
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),
            # C beats A
            (2, create_single_game_match(3, 1, GameResult.P1_WIN)),
            # B beats D (gives B a win so B ends at 2 MP)
            (1, create_single_game_match(2, 4, GameResult.P1_WIN)),
            # E beats C (gives C a loss so C ends at 2 MP)
            (2, create_single_game_match(5, 3, GameResult.P1_WIN)),
        ]

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        # A: beat B (2) + lost to C (0) = 2 MP, 1.0 GP
        # B: lost to A (0) + beat D (2) = 2 MP, 1.0 GP
        # C: beat A (2) + lost to E (0) = 2 MP, 1.0 GP
        self.assertEqual(results[1].match_points, 2)
        self.assertEqual(results[2].match_points, 2)
        self.assertEqual(results[3].match_points, 2)

        tied_set = {1, 2, 3}

        # B and C never played, so H2H is not applicable — all should be 0
        self.assertEqual(calculate_head_to_head(results[1], tied_set, results), 0)
        self.assertEqual(calculate_head_to_head(results[2], tied_set, results), 0)
        self.assertEqual(calculate_head_to_head(results[3], tied_set, results), 0)

    def test_head_to_head_no_games_against_tied(self):
        """Test H2H when player hasn't played anyone in the tied set."""
        players = [1, 2, 3, 4, 5, 6]
        matches_with_rounds = [
            # Player 1 only plays 5 and 6
            (1, create_single_game_match(1, 5, GameResult.P1_WIN)),
            (2, create_single_game_match(1, 6, GameResult.P1_WIN)),
            # Players 2, 3, 4 play among themselves
            (1, create_single_game_match(2, 3, GameResult.DRAW)),
            (2, create_single_game_match(3, 4, GameResult.DRAW)),
            (3, create_single_game_match(2, 4, GameResult.DRAW)),
        ]

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        tied_set = {2, 3, 4}  # Player 1 hasn't played any of these

        self.assertEqual(calculate_head_to_head(results[1], tied_set, results), 0)

    def test_games_won_team_tournament(self):
        """Test games won calculation for team tournaments."""
        teams = [1, 2, 3, 4]
        matches_with_rounds = [
            # Round 1: Team 1 sweeps Team 2 (4-0)
            (
                1,
                create_team_match(
                    1,
                    2,
                    [
                        (101, 201, GameResult.P1_WIN),
                        (102, 202, GameResult.P1_WIN),
                        (103, 203, GameResult.P1_WIN),
                        (104, 204, GameResult.P1_WIN),
                    ],
                ),
            ),
            # Round 2: Team 1 draws Team 3 (2-2)
            (
                2,
                create_team_match(
                    1,
                    3,
                    [
                        (101, 301, GameResult.P1_WIN),
                        (102, 302, GameResult.P2_WIN),
                        (103, 303, GameResult.P1_WIN),
                        (104, 304, GameResult.P2_WIN),
                    ],
                ),
            ),
            # Round 3: Team 1 wins vs Team 4 (5-3 in 8 boards)
            (
                3,
                create_team_match(
                    1,
                    4,
                    [
                        (101, 401, GameResult.P1_WIN),
                        (102, 402, GameResult.P1_WIN),
                        (103, 403, GameResult.P2_WIN),
                        (104, 404, GameResult.P1_WIN),
                        (105, 405, GameResult.P2_WIN),
                        (106, 406, GameResult.P1_WIN),
                        (107, 407, GameResult.P2_WIN),
                        (108, 408, GameResult.P1_WIN),
                    ],
                ),
            ),
        ]

        tournament = create_tournament_from_matches(
            teams, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        # Total games won by Team 1: 4 + 2 + 5 = 11
        self.assertEqual(calculate_games_won(results[1]), 11)

    def test_games_won_individual_tournament(self):
        """Test games won for individual tournament (should be 0 or match wins)."""
        players = [1, 2, 3, 4]
        matches_with_rounds = [
            # Individual matches - single game per match
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),
            (2, create_single_game_match(1, 3, GameResult.DRAW)),
            (3, create_single_game_match(1, 4, GameResult.DRAW)),
        ]

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        # For individuals with single-game matches, games_won counts actual game wins
        # Player 1 won 1 game, drew 2 games
        self.assertEqual(calculate_games_won(results[1]), 1)

    def test_all_tiebreaks_empty_tournament(self):
        """Test edge case: no games played."""
        players = [1]
        matches_with_rounds = []  # No matches played

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        tied_set = {1}

        self.assertEqual(calculate_sonneborn_berger(results[1], results), 0)
        self.assertEqual(calculate_buchholz(results[1], results), 0)
        self.assertEqual(calculate_head_to_head(results[1], tied_set, results), 0)
        self.assertEqual(calculate_games_won(results[1]), 0)

    def test_complete_round_robin_with_all_tiebreaks(self):
        """Test a complete round robin demonstrating all tiebreak calculations."""
        # 4-player round robin where final standings need multiple tiebreaks
        players = [1, 2, 3, 4]
        matches_with_rounds = [
            # Round 1
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),  # P1 beats P2
            (1, create_single_game_match(3, 4, GameResult.DRAW)),  # P3 draws P4
            # Round 2
            (2, create_single_game_match(1, 3, GameResult.P2_WIN)),  # P3 beats P1
            (2, create_single_game_match(2, 4, GameResult.P1_WIN)),  # P2 beats P4
            # Round 3
            (3, create_single_game_match(1, 4, GameResult.DRAW)),  # P1 draws P4
            (3, create_single_game_match(2, 3, GameResult.P2_WIN)),  # P3 beats P2
        ]

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        results = tournament.calculate_results()

        # Final standings:
        # P1: Win + Loss + Draw = 2+0+1 = 3 MP, 1.5 game points
        # P2: Loss + Win + Loss = 0+2+0 = 2 MP, 1 game point
        # P3: Draw + Win + Win = 1+2+2 = 5 MP, 2.5 game points
        # P4: Draw + Loss + Draw = 1+0+1 = 2 MP, 1 game point

        self.assertEqual(results[1].match_points, 3)
        self.assertEqual(results[2].match_points, 2)
        self.assertEqual(results[3].match_points, 5)
        self.assertEqual(results[4].match_points, 2)

        # P2 and P4 are tied at 2 MP, 1 game point
        tied_set = {2, 4}

        # Head-to-head: P2 beat P4 in round 2
        self.assertEqual(calculate_head_to_head(results[2], tied_set, results), 2)
        self.assertEqual(calculate_head_to_head(results[4], tied_set, results), 0)

        # Sonneborn-Berger calculations
        # P1: Beat P2 (2 MP) = 2, Drew P4 (2 MP) = 1, Total = 3
        self.assertEqual(calculate_sonneborn_berger(results[1], results), 3.0)

        # P3: Drew P4 (2 MP) = 1, Beat P1 (3 MP) = 3, Beat P2 (2 MP) = 2, Total = 6
        self.assertEqual(calculate_sonneborn_berger(results[3], results), 6.0)

    def test_team_tournament_forfeit_win_game_points(self):
        """Test that forfeit wins count properly in game points tiebreaker."""
        # Create a team tournament with one round
        builder = TournamentBuilder()
        builder.league("Test League", "TL", "team")
        builder.season("TL", "Spring 2024", rounds=1, boards=4)

        # Team A has 4 players
        builder.team(
            "Team A", ("Alice", 2000), ("Bob", 1900), ("Charlie", 1800), ("David", 1700)
        )

        # Team B has only 3 players
        builder.team("Team B", ("Eve", 1950), ("Frank", 1850), ("Grace", 1750))

        # Round 1: Team A wins 4-0 (3 regular wins + 1 forfeit win on board 4)
        # Board 1: Team A (white) wins
        # Board 2: Team B (white) loses to Team A (black)
        # Board 3: Team A (white) wins
        # Board 4: Team B (white) forfeits to Team A (black)
        builder.round(1)
        builder.match("Team A", "Team B", "1-0", "0-1", "1X-0F", "0F-1X")
        builder.complete()

        tournament = builder.build()
        results = tournament.calculate_results()

        # Get Team A's ID
        team_a_id = tournament.name_to_id["Team A"]
        team_a_result = results[team_a_id]

        # Team A should have:
        # - 2 match point (match result is a win)
        self.assertEqual(team_a_result.match_points, 2)
        self.assertEqual(team_a_result.game_points, 4.0)

        # Check games won tiebreaker
        games_won_tb = calculate_games_won(team_a_result)
        self.assertEqual(games_won_tb, 4)

        # Also verify using the assertion interface
        assert_tournament(tournament).team("Team A").assert_().match_points(
            2
        ).game_points(4.0).games_won(4).position(1)

    def test_team_tournament_forfeit_win_game_points_team_b(self):
        """Test that forfeit wins count properly in game points tiebreaker."""
        # Create a team tournament with one round
        builder = TournamentBuilder()
        builder.league("Test League", "TL", "team")
        builder.season("TL", "Spring 2024", rounds=1, boards=4)

        # Team A has only 3 players
        builder.team("Team A", ("Alice", 2000), ("Bob", 1900), ("Charlie", 1800))

        # Team B has 4 players
        builder.team(
            "Team B", ("Eve", 1950), ("Frank", 1850), ("Grace", 1750), ("Henry", 1650)
        )

        # Round 1: Team B wins 4-0 (3 regular wins + 1 forfeit win on board 4)
        # Board 1: Team A (white) loses to Team B (black)
        # Board 2: Team B (white) wins
        # Board 3: Team A (white) forfeits to Team B (black)
        # Board 4: Team B (white) wins by forfeit (Team A has no player)
        builder.round(1)
        builder.match("Team A", "Team B", "0-1", "1-0", "0F-1X", "1X-0F")
        builder.complete()

        tournament = builder.build()
        results = tournament.calculate_results()

        # Get Team B's ID
        team_b_id = tournament.name_to_id["Team B"]
        team_b_result = results[team_b_id]

        # Team B should have:
        # - 2 match points (match result is a win)
        self.assertEqual(team_b_result.match_points, 2)
        self.assertEqual(team_b_result.game_points, 4.0)

        # Check games won tiebreaker
        games_won_tb = calculate_games_won(team_b_result)
        self.assertEqual(games_won_tb, 4)

        # Also verify using the assertion interface
        assert_tournament(tournament).team("Team B").assert_().match_points(
            2
        ).game_points(4.0).games_won(4).position(1)


    def test_royal_knights_ice_warriors_forfeit_issue(self):
        """Test the specific forfeit issue from Royal Knights vs Ice Warriors match."""
        # Create a team tournament with one round
        builder = TournamentBuilder()
        builder.league("Test League", "TL", "team")
        builder.season("TL", "Spring 2024", rounds=1, boards=4)

        # Royal Knights has only 3 players (no board 4)
        builder.team(
            "Royal Knights",
            ("Shakhriyar", 1578),
            ("Levon", 1995),
            ("Anatoly", 1899)
        )

        # Ice Warriors has 4 players
        builder.team(
            "Ice Warriors",
            ("Ding", 2067),
            ("Bobby", 1735),
            ("Viswanathan", 1917),
            ("Anish", 1740)
        )

        # The match: Royal Knights 1½ - 2½ Ice Warriors
        # Board 1: Shakhriyar (white) loses to Ding (black) → "0-1"
        # Board 2: Bobby (white) forfeits to Levon (black) → "0F-1X"
        # Board 3: Anatoly (white) draws Viswanathan (black) → "1/2-1/2"
        # Board 4: Anish (white) wins by forfeit (Royal Knights has no player) → "1X-0F"
        builder.round(1)
        builder.match("Royal Knights", "Ice Warriors", "0-1", "0F-1X", "1/2-1/2", "1X-0F")
        builder.complete()

        tournament = builder.build()
        results = tournament.calculate_results()

        # Get team IDs
        rk_id = tournament.name_to_id["Royal Knights"]
        iw_id = tournament.name_to_id["Ice Warriors"]

        # Royal Knights should have:
        # - 0 match points (lost the match)
        # - 1.5 game points (0 + 1 + 0.5 + 0)
        rk_result = results[rk_id]
        self.assertEqual(rk_result.match_points, 0)
        self.assertEqual(rk_result.game_points, 1.5)

        # Ice Warriors should have:
        # - 2 match points (won the match)
        # - 2.5 game points (1 + 0 + 0.5 + 1)
        iw_result = results[iw_id]
        self.assertEqual(iw_result.match_points, 2)
        self.assertEqual(iw_result.game_points, 2.5)

        # Also verify using assertions
        assert_tournament(tournament).team("Royal Knights").assert_().match_points(0).game_points(1.5)
        assert_tournament(tournament).team("Ice Warriors").assert_().match_points(2).game_points(2.5)


class BuchholzCut1Tests(unittest.TestCase):
    """Test Buchholz Cut-1 calculation."""

    def _make_round_robin(self):
        """4-player round robin returning tournament and results."""
        players = [1, 2, 3, 4]
        matches_with_rounds = [
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),
            (1, create_single_game_match(3, 4, GameResult.DRAW)),
            (2, create_single_game_match(1, 3, GameResult.P2_WIN)),
            (2, create_single_game_match(2, 4, GameResult.P1_WIN)),
            (3, create_single_game_match(1, 4, GameResult.DRAW)),
            (3, create_single_game_match(2, 3, GameResult.P2_WIN)),
        ]
        tournament = create_tournament_from_matches(players, matches_with_rounds, STANDARD_SCORING)
        return tournament, tournament.calculate_results()

    def test_buchholz_cut1_basic(self):
        """Buchholz Cut-1 = Buchholz minus the lowest opponent score."""
        _, results = self._make_round_robin()

        # MP: P1=3, P2=2, P3=5, P4=2
        # P1 opponents: P2(2), P3(5), P4(2) → sorted [2,2,5] → drop lowest → [2,5] = 7
        full_buchholz = calculate_buchholz(results[1], results)
        cut1 = calculate_buchholz_cut1(results[1], results)
        self.assertEqual(full_buchholz, 9)
        self.assertEqual(cut1, 7)

    def test_buchholz_cut1_with_bye(self):
        """Bye opponent gets own score; still drops the lowest."""
        players = [1, 2, 3]
        matches_with_rounds = [
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),
            (1, create_bye_match(3)),
            (2, create_single_game_match(1, 3, GameResult.DRAW)),
            (2, create_bye_match(2)),
        ]
        tournament = create_tournament_from_matches(players, matches_with_rounds, STANDARD_SCORING)
        results = tournament.calculate_results()

        # P1: 3 MP. Opponents: P2(1), P3(2)
        cut1 = calculate_buchholz_cut1(results[1], results)
        # sorted [1, 2] → drop lowest → [2] = 2
        self.assertEqual(cut1, 2)


class UseGamePointsTests(unittest.TestCase):
    """Test the use_game_points flag on buchholz/h2h/cut1."""

    def _make_simple(self):
        """3-player simple scenario for game_points testing."""
        players = [1, 2, 3]
        matches_with_rounds = [
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),
            (1, create_bye_match(3)),
            (2, create_single_game_match(2, 3, GameResult.DRAW)),
            (2, create_bye_match(1)),
        ]
        tournament = create_tournament_from_matches(players, matches_with_rounds, STANDARD_SCORING)
        return tournament.calculate_results()

    def test_buchholz_with_game_points(self):
        results = self._make_simple()
        # bye_game_points_factor=0.5, so bye gives 0.5 GP
        # P1: 3 MP / 1.5 GP, P2: 1 MP / 0.5 GP, P3: 2 MP / 1.0 GP
        # P1 opponents (game_points): P2(0.5) + bye(own=1.5) = 2.0
        gp_buchholz = calculate_buchholz(results[1], results, use_game_points=True)
        mp_buchholz = calculate_buchholz(results[1], results, use_game_points=False)
        self.assertEqual(gp_buchholz, 2.0)
        self.assertEqual(mp_buchholz, 4)  # P2(1) + bye(own=3)

    def test_buchholz_cut1_with_game_points(self):
        results = self._make_simple()
        gp_cut1 = calculate_buchholz_cut1(results[1], results, use_game_points=True)
        # sorted [0.5, 1.5] → drop 0.5 → 1.5
        self.assertEqual(gp_cut1, 1.5)

    def test_head_to_head_with_game_points(self):
        results = self._make_simple()
        # P2 and P3 tied at 1 MP
        tied = {2, 3}
        gp_h2h_2 = calculate_head_to_head(results[2], tied, results, use_game_points=True)
        gp_h2h_3 = calculate_head_to_head(results[3], tied, results, use_game_points=True)
        # P2 drew P3 → 0.5 game points each
        self.assertEqual(gp_h2h_2, 0.5)
        self.assertEqual(gp_h2h_3, 0.5)


class CalculateAllTiebreaksTests(unittest.TestCase):
    """Test calculate_all_tiebreaks with new tiebreak names."""

    def test_lone_fide_tiebreaks(self):
        """Test the full FIDE tiebreak order for a lone tournament."""
        players = [1, 2, 3]
        matches_with_rounds = [
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),
            (1, create_bye_match(3)),
            (2, create_single_game_match(1, 3, GameResult.DRAW)),
            (2, create_bye_match(2)),
            (3, create_single_game_match(2, 3, GameResult.P1_WIN)),
            (3, create_bye_match(1)),
        ]
        tournament = create_tournament_from_matches(players, matches_with_rounds, STANDARD_SCORING)
        results = tournament.calculate_results()

        tiebreak_order = ["head_to_head", "buchholz_cut1", "buchholz", "games_won", "sonneborn_berger"]
        tb = calculate_all_tiebreaks(results, tiebreak_order, use_game_points=True)

        # Verify all keys present for each player
        for pid in players:
            for name in tiebreak_order:
                self.assertIn(name, tb[pid], f"Missing {name} for player {pid}")

        # P1: 4 MP / 2.0 GP, P2: 3 MP / 1.0 GP, P3: 2 MP / 1.5 GP
        # games_won: P1 won 1 game (vs P2), P2 won 1 game (vs P3), P3 won 0 games
        self.assertEqual(tb[1]["games_won"], 1)
        self.assertEqual(tb[2]["games_won"], 1)
        self.assertEqual(tb[3]["games_won"], 0)


class ScoredByeBuchholzTests(unittest.TestCase):
    """Test Buchholz with bye-type-aware scoring (zero/half/full-point byes)."""

    def _build_tournament_with_scored_bye(self, bye_gp, bye_mp):
        """Build a 4-player, 3-round lone tournament where P4 gets a scored bye in R1.

        R1: P1 beats P2, P3 beats P4-placeholder (but P4 gets a scored bye instead)
        R2: P1 beats P3, P2 beats P4
        R3: P2 draws P3, P1 beats P4

        bye_gp / bye_mp control P4's bye in R1.
        """
        players = [1, 2, 3, 4]
        matches_with_rounds = [
            # Round 1: P1 beats P2, P3 gets normal bye (half-point), P4 gets scored bye
            (1, create_single_game_match(1, 2, GameResult.P1_WIN)),
            (1, create_scored_bye_match(3, 0.5, 1)),
            (1, create_scored_bye_match(4, bye_gp, bye_mp)),
            # Round 2: P1 draws P3, P2 beats P4
            (2, create_single_game_match(1, 3, GameResult.DRAW)),
            (2, create_single_game_match(2, 4, GameResult.P1_WIN)),
            # Round 3: P2 draws P3, P1 beats P4
            (3, create_single_game_match(2, 3, GameResult.DRAW)),
            (3, create_single_game_match(1, 4, GameResult.P1_WIN)),
        ]

        tournament = create_tournament_from_matches(
            players, matches_with_rounds, STANDARD_SCORING
        )
        return tournament, tournament.calculate_results()

    def test_zero_point_bye_game_points(self):
        """Zero-point bye gives 0 GP and 0 MP to the player."""
        _, results = self._build_tournament_with_scored_bye(0.0, 0)

        # P4 scores: bye(0 GP, 0 MP) + loss(0 GP, 0 MP) + loss(0 GP, 0 MP) = 0 GP, 0 MP
        self.assertEqual(results[4].game_points, 0.0)
        self.assertEqual(results[4].match_points, 0)

    def test_half_point_bye_game_points(self):
        """Half-point bye gives 0.5 GP and 1 MP."""
        _, results = self._build_tournament_with_scored_bye(0.5, 1)

        # P4: bye(0.5 GP, 1 MP) + loss(0, 0) + loss(0, 0) = 0.5 GP, 1 MP
        self.assertEqual(results[4].game_points, 0.5)
        self.assertEqual(results[4].match_points, 1)

    def test_full_point_bye_game_points(self):
        """Full-point bye gives 1.0 GP and 2 MP."""
        _, results = self._build_tournament_with_scored_bye(1.0, 2)

        # P4: bye(1.0 GP, 2 MP) + loss(0, 0) + loss(0, 0) = 1.0 GP, 2 MP
        self.assertEqual(results[4].game_points, 1.0)
        self.assertEqual(results[4].match_points, 2)

    def test_zero_point_bye_buchholz_lower_than_half_point(self):
        """A zero-point bye should produce lower Buchholz than a half-point bye.

        Buchholz for a bye round uses the player's own score as virtual opponent.
        Zero-point bye → player has fewer total points → lower virtual opponent → lower Buchholz.
        """
        _, results_zero = self._build_tournament_with_scored_bye(0.0, 0)
        _, results_half = self._build_tournament_with_scored_bye(0.5, 1)

        buchholz_zero = calculate_buchholz(
            results_zero[4], results_zero, use_game_points=True
        )
        buchholz_half = calculate_buchholz(
            results_half[4], results_half, use_game_points=True
        )

        self.assertLess(buchholz_zero, buchholz_half)

    def test_zero_point_bye_buchholz_values(self):
        """Verify exact Buchholz values with a zero-point bye."""
        _, results = self._build_tournament_with_scored_bye(0.0, 0)

        # Standings with zero-point bye for P4:
        # P1: Win(R1 vs P2) + Draw(R2 vs P3) + Win(R3 vs P4) = 2+1+2 = 5 MP, 2.5 GP
        # P2: Loss(R1 vs P1) + Win(R2 vs P4) + Draw(R3 vs P3) = 0+2+1 = 3 MP, 1.5 GP
        # P3: Bye(R1, 0.5GP/1MP) + Draw(R2 vs P1) + Draw(R3 vs P2) = 1+1+1 = 3 MP, 1.5 GP
        # P4: Bye(R1, 0GP/0MP) + Loss(R2 vs P2) + Loss(R3 vs P1) = 0+0+0 = 0 MP, 0.0 GP
        self.assertEqual(results[1].match_points, 5)
        self.assertAlmostEqual(results[1].game_points, 2.5)
        self.assertEqual(results[2].match_points, 3)
        self.assertAlmostEqual(results[2].game_points, 1.5)
        self.assertEqual(results[3].match_points, 3)
        self.assertAlmostEqual(results[3].game_points, 1.5)
        self.assertEqual(results[4].match_points, 0)
        self.assertAlmostEqual(results[4].game_points, 0.0)

        # Buchholz (use_game_points=True) for P4:
        # Opponents: bye(own=0.0) + P2(1.5) + P1(2.5) = 4.0
        buchholz_p4 = calculate_buchholz(results[4], results, use_game_points=True)
        self.assertAlmostEqual(buchholz_p4, 4.0)

        # Buchholz Cut-1 for P4: sorted [0.0, 1.5, 2.5] → drop 0.0 → 4.0
        cut1_p4 = calculate_buchholz_cut1(results[4], results, use_game_points=True)
        self.assertAlmostEqual(cut1_p4, 4.0)

    def test_half_point_bye_buchholz_values(self):
        """Verify exact Buchholz values with a half-point bye."""
        _, results = self._build_tournament_with_scored_bye(0.5, 1)

        # P4: bye(0.5GP/1MP) + Loss(R2) + Loss(R3) = 1 MP, 0.5 GP
        self.assertEqual(results[4].match_points, 1)
        self.assertAlmostEqual(results[4].game_points, 0.5)

        # Buchholz (use_game_points=True) for P4:
        # Opponents: bye(own=0.5) + P2(1.5) + P1(2.5) = 4.5
        buchholz_p4 = calculate_buchholz(results[4], results, use_game_points=True)
        self.assertAlmostEqual(buchholz_p4, 4.5)

        # Buchholz Cut-1: sorted [0.5, 1.5, 2.5] → drop 0.5 → 4.0
        cut1_p4 = calculate_buchholz_cut1(results[4], results, use_game_points=True)
        self.assertAlmostEqual(cut1_p4, 4.0)

    def test_zero_point_bye_buchholz_match_points(self):
        """Buchholz with use_game_points=False sums opponents' match points."""
        _, results = self._build_tournament_with_scored_bye(0.0, 0)

        # P4: 0 MP. Opponents: bye(virtual=own MP=0), P2(3 MP), P1(5 MP)
        buchholz_p4 = calculate_buchholz(results[4], results, use_game_points=False)
        self.assertEqual(buchholz_p4, 8)

    def test_full_point_bye_buchholz_values(self):
        """Verify exact Buchholz and Cut-1 with a full-point bye."""
        _, results = self._build_tournament_with_scored_bye(1.0, 2)

        # P4: bye(1.0 GP, 2 MP) + loss + loss = 1.0 GP, 2 MP
        self.assertEqual(results[4].match_points, 2)
        self.assertAlmostEqual(results[4].game_points, 1.0)

        # Buchholz(GP): bye(own=1.0) + P2(1.5) + P1(2.5) = 5.0
        buchholz_p4 = calculate_buchholz(results[4], results, use_game_points=True)
        self.assertAlmostEqual(buchholz_p4, 5.0)

        # Buchholz Cut-1(GP): sorted [1.0, 1.5, 2.5] → drop 1.0 → 4.0
        cut1_p4 = calculate_buchholz_cut1(results[4], results, use_game_points=True)
        self.assertAlmostEqual(cut1_p4, 4.0)

    def test_scored_bye_sonneborn_berger_unaffected(self):
        """SB skips byes; P4 lost all non-bye games so SB = 0 regardless of bye type."""
        _, results_zero = self._build_tournament_with_scored_bye(0.0, 0)
        _, results_full = self._build_tournament_with_scored_bye(1.0, 2)

        self.assertEqual(calculate_sonneborn_berger(results_zero[4], results_zero), 0)
        self.assertEqual(calculate_sonneborn_berger(results_full[4], results_full), 0)


if __name__ == "__main__":
    unittest.main()
