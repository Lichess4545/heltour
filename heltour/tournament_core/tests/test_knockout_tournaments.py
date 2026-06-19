"""
Comprehensive tests for knockout tournament functionality.

This test suite covers:
- Bracket generation with different seeding patterns
- Multi-game match support and aggregated scoring
- Manual tiebreak resolution per pairing
- Tournament advancement and elimination logic
- Full tournament simulation from seeding to finals
- Bye handling for non-power-of-2 team counts
- Integration with TournamentBuilder and assertions
"""

import unittest
from heltour.tournament_core.structure import (
    Tournament,
    Match,
    Game,
    Player,
    GameResult,
    TournamentFormat,
)
from heltour.tournament_core.knockout import (
    validate_bracket_size,
    calculate_rounds_needed,
    get_knockout_stage_name,
    generate_knockout_seedings_adjacent,
    generate_knockout_seedings_traditional,
    calculate_knockout_advancement,
    generate_next_round_pairings,
    create_knockout_tournament,
    update_knockout_tournament_with_winners,
    is_knockout_tournament_complete,
    get_knockout_winner,
)
from heltour.tournament_core.builder import TournamentBuilder
from heltour.tournament_core.assertions import assert_tournament


class TestKnockoutBracketGeneration(unittest.TestCase):
    """Test knockout bracket generation and validation."""

    def test_validate_bracket_size(self):
        """Test bracket size validation (must be power of 2)."""
        # Valid sizes
        self.assertTrue(validate_bracket_size(2))
        self.assertTrue(validate_bracket_size(4))
        self.assertTrue(validate_bracket_size(8))
        self.assertTrue(validate_bracket_size(16))
        self.assertTrue(validate_bracket_size(32))

        # Invalid sizes
        self.assertFalse(validate_bracket_size(0))
        self.assertFalse(validate_bracket_size(1))
        self.assertFalse(validate_bracket_size(3))
        self.assertFalse(validate_bracket_size(5))
        self.assertFalse(validate_bracket_size(6))
        self.assertFalse(validate_bracket_size(7))
        self.assertFalse(validate_bracket_size(9))

    def test_calculate_rounds_needed(self):
        """Test calculation of rounds needed for bracket sizes."""
        self.assertEqual(calculate_rounds_needed(2), 1)  # Finals only
        self.assertEqual(calculate_rounds_needed(4), 2)  # Semis + Finals
        self.assertEqual(calculate_rounds_needed(8), 3)  # Quarters + Semis + Finals
        self.assertEqual(calculate_rounds_needed(16), 4)
        self.assertEqual(calculate_rounds_needed(32), 5)

        # Invalid size should raise error
        with self.assertRaises(ValueError):
            calculate_rounds_needed(5)

    def test_get_knockout_stage_name(self):
        """Test stage name generation."""
        self.assertEqual(get_knockout_stage_name(2), "finals")
        self.assertEqual(get_knockout_stage_name(4), "semifinals")
        self.assertEqual(get_knockout_stage_name(8), "quarterfinals")
        self.assertEqual(get_knockout_stage_name(16), "round-of-16")
        self.assertEqual(get_knockout_stage_name(32), "round-of-32")
        self.assertEqual(get_knockout_stage_name(64), "round-of-64")
        self.assertEqual(get_knockout_stage_name(128), "round-of-128")

    def test_generate_knockout_seedings_adjacent(self):
        """Test adjacent seeding (1v2, 3v4, 5v6, etc.)."""
        teams = [1, 2, 3, 4, 5, 6, 7, 8]
        pairings = generate_knockout_seedings_adjacent(teams)

        expected = [(1, 2), (3, 4), (5, 6), (7, 8)]
        self.assertEqual(pairings, expected)

        # Test with smaller bracket
        teams_4 = [1, 2, 3, 4]
        pairings_4 = generate_knockout_seedings_adjacent(teams_4)
        expected_4 = [(1, 2), (3, 4)]
        self.assertEqual(pairings_4, expected_4)

    def test_generate_knockout_seedings_traditional(self):
        """Test traditional seeding with proper bracket positioning."""
        teams = [1, 2, 3, 4, 5, 6, 7, 8]
        pairings = generate_knockout_seedings_traditional(teams)

        # Expected bracket order for 8 teams: 1v8, 4v5, 3v6, 2v7
        # This ensures proper tournament flow where winners meet correctly
        expected = [(1, 8), (4, 5), (3, 6), (2, 7)]
        self.assertEqual(pairings, expected)

        # Test with 4-team bracket
        teams_4 = [1, 2, 3, 4]
        pairings_4 = generate_knockout_seedings_traditional(teams_4)
        expected_4 = [(1, 4), (2, 3)]
        self.assertEqual(pairings_4, expected_4)

    def test_invalid_bracket_sizes(self):
        """Test that invalid bracket sizes raise errors."""
        invalid_teams = [1, 2, 3]  # Not power of 2

        with self.assertRaises(ValueError):
            generate_knockout_seedings_adjacent(invalid_teams)

        with self.assertRaises(ValueError):
            generate_knockout_seedings_traditional(invalid_teams)


