"""
Test bye rotation with controlled results.

This test ensures that different teams get byes in different rounds by
controlling the match results to create the desired score groups.
"""

from unittest import skipUnless
from django.test import TestCase

from heltour.tournament.models import TeamPairing, TeamBye
from heltour.tournament.builder import TournamentBuilder
from heltour.tournament.tests.testutils import can_run_javafo


@skipUnless(can_run_javafo(), "JavaFo environment not available")
class ControlledByeRotationTest(TestCase):
    """Test that byes rotate properly with controlled results."""

    def test_bye_rotation_with_controlled_results(self):
        """Test that different teams get byes when we control the results."""
        tournament = (
            TournamentBuilder()
            .league(
                "Controlled League",
                "CL",
                "team",
                rating_type="classical",
                pairing_type="swiss-dutch",
                theme="blue",
            )
            .season("CL", "Controlled Season", rounds=3, boards=1, is_active=True)
            # Create 5 teams with similar ratings
            .team("Team 1", ("Player1", 1600))
            .team("Team 2", ("Player2", 1600))
            .team("Team 3", ("Player3", 1600))
            .team("Team 4", ("Player4", 1600))
            .team("Team 5", ("Player5", 1600))
            .build()
        )

        season = tournament.seasons["Controlled Season"]

        # Round 1: Generate pairings
        round1 = tournament.start_round(1, generate_pairings_auto=True)

        # Manually set results to ensure specific standings
        # We want: Teams 1,2 win, Teams 3,4 lose, Team 5 gets bye
        pairings = list(
            TeamPairing.objects.filter(round=round1).order_by("pairing_order")
        )

        # Set results to create groups: 2 winners, 2 losers, 1 bye
        for pairing in pairings:
            for board_pairing in pairing.teamplayerpairing_set.all():
                # Make the team with lower ID win (Teams 1 and 3 should be playing)
                if pairing.white_team.number < pairing.black_team.number:
                    board_pairing.result = "1-0"  # White wins
                else:
                    board_pairing.result = "0-1"  # Black wins
                board_pairing.save()
            pairing.refresh_points()
            pairing.save()

        # Complete round 1
        round1.is_completed = True
        round1.save()
        season.calculate_scores()

        # Find which team got bye in round 1
        bye_r1 = TeamBye.objects.get(round=round1)
        team_with_bye_r1 = bye_r1.team.number

        # Round 2: Generate pairings
        round2 = tournament.start_round(2, generate_pairings_auto=True)

        # Check which team got bye in round 2
        bye_r2 = TeamBye.objects.get(round=round2)
        team_with_bye_r2 = bye_r2.team.number

        # The key test: different teams should get byes
        self.assertNotEqual(
            team_with_bye_r1,
            team_with_bye_r2,
            f"Team {team_with_bye_r1} got bye in both rounds - Swiss pairing should rotate byes",
        )

    def test_forced_bye_rotation_scenario(self):
        """Create a specific scenario where bye must rotate."""
        tournament = (
            TournamentBuilder()
            .league(
                "Forced Rotation",
                "FR",
                "team",
                rating_type="classical",
                pairing_type="swiss-dutch",
                theme="blue",
            )
            .season("FR", "Forced Season", rounds=2, boards=1, is_active=True)
            # Create 5 teams - use very different ratings to control initial pairings
            .team("Team A", ("PlayerA", 2000))  # Highest rated
            .team("Team B", ("PlayerB", 1900))
            .team("Team C", ("PlayerC", 1800))
            .team("Team D", ("PlayerD", 1700))
            .team("Team E", ("PlayerE", 1600))  # Lowest rated - should get R1 bye
            .build()
        )

        season = tournament.seasons["Forced Season"]

        # Round 1: Let JavaFo pair naturally
        round1 = tournament.start_round(1, generate_pairings_auto=True)

        # Set specific results: higher rated teams win
        for pairing in TeamPairing.objects.filter(round=round1):
            for board_pairing in pairing.teamplayerpairing_set.all():
                # Higher rated team wins
                white_rating = pairing.white_team.seed_rating
                black_rating = pairing.black_team.seed_rating
                if white_rating > black_rating:
                    board_pairing.result = "1-0"
                else:
                    board_pairing.result = "0-1"
                board_pairing.save()
            pairing.refresh_points()
            pairing.save()

        # Complete round 1
        round1.is_completed = True
        round1.save()
        season.calculate_scores()

        # Check who got bye in round 1
        bye_r1 = TeamBye.objects.get(round=round1)
        bye_team_r1 = bye_r1.team

        # After R1, standings should be:
        # Winners: 2 match points
        # Bye: 1 match point
        # Losers: 0 match points

        # Round 2
        round2 = tournament.start_round(2, generate_pairings_auto=True)

        # Check who got bye in round 2
        bye_r2 = TeamBye.objects.get(round=round2)
        bye_team_r2 = bye_r2.team

        # In a 5-team Swiss with proper pairing:
        # - Team that had bye in R1 should play in R2
        # - A different team should get bye in R2
        self.assertNotEqual(
            bye_team_r1.id,
            bye_team_r2.id,
            f"{bye_team_r1.name} got bye in both rounds - this violates Swiss pairing principles",
        )
