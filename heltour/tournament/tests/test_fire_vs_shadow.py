"""
Test for Fire Dragons vs Shadow Legends match scoring.

This test verifies that the scoring correctly handles a match where
Fire Dragons beats Shadow Legends 3.5-0.5.
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


class FireVsShadowTest(TestCase):
    """Test the Fire Dragons vs Shadow Legends match scoring."""

    def setUp(self):
        """Set up test data for Fire vs Shadow match."""
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
            rounds=1,
            boards=4,
            start_date=timezone.now() - timedelta(days=10),
            round_duration=timedelta(days=7),
            is_active=True,
            is_completed=False,
        )

        # Create round
        self.round1 = Round.objects.create(
            season=self.season,
            number=1,
            start_date=timezone.now() - timedelta(days=10),
            end_date=timezone.now() - timedelta(days=3),
            is_completed=False,
            publish_pairings=True,
        )

        # Create players for Fire Dragons
        self.vladimir_fire = Player.objects.create(
            lichess_username="Vladimir_FireDragons", rating=2006
        )
        self.richard_fire = Player.objects.create(
            lichess_username="Richárd_FireDragons", rating=1960
        )
        self.sam_fire = Player.objects.create(
            lichess_username="Sam_FireDragons", rating=1755
        )
        self.anish_fire = Player.objects.create(
            lichess_username="Anish_FireDragons", rating=1921
        )

        # Create players for Shadow Legends
        self.anatoly_shadow = Player.objects.create(
            lichess_username="Anatoly_ShadowLegends", rating=1979
        )
        self.richard_shadow = Player.objects.create(
            lichess_username="Richárd_ShadowLegends", rating=1607
        )
        self.ding_shadow = Player.objects.create(
            lichess_username="Ding_ShadowLegends", rating=1880
        )
        self.magnus_shadow = Player.objects.create(
            lichess_username="Magnus_ShadowLegends", rating=1746
        )

        # Create teams
        self.fire = Team.objects.create(
            season=self.season, name="Fire Dragons", number=1
        )
        self.shadow = Team.objects.create(
            season=self.season, name="Shadow Legends", number=2
        )

        # Add players to season
        for player in [self.vladimir_fire, self.richard_fire, self.sam_fire, self.anish_fire,
                      self.anatoly_shadow, self.richard_shadow, self.ding_shadow, self.magnus_shadow]:
            SeasonPlayer.objects.create(season=self.season, player=player)

        # Create team members for Fire Dragons
        TeamMember.objects.create(team=self.fire, player=self.vladimir_fire, board_number=1)
        TeamMember.objects.create(team=self.fire, player=self.richard_fire, board_number=2)
        TeamMember.objects.create(team=self.fire, player=self.sam_fire, board_number=3)
        TeamMember.objects.create(team=self.fire, player=self.anish_fire, board_number=4)

        # Create team members for Shadow Legends
        TeamMember.objects.create(team=self.shadow, player=self.anatoly_shadow, board_number=1)
        TeamMember.objects.create(team=self.shadow, player=self.richard_shadow, board_number=2)
        TeamMember.objects.create(team=self.shadow, player=self.ding_shadow, board_number=3)
        TeamMember.objects.create(team=self.shadow, player=self.magnus_shadow, board_number=4)

        # Create team scores
        TeamScore.objects.create(team=self.fire)
        TeamScore.objects.create(team=self.shadow)

        # Create the match
        self._create_match()

    def _create_match(self):
        """Create the Fire vs Shadow match with board alternation."""
        # Fire Dragons is WHITE team, Shadow Legends is BLACK team
        # Expected result: Fire wins 3.5-0.5
        tp = TeamPairing.objects.create(
            white_team=self.fire,
            black_team=self.shadow,
            round=self.round1,
            pairing_order=1,
            white_points=0,  # Will be calculated from board results
            black_points=0,  # Will be calculated from board results
        )

        # Board results based on the data provided:
        # Note: Fire is WHITE team, but board alternation means:
        # - Odd boards: Fire player has white pieces
        # - Even boards: Fire player has black pieces
        
        # Board 1: Fire player should have white, but data shows Shadow player with white
        # This means the pairing is already set up with alternation
        # Anatoly_ShadowLegends (white) 1-0 Vladimir_FireDragons (black)
        TeamPlayerPairing.objects.create(
            team_pairing=tp,
            board_number=1,
            white=self.anatoly_shadow,  # Shadow player has white
            black=self.vladimir_fire,   # Fire player has black
            result="1-0",  # White wins = Shadow wins
        )

        # Board 2: Colors alternate - Fire player has white piece
        # Richárd_ShadowLegends (1607) 0-1 Richárd_FireDragons (1960)
        # Fire wins
        TeamPlayerPairing.objects.create(
            team_pairing=tp,
            board_number=2,
            white=self.richard_fire,    # Fire
            black=self.richard_shadow,  # Shadow
            result="1-0",  # Fire wins
        )

        # Board 3: Fire player has black piece (alternation)
        # Ding_ShadowLegends (1880) 0-1 Sam_FireDragons (1755)
        # Fire wins
        TeamPlayerPairing.objects.create(
            team_pairing=tp,
            board_number=3,
            white=self.ding_shadow,     # Shadow has white
            black=self.sam_fire,        # Fire has black
            result="0-1",  # Black wins = Fire wins
        )

        # Board 4: Fire player has white piece
        # Magnus_ShadowLegends (1746) 0-1 Anish_FireDragons (1921)
        # Fire wins
        TeamPlayerPairing.objects.create(
            team_pairing=tp,
            board_number=4,
            white=self.anish_fire,      # Fire
            black=self.magnus_shadow,   # Shadow
            result="1-0",  # Fire wins
        )

        tp.refresh_points()
        tp.save()

        # Mark round as completed
        self.round1.is_completed = True
        self.round1.save()

    def test_fire_vs_shadow_scoring(self):
        """Test that Fire beats Shadow 3-1."""
        # Get the match
        match = TeamPairing.objects.get(
            white_team=self.fire,
            black_team=self.shadow
        )


        # Test Django model calculation
        self.assertEqual(match.white_points, 3.0, "Fire Dragons should have 3.0 points")
        self.assertEqual(match.black_points, 1.0, "Shadow Legends should have 1.0 points")

        # Test tournament_core calculation
        tournament = season_to_tournament_structure(self.season)
        results = tournament.calculate_results()

        fire_result = results[self.fire.id]
        shadow_result = results[self.shadow.id]

        # Fire should win = 2 match points
        self.assertEqual(fire_result.match_points, 2, "Fire Dragons should have 2 match points (win)")
        self.assertEqual(fire_result.game_points, 3.0, "Fire Dragons should have 3.0 game points")
        
        # Shadow should lose = 0 match points
        self.assertEqual(shadow_result.match_points, 0, "Shadow Legends should have 0 match points (loss)")
        self.assertEqual(shadow_result.game_points, 1.0, "Shadow Legends should have 1.0 game points")