class TestMatchWinnerDetermination(unittest.TestCase):
    """Test match winner determination with game points and manual tiebreaks."""

    def test_single_game_winner_determination(self):
        """Test winner determination for single-game matches."""
        # Player 1 wins
        player1 = Player(1, 1)
        player2 = Player(2, 2)
        game = Game(player1, player2, GameResult.P1_WIN)
        match = Match(1, 2, [game])

        self.assertEqual(match.winner_id(), 1)

        # Player 2 wins
        game2 = Game(player1, player2, GameResult.P2_WIN)
        match2 = Match(1, 2, [game2])

        self.assertEqual(match2.winner_id(), 2)

        # Draw - no winner
        game3 = Game(player1, player2, GameResult.DRAW)
        match3 = Match(1, 2, [game3])

        self.assertIsNone(match3.winner_id())

    def test_multi_game_winner_determination(self):
        """Test winner determination for multi-game matches."""
        player1 = Player(1, 1)
        player2 = Player(2, 2)

        # Player 1 wins 2 games, player 2 wins 1 game (2.0 vs 1.0 points)
        games = [
            Game(player1, player2, GameResult.P1_WIN),  # 1.0 - 0.0
            Game(player1, player2, GameResult.P2_WIN),  # 0.0 - 1.0
            Game(player1, player2, GameResult.P1_WIN),  # 1.0 - 0.0
        ]
        match = Match(1, 2, games, games_per_match=3)

        self.assertEqual(match.winner_id(), 1)  # Player 1 has 2.0 points vs 1.0

    def test_manual_tiebreak_resolution(self):
        """Test manual tiebreak resolution for tied matches."""
        player1 = Player(1, 1)
        player2 = Player(2, 2)

        # Create tied match (1.5 - 1.5)
        games = [
            Game(player1, player2, GameResult.P1_WIN),  # 1.0 - 0.0
            Game(player1, player2, GameResult.P2_WIN),  # 0.0 - 1.0
            Game(player1, player2, GameResult.DRAW),  # 0.5 - 0.5
        ]
        tied_match = Match(1, 2, games, games_per_match=3)

        # Without manual tiebreak, no winner
        self.assertIsNone(tied_match.winner_id())

        # With positive manual tiebreak, player 1 wins
        match_with_tiebreak = Match(
            1, 2, games, games_per_match=3, manual_tiebreak_value=1.0
        )
        self.assertEqual(match_with_tiebreak.winner_id(), 1)

        # With negative manual tiebreak, player 2 wins
        match_with_tiebreak2 = Match(
            1, 2, games, games_per_match=3, manual_tiebreak_value=-1.0
        )
        self.assertEqual(match_with_tiebreak2.winner_id(), 2)

        # With zero tiebreak, still no winner
        match_with_zero = Match(
            1, 2, games, games_per_match=3, manual_tiebreak_value=0.0
        )
        self.assertIsNone(match_with_zero.winner_id())

    def test_bye_match_winner(self):
        """Test that bye matches always return the competitor as winner."""
        from heltour.tournament_core.structure import create_bye_match

        bye_match = create_bye_match(1, 1)
        self.assertEqual(bye_match.winner_id(), 1)

        # Multi-game bye
        bye_match_multi = create_bye_match(2, 3)
        self.assertEqual(bye_match_multi.winner_id(), 2)


