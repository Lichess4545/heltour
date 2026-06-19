"""
Test team bye handling in pairing generation.

This test isolates the issue with odd numbers of teams in JavaFo pairings.
"""

from unittest import skipUnless
from django.test import TestCase

from heltour.tournament.models import TeamPairing, TeamBye, TeamScore
from heltour.tournament.db_to_structure import season_to_tournament_structure
from heltour.tournament.builder import TournamentBuilder
from heltour.tournament.tests.testutils import can_run_javafo


@skipUnless(can_run_javafo(), "JavaFo environment not available")
class TeamByeHandlingTest(TestCase):
    """Test that team byes are handled correctly in pairing generation."""

    def test_minimal_team_bye_scenario(self):
        """Test pairing generation with 3 teams (one must get a bye)."""
        tournament = (
            TournamentBuilder()
            .league(
                "Test Team League",
                "TTL",
                "team",
                rating_type="classical",
                pairing_type="swiss-dutch",
                theme="blue",
            )
            .season("TTL", "Test Season", rounds=2, boards=2, is_active=True)
            # Create 3 teams with different ratings
            .team("Team 1", ("Team1Player1", 2000), ("Team1Player2", 1950))
            .team("Team 2", ("Team2Player1", 1950), ("Team2Player2", 1900))
            .team("Team 3", ("Team3Player1", 1900), ("Team3Player2", 1850))
            .build()
        )

        season = tournament.seasons["Test Season"]

        # Create round and generate pairings
        round1 = tournament.start_round(1, generate_pairings_auto=True)

        # Check what was created
        pairings = TeamPairing.objects.filter(round=round1)

        # With 3 teams, we expect 1 pairing (2 teams play, 1 gets bye)
        self.assertEqual(pairings.count(), 1, "Should have 1 pairing with 3 teams")

        # Check which teams played
        teams_that_played = set()
        for pairing in pairings:
            teams_that_played.add(pairing.white_team_id)
            teams_that_played.add(pairing.black_team_id)

        # Check TeamBye was created
        team_byes = TeamBye.objects.filter(round=round1)
        self.assertEqual(team_byes.count(), 1, "Should have 1 TeamBye record")

        # The TeamBye should be for the team that didn't play
        bye_team = team_byes.first().team
        self.assertNotIn(
            bye_team.id, teams_that_played, "Team with bye should not have a pairing"
        )

        # Mark round as completed
        round1.is_completed = True
        round1.save()

        # Convert to tournament structure and verify bye handling
        tournament_structure = season_to_tournament_structure(season)
        results = tournament_structure.calculate_results()

        # Team with bye should have 1 match point
        bye_team_id = team_byes.first().team_id
        score = results[bye_team_id]
        self.assertEqual(
            score.match_points, 1, "Team with bye should have 1 match point"
        )
        self.assertEqual(
            score.game_points,
            1,
            "Team with bye should have 1 game point (0.5 per board)",
        )

    def test_five_teams_two_rounds(self):
        """Test multiple rounds with 5 teams (one gets bye each round)."""
        tournament = (
            TournamentBuilder()
            .league(
                "Five Team League",
                "FTL",
                "team",
                rating_type="classical",
                pairing_type="swiss-dutch",
                theme="blue",
            )
            .season("FTL", "Five Team Season", rounds=3, boards=1, is_active=True)
            # Create 5 teams with single boards
            .team("Team A", ("PlayerA", 2200))
            .team("Team B", ("PlayerB", 2150))
            .team("Team C", ("PlayerC", 2100))
            .team("Team D", ("PlayerD", 2050))
            .team("Team E", ("PlayerE", 2000))
            .build()
        )

        season = tournament.seasons["Five Team Season"]

        # Play two rounds
        teams_with_byes_by_round = []

        for round_num in range(1, 3):
            # Generate pairings for the round
            round_obj = tournament.start_round(round_num, generate_pairings_auto=True)

            # Check pairings
            pairings = TeamPairing.objects.filter(round=round_obj)

            teams_that_played = set()
            for p in pairings:
                teams_that_played.add(p.white_team_id)
                teams_that_played.add(p.black_team_id)

            # Check team byes
            team_byes = TeamBye.objects.filter(round=round_obj)
            self.assertEqual(
                team_byes.count(), 1, f"Round {round_num} should have 1 TeamBye"
            )

            teams_with_bye = set(tb.team_id for tb in team_byes)
            teams_with_byes_by_round.append(teams_with_bye)

            self.assertEqual(
                pairings.count(), 2, f"Round {round_num} should have 2 pairings"
            )
            self.assertEqual(
                len(teams_with_bye), 1, f"Round {round_num} should have 1 team with bye"
            )

            # Complete the round
            tournament.complete_round(round_obj)

        # Check that different teams got byes in different rounds (Swiss principle)
        if len(teams_with_byes_by_round) >= 2:
            # JavaFo should try to give different teams byes
            self.assertNotEqual(
                teams_with_byes_by_round[0],
                teams_with_byes_by_round[1],
                "Different teams should get byes in different rounds (Swiss principle)",
            )

    def test_seven_teams_swiss(self):
        """Test JavaFo pairing with 7 teams (was causing NullPointerException)."""
        # Build tournament with 7 teams
        builder = (
            TournamentBuilder()
            .league(
                "Seven Team League",
                "STL",
                "team",
                rating_type="classical",
                pairing_type="swiss-dutch",
                theme="blue",
            )
            .season("STL", "Seven Team Season", rounds=3, boards=2, is_active=True)
        )

        # Add 7 teams
        for i in range(7):
            team_name = f"Team {i+1}"
            player1 = (f"{team_name}_P1", 2000 - i * 30)
            player2 = (f"{team_name}_P2", 1980 - i * 30)
            builder.team(team_name, player1, player2)

        tournament = builder.build()
        season = tournament.seasons["Seven Team Season"]

        # Generate first round pairings
        round1 = tournament.start_round(1, generate_pairings_auto=True)

        # Check results
        pairings = TeamPairing.objects.filter(round=round1)
        team_byes = TeamBye.objects.filter(round=round1)

        # With 7 teams: 3 pairings, 1 bye
        self.assertEqual(pairings.count(), 3, "Should have 3 pairings with 7 teams")
        self.assertEqual(team_byes.count(), 1, "Should have 1 team bye with 7 teams")

        # Verify all teams are accounted for
        teams_in_pairings = set()
        for p in pairings:
            teams_in_pairings.add(p.white_team_id)
            teams_in_pairings.add(p.black_team_id)

        teams_with_bye = set(tb.team_id for tb in team_byes)

        all_team_ids = set(season.team_set.values_list("id", flat=True))
        accounted_teams = teams_in_pairings | teams_with_bye

        self.assertEqual(
            all_team_ids,
            accounted_teams,
            "All teams should either have a pairing or a bye",
        )

        # Test that we can convert to tournament structure without errors
        # (This was failing with NullPointerException in JavaFo)
        tournament_structure = season_to_tournament_structure(season)
        self.assertIsNotNone(tournament_structure)

    def test_manual_pairing_with_bye(self):
        """Test that manual match creation also handles byes correctly."""
        tournament = (
            TournamentBuilder()
            .league(
                "Manual Bye League",
                "MBL",
                "team",
                rating_type="classical",
                pairing_type="swiss-dutch",
                theme="blue",
            )
            .season("MBL", "Manual Season", rounds=1, boards=2)
            .team("Alpha", "A1", "A2")
            .team("Beta", "B1", "B2")
            .team("Gamma", "G1", "G2")
            .round(1)
            .match("Alpha", "Beta", "1-0", "1/2-1/2")  # Alpha wins 1.5-0.5
            # Gamma gets automatic bye
            .complete()
            .calculate()
            .build()
        )

        season = tournament.seasons["Manual Season"]

        # Check that TeamBye was created for Gamma
        team_byes = TeamBye.objects.filter(round__season=season)
        self.assertEqual(team_byes.count(), 1, "Should have 1 TeamBye for Gamma")

        bye_team = team_byes.first().team
        self.assertEqual(bye_team.name, "Gamma", "Gamma should have the bye")

        # Verify scores
        scores = {
            ts.team.name: ts for ts in TeamScore.objects.filter(team__season=season)
        }

        self.assertEqual(scores["Alpha"].match_points, 2)  # Win
        self.assertEqual(scores["Beta"].match_points, 0)  # Loss
        self.assertEqual(scores["Gamma"].match_points, 1)  # Bye
        self.assertEqual(scores["Gamma"].game_points, 1.0)  # Half points for bye
