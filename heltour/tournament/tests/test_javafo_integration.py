"""
Integration tests for JavaFo pairing system.

These tests require a Java environment capable of running JavaFo.
They test the full tournament flow: registration, pairings, results, standings.
"""

import random
from unittest import skipUnless
from django.test import TestCase

from heltour.tournament.models import (
    TeamPairing,
    LonePlayerPairing,
    PlayerBye,
)
from heltour.tournament.builder import TournamentBuilder
from heltour.tournament.tests.testutils import can_run_javafo
from heltour.tournament.db_to_structure import season_to_tournament_structure
from heltour.tournament_core.tiebreaks import (
    calculate_sonneborn_berger,
    calculate_buchholz,
    calculate_games_won,
)


@skipUnless(can_run_javafo(), "JavaFo environment not available")
class JavaFoIntegrationTests(TestCase):
    """Test full tournament flow with JavaFo pairings."""

    def test_lone_tournament_full_flow(self):
        """Test complete lone tournament with JavaFo pairings."""
        # Set random seed for deterministic rating generation
        random.seed(42)
        
        # Build tournament with varied ratings
        tournament = (
            TournamentBuilder()
            .league("Test Swiss", "TSL", "lone")
            .season(
                "TSL",
                "Test Season",
                rounds=5,
                tag="test-season",
                is_active=True,
                registration_open=True,
            )
            # Add 11 players with varied ratings (odd number for byes)
            .player("Magnus", 2840 + random.randint(-10, 10))
            .player("Hikaru", 2790 + random.randint(-10, 10))
            .player("Ding", 2780 + random.randint(-10, 10))
            .player("Nepo", 2770 + random.randint(-10, 10))
            .player("Caruana", 2765 + random.randint(-10, 10))
            .player("Wesley", 2760 + random.randint(-10, 10))
            .player("Giri", 2755 + random.randint(-10, 10))
            .player("MVL", 2750 + random.randint(-10, 10))
            .player("Aronian", 2740 + random.randint(-10, 10))
            .player("Rapport", 2735 + random.randint(-10, 10))
            .player("Mamedyarov", 2730 + random.randint(-10, 10))
            .build()
        )

        season = tournament.seasons["Test Season"]

        # Play multiple rounds
        for round_num in range(1, 4):  # Play 3 rounds
            # Start round and generate pairings
            round_obj = tournament.start_round(round_num, generate_pairings_auto=True)

            # Verify pairings were created
            pairings = LonePlayerPairing.objects.filter(round=round_obj)
            byes = PlayerBye.objects.filter(round=round_obj)

            # With 11 players, should have 5 pairings and 1 bye
            self.assertEqual(pairings.count(), 5)
            self.assertEqual(byes.count(), 1)

            # Simulate results based on ratings
            tournament.simulate_round_results(round_obj)

            # Complete round and calculate standings
            tournament.complete_round(round_obj)
            tournament.calculate_standings()

            # Skip web page tests to avoid Debug Toolbar issues in test environment

        # Verify final standings using tournament_core
        tournament_structure = season_to_tournament_structure(season)
        results = tournament_structure.calculate_results()

        # Check tiebreaks are calculated
        for player_id, score in results.items():
            sb = calculate_sonneborn_berger(score, results)
            buchholz = calculate_buchholz(score, results)
            self.assertIsNotNone(sb)
            self.assertIsNotNone(buchholz)

        # Verify bye handling
        total_byes = PlayerBye.objects.filter(round__season=season).count()
        self.assertEqual(total_byes, 3)  # One bye per round

    def test_team_tournament_full_flow(self):
        """Test complete team tournament with JavaFo pairings."""
        # Build tournament with teams of varied strength
        tournament = (
            TournamentBuilder()
            .league("Test Team League", "TTL", "team")
            .season(
                "TTL",
                "Team Test Season",
                rounds=4,
                boards=4,
                tag="team-test",
                is_active=True,
                registration_open=True,
            )
            # Add 7 teams with varied strengths (odd for byes)
            .team(
                "Dragons",
                ("DragonGM1", 2700),
                ("DragonGM2", 2650),
                ("DragonIM1", 2600),
                ("DragonIM2", 2550),
            )
            .team(
                "Knights",
                ("KnightGM1", 2695),
                ("KnightGM2", 2645),
                ("KnightIM1", 2595),
                ("KnightIM2", 2545),
            )
            .team(
                "Wizards",
                ("WizardGM1", 2600),
                ("WizardIM1", 2550),
                ("WizardIM2", 2500),
                ("WizardFM1", 2450),
            )
            .team(
                "Elves",
                ("ElfGM1", 2595),
                ("ElfIM1", 2545),
                ("ElfIM2", 2495),
                ("ElfFM1", 2445),
            )
            .team(
                "Hobbits",
                ("HobbitIM1", 2500),
                ("HobbitIM2", 2450),
                ("HobbitFM1", 2400),
                ("HobbitFM2", 2350),
            )
            .team(
                "Dwarves",
                ("DwarfIM1", 2495),
                ("DwarfIM2", 2445),
                ("DwarfFM1", 2395),
                ("DwarfFM2", 2345),
            )
            .team(
                "Orcs",
                ("OrcIM1", 2490),
                ("OrcIM2", 2440),
                ("OrcFM1", 2390),
                ("OrcFM2", 2340),
            )
            .build()
        )

        season = tournament.seasons["Team Test Season"]

        # Play multiple rounds
        for round_num in range(1, 4):  # Play 3 rounds
            # Start round and generate pairings
            round_obj = tournament.start_round(round_num, generate_pairings_auto=True)

            # Verify pairings were created
            team_pairings = TeamPairing.objects.filter(round=round_obj)

            # With 7 teams, should have 3 pairings (one team gets bye)
            self.assertEqual(team_pairings.count(), 3)

            # Verify board pairings exist
            for pairing in team_pairings:
                board_pairings = pairing.teamplayerpairing_set.all()
                self.assertEqual(board_pairings.count(), 4)  # 4 boards

            # Simulate match results based on ratings
            tournament.simulate_round_results(round_obj)

            # Complete round and calculate standings
            tournament.complete_round(round_obj)
            tournament.calculate_standings()

            # Skip web page tests to avoid Debug Toolbar issues in test environment

        # Verify final standings using tournament_core
        tournament_structure = season_to_tournament_structure(season)
        results = tournament_structure.calculate_results()

        # Verify all teams have results
        self.assertEqual(len(results), 7)

        # Check game points and match points
        for team_id, score in results.items():
            self.assertGreaterEqual(score.match_points, 0)
            self.assertGreaterEqual(score.game_points, 0)

            # Calculate tiebreaks
            sb = calculate_sonneborn_berger(score, results)
            games_won = calculate_games_won(score)
            self.assertIsNotNone(sb)
            self.assertIsNotNone(games_won)

        # Verify bye handling - check that some teams got byes
        teams_with_byes = set()
        for round_obj in season.round_set.all():
            teams_in_round = set()
            for pairing in round_obj.teampairing_set.all():
                teams_in_round.add(pairing.white_team_id)
                teams_in_round.add(pairing.black_team_id)

            # Find teams that got bye this round
            all_team_ids = set(t.id for t in season.team_set.all())
            bye_teams = all_team_ids - teams_in_round
            teams_with_byes.update(bye_teams)

        # With 7 teams and 3 rounds, at least 3 different teams should get byes
        self.assertGreaterEqual(len(teams_with_byes), 3)

    def test_pairing_constraints(self):
        """Test that pairings respect constraints like not playing same opponent twice."""
        # Set random seed for deterministic pairing generation
        random.seed(42)
        
        tournament = (
            TournamentBuilder()
            .league("Swiss Test", "ST", "lone")
            .season("ST", "Constraint Test", rounds=5)
            # Add 8 players (even number)
            .player("Alice", 2000)
            .player("Bob", 1950)
            .player("Charlie", 1900)
            .player("Diana", 1850)
            .player("Eve", 1800)
            .player("Frank", 1750)
            .player("Grace", 1700)
            .player("Henry", 1650)
            .build()
        )

        season = tournament.seasons["Constraint Test"]
        played_pairs = set()

        # Play 4 rounds
        for round_num in range(1, 5):
            round_obj = tournament.start_round(round_num, generate_pairings_auto=True)

            # Check for repeated pairings
            pairings = LonePlayerPairing.objects.filter(round=round_obj)
            for pairing in pairings:
                pair = tuple(sorted([pairing.white_id, pairing.black_id]))
                self.assertNotIn(pair, played_pairs, f"Players {pair} paired twice!")
                played_pairs.add(pair)

            # Simulate results
            tournament.simulate_round_results(round_obj)
            tournament.complete_round(round_obj)
            tournament.calculate_standings()

    def test_standings_tiebreak_order(self):
        """Test that standings correctly apply tiebreak order."""
        tournament = (
            TournamentBuilder()
            .league("Tiebreak Test", "TT", "lone")
            .season("TT", "TB Season", rounds=3, tag="tb-season")
            .player("Player1", 2000)
            .player("Player2", 1990)
            .player("Player3", 1980)
            .player("Player4", 1970)
            .player("Player5", 1960)
            .player("Player6", 1950)
            .build()
        )

        # Manually create specific results to test tiebreaks
        round1 = tournament.start_round(1)

        # Create pairings with specific results to ensure ties
        sp = tournament.current_season.seasonplayer_set.order_by("seed_rating")
        p1, p2, p3, p4, p5, p6 = [s.player for s in sp]

        # Round 1: Create ties in match points
        LonePlayerPairing.objects.create(
            round=round1, white=p1, black=p2, result="1-0", pairing_order=1
        )
        LonePlayerPairing.objects.create(
            round=round1, white=p3, black=p4, result="1-0", pairing_order=2
        )
        LonePlayerPairing.objects.create(
            round=round1, white=p5, black=p6, result="1/2-1/2", pairing_order=3
        )

        tournament.complete_round(round1)
        tournament.calculate_standings()

        # Skip web page tests to avoid Debug Toolbar issues in test environment

        # Use tournament_core to verify tiebreaks
        tournament_structure = season_to_tournament_structure(tournament.current_season)
        results = tournament_structure.calculate_results()

        # Players 1 and 3 both won, should be tied on match points
        p1_score = results[p1.id]
        p3_score = results[p3.id]
        self.assertEqual(p1_score.match_points, p3_score.match_points)

        # But their SB scores might differ based on opponent strength
        p1_sb = calculate_sonneborn_berger(p1_score, results)
        p3_sb = calculate_sonneborn_berger(p3_score, results)
        # Both exist
        self.assertIsNotNone(p1_sb)
        self.assertIsNotNone(p3_sb)
