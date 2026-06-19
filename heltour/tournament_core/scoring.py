"""
Configurable scoring systems for tournaments.

This module defines how game results are converted to points and
how match results are determined from game scores.
"""

from typing import Tuple
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringSystem:
    """Defines how games and matches are scored in a tournament."""

    # Game scoring
    game_win_points: float = 1.0
    game_draw_points: float = 0.5
    game_loss_points: float = 0.0

    # Match scoring
    match_win_points: int = 2
    match_draw_points: int = 1
    match_loss_points: int = 0

    # Bye scoring
    bye_match_points: int = 1
    bye_game_points_factor: float = 0.5  # Fraction of max possible game points

    def game_points(self, winner: bool, draw: bool = False) -> float:
        """Get game points for a result."""
        if draw:
            return self.game_draw_points
        return self.game_win_points if winner else self.game_loss_points

    def match_points(self, games_for: float, games_against: float) -> Tuple[int, int]:
        """
        Determine match points based on game scores.

        Args:
            games_for: Game points scored by first competitor
            games_against: Game points scored by second competitor

        Returns:
            Tuple of (first_competitor_match_points, second_competitor_match_points)
        """
        if games_for > games_against:
            return (self.match_win_points, self.match_loss_points)
        elif games_for < games_against:
            return (self.match_loss_points, self.match_win_points)
        else:
            return (self.match_draw_points, self.match_draw_points)


# Pre-defined scoring systems
STANDARD_SCORING = ScoringSystem()

THREE_ONE_ZERO_SCORING = ScoringSystem(
    match_win_points=3, match_draw_points=1, match_loss_points=0
)

# Some tournaments use different game scoring
FOOTBALL_SCORING = ScoringSystem(
    game_win_points=3.0,
    game_draw_points=1.0,
    game_loss_points=0.0,
    match_win_points=3,
    match_draw_points=1,
    match_loss_points=0,
)