class TestKnockoutAdvancement(unittest.TestCase):
    """Test knockout tournament advancement logic."""

    def test_calculate_knockout_advancement_clear_winners(self):
        """Test advancement calculation when all matches have clear winners."""
        player1 = Player(1, 1)
        player2 = Player(2, 2)
        player3 = Player(3, 3)
        player4 = Player(4, 4)

        # Two matches with clear winners
        match1 = Match(1, 2, [Game(player1, player2, GameResult.P1_WIN)])  # 1 wins
        match2 = Match(3, 4, [Game(player3, player4, GameResult.P2_WIN)])  # 4 wins

        matches = [match1, match2]
        advancing = calculate_knockout_advancement(matches)

        self.assertEqual(advancing, [1, 4])

    def test_calculate_knockout_advancement_with_ties(self):
        """Test that tied matches without tiebreaks raise errors."""
        player1 = Player(1, 1)
        player2 = Player(2, 2)

        # Tied match without manual tiebreak
        tied_match = Match(1, 2, [Game(player1, player2, GameResult.DRAW)])

        with self.assertRaises(ValueError) as context:
            calculate_knockout_advancement([tied_match])

        self.assertIn("tied and requires manual tiebreak", str(context.exception))

    def test_calculate_knockout_advancement_with_tiebreaks(self):
        """Test advancement calculation with manual tiebreaks."""
        player1 = Player(1, 1)
        player2 = Player(2, 2)

        # Tied match with manual tiebreak favoring player 1
        tied_match = Match(
            1, 2, [Game(player1, player2, GameResult.DRAW)], manual_tiebreak_value=1.0
        )

        advancing = calculate_knockout_advancement([tied_match])
        self.assertEqual(advancing, [1])

    def test_generate_next_round_pairings(self):
        """Test pairing generation for subsequent rounds."""
        advancing = [1, 3, 5, 7]
        pairings = generate_next_round_pairings(advancing)

        expected = [(1, 3), (5, 7)]
        self.assertEqual(pairings, expected)

        # Odd number should raise error
        with self.assertRaises(ValueError):
            generate_next_round_pairings([1, 2, 3])


