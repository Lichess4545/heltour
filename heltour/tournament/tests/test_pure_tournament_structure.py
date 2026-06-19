"""
Test tournament structure using only pure Python models.

This test verifies that the tournament_core structures correctly represent
tournaments without any database dependencies.
"""

from django.test import TestCase
from heltour.tournament_core.builder import TournamentBuilder
from heltour.tournament_core.structure import GameResult


class PureTournamentStructureTest(TestCase):
    """Test tournament calculations using only pure Python structures."""

    def test_five_teams_two_rounds_pure_structure(self):
        """Test the exact same scenario as test_five_teams_two_rounds but with pure structures."""

        # Build tournament structure
        builder = TournamentBuilder()

        # Add league and season metadata
        builder.league(
            "Five Team League",
            "FTL",
            "team",
            rating_type="classical",
            pairing_type="swiss-dutch",
            theme="blue",
        )
        builder.season("FTL", "Five Team Season", rounds=3, boards=1, is_active=True)

        # Add 5 teams with single boards
        builder.team("Team A", ("PlayerA", 2200))
        builder.team("Team B", ("PlayerB", 2150))
        builder.team("Team C", ("PlayerC", 2100))
        builder.team("Team D", ("PlayerD", 2050))
        builder.team("Team E", ("PlayerE", 2000))

        # Round 1: Manual pairings to match what JavaFo would generate
        # Highest rated teams play each other, lowest gets bye
        builder.round(1)
        builder.match("Team A", "Team B", "1-0")  # A beats B
        builder.match("Team C", "Team D", "1/2-1/2")  # C draws D
        # Team E should get automatic bye via complete()
        builder.complete()

        # Build the tournament
        tournament = builder.build()

        # Verify Round 1 structure
        self.assertEqual(len(tournament.rounds), 1)
        round1 = tournament.rounds[0]
        self.assertEqual(
            len(round1.matches),
            3,
            f"Should have 3 matches but got {len(round1.matches)}",
        )  # 2 played matches + 1 bye

        # Find the bye match
        bye_matches = [m for m in round1.matches if m.is_bye]
        self.assertEqual(len(bye_matches), 1, "Should have exactly 1 bye in round 1")

        # Verify it's Team E (id=5) that got the bye
        bye_match = bye_matches[0]
        self.assertEqual(
            bye_match.competitor1_id, 5, "Team E (id=5) should have the bye"
        )

        # Calculate results after round 1
        results = tournament.calculate_results()

        # Check scores after round 1
        # Team A: Won (2 points)
        # Team B: Lost (0 points)
        # Team C: Drew (1 point)
        # Team D: Drew (1 point)
        # Team E: Bye (1 point)
        self.assertEqual(
            results[1].match_points, 2.0, "Team A should have 2 match points"
        )
        self.assertEqual(
            results[2].match_points, 0.0, "Team B should have 0 match points"
        )
        self.assertEqual(
            results[3].match_points, 1.0, "Team C should have 1 match point"
        )
        self.assertEqual(
            results[4].match_points, 1.0, "Team D should have 1 match point"
        )
        self.assertEqual(
            results[5].match_points, 1.0, "Team E should have 1 match point (bye)"
        )

        # Round 2: Standings are A(2), C/D/E(1), B(0)
        # Swiss principle: Team with bye in R1 shouldn't get bye in R2
        # Typical pairing: A vs C (2 vs 1), D vs E (1 vs 1), B gets bye
        builder.round(2)
        builder.match("Team A", "Team C", "1-0")  # A beats C
        builder.match("Team D", "Team E", "1-0")  # D beats E
        # Team B should get automatic bye via complete()
        builder.complete()

        # Rebuild tournament to include round 2
        tournament = builder.build()

        # Verify Round 2 structure
        self.assertEqual(len(tournament.rounds), 2)
        round2 = tournament.rounds[1]
        self.assertEqual(len(round2.matches), 3)  # 2 played matches + 1 bye

        # Find the bye match in round 2
        bye_matches_r2 = [m for m in round2.matches if m.is_bye]
        self.assertEqual(len(bye_matches_r2), 1, "Should have exactly 1 bye in round 2")

        # Verify it's Team B (id=2) that got the bye
        bye_match_r2 = bye_matches_r2[0]
        self.assertEqual(
            bye_match_r2.competitor1_id,
            2,
            "Team B (id=2) should have the bye in round 2",
        )

        # Verify that different teams got byes in each round
        self.assertNotEqual(
            bye_match.competitor1_id,
            bye_match_r2.competitor1_id,
            "Different teams should get byes in different rounds",
        )

        # Calculate final results
        final_results = tournament.calculate_results()

        # Final scores:
        # Team A: 2 wins (4 points)
        # Team B: 1 loss + 1 bye (1 point)
        # Team C: 1 draw + 1 loss (1 point)
        # Team D: 1 draw + 1 win (3 points)
        # Team E: 1 bye + 1 loss (1 point)
        self.assertEqual(
            final_results[1].match_points, 4.0, "Team A should have 4 match points"
        )
        self.assertEqual(
            final_results[2].match_points, 1.0, "Team B should have 1 match point"
        )
        self.assertEqual(
            final_results[3].match_points, 1.0, "Team C should have 1 match point"
        )
        self.assertEqual(
            final_results[4].match_points, 3.0, "Team D should have 3 match points"
        )
        self.assertEqual(
            final_results[5].match_points, 1.0, "Team E should have 1 match point"
        )

    def test_tournament_metadata(self):
        """Test that metadata is correctly stored."""
        builder = TournamentBuilder()

        # Set up metadata
        builder.league("Test League", "TL", "team", theme="blue", rating_type="rapid")
        builder.season("TL", "Test Season", rounds=5, boards=3, is_active=True)

        # Add teams
        builder.team("Alpha", ("A1", 1800), ("A2", 1750), ("A3", 1700))
        builder.team("Beta", ("B1", 1780), ("B2", 1730), ("B3", 1680))

        # Check metadata
        self.assertEqual(builder.metadata.league_name, "Test League")
        self.assertEqual(builder.metadata.league_tag, "TL")
        self.assertEqual(builder.metadata.competitor_type, "team")
        self.assertEqual(builder.metadata.boards, 3)
        self.assertEqual(builder.metadata.league_settings["theme"], "blue")
        self.assertEqual(builder.metadata.league_settings["rating_type"], "rapid")

        # Check team metadata
        self.assertIn("Alpha", builder.metadata.teams)
        self.assertIn("Beta", builder.metadata.teams)
        self.assertEqual(len(builder.metadata.teams["Alpha"]["players"]), 3)
        self.assertEqual(builder.metadata.teams["Alpha"]["players"][0]["name"], "A1")
        self.assertEqual(builder.metadata.teams["Alpha"]["players"][0]["rating"], 1800)

    def test_color_alternation_in_team_matches(self):
        """Test that colors alternate correctly by board in team matches."""
        builder = TournamentBuilder()

        builder.league("Color Test League", "CTL", "team")
        builder.season("CTL", "Color Test", rounds=1, boards=4)

        # Add two teams with 4 boards each
        builder.team("White Team", "W1", "W2", "W3", "W4")
        builder.team("Black Team", "B1", "B2", "B3", "B4")

        # Play a match
        builder.round(1)
        builder.match("White Team", "Black Team", "1-0", "0-1", "1-0", "0-1")

        tournament = builder.build()
        match = tournament.rounds[0].matches[0]

        # Check board colors
        # Board 1 (index 0): White Team gets white
        self.assertEqual(match.games[0].player1.player_id, builder.metadata.players["W1"])
        self.assertEqual(match.games[0].player2.player_id, builder.metadata.players["B1"])
        self.assertEqual(match.games[0].result, GameResult.P1_WIN)

        # Board 2 (index 1): Black Team gets white (colors swapped)
        self.assertEqual(match.games[1].player1.player_id, builder.metadata.players["B2"])
        self.assertEqual(match.games[1].player2.player_id, builder.metadata.players["W2"])
        self.assertEqual(
            match.games[1].result, GameResult.P2_WIN
        )  # "0-1" means black wins, which is W2

        # Board 3 (index 2): White Team gets white again
        self.assertEqual(match.games[2].player1.player_id, builder.metadata.players["W3"])
        self.assertEqual(match.games[2].player2.player_id, builder.metadata.players["B3"])
        self.assertEqual(match.games[2].result, GameResult.P1_WIN)

        # Board 4 (index 3): Black Team gets white (colors swapped)
        self.assertEqual(match.games[3].player1.player_id, builder.metadata.players["B4"])
        self.assertEqual(match.games[3].player2.player_id, builder.metadata.players["W4"])
        self.assertEqual(
            match.games[3].result, GameResult.P2_WIN
        )  # "0-1" means black wins, which is W4
