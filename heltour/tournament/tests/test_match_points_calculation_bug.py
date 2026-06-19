"""
Unit test for match points calculation bug.

This test verifies that the DB to tournament structure conversion
correctly calculates match points for teams. The test creates its own
data and does not depend on external seed data.
"""

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from heltour.tournament.models import (
    League,
    Season,
    Round,
    Team,
    TeamMember,
    Player,
    TeamPairing,
    TeamPlayerPairing,
    TeamScore,
    SeasonPlayer,
)
from heltour.tournament.db_to_structure import season_to_tournament_structure


class MatchPointsCalculationTest(TestCase):
    """Test that match points are calculated correctly during DB conversion."""

    def setUp(self):
        """Set up test data that reproduces the match points bug."""
        # Create league
        self.league = League.objects.create(
            name="Test League",
            tag="TEST",
            competitor_type="team",
            rating_type="classical",
            team_tiebreak_1="game_points",
            team_tiebreak_2="eggsb",
            team_tiebreak_3="buchholz",
            team_tiebreak_4="",
        )

        # Create season
        self.season = Season.objects.create(
            league=self.league,
            name="Test Season",
            tag="test",
            rounds=2,
            boards=4,
            start_date=timezone.now() - timedelta(days=10),
            round_duration=timedelta(days=7),
            is_active=True,
            is_completed=False,
        )

        # Create rounds (initially not completed to avoid score calculation during setup)
        self.round1 = Round.objects.create(
            season=self.season,
            number=1,
            start_date=timezone.now() - timedelta(days=10),
            end_date=timezone.now() - timedelta(days=3),
            is_completed=False,
            publish_pairings=True,
        )

        self.round2 = Round.objects.create(
            season=self.season,
            number=2,
            start_date=timezone.now() - timedelta(days=3),
            end_date=timezone.now() + timedelta(days=4),
            is_completed=False,
            publish_pairings=True,
        )

        # Create players
        self.players = {}
        for i in range(1, 25):
            player = Player.objects.create(
                lichess_username=f"Player{i}", rating=1800 - (i * 10)
            )
            self.players[f"Player{i}"] = player

        # Create teams
        self.storm = Team.objects.create(
            season=self.season, name="Storm Tacticians", number=1
        )
        self.quantum = Team.objects.create(
            season=self.season, name="Quantum Lions", number=2
        )
        self.swift = Team.objects.create(
            season=self.season, name="Swift Bishops", number=3
        )
        self.thunder = Team.objects.create(
            season=self.season, name="Thunder Masters", number=4
        )
        self.royal = Team.objects.create(
            season=self.season, name="Royal Knights", number=5
        )
        self.fire = Team.objects.create(
            season=self.season, name="Fire Dragons", number=6
        )

        # Create team members (4 boards each)
        teams_players = [
            (self.storm, ["Player1", "Player2", "Player3", "Player4"]),
            (self.quantum, ["Player5", "Player6", "Player7", "Player8"]),
            (self.swift, ["Player9", "Player10", "Player11", "Player12"]),
            (self.thunder, ["Player13", "Player14", "Player15", "Player16"]),
            (self.royal, ["Player17", "Player18", "Player19", "Player20"]),
            (self.fire, ["Player21", "Player22", "Player23", "Player24"]),
        ]

        for team, player_names in teams_players:
            for board, player_name in enumerate(player_names, 1):
                player = self.players[player_name]
                SeasonPlayer.objects.create(season=self.season, player=player)
                TeamMember.objects.create(team=team, player=player, board_number=board)

        # Create team scores (will be calculated by the test)
        for team in [
            self.storm,
            self.quantum,
            self.swift,
            self.thunder,
            self.royal,
            self.fire,
        ]:
            TeamScore.objects.create(team=team)

        # Create the specific match results that demonstrate the bug
        self._create_match_results()

    def _create_match_results(self):
        """Create the specific match results that demonstrate the bug."""
        # Round 1: Storm (BLACK) vs Swift (WHITE) - Swift wins 2.5-1.5
        # With board alternation: Swift is white team, Storm is black team
        tp1 = TeamPairing.objects.create(
            white_team=self.swift,
            black_team=self.storm,
            round=self.round1,
            pairing_order=1,
            white_points=0,  # Will be calculated from board results
            black_points=0,  # Will be calculated from board results
        )

        # Board results for this match with alternation
        # Board 1: Swift player has white - Anatoly vs Levon
        TeamPlayerPairing.objects.create(
            team_pairing=tp1,
            board_number=1,
            white=self.players["Player9"],   # Swift (Anatoly)
            black=self.players["Player1"],   # Storm (Levon)
            result="1/2-1/2",  # Draw
        )
        # Board 2: Colors alternate - Swift player has black - Sergey vs Jan-Krzysztof
        TeamPlayerPairing.objects.create(
            team_pairing=tp1,
            board_number=2,
            white=self.players["Player2"],   # Storm (Jan-Krzysztof)
            black=self.players["Player10"],  # Swift (Sergey)
            result="0-1",  # Swift wins (black wins)
        )
        # Board 3: Swift player has white - Anish vs Alireza
        TeamPlayerPairing.objects.create(
            team_pairing=tp1,
            board_number=3,
            white=self.players["Player11"],  # Swift (Anish)
            black=self.players["Player3"],   # Storm (Alireza)
            result="1-0",  # Swift wins
        )
        # Board 4: Swift player has black (alternation), but forfeits
        # Storm's Sergey wins by forfeit
        TeamPlayerPairing.objects.create(
            team_pairing=tp1,
            board_number=4,
            white=self.players["Player4"],   # Storm (Sergey)
            black=self.players["Player12"],  # Swift forfeits
            result="1X-0F",  # White wins by forfeit (Storm wins)
        )

        # Update team pairing points after creating board results
        tp1.refresh_points()
        tp1.save()

        # Round 1: Quantum (WHITE) vs Royal (BLACK) - Quantum wins 2.5-1.5
        # With board alternation
        tp2 = TeamPairing.objects.create(
            white_team=self.quantum,
            black_team=self.royal,
            round=self.round1,
            pairing_order=2,
            white_points=0,
            black_points=0,
        )

        # Board results for quantum vs royal with alternation
        # Board 1: Quantum player has white
        TeamPlayerPairing.objects.create(
            team_pairing=tp2,
            board_number=1,
            white=self.players["Player5"],     # Quantum
            black=self.players["Player17"],    # Royal
            result="1-0",
        )
        # Board 2: Colors alternate - Quantum player has black
        # Teimour_RoyalKnights (white) beats Fabiano_QuantumLions (black)
        TeamPlayerPairing.objects.create(
            team_pairing=tp2,
            board_number=2,
            white=self.players["Player18"],    # Royal (Teimour)
            black=self.players["Player6"],     # Quantum (Fabiano)
            result="1-0",  # Royal wins
        )
        # Board 3: Quantum player has white
        # Teimour_QuantumLions (white) beats Anatoly_RoyalKnights (black)
        TeamPlayerPairing.objects.create(
            team_pairing=tp2,
            board_number=3,
            white=self.players["Player7"],     # Quantum (Teimour)
            black=self.players["Player19"],    # Royal (Anatoly)
            result="1-0",  # Quantum wins
        )
        # Board 4: Quantum wins by forfeit
        # Sergey_QuantumLions gets forfeit win
        TeamPlayerPairing.objects.create(
            team_pairing=tp2,
            board_number=4,
            white=self.players["Player20"],    # Royal forfeits
            black=self.players["Player8"],     # Quantum (Sergey)
            result="0F-1X",  # Quantum wins by forfeit
        )

        tp2.refresh_points()
        tp2.save()

        # Round 2: Storm (WHITE) vs Thunder (BLACK) - Storm wins 3.0-1.0
        # With board alternation
        tp3 = TeamPairing.objects.create(
            white_team=self.storm,
            black_team=self.thunder,
            round=self.round2,
            pairing_order=1,
            white_points=0,
            black_points=0,
        )

        # Board results for this match with alternation
        # Board 1: Storm player has white
        TeamPlayerPairing.objects.create(
            team_pairing=tp3,
            board_number=1,
            white=self.players["Player1"],     # Storm
            black=self.players["Player13"],    # Thunder
            result="1-0",
        )
        # Board 2: Colors alternate - Storm player has black
        TeamPlayerPairing.objects.create(
            team_pairing=tp3,
            board_number=2,
            white=self.players["Player14"],    # Thunder
            black=self.players["Player2"],     # Storm
            result="0-1",  # Storm wins
        )
        # Board 3: Storm player has white
        TeamPlayerPairing.objects.create(
            team_pairing=tp3,
            board_number=3,
            white=self.players["Player3"],     # Storm
            black=self.players["Player15"],    # Thunder
            result="1-0",
        )
        # Board 4: Storm player has black
        TeamPlayerPairing.objects.create(
            team_pairing=tp3,
            board_number=4,
            white=self.players["Player16"],    # Thunder
            black=self.players["Player4"],     # Storm
            result="1-0",  # Thunder wins
        )

        tp3.refresh_points()
        tp3.save()

        # Round 2: Fire (WHITE) vs Quantum (BLACK) - Fire wins 2.5-1.5
        # Based on front-end data showing board alternation
        tp4 = TeamPairing.objects.create(
            white_team=self.fire,
            black_team=self.quantum,
            round=self.round2,
            pairing_order=2,
            white_points=0,
            black_points=0,
        )

        # Board results matching front-end data
        # Board 1: Fire player has white - Vladimir_FireDragons beats Shakhriyar_QuantumLions
        TeamPlayerPairing.objects.create(
            team_pairing=tp4,
            board_number=1,
            white=self.players["Player21"],  # Fire (Vladimir)
            black=self.players["Player5"],    # Quantum (Shakhriyar)
            result="1-0",
        )
        # Board 2: Fire player has black - Richárd_FireDragons beats Fabiano_QuantumLions  
        TeamPlayerPairing.objects.create(
            team_pairing=tp4,
            board_number=2,
            white=self.players["Player6"],    # Quantum (Fabiano)
            black=self.players["Player22"],   # Fire (Richárd)
            result="0-1",  # Fire wins (black wins)
        )
        # Board 3: Fire player has white - Sam_FireDragons draws Teimour_QuantumLions
        TeamPlayerPairing.objects.create(
            team_pairing=tp4,
            board_number=3,
            white=self.players["Player23"],   # Fire (Sam)
            black=self.players["Player7"],    # Quantum (Teimour)
            result="1/2-1/2",  # Draw
        )
        # Board 4: Fire player has black - Anish_FireDragons loses to Sergey_QuantumLions
        TeamPlayerPairing.objects.create(
            team_pairing=tp4,
            board_number=4,
            white=self.players["Player8"],    # Quantum (Sergey)
            black=self.players["Player24"],   # Fire (Anish)
            result="1-0",  # Quantum wins
        )

        tp4.refresh_points()
        tp4.save()

        # Now mark rounds as completed to trigger score calculation
        self.round1.is_completed = True
        self.round1.save()
        self.round2.is_completed = True
        self.round2.save()

    def test_match_points_calculation_bug(self):
        """Test the specific match points calculation bug.

        Expected results based on the match setup:
        - Storm: 1 win (vs Thunder 3.0-1.0), 1 loss (vs Swift 1.5-2.5) → 2 match points
        - Quantum: 1 win (vs Royal 3.0-1.0), 1 loss (vs Fire 1.5-2.5) → 2 match points
        """

        # Convert to tournament structure and calculate results
        tournament = season_to_tournament_structure(self.season)
        results = tournament.calculate_results()

        storm_actual = results[self.storm.id].match_points
        quantum_actual = results[self.quantum.id].match_points

        # Create debug info for when the test fails
        debug_info = f"""
Match results summary:
Storm Tacticians:
  Round 1: vs Swift Bishops (BLACK) → 1.5-2.5 LOSS
  Round 2: vs Thunder Masters (WHITE) → 3.0-1.0 WIN
  Expected: 1 win = 2 match points
  Actual: {storm_actual} match points

Quantum Lions:  
  Round 1: vs Royal Knights (WHITE) → 2.5-1.5 WIN
  Round 2: vs Fire Dragons (BLACK) → 1.0-3.0 LOSS
  Expected: 1 win = 2 match points
  Actual: {quantum_actual} match points
"""

        # Assert correct match points
        self.assertEqual(
            storm_actual,
            2,
            f"Storm Tacticians has 1 win and should have 2 match points, got {storm_actual}\n{debug_info}",
        )

        self.assertEqual(
            quantum_actual,
            2,
            f"Quantum Lions has 1 win and should have 2 match points, got {quantum_actual}\n{debug_info}",
        )

    def test_django_data_consistency(self):
        """Verify that the Django data setup is correct."""
        # Verify Storm's matches
        storm_white_pairings = TeamPairing.objects.filter(
            white_team=self.storm, round__is_completed=True
        )
        storm_black_pairings = TeamPairing.objects.filter(
            black_team=self.storm, round__is_completed=True
        )

        self.assertEqual(
            storm_white_pairings.count(), 1, "Storm should have 1 match as white"
        )
        self.assertEqual(
            storm_black_pairings.count(), 1, "Storm should have 1 match as black"
        )

        # Storm as white: vs Thunder, won 3.0-1.0
        white_match = storm_white_pairings.first()
        self.assertEqual(white_match.black_team, self.thunder)
        self.assertEqual(white_match.white_points, 3.0)
        self.assertEqual(white_match.black_points, 1.0)

        # Storm as black: vs Swift
        black_match = storm_black_pairings.first()
        self.assertEqual(black_match.white_team, self.swift)
        
        # Check actual calculated values
        self.assertEqual(black_match.white_points, 2.5)  
        self.assertEqual(black_match.black_points, 1.5)

        # Verify Quantum's matches
        quantum_white_pairings = TeamPairing.objects.filter(
            white_team=self.quantum, round__is_completed=True
        )
        quantum_black_pairings = TeamPairing.objects.filter(
            black_team=self.quantum, round__is_completed=True
        )

        self.assertEqual(
            quantum_white_pairings.count(), 1, "Quantum should have 1 match as white"
        )
        self.assertEqual(
            quantum_black_pairings.count(), 1, "Quantum should have 1 match as black"
        )

        # Quantum as white: vs Royal, won 3-1
        white_match = quantum_white_pairings.first()
        self.assertEqual(white_match.black_team, self.royal)
        
        self.assertEqual(white_match.white_points, 3.0)
        self.assertEqual(white_match.black_points, 1.0)

        # Quantum as black: vs Fire, lost 1.5-2.5
        black_match = quantum_black_pairings.first()
        self.assertEqual(black_match.white_team, self.fire)
        
        self.assertEqual(black_match.white_points, 2.5)
        self.assertEqual(black_match.black_points, 1.5)