class TestCompleteKnockoutTournament(unittest.TestCase):
    """Test complete knockout tournament creation and management."""

    def test_create_knockout_tournament_structure(self):
        """Test creating a complete knockout tournament structure."""
        team_ids = [1, 2, 3, 4]
        tournament = create_knockout_tournament(
            team_ids, "traditional", games_per_match=1
        )

        self.assertEqual(tournament.format, TournamentFormat.KNOCKOUT)
        self.assertEqual(len(tournament.competitors), 4)
        self.assertEqual(len(tournament.rounds), 2)  # Semis + Finals

        # Check first round structure
        first_round = tournament.rounds[0]
        self.assertEqual(first_round.number, 1)
        self.assertEqual(first_round.knockout_stage, "semifinals")
        self.assertEqual(len(first_round.matches), 2)

        # Check seedings (1v4, 2v3 for traditional)
        match1 = first_round.matches[0]
        match2 = first_round.matches[1]

        self.assertIn((match1.competitor1_id, match1.competitor2_id), [(1, 4), (2, 3)])
        self.assertIn((match2.competitor1_id, match2.competitor2_id), [(1, 4), (2, 3)])

    def test_create_knockout_tournament_adjacent_seeding(self):
        """Test knockout tournament with adjacent seeding."""
        team_ids = [1, 2, 3, 4]
        tournament = create_knockout_tournament(team_ids, "adjacent", games_per_match=2)

        first_round = tournament.rounds[0]
        matches = first_round.matches

        # Should be 1v2, 3v4
        expected_pairings = {(1, 2), (3, 4)}
        actual_pairings = {(m.competitor1_id, m.competitor2_id) for m in matches}

        self.assertEqual(actual_pairings, expected_pairings)

        # Check games per match
        for match in matches:
            self.assertEqual(match.games_per_match, 2)

    def test_update_knockout_tournament_with_winners(self):
        """Test updating tournament structure with round winners."""
        team_ids = [1, 2, 3, 4]
        tournament = create_knockout_tournament(team_ids, "traditional")

        # Simulate first round winners: 1 and 3
        winners = [1, 3]
        updated_tournament = update_knockout_tournament_with_winners(
            tournament, 1, winners
        )

        # Check that finals round is updated
        finals_round = updated_tournament.rounds[1]
        finals_match = finals_round.matches[0]

        self.assertEqual(finals_match.competitor1_id, 1)
        self.assertEqual(finals_match.competitor2_id, 3)

    def test_knockout_tournament_completion_detection(self):
        """Test detection of complete tournaments."""
        team_ids = [1, 2]
        tournament = create_knockout_tournament(team_ids, "traditional")

        # Tournament not complete without results
        self.assertFalse(is_knockout_tournament_complete(tournament))

        # Add result to final match
        final_match = tournament.rounds[0].matches[0]
        player1 = Player(1, 1)
        player2 = Player(2, 2)
        game = Game(player1, player2, GameResult.P1_WIN)

        from heltour.tournament_core.structure import Match, Round

        completed_match = Match(
            competitor1_id=final_match.competitor1_id,
            competitor2_id=final_match.competitor2_id,
            games=[game],
            games_per_match=final_match.games_per_match,
        )
        completed_round = Round(
            number=tournament.rounds[0].number,
            matches=[completed_match],
            knockout_stage=tournament.rounds[0].knockout_stage,
        )
        completed_tournament = Tournament(
            competitors=tournament.competitors,
            rounds=[completed_round],
            scoring=tournament.scoring,
            format=tournament.format,
        )

        self.assertTrue(is_knockout_tournament_complete(completed_tournament))
        self.assertEqual(get_knockout_winner(completed_tournament), 1)


