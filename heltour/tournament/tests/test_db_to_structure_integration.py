"""
Integration tests to verify that db_to_structure produces correct results
when used with the actual score calculation methods.
"""

from django.test import TestCase
from heltour.tournament.models import Team, TeamScore
from heltour.tournament.db_to_structure import season_to_tournament_structure
from heltour.tournament.builder import TournamentBuilder


class DbToStructureIntegrationTests(TestCase):
    """Test that the conversion works correctly with real score calculations."""

    def test_simple_tournament_scores(self):
        """Test a simple 3-team round robin."""
        tournament = (
            TournamentBuilder()
            .league(
                "Test League",
                "TL",
                "team",
                rating_type="classical",
                theme="blue",
                pairing_type="swiss-dutch",
                # Configure tiebreaks
                team_tiebreak_1="game_points",
                team_tiebreak_2="head_to_head",
                team_tiebreak_3="games_won",
                team_tiebreak_4="sonneborn_berger",
            )
            .season("TL", "Test Season", rounds=3, boards=2)
            .team("Team 1", "team1_player1", "team1_player2")
            .team("Team 2", "team2_player1", "team2_player2")
            .team("Team 3", "team3_player1", "team3_player2")
            # Round 1: Team 1 beats Team 2 (1.5-0.5), Team 3 gets bye
            .round(1)
            .match("Team 1", "Team 2", "1-0", "1/2-1/2")
            # Team 3 gets automatic bye
            .complete()
            # Round 2: Team 1 vs Team 3 (1-1), Team 2 gets bye
            .round(2)
            # 1-1 draw: Board 1: Team 1(white) wins, Board 2: Team 3(white) wins
            .match("Team 1", "Team 3", "1-0", "1-0")
            # Team 2 gets automatic bye
            .complete()
            # Round 3: Team 2 vs Team 3 (1-1), Team 1 gets bye
            .round(3)
            # 1-1 draw: Board 1: Team 2(white) wins, Board 2: Team 3(white) wins
            .match("Team 2", "Team 3", "1-0", "1-0")
            # Team 1 gets automatic bye
            .complete()
            .calculate()
            .build()
        )

        season = tournament.seasons["Test Season"]

        # Get the scores
        scores = {
            ts.team.number: ts for ts in TeamScore.objects.filter(team__season=season)
        }

        # Verify match points
        # Team 1: Win + Draw + Bye = 2 + 1 + 1 = 4
        self.assertEqual(scores[1].match_points, 4)
        # Team 2: Loss + Bye + Draw = 0 + 1 + 1 = 2
        self.assertEqual(scores[2].match_points, 2)
        # Team 3: Bye + Draw + Draw = 1 + 1 + 1 = 3
        self.assertEqual(scores[3].match_points, 3)

        # Verify game points
        # Team 1: 1.5 + 1 + 1 (bye) = 3.5
        self.assertEqual(scores[1].game_points, 3.5)
        # Team 2: 0.5 + 1 (bye) + 1 = 2.5
        self.assertEqual(scores[2].game_points, 2.5)
        # Team 3: 1 (bye) + 1 + 1 = 3
        self.assertEqual(scores[3].game_points, 3)

        # Verify games won
        # Team 1: 1 + 1 + 0 = 2
        self.assertEqual(scores[1].games_won, 2)
        # Team 2: 0 + 0 + 1 = 1
        self.assertEqual(scores[2].games_won, 1)
        # Team 3: 0 + 1 + 1 = 2
        self.assertEqual(scores[3].games_won, 2)

        # Verify match count (excluding byes)
        self.assertEqual(scores[1].match_count, 2)
        self.assertEqual(scores[2].match_count, 2)
        self.assertEqual(scores[3].match_count, 2)

        # Verify Sonneborn-Berger
        # Team 1: Win vs Team2(2MP) = 2*1 = 2, Draw vs Team3(3MP) = 3*0.5 = 1.5, Total = 3.5
        self.assertEqual(scores[1].sb_score, 3.5)
        # Team 2: Loss vs Team1(4MP) = 0, Draw vs Team3(3MP) = 3*0.5 = 1.5, Total = 1.5
        self.assertEqual(scores[2].sb_score, 1.5)
        # Team 3: Draw vs Team1(4MP) = 4*0.5 = 2, Draw vs Team2(2MP) = 2*0.5 = 1, Total = 3
        self.assertEqual(scores[3].sb_score, 3.0)

    def test_conversion_matches_calculation(self):
        """Test that direct conversion gives same results as calculate_scores."""
        tournament = (
            TournamentBuilder()
            .league(
                "Test League",
                "TL",
                "team",
                rating_type="classical",
                theme="blue",
                pairing_type="swiss-dutch",
                team_tiebreak_1="game_points",
                team_tiebreak_2="head_to_head",
                team_tiebreak_3="games_won",
                team_tiebreak_4="sonneborn_berger",
            )
            .season("TL", "Test Season", rounds=3, boards=2)
            .team("Team 1", "team1_player1", "team1_player2")
            .team("Team 2", "team2_player1", "team2_player2")
            .team("Team 3", "team3_player1", "team3_player2")
            # Round 1
            .round(1)
            # Team 1 wins 1.5-0.5: Board 1: T1(white) wins, Board 2: T2(white) draws with T1(black)
            .match("Team 1", "Team 2", "1-0", "1/2-1/2")
            .complete()
            # Round 2
            .round(2)
            # Team 1 wins 1.5-0.5: Board 1: T1(white) wins, Board 2: T3(white) draws with T1(black)
            .match("Team 1", "Team 3", "1-0", "1/2-1/2")
            .complete()
            # Round 3
            .round(3)
            # Team 2 wins 2-0: Board 1: T2(white) wins, Board 2: T3(white) loses to T2(black)
            .match("Team 2", "Team 3", "1-0", "0-1")
            .complete()
            .calculate()
            .build()
        )

        season = tournament.seasons["Test Season"]
        teams = list(Team.objects.filter(season=season).order_by("number"))

        # Convert to tournament structure
        tournament_structure = season_to_tournament_structure(season)

        # Calculate results using tournament_core
        results = tournament_structure.calculate_results()

        # Verify match points
        # Team 1: Win + Win + Bye = 2 + 2 + 1 = 5
        self.assertEqual(results[teams[0].id].match_points, 5)
        # Team 2: Loss + Bye + Win = 0 + 1 + 2 = 3
        self.assertEqual(results[teams[1].id].match_points, 3)
        # Team 3: Bye + Loss + Loss = 1 + 0 + 0 = 1
        self.assertEqual(results[teams[2].id].match_points, 1)

        # Verify game points
        # Team 1: 1.5 + 1.5 + 1 (bye) = 4.0
        self.assertEqual(results[teams[0].id].game_points, 4.0)
        # Team 2: 0.5 + 1 (bye) + 2 = 3.5
        self.assertEqual(results[teams[1].id].game_points, 3.5)
        # Team 3: 1 (bye) + 0.5 + 0 = 1.5
        self.assertEqual(results[teams[2].id].game_points, 1.5)

        # Compare with database calculation
        season.calculate_scores()
        db_scores = {
            ts.team.id: ts for ts in TeamScore.objects.filter(team__season=season)
        }

        for team in teams:
            self.assertEqual(
                db_scores[team.id].match_points,
                results[team.id].match_points,
                f"Match points mismatch for {team.name}",
            )
            self.assertEqual(
                db_scores[team.id].game_points,
                results[team.id].game_points,
                f"Game points mismatch for {team.name}",
            )

    def test_head_to_head_tiebreak(self):
        """Test head-to-head calculation for tied teams."""
        tournament = (
            TournamentBuilder()
            .league(
                "Test League",
                "TL",
                "team",
                rating_type="classical",
                theme="blue",
                pairing_type="swiss-dutch",
                team_tiebreak_1="head_to_head",
                team_tiebreak_2="sonneborn_berger",
            )
            .season("TL", "Test Season", rounds=3, boards=2)
            # Create 4 teams
            .team("Team A", "A1", "A2")
            .team("Team B", "B1", "B2")
            .team("Team C", "C1", "C2")
            .team("Team D", "D1", "D2")
            # Round 1
            .round(1)
            .match("Team A", "Team B", "1-0", "1/2-1/2")  # A wins 1.5-0.5
            .match("Team C", "Team D", "1/2-1/2", "1/2-1/2")  # Draw 1-1
            .complete()
            # Round 2
            .round(2)
            .match("Team A", "Team C", "1-0", "1/2-1/2")  # A wins 1.5-0.5
            .match("Team B", "Team D", "1/2-1/2", "1/2-1/2")  # Draw 1-1
            .complete()
            # Round 3
            .round(3)
            .match("Team A", "Team D", "1-0", "1/2-1/2")  # A wins 1.5-0.5
            .match("Team B", "Team C", "1-0", "1/2-1/2")  # B wins 1.5-0.5
            .complete()
            .calculate()
            .build()
        )

        season = tournament.seasons["Test Season"]

        # Convert to tournament structure
        tournament_structure = season_to_tournament_structure(season)
        results = tournament_structure.calculate_results()

        # Get teams by name for easier reference
        teams = {t.name: t for t in Team.objects.filter(season=season)}

        # Team A: 3 wins = 6 match points
        self.assertEqual(results[teams["Team A"].id].match_points, 6)
        # Team B: 1 win, 1 draw, 1 loss = 3 match points
        self.assertEqual(results[teams["Team B"].id].match_points, 3)
        # Team C: 1 draw, 2 losses = 1 match point
        self.assertEqual(results[teams["Team C"].id].match_points, 1)
        # Team D: 2 draws, 1 loss = 2 match points
        self.assertEqual(results[teams["Team D"].id].match_points, 2)

    def test_complex_bye_scenario(self):
        """Test with 5 teams where different teams get byes each round."""
        tournament = (
            TournamentBuilder()
            .league(
                "Test League",
                "TL",
                "team",
                rating_type="classical",
                theme="blue",
                pairing_type="swiss-dutch",
            )
            .season("TL", "Test Season", rounds=3, boards=2)
            # Create 5 teams
            .team("Red", "R1", "R2")
            .team("Blue", "B1", "B2")
            .team("Green", "G1", "G2")
            .team("Yellow", "Y1", "Y2")
            .team("Purple", "P1", "P2")
            # Round 1: Purple gets bye
            .round(1)
            # Red wins 2-0: Board 1: Red(white) beats Blue(black), Board 2: Blue(white) loses to Red(black)
            .match("Red", "Blue", "1-0", "0-1")
            # Draw 1-1: Both boards drawn
            .match("Green", "Yellow", "1/2-1/2", "1/2-1/2")
            .complete()
            # Round 2: Yellow gets bye
            .round(2)
            # Draw 1-1: Board 1: Red(white) beats Green(black), Board 2: Green(white) beats Red(black)
            .match("Red", "Green", "1-0", "1-0")
            # Purple wins 2-0: Board 1: Blue(white) loses to Purple(black), Board 2: Purple(white) beats Blue(black)
            .match("Blue", "Purple", "0-1", "1-0")
            .complete()
            # Round 3: Red gets bye
            .round(3)
            # Blue wins 1.5-0.5: Board 1: Blue(white) wins, Board 2: Green(white) draws Blue(black)
            .match("Blue", "Green", "1-0", "1/2-1/2")
            # Draw 1-1: Both boards drawn
            .match("Yellow", "Purple", "1/2-1/2", "1/2-1/2")
            .complete()
            .calculate()
            .build()
        )

        season = tournament.seasons["Test Season"]

        # Get scores
        scores = {
            ts.team.name: ts for ts in TeamScore.objects.filter(team__season=season)
        }

        # Verify match points
        # Red: Win + Draw + Bye = 2 + 1 + 1 = 4
        self.assertEqual(scores["Red"].match_points, 4)
        # Blue: Loss + Loss + Win = 0 + 0 + 2 = 2
        self.assertEqual(scores["Blue"].match_points, 2)
        # Green: Draw + Draw + Loss = 1 + 1 + 0 = 2
        self.assertEqual(scores["Green"].match_points, 2)
        # Yellow: Draw + Bye + Draw = 1 + 1 + 1 = 3
        self.assertEqual(scores["Yellow"].match_points, 3)
        # Purple: Bye + Win + Draw = 1 + 2 + 1 = 4
        self.assertEqual(scores["Purple"].match_points, 4)

        # Verify that all teams played the correct number of matches
        self.assertEqual(scores["Red"].match_count, 2)  # Played 2, bye 1
        self.assertEqual(scores["Blue"].match_count, 3)  # Played all 3
        self.assertEqual(scores["Green"].match_count, 3)  # Played all 3
        self.assertEqual(scores["Yellow"].match_count, 2)  # Played 2, bye 1
        self.assertEqual(scores["Purple"].match_count, 2)  # Played 2, bye 1

    def test_forfeit_results(self):
        """Test handling of forfeit results in tournament structure."""
        tournament = (
            TournamentBuilder()
            .league(
                "Test League",
                "TL",
                "team",
                rating_type="classical",
                theme="blue",
                pairing_type="swiss-dutch",
            )
            .season("TL", "Test Season", rounds=1, boards=2)
            .team("Team 1", "T1P1", "T1P2")
            .team("Team 2", "T2P1", "T2P2")
            .round(1)
            # Team 1 wins 2-0: Board 1: T1(white) wins by forfeit, Board 2: T1(black) wins
            .match("Team 1", "Team 2", "1X-0F", "0-1")
            .complete()
            .calculate()
            .build()
        )

        season = tournament.seasons["Test Season"]

        # Get scores
        scores = {
            ts.team.number: ts for ts in TeamScore.objects.filter(team__season=season)
        }

        # Match should be 2-0 win for Team 1
        # Team 1 wins board 1 by forfeit, Team 1 wins board 2
        self.assertEqual(scores[1].match_points, 2)  # Win
        self.assertEqual(scores[2].match_points, 0)  # Loss
        self.assertEqual(scores[1].game_points, 2.0)
        self.assertEqual(scores[2].game_points, 0.0)

    def test_forfeit_win_database_roundtrip(self):
        """Test that forfeit wins are properly saved to DB and converted back."""
        # Create tournament with TournamentBuilder
        tournament = (
            TournamentBuilder()
            .league(
                "Test League",
                "TL",
                "team",
                rating_type="standard",
                team_tiebreak_1="game_points",
                team_tiebreak_2="games_won",
            )
            .season("TL", "Test Season", rounds=1, boards=4)
            # Team A has 4 players
            .team(
                "Team A",
                ("Alice", 2000),
                ("Bob", 1900),
                ("Charlie", 1800),
                ("David", 1700),
            )
            # Team B has only 3 players
            .team("Team B", ("Eve", 1950), ("Frank", 1850), ("Grace", 1750))
            .round(1)
            # Team A wins all 4 boards - provide results from white's perspective
            # Board 1: Alice (Team A, white) beats Eve (Team B, black) = "1-0"
            # Board 2: Frank (Team B, white) loses to Bob (Team A, black) = "0-1"
            # Board 3: Charlie (Team A, white) beats Grace (Team B, black) = "1-0"
            # Board 4: None (Team B, white) forfeits to David (Team A, black) = "0F-1X"
            .match("Team A", "Team B", "1-0", "0-1", "1-0", "0F-1X")
            .complete()
            .calculate()
            .build()
        )

        season = tournament.seasons["Test Season"]

        # Get the teams
        team_a = Team.objects.get(season=season, name="Team A")
        team_b = Team.objects.get(season=season, name="Team B")

        # Verify board pairings were created correctly
        from heltour.tournament.models import TeamPairing, TeamPlayerPairing

        team_pairing = TeamPairing.objects.get(
            round__season=season, white_team=team_a, black_team=team_b
        )

        # Check that 4 board pairings exist
        board_pairings = TeamPlayerPairing.objects.filter(
            team_pairing=team_pairing
        ).order_by("board_number")
        self.assertEqual(board_pairings.count(), 4)

        # Verify board 4 is a forfeit win
        board4 = board_pairings[3]
        self.assertEqual(board4.board_number, 4)

        # Check which side has the player
        self.assertTrue(
            board4.white or board4.black, "Board 4 should have at least one player"
        )
        self.assertEqual(board4.result, "0F-1X")  # Black (Team A) wins by forfeit

        # Convert to tournament structure and back
        tournament_structure = season_to_tournament_structure(season)

        results = tournament_structure.calculate_results()

        # Verify Team A has correct scores
        team_a_result = results[team_a.id]
        self.assertEqual(team_a_result.match_points, 2)  # Won the match
        self.assertEqual(team_a_result.game_points, 4.0)  # Won all 4 boards

        # Calculate tiebreaks
        from heltour.tournament_core.tiebreaks import (
            calculate_games_won,
            calculate_all_tiebreaks,
        )

        # Verify games won tiebreaker
        games_won = calculate_games_won(team_a_result)
        self.assertEqual(games_won, 4)

        # Calculate all tiebreaks to verify game_points tiebreaker
        tiebreak_scores = calculate_all_tiebreaks(results, ["game_points", "games_won"])

        self.assertEqual(tiebreak_scores[team_a.id]["game_points"], 4.0)
        self.assertEqual(tiebreak_scores[team_a.id]["games_won"], 4)
