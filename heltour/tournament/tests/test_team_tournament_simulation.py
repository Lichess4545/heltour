"""
Test team tournament simulation using the tournament builder API.

This test simulates a complete team tournament from start to finish,
testing roster confirmation, round-by-round results, standings, and tiebreaks.
The tests are organized to read from top to bottom like following a real tournament.
"""

from unittest import TestCase
from heltour.tournament_core.builder import TournamentBuilder
from heltour.tournament_core.tiebreaks import (
    calculate_sonneborn_berger,
)


class TeamTournamentSimulationTest(TestCase):
    """Simulate a complete team tournament from start to finish."""

    # ========================================================================
    # TOURNAMENT SETUP HELPERS
    # ========================================================================

    def setUp(self):
        """Set up the basic tournament infrastructure using TournamentBuilder."""
        # Create tournament builder
        self.builder = TournamentBuilder()

        # Define the league and season
        self.builder.league(
            name="Test Team League", tag="test-team", type="team"
        ).season(league_tag="test-team", name="Test Season 2024", rounds=4, boards=4)

        # Add 6 teams with 4 players each
        team_data = [
            ("Alpha Knights", 2000),
            ("Beta Bishops", 1900),
            ("Gamma Rooks", 1800),
            ("Delta Queens", 1700),
            ("Epsilon Pawns", 1600),
            ("Zeta Kings", 1500),
        ]

        for team_name, base_rating in team_data:
            players = []
            for board in range(1, 5):
                player_name = f"{team_name} Board {board}"
                rating = base_rating - (board * 50)
                players.append((player_name, rating))
            self.builder.team(team_name, *players)

        # Store team names for easy reference
        self.team_names = [name for name, _ in team_data]

    # ========================================================================
    # VERIFICATION HELPERS
    # ========================================================================

    def _get_standings(self):
        """Get current standings with scores and tiebreaks."""
        tournament = self.builder.build()

        # Calculate base results
        results = tournament.calculate_results()

        # Calculate tiebreaks and create standings
        standings = []
        for comp_id, comp_score in results.items():
            sb_score = calculate_sonneborn_berger(comp_score, results)

            # Create a result object with tiebreak scores
            standing = type(
                "Standing",
                (),
                {
                    "competitor": comp_id,
                    "tiebreak_scores": {
                        "Match Points": comp_score.match_points,
                        "Game Points": comp_score.game_points,
                        "Sonneborn-Berger": sb_score,
                    },
                },
            )()
            standings.append(standing)

        # Sort by tiebreaks
        sorted_standings = sorted(
            standings,
            key=lambda x: (
                x.tiebreak_scores["Match Points"],
                x.tiebreak_scores["Game Points"],
                x.tiebreak_scores["Sonneborn-Berger"],
            ),
            reverse=True,
        )

        return sorted_standings

    def _get_team_name(self, team_id):
        """Get team name from ID."""
        for name, info in self.builder.metadata.teams.items():
            if info["id"] == team_id:
                return name
        return f"Team {team_id}"

    def _print_standings(self, round_num):
        """Print standings in a nice format for debugging."""
        print(f"\n=== STANDINGS AFTER ROUND {round_num} ===")
        standings = self._get_standings()

        for pos, result in enumerate(standings, 1):
            team_name = self._get_team_name(result.competitor)
            mp = result.tiebreak_scores.get("Match Points", 0)
            gp = result.tiebreak_scores.get("Game Points", 0)
            sb = result.tiebreak_scores.get("Sonneborn-Berger", 0)
            print(f"{pos}. {team_name}: MP={mp:.1f} GP={gp:.1f} SB={sb:.1f}")

    # ========================================================================
    # THE ACTUAL TOURNAMENT TESTS
    # ========================================================================

    def test_01_initial_roster_confirmation(self):
        """Test 01: Confirm initial team rosters are set up correctly."""
        # Verify we have 6 teams
        self.assertEqual(len(self.builder.metadata.teams), 6)

        # Verify each team has 4 players
        for team_name, team_info in self.builder.metadata.teams.items():
            self.assertEqual(
                len(team_info["players"]), 4, f"{team_name} should have 4 players"
            )

            # Verify ratings decrease by board
            for i, player in enumerate(team_info["players"]):
                if i > 0:
                    prev_rating = team_info["players"][i - 1]["rating"]
                    self.assertLess(
                        player["rating"],
                        prev_rating,
                        f"Board {i+1} should have lower rating than board {i}",
                    )

        # Verify competitors list
        tournament = self.builder.build()
        self.assertEqual(len(tournament.competitors), 6)

    def test_02_round_1_pairings_and_results(self):
        """Test 02: Round 1 - Top half vs bottom half pairings."""
        # Create round 1
        self.builder.round(1)

        # Play matches (top half vs bottom half)
        # Note: On odd boards (1,3), first team has white pieces
        # On even boards (2,4), second team has white pieces
        # Results are always from white's perspective
        # Alpha wins 3-1
        self.builder.match(
            "Alpha Knights",
            "Delta Queens",
            "1-0",  # Board 1: Alpha (white) beats Delta (black)
            "1-0",  # Board 2: Delta (white) beats Alpha (black)
            "1-0",  # Board 3: Alpha (white) beats Delta (black)
            "0-1",  # Board 4: Delta (white) loses to Alpha (black)
        )
        # Beta wins 5-1
        self.builder.match(
            "Beta Bishops",
            "Epsilon Pawns",
            "1-0",  # Board 1: Beta (white) beats Epsilon (black)
            "0-1",  # Board 2: Epsilon (white) loses to Beta (black)
            "1-0",  # Board 3: Beta (white) beats Epsilon (black)
            "0-1",  # Board 4: Epsilon (white) loses to Beta (black)
        )
        # Gamma wins 4-0
        self.builder.match(
            "Gamma Rooks",
            "Zeta Kings",
            "1-0",  # Board 1: Gamma (white) beats Zeta (black)
            "0-1",  # Board 2: Zeta (white) loses to Gamma (black)
            "1-0",  # Board 3: Gamma (white) beats Zeta (black)
            "0-1",  # Board 4: Zeta (white) loses to Gamma (black)
        )

        # Complete the round
        self.builder.complete()

        # Verify standings after round 1
        standings = self._get_standings()

        # Check match points by team
        expected_results = {
            "Alpha Knights": 2,  # Won 3-1
            "Gamma Rooks": 2,  # Won 4-0
            "Beta Bishops": 2,  # Won 3-1
            "Delta Queens": 0,  # Lost
            "Epsilon Pawns": 0,  # Lost
            "Zeta Kings": 0,  # Lost
        }

        for standing in standings:
            team_name = self._get_team_name(standing.competitor)
            mp = standing.tiebreak_scores.get("Match Points", 0)
            expected_mp = expected_results.get(team_name, -1)
            self.assertEqual(
                mp,
                expected_mp,
                f"{team_name} should have {expected_mp} match points, got {mp}",
            )

    def test_03_round_2_swiss_pairings(self):
        """Test 03: Round 2 - Swiss pairings based on round 1 results."""
        # First run round 1
        self.test_02_round_1_pairings_and_results()

        # Create round 2
        self.builder.round(2)

        # Swiss pairings - winners play winners
        self.builder.match(
            "Alpha Knights",
            "Beta Bishops",
            "1-0",  # Board 1: Alpha (white) beats Beta (black) = 1-0
            "0-1",  # Board 2: Beta (white) loses to Alpha (black) = 0-1
            "1-0",  # Board 3: Alpha (white) beats Beta (black) = 1-0
            "1/2-1/2",  # Board 4: Draw = 0.5-0.5
        )  # Final: Alpha 2.5-1.5 Beta
        self.builder.match(
            "Gamma Rooks",
            "Delta Queens",
            "1-0",
            "1/2-1/2",
            "1-0",
            "1-0",  # Gamma 3.5-0.5 Delta
        )
        self.builder.match(
            "Epsilon Pawns",
            "Zeta Kings",
            "1/2-1/2",  # Board 1: Draw
            "0-1",  # Board 2: Zeta (white) beats Epsilon (black) → flipped to 1-0 = Zeta wins
            "1/2-1/2",  # Board 3: Draw
            "1-0",  # Board 4: Epsilon (white) beats Zeta (black) → flipped to 0-1 = Epsilon wins
        )  # Final: 2-2 draw

        # Verify standings
        standings = self._get_standings()

        # Check that we have two teams with 4 match points (Alpha and Gamma)
        teams_with_4mp = []
        for standing in standings:  # Check all standings
            name = self._get_team_name(standing.competitor)
            mp = standing.tiebreak_scores.get("Match Points", 0)
            if mp == 4.0:
                teams_with_4mp.append(name)

        self.assertEqual(
            len(teams_with_4mp), 2, "Should have 2 teams with 4 match points"
        )
        self.assertIn("Alpha Knights", teams_with_4mp)
        self.assertIn("Gamma Rooks", teams_with_4mp)

    def test_04_round_3_critical_matchups(self):
        """Test 04: Round 3 - Critical matchups for tournament lead."""
        # Run previous rounds
        self.test_03_round_2_swiss_pairings()

        # Create round 3
        self.builder.round(3)

        # Critical matchups
        self.builder.match(
            "Alpha Knights",
            "Gamma Rooks",
            "0-1",
            "1/2-1/2",
            "0-1",
            "1/2-1/2",  # Gamma 3-1 Alpha (upset!)
        )
        self.builder.match(
            "Beta Bishops",
            "Delta Queens",
            "1-0",
            "1-0",
            "1-0",
            "1-0",  # Beta 4-0 Delta (whitewash)
        )
        self.builder.match(
            "Epsilon Pawns",
            "Zeta Kings",
            "1-0",  # Board 1: Epsilon wins
            "1-0",  # Board 2: Zeta (white) loses → flipped to 0-1 = Epsilon wins
            "0-1",  # Board 3: Zeta wins
            "0-1",  # Board 4: Epsilon (white) loses → flipped to 1-0 = Zeta wins
        )  # Final: 2-2 draw

        # Verify standings
        standings = self._get_standings()

        # Gamma should have 6 match points
        gamma_found = False
        for standing in standings:
            name = self._get_team_name(standing.competitor)
            if name == "Gamma Rooks":
                mp = standing.tiebreak_scores.get("Match Points", 0)
                self.assertEqual(mp, 6.0, "Gamma should have 6 match points")
                gamma_found = True
                break
        self.assertTrue(gamma_found, "Gamma Rooks not found in standings")

    def test_05_final_round_and_tournament_results(self):
        """Test 05: Round 4 - Final round determines the champion."""
        # Run previous rounds
        self.test_04_round_3_critical_matchups()

        # Create round 4
        self.builder.round(4)

        # Final round pairings
        self.builder.match(
            "Beta Bishops",
            "Gamma Rooks",
            "1-0",
            "1-0",
            "1/2-1/2",
            "0-1",  # Beta 2.5-1.5 Gamma (Beta spoils!)
        )
        self.builder.match(
            "Alpha Knights",
            "Epsilon Pawns",
            "1-0",
            "1-0",
            "1-0",
            "1/2-1/2",  # Alpha 3.5-0.5 Epsilon
        )
        self.builder.match(
            "Delta Queens", "Zeta Kings", "1-0", "0-1", "1-0", "1-0"  # Delta 3-1 Zeta
        )

        # Get final standings
        standings = self._get_standings()

        # Verify final positions
        final_positions = []
        for pos, result in enumerate(standings, 1):
            team_name = self._get_team_name(result.competitor)
            mp = result.tiebreak_scores.get("Match Points", 0)
            gp = result.tiebreak_scores.get("Game Points", 0)
            sb = result.tiebreak_scores.get("Sonneborn-Berger", 0)
            final_positions.append(
                {
                    "position": pos,
                    "team": team_name,
                    "match_points": mp,
                    "game_points": gp,
                    "sonneborn_berger": sb,
                }
            )

        # Count how many teams have 6 match points
        teams_with_6mp = [pos for pos in final_positions if pos["match_points"] == 6.0]
        self.assertGreaterEqual(
            len(teams_with_6mp), 2, "Should have at least 2 teams with 6 match points"
        )

        # The winner should have the best tiebreaks among teams with 6 match points
        if len(teams_with_6mp) > 1:
            self.assertEqual(
                teams_with_6mp[0],
                final_positions[0],
                "Team with 6 MP and best tiebreaks should be first",
            )

    def test_06_complete_tournament_verification(self):
        """Test 06: Verify complete tournament data integrity."""
        # Run the complete tournament
        self.test_05_final_round_and_tournament_results()

        # Get tournament structure
        tournament = self.builder.build()

        # Verify all rounds are created
        self.assertEqual(len(tournament.rounds), 4)

        # Verify we have 6 competitors
        self.assertEqual(len(tournament.competitors), 6)

        # Verify total games played
        total_games = 0
        for round_obj in tournament.rounds:
            for match in round_obj.matches:
                total_games += len(match.games)

        expected_games = 3 * 4 * 4  # 3 matches per round * 4 boards * 4 rounds
        self.assertEqual(total_games, expected_games)

        # Verify all games have results
        games_with_results = 0
        for round_obj in tournament.rounds:
            for match in round_obj.matches:
                for game in match.games:
                    if game.result is not None:
                        games_with_results += 1

        self.assertEqual(games_with_results, total_games)

        # Verify match points sum to correct total
        standings = self._get_standings()
        total_match_points = sum(
            result.tiebreak_scores.get("Match Points", 0) for result in standings
        )
        expected_match_points = 3 * 2 * 4  # 3 matches * 2 points * 4 rounds
        self.assertEqual(total_match_points, expected_match_points)