class TestTournamentBuilderKnockoutIntegration(unittest.TestCase):
    """Test knockout functionality with TournamentBuilder."""

    def test_builder_knockout_format_methods(self):
        """Test knockout-specific builder methods."""
        builder = TournamentBuilder()

        # Test method chaining
        result = (
            builder.knockout_format()
            .games_per_match(2)
            .league("Test League", "TL", "team")
            .season("TL", "Test Season")
        )

        self.assertIs(result, builder)  # Method chaining works

        tournament = builder.build()
        self.assertEqual(tournament.format, TournamentFormat.KNOCKOUT)

    def test_builder_bracket_seeding_traditional(self):
        """Test bracket seeding with TournamentBuilder."""
        builder = (
            TournamentBuilder()
            .knockout_format()
            .league("Test League", "TL", "team")
            .season("TL", "Test Season")
            .team("Dragons", ("Alice", 2000), ("Bob", 1900))
            .team("Knights", ("Charlie", 1950), ("Dave", 1850))
            .team("Wizards", ("Eve", 1800), ("Frank", 1750))
            .team("Warriors", ("Grace", 1700), ("Henry", 1650))
            .bracket_seeding(
                ["Dragons", "Knights", "Wizards", "Warriors"], "traditional"
            )
        )

        tournament = builder.build()

        # Should have first round with traditional seedings
        self.assertEqual(len(tournament.rounds), 1)
        first_round = tournament.rounds[0]
        self.assertEqual(first_round.knockout_stage, "semifinals")
        self.assertEqual(len(first_round.matches), 2)

    def test_builder_bracket_seeding_adjacent(self):
        """Test adjacent bracket seeding with TournamentBuilder."""
        builder = (
            TournamentBuilder()
            .knockout_format()
            .league("Test League", "TL", "team")
            .season("TL", "Test Season")
            .team("A", ("P1", 2000))
            .team("B", ("P2", 1900))
            .team("C", ("P3", 1800))
            .team("D", ("P4", 1700))
            .bracket_seeding(["A", "B", "C", "D"], "adjacent")
        )

        tournament = builder.build()

        first_round = tournament.rounds[0]
        matches = first_round.matches

        # Get team IDs for verification
        team_a_id = tournament.name_to_id["A"]
        team_b_id = tournament.name_to_id["B"]
        team_c_id = tournament.name_to_id["C"]
        team_d_id = tournament.name_to_id["D"]

        # Should be A vs B and C vs D
        pairings = [(m.competitor1_id, m.competitor2_id) for m in matches]
        expected_pairings = [(team_a_id, team_b_id), (team_c_id, team_d_id)]

        self.assertEqual(pairings, expected_pairings)

    def test_builder_manual_tiebreak(self):
        """Test manual tiebreak setting with TournamentBuilder."""
        builder = (
            TournamentBuilder()
            .knockout_format()
            .league("Test League", "TL", "team")
            .team("A", ("P1", 2000))
            .team("B", ("P2", 1900))
            .bracket_seeding(["A", "B"], "adjacent")
            .manual_tiebreak("A", "B", 1.5)
        )

        tournament = builder.build()
        match = tournament.rounds[0].matches[0]

        # Manual tiebreak should be set
        self.assertEqual(match.manual_tiebreak_value, 1.5)

    def test_builder_multi_game_matches(self):
        """Test multi-game match support in builder."""
        builder = (
            TournamentBuilder()
            .knockout_format()
            .games_per_match(3)
            .league("Test", "T", "individual")
            .player("Alice")
            .player("Bob")
            .bracket_seeding(["Alice", "Bob"], "adjacent")
        )

        tournament = builder.build()
        match = tournament.rounds[0].matches[0]

        self.assertEqual(match.games_per_match, 3)

    def test_builder_knockout_stage_naming(self):
        """Test knockout stage naming in builder."""
        builder = (
            TournamentBuilder()
            .knockout_format()
            .league("Test", "T", "team")
            .team("A", ("P1", 2000))
            .team("B", ("P2", 1900))
            .bracket_seeding(["A", "B"], "adjacent")
            .knockout_stage("custom-final")
        )

        tournament = builder.build()
        round = tournament.rounds[0]

        self.assertEqual(round.knockout_stage, "custom-final")


