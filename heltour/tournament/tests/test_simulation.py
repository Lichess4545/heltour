"""
Tests for the tournament simulation framework.
"""

from django.test import TestCase
from heltour.tournament.db_to_structure import season_to_tournament_structure
from heltour.tournament.builder import TournamentBuilder


class TournamentSimulationTests(TestCase):
    """Demonstrate the clean API for tournament simulation."""

    def test_simple_lone_tournament(self):
        """Demonstrate a simple individual tournament."""
        # Build a tournament with fluent syntax
        tournament = (
            TournamentBuilder()
            .league("Weekend Blitz", "WB", "lone")
            .season("WB", "January 2024", rounds=3)
            .player("Magnus", 2850)
            .player("Hikaru", 2800)
            .player("Ding", 2780)
            .player("Nepo", 2760)
            # Round 1
            .round(1)
            .game("Magnus", "Hikaru", "1-0")
            .game("Ding", "Nepo", "1/2-1/2")
            .complete()
            # Round 2
            .round(2)
            .game("Magnus", "Ding", "1/2-1/2")
            .game("Hikaru", "Nepo", "1-0")
            .complete()
            # Round 3
            .round(3)
            .game("Magnus", "Nepo", "1-0")
            .game("Hikaru", "Ding", "1/2-1/2")
            .complete()
            .calculate()
            .build()
        )

        # Verify standings
        season = tournament.seasons["January 2024"]
        scores = {
            sp.player.lichess_username: sp.loneplayerscore
            for sp in season.seasonplayer_set.all()
        }

        # Magnus: 2.5/3 (W, D, W)
        self.assertEqual(scores["Magnus"].points, 2.5)
        # Hikaru: 1.5/3 (L, W, D)
        self.assertEqual(scores["Hikaru"].points, 1.5)
        # Ding: 1.5/3 (D, D, D)
        self.assertEqual(scores["Ding"].points, 1.5)
        # Nepo: 0.5/3 (D, L, L)
        self.assertEqual(scores["Nepo"].points, 0.5)

    def test_simple_team_tournament(self):
        """Demonstrate a simple team tournament."""
        # Build a team tournament
        tournament = (
            TournamentBuilder()
            .league("Team Battle", "TB", "team")
            .season("TB", "Spring 2024", rounds=2, boards=4)
            # Teams with players
            .team(
                "Dragons",
                "DragonPlayer1",
                "DragonPlayer2",
                "DragonPlayer3",
                "DragonPlayer4",
            )
            .team(
                "Knights",
                "KnightPlayer1",
                "KnightPlayer2",
                "KnightPlayer3",
                "KnightPlayer4",
            )
            .team(
                "Wizards",
                "WizardPlayer1",
                "WizardPlayer2",
                "WizardPlayer3",
                "WizardPlayer4",
            )
            # Round 1
            .round(1)
            # Dragons win 2.5-1.5
            # Board 1: Dragons(W) win, Board 2: Knights(W) lose, Board 3: draw, Board 4: Knights(W) lose
            .match("Dragons", "Knights", "1-0", "0-1", "1/2-1/2", "0-1")
            .complete()
            # Round 2
            .round(2)
            # Knights win 2.5-1.5
            # Board 1: Knights(W) win, Board 2: Wizards(W) lose, Board 3: Knights(W) lose, Board 4: draw
            .match("Knights", "Wizards", "1-0", "0-1", "0-1", "1/2-1/2")
            .complete()
            .calculate()
            .build()
        )

        # Verify team standings
        season = tournament.seasons["Spring 2024"]
        scores = {team.name: team.teamscore for team in season.team_set.all()}

        # Note: Teams get automatic byes when they don't play in a round
        # Round 1: Dragons beat Knights, Wizards gets bye
        # Round 2: Knights beat Wizards, Dragons gets bye

        # Dragons: Win vs Knights (2), Bye (1) = 3 match points
        self.assertEqual(scores["Dragons"].match_points, 3)
        self.assertEqual(scores["Dragons"].game_points, 5.5)  # 3.5 + 2.0 (bye)

        # Knights: Loss vs Dragons (0), Win vs Wizards (2) = 2 match points
        self.assertEqual(scores["Knights"].match_points, 2)
        self.assertEqual(scores["Knights"].game_points, 3.0)  # 0.5 + 2.5

        # Wizards: Bye round 1 (1), Loss vs Knights (0) = 1 match points
        self.assertEqual(scores["Wizards"].match_points, 1)
        self.assertEqual(scores["Wizards"].game_points, 3.5)  # 2.0 (bye) + 1.5

    def test_alternative_api_style(self):
        """Show alternative API usage for more control."""
        # Create builder and set up tournament
        builder = TournamentBuilder()
        builder.league("Classical Masters", "CM", "lone")
        builder.season("CM", "Final Stage", rounds=2)

        # Add players
        builder.player("Carlsen", 2830)
        builder.player("Caruana", 2800)

        # Build database objects
        builder.build()

        # Play rounds with explicit control using start_round
        round1 = builder.start_round(1)

        # Manual pairing - get players
        from heltour.tournament.models import Player, LonePlayerPairing

        carlsen = Player.objects.get(lichess_username="Carlsen")
        caruana = Player.objects.get(lichess_username="Caruana")

        # Create pairing manually
        LonePlayerPairing.objects.create(
            round=round1, white=carlsen, black=caruana, result="1-0", pairing_order=1
        )
        builder.complete_round(round1)

        round2 = builder.start_round(2)
        LonePlayerPairing.objects.create(
            round=round2,
            white=caruana,
            black=carlsen,
            result="1/2-1/2",
            pairing_order=1,
        )
        builder.complete_round(round2)

        builder.calculate_standings()

        # Verify
        season = builder.current_season
        scores = {
            sp.player.lichess_username: sp.loneplayerscore
            for sp in season.seasonplayer_set.all()
        }
        self.assertEqual(scores["Carlsen"].points, 1.5)
        self.assertEqual(scores["Caruana"].points, 0.5)

    def test_simulation_with_db_to_structure(self):
        """Test that simulation properly populates database for db_to_structure."""
        # Build a comprehensive team tournament
        tournament = (
            TournamentBuilder()
            .league("Champions League", "CL", "team")
            .season("CL", "2024 Finals", rounds=3, boards=2)
            # Create 4 teams
            .team("Alpha", "AlphaBoard1", "AlphaBoard2")
            .team("Beta", "BetaBoard1", "BetaBoard2")
            .team("Gamma", "GammaBoard1", "GammaBoard2")
            .team("Delta", "DeltaBoard1", "DeltaBoard2")
            # Round 1: Alpha vs Beta, Gamma vs Delta
            .round(1)
            # Alpha wins 2-0: Board 1: Alpha(W) wins, Board 2: Beta(W) loses
            .match("Alpha", "Beta", "1-0", "0-1")
            # Draw 1-1
            .match("Gamma", "Delta", "1/2-1/2", "1/2-1/2")
            .complete()
            # Round 2: Alpha vs Gamma, Beta vs Delta
            .round(2)
            # Alpha wins 1.5-0.5: Board 1: Alpha(W) wins, Board 2: draw
            .match("Alpha", "Gamma", "1-0", "1/2-1/2")
            # Delta wins 2-0: Board 1: Beta(W) loses, Board 2: Delta(W) wins
            .match("Beta", "Delta", "0-1", "1-0")
            .complete()
            # Round 3: Alpha vs Delta, Beta vs Gamma
            .round(3)
            # Draw 1-1
            .match("Alpha", "Delta", "1/2-1/2", "1/2-1/2")
            # Beta wins 2-0: Board 1: Beta(W) wins, Board 2: Gamma(W) loses
            .match("Beta", "Gamma", "1-0", "0-1")
            .complete()
            .calculate()
            .build()
        )

        # Get the season
        season = tournament.seasons["2024 Finals"]

        # Convert to tournament structure
        tournament_structure = season_to_tournament_structure(season)

        # Calculate results using tournament_core
        results = tournament_structure.calculate_results()

        # Verify the structure was created correctly
        self.assertEqual(len(tournament_structure.competitors), 4)
        self.assertEqual(len(tournament_structure.rounds), 3)

        # Get team IDs for verification
        teams = {team.name: team for team in season.team_set.all()}

        # Verify match points from tournament_core
        # Alpha: 2 wins, 1 draw (2 + 2 + 1) = 5 match points
        self.assertEqual(results[teams["Alpha"].id].match_points, 5)
        # Beta: 1 win, 2 losses (0 + 0 + 2) = 2 match points
        self.assertEqual(results[teams["Beta"].id].match_points, 2)
        # Gamma: 1 draw, 2 losses (1 + 0 + 0) = 1 match point
        self.assertEqual(results[teams["Gamma"].id].match_points, 1)
        # Delta: 1 win, 2 draws (1 + 2 + 1) = 4 match points
        self.assertEqual(results[teams["Delta"].id].match_points, 4)

        # Verify game points (no byes in this tournament - all teams play all rounds)
        self.assertEqual(results[teams["Alpha"].id].game_points, 4.5)  # 2 + 1.5 + 1
        self.assertEqual(results[teams["Beta"].id].game_points, 2.0)  # 0 + 0 + 2
        self.assertEqual(results[teams["Gamma"].id].game_points, 1.5)  # 1 + 0.5 + 0
        self.assertEqual(results[teams["Delta"].id].game_points, 4.0)  # 1 + 2 + 1

        # Verify tiebreaks can be calculated from the results
        from heltour.tournament_core.tiebreaks import calculate_sonneborn_berger

        alpha_sb = calculate_sonneborn_berger(results[teams["Alpha"].id], results)
        self.assertIsNotNone(alpha_sb)
        self.assertGreater(alpha_sb, 0)

        # Verify database scores match
        db_scores = {team.name: team.teamscore for team in season.team_set.all()}
        for team_name, team in teams.items():
            self.assertEqual(
                db_scores[team_name].match_points,
                results[team.id].match_points,
                f"{team_name} match points mismatch between DB and structure",
            )

    def test_lone_tournament_with_byes(self):
        """Test individual tournament with byes using db_to_structure."""
        # Odd number of players to force byes
        tournament = (
            TournamentBuilder()
            .league("Open Swiss", "OS", "lone")
            .season("OS", "March 2024", rounds=3)
            .player("Alice", 2000)
            .player("Bob", 1950)
            .player("Charlie", 1900)
            .player("Diana", 1850)
            .player("Eve", 1800)
            # Round 1: 5 players, so one gets a bye
            .round(1)
            .game("Alice", "Bob", "1-0")
            .game("Charlie", "Diana", "1/2-1/2")
            # Eve gets automatic bye
            .complete()
            # Round 2
            .round(2)
            .game("Eve", "Alice", "0-1")
            .game("Bob", "Charlie", "1-0")
            # Diana gets bye
            .complete()
            # Round 3
            .round(3)
            .game("Alice", "Diana", "1-0")
            .game("Bob", "Eve", "1/2-1/2")
            # Charlie gets bye
            .complete()
            .calculate()
            .build()
        )

        season = tournament.seasons["March 2024"]

        # Convert and verify structure
        tournament_structure = season_to_tournament_structure(season)
        results = tournament_structure.calculate_results()

        # Get player IDs
        players = {
            sp.player.lichess_username: sp.player.id
            for sp in season.seasonplayer_set.all()
        }

        # Individual tournaments use match scoring (2-1-0) not game scoring
        # Alice: 3 wins = 6 match points (3 * 2)
        self.assertEqual(results[players["Alice"]].match_points, 6)
        # Bob: 1 win (2 pts), 1 draw (1 pt), 1 loss (0 pt) = 3 match points
        self.assertEqual(results[players["Bob"]].match_points, 3)
        # Charlie: 1 draw (1 pt), 1 loss (0 pt), 1 bye (1 pt) = 2 match points
        self.assertEqual(results[players["Charlie"]].match_points, 2)
        # Diana: 1 draw (1 pt), 1 loss (0 pt), 1 bye (1 pt) = 2 match points
        self.assertEqual(results[players["Diana"]].match_points, 2)
        # Eve: 1 draw (1 pt), 1 loss (0 pt), 1 bye (1 pt) = 2 match points
        self.assertEqual(results[players["Eve"]].match_points, 2)