class TestKnockoutAssertions(unittest.TestCase):
    """Test knockout-specific assertion methods."""

    def test_advances_to_round_assertion(self):
        """Test assertion for advancement to specific rounds."""
        tournament = (
            TournamentBuilder()
            .knockout_format()
            .league("Test", "T", "team")
            .team("A", ("P1", 2000))
            .team("B", ("P2", 1900))
            .team("C", ("P3", 1800))
            .team("D", ("P4", 1700))
            .bracket_seeding(["A", "B", "C", "D"], "traditional")
            .round(2)
            .knockout_stage("finals")
            .match("A", "C", "1-0")  # Simulate A and C advancing to finals
            .build()
        )

        # A should have advanced to finals
        assert_tournament(tournament).team("A").assert_().advances_to_round("finals")

        # B should not have advanced to finals
        with self.assertRaises(AssertionError):
            assert_tournament(tournament).team("B").assert_().advances_to_round(
                "finals"
            )

    def test_eliminated_in_round_assertion(self):
        """Test assertion for elimination in specific rounds."""
        tournament = (
            TournamentBuilder()
            .knockout_format()
            .league("Test", "T", "team")
            .team("Winner", ("W1", 2000))
            .team("Loser", ("L1", 1900))
            .bracket_seeding(["Winner", "Loser"], "adjacent")
            .match("Winner", "Loser", "1-0")  # Winner beats Loser
            .build()
        )

        # Loser should be eliminated in finals
        assert_tournament(tournament).team("Loser").assert_().eliminated_in_round(
            "finals"
        )

        # Winner should not be eliminated in finals
        with self.assertRaises(AssertionError):
            assert_tournament(tournament).team("Winner").assert_().eliminated_in_round(
                "finals"
            )

    def test_bracket_position_assertion(self):
        """Test assertion for bracket position."""
        tournament = (
            TournamentBuilder()
            .knockout_format()
            .league("Test", "T", "team")
            .team("A", ("P1", 2000))
            .team("B", ("P2", 1900))
            .team("C", ("P3", 1800))
            .team("D", ("P4", 1700))
            .bracket_seeding(["A", "B", "C", "D"], "adjacent")
            .build()
        )

        # A should be in semifinals match 1
        assert_tournament(tournament).team("A").assert_().bracket_position(
            "semifinals", 1
        )

        # C should be in semifinals match 2
        assert_tournament(tournament).team("C").assert_().bracket_position(
            "semifinals", 2
        )

        # A should not be in match 2
        with self.assertRaises(AssertionError):
            assert_tournament(tournament).team("A").assert_().bracket_position(
                "semifinals", 2
            )

    def test_wins_knockout_tournament_assertion(self):
        """Test assertion for tournament winner."""
        tournament = (
            TournamentBuilder()
            .knockout_format()
            .league("Test", "T", "individual")
            .player("Champion")
            .player("Runner-up")
            .bracket_seeding(["Champion", "Runner-up"], "adjacent")
            .game("Champion", "Runner-up", "1-0")  # Champion wins
            .build()
        )

        # Champion should win tournament
        assert_tournament(tournament).player(
            "Champion"
        ).assert_().wins_knockout_tournament()

        # Runner-up should not win
        with self.assertRaises(AssertionError):
            assert_tournament(tournament).player(
                "Runner-up"
            ).assert_().wins_knockout_tournament()


class TestFullKnockoutTournamentSimulation(unittest.TestCase):
    """Test complete knockout tournament from start to finish."""

    def test_8_team_knockout_traditional_seeding(self):
        """Test complete 8-team knockout tournament with traditional seeding."""
        tournament = (
            TournamentBuilder()
            .knockout_format()
            .league("Championship", "CHAMP", "team")
            .season("CHAMP", "2024", boards=2)
            .team("Seed1", ("A1", 2200), ("A2", 2100))
            .team("Seed2", ("B1", 2150), ("B2", 2050))
            .team("Seed3", ("C1", 2100), ("C2", 2000))
            .team("Seed4", ("D1", 2050), ("D2", 1950))
            .team("Seed5", ("E1", 2000), ("E2", 1900))
            .team("Seed6", ("F1", 1950), ("F2", 1850))
            .team("Seed7", ("G1", 1900), ("G2", 1800))
            .team("Seed8", ("H1", 1850), ("H2", 1750))
            .bracket_seeding(
                [
                    "Seed1",
                    "Seed2",
                    "Seed3",
                    "Seed4",
                    "Seed5",
                    "Seed6",
                    "Seed7",
                    "Seed8",
                ],
                "traditional",
            )
            # Quarterfinals results
            .match("Seed1", "Seed8", "1-0", "1/2-1/2")  # Seed1 wins 1.5-0.5
            .match("Seed2", "Seed7", "1/2-1/2", "0-1")  # Seed2 wins 1.5-0.5
            .match("Seed3", "Seed6", "1-0", "1-0")  # Tied 1-1, need tiebreak
            .match("Seed4", "Seed5", "1-0", "0-1")  # Seed4 wins 2-0
            .manual_tiebreak("Seed3", "Seed6", 0.5)  # Seed3 advances on tiebreak
            # Semifinals
            .round(2)
            .knockout_stage("semifinals")
            .match("Seed1", "Seed2", "1/2-1/2", "1-0")  # Seed2 wins 1.5-0.5
            .match("Seed3", "Seed4", "1-0", "1/2-1/2")  # Seed3 wins 1.5-0.5
            # Finals
            .round(3)
            .knockout_stage("finals")
            .match("Seed2", "Seed3", "1-0", "0-1")  # Seed2 wins 2-0
            .build()
        )

        # Verify tournament structure
        self.assertEqual(tournament.format, TournamentFormat.KNOCKOUT)
        self.assertEqual(len(tournament.rounds), 3)

        # Verify stage names
        self.assertEqual(tournament.rounds[0].knockout_stage, "quarterfinals")
        self.assertEqual(tournament.rounds[1].knockout_stage, "semifinals")
        self.assertEqual(tournament.rounds[2].knockout_stage, "finals")

        # Test assertions
        assertions = assert_tournament(tournament)

        # Quarter-finalists
        assertions.team("Seed1").assert_().advances_to_round("semifinals")
        assertions.team("Seed2").assert_().advances_to_round("semifinals")
        assertions.team("Seed3").assert_().advances_to_round("semifinals")
        assertions.team("Seed4").assert_().advances_to_round("semifinals")

        # Eliminated in quarters
        assertions.team("Seed5").assert_().eliminated_in_round("quarterfinals")
        assertions.team("Seed6").assert_().eliminated_in_round("quarterfinals")
        assertions.team("Seed7").assert_().eliminated_in_round("quarterfinals")
        assertions.team("Seed8").assert_().eliminated_in_round("quarterfinals")

        # Finalists
        assertions.team("Seed2").assert_().advances_to_round("finals")
        assertions.team("Seed3").assert_().advances_to_round("finals")

        # Eliminated in semis
        assertions.team("Seed1").assert_().eliminated_in_round("semifinals")
        assertions.team("Seed4").assert_().eliminated_in_round("semifinals")

        # Tournament winner
        assertions.team("Seed2").assert_().wins_knockout_tournament()
        assertions.team("Seed3").assert_().eliminated_in_round("finals")

    def test_4_team_individual_knockout_multi_game(self):
        """Test 4-player individual knockout with multi-game matches."""
        tournament = (
            TournamentBuilder()
            .knockout_format()
            .games_per_match(3)  # 3 games per match
            .league("Blitz Championship", "BLITZ", "individual")
            .player("Magnus", 2800)
            .player("Hikaru", 2750)
            .player("Wesley", 2700)
            .player("Fabiano", 2650)
            .bracket_seeding(["Magnus", "Hikaru", "Wesley", "Fabiano"], "traditional")
            # Semifinals - each match has 3 games
            .game("Magnus", "Fabiano", "1-0")  # Game 1
            .game("Magnus", "Fabiano", "1/2-1/2")  # Game 2
            .game("Magnus", "Fabiano", "1-0")  # Game 3 (Magnus wins 2.5-0.5)
            .game("Hikaru", "Wesley", "0-1")  # Game 1
            .game("Hikaru", "Wesley", "1-0")  # Game 2
            .game(
                "Hikaru", "Wesley", "1/2-1/2"
            )  # Game 3 (Wesley wins 1.5-1.5, need tiebreak)
            .manual_tiebreak("Hikaru", "Wesley", -0.5)  # Wesley advances
            # Finals
            .round(2)
            .knockout_stage("finals")
            .game("Magnus", "Wesley", "1/2-1/2")  # Game 1
            .game("Magnus", "Wesley", "1-0")  # Game 2
            .game("Magnus", "Wesley", "1/2-1/2")  # Game 3 (Magnus wins 2.0-1.0)
            .build()
        )

        # Verify multi-game structure
        semis_matches = tournament.rounds[0].matches
        for match in semis_matches:
            self.assertEqual(match.games_per_match, 3)
            self.assertEqual(len(match.games), 3)

        # Test results
        assertions = assert_tournament(tournament)
        assertions.player("Magnus").assert_().wins_knockout_tournament()
        assertions.player("Wesley").assert_().eliminated_in_round("finals")
        assertions.player("Hikaru").assert_().eliminated_in_round("semifinals")
        assertions.player("Fabiano").assert_().eliminated_in_round("semifinals")


if __name__ == "__main__":
    unittest.main()
