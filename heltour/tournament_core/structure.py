"""
Tournament utilities for representing and calculating tournament results.

This module provides a simple, clean way to represent tournaments with:
- Competitors (players or teams)
- Matches between competitors
- Games within matches
- Scoring functions to convert game results to match points
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from heltour.tournament_core.tiebreaks import MatchResult, CompetitorScore
from heltour.tournament_core.scoring import ScoringSystem, STANDARD_SCORING


class TournamentFormat(Enum):
    """Tournament format type."""

    SWISS = "swiss"
    KNOCKOUT = "knockout"


@dataclass(frozen=True)
class Player:
    """Represents a player with their ID and the competitor (team) they belong to."""

    player_id: int
    competitor_id: int


class GameResult(Enum):
    """Result of a single game."""

    P1_WIN = "1-0"
    DRAW = "1/2-1/2"
    P2_WIN = "0-1"
    P1_FORFEIT_WIN = "1X-0F"
    P2_FORFEIT_WIN = "0F-1X"
    DOUBLE_FORFEIT = "0F-0F"


@dataclass(frozen=True)
class Game:
    """A single game between two players."""

    player1: Player
    player2: Player
    result: GameResult

    def points(self, scoring: ScoringSystem = STANDARD_SCORING) -> Tuple[float, float]:
        """Return (player1_points, player2_points) for this game."""
        if self.result == GameResult.P1_WIN:
            return (scoring.game_win_points, scoring.game_loss_points)
        elif self.result == GameResult.P2_WIN:
            return (scoring.game_loss_points, scoring.game_win_points)
        elif self.result == GameResult.DRAW:
            return (scoring.game_draw_points, scoring.game_draw_points)
        elif self.result == GameResult.P1_FORFEIT_WIN:
            return (scoring.game_win_points, scoring.game_loss_points)
        elif self.result == GameResult.P2_FORFEIT_WIN:
            return (scoring.game_loss_points, scoring.game_win_points)
        else:  # DOUBLE_FORFEIT
            return (0.0, 0.0)

    def winner_id(self) -> Optional[int]:
        """Return the ID of the winner, or None if draw/double forfeit."""
        if self.result in (GameResult.P1_WIN, GameResult.P1_FORFEIT_WIN):
            return self.player1.player_id
        elif self.result in (GameResult.P2_WIN, GameResult.P2_FORFEIT_WIN):
            return self.player2.player_id
        return None


@dataclass(frozen=True)
class Match:
    """A match consisting of one or more games between two competitors.

    For team matches, the games represent individual boards where the player IDs
    are the individual players, but the match is between the teams (competitors).
    The games should be ordered such that the first player in each game belongs
    to competitor1's team.

    For knockout tournaments:
    - games_per_match: Number of games in this match (for multi-game knockout matches)
    - manual_tiebreak_value: Arbiter-set value to determine winner in case of tie
    """

    competitor1_id: int
    competitor2_id: int
    games: List[Game] = field(default_factory=list)
    is_bye: bool = False
    games_per_match: int = 1
    manual_tiebreak_value: Optional[float] = None
    bye_game_points: Optional[float] = None
    bye_match_points: Optional[int] = None

    def _calculate_game_results(
        self, scoring: ScoringSystem = STANDARD_SCORING
    ) -> Tuple[float, float, int, int]:
        """Calculate game points and wins for both competitors.

        Returns: (c1_points, c2_points, c1_wins, c2_wins)
        """
        c1_points = 0.0
        c2_points = 0.0
        c1_wins = 0
        c2_wins = 0

        for game in self.games:
            p1_pts, p2_pts = game.points(scoring)

            # Determine which competitor each player belongs to
            if game.player1.competitor_id == self.competitor1_id:
                # Player1 is on team1, player2 is on team2
                c1_points += p1_pts
                c2_points += p2_pts

                # Count wins
                if game.result in (GameResult.P1_WIN, GameResult.P1_FORFEIT_WIN):
                    c1_wins += 1
                elif game.result in (GameResult.P2_WIN, GameResult.P2_FORFEIT_WIN):
                    c2_wins += 1
            else:
                # Player1 is on team2, player2 is on team1
                c1_points += p2_pts
                c2_points += p1_pts

                # Count wins
                if game.result in (GameResult.P1_WIN, GameResult.P1_FORFEIT_WIN):
                    c2_wins += 1
                elif game.result in (GameResult.P2_WIN, GameResult.P2_FORFEIT_WIN):
                    c1_wins += 1

        return (c1_points, c2_points, c1_wins, c2_wins)

    def game_points(
        self, scoring: ScoringSystem = STANDARD_SCORING
    ) -> Tuple[float, float]:
        """Return total (competitor1_game_points, competitor2_game_points)."""
        if self.is_bye:
            if self.bye_game_points is not None:
                return (self.bye_game_points, 0.0)
            # In a bye, the player gets the configured fraction of maximum possible points
            max_points = (
                scoring.game_win_points * len(self.games)
                if self.games
                else scoring.game_win_points
            )
            return (max_points * scoring.bye_game_points_factor, 0.0)

        c1_points, c2_points, _, _ = self._calculate_game_results(scoring)
        return (c1_points, c2_points)

    def games_won(self) -> Tuple[int, int]:
        """Return (competitor1_games_won, competitor2_games_won)."""
        if self.is_bye:
            return (0, 0)

        _, _, c1_wins, c2_wins = self._calculate_game_results()
        return (c1_wins, c2_wins)

    def winner_id(self, scoring: ScoringSystem = STANDARD_SCORING) -> Optional[int]:
        """Return the ID of the match winner, or None if draw/no winner determined.

        For knockout tournaments, this considers:
        1. Game points comparison
        2. Manual tiebreak value (if set)
        3. None if still tied (needs manual intervention)
        """
        if self.is_bye:
            return self.competitor1_id

        c1_game_pts, c2_game_pts = self.game_points(scoring)

        # First check game points
        if c1_game_pts > c2_game_pts:
            return self.competitor1_id
        elif c2_game_pts > c1_game_pts:
            return self.competitor2_id

        # If tied on game points, check manual tiebreak
        if self.manual_tiebreak_value is not None:
            if self.manual_tiebreak_value > 0:
                return self.competitor1_id
            elif self.manual_tiebreak_value < 0:
                return self.competitor2_id

        # Still tied - needs manual intervention
        return None


@dataclass(frozen=True)
class Round:
    """A round in a tournament containing multiple matches.

    For knockout tournaments:
    - knockout_stage: Stage name like "semifinals", "finals", etc.
    """

    number: int
    matches: List[Match] = field(default_factory=list)
    knockout_stage: Optional[str] = None

    def add_match(self, match: Match) -> "Round":
        """Return a new Round with the match added (immutable pattern)."""
        return Round(self.number, self.matches + [match], self.knockout_stage)


@dataclass
class Tournament:
    """Represents a complete tournament organized by rounds."""

    competitors: List[int]  # List of competitor IDs
    rounds: List[Round] = field(default_factory=list)  # List of rounds
    scoring: ScoringSystem = field(default_factory=lambda: STANDARD_SCORING)
    format: TournamentFormat = TournamentFormat.SWISS
    
    # Multi-match knockout fields
    matches_per_stage: int = 1  # Number of matches each pair plays before elimination (e.g., 2 for return matches)
    current_match_number: int = 1  # Current match number being played in active stages

    @property
    def matches(self) -> List[Match]:
        """Get all matches across all rounds (for backward compatibility)."""
        all_matches = []
        for round in self.rounds:
            all_matches.extend(round.matches)
        return all_matches

    @property
    def num_rounds(self) -> int:
        """Get the number of rounds in the tournament."""
        return len(self.rounds)

    def calculate_results(self) -> Dict[int, CompetitorScore]:
        """Calculate complete tournament results with match points and game points."""
        # Initialize results for all competitors
        results: Dict[int, List[MatchResult]] = {c: [] for c in self.competitors}

        # Process each round and match
        for round in self.rounds:
            for match in round.matches:
                c1_game_pts, c2_game_pts = match.game_points(self.scoring)
                c1_match_pts, c2_match_pts = self.scoring.match_points(
                    c1_game_pts, c2_game_pts
                )
                c1_games_won, c2_games_won = match.games_won()

                if not match.is_bye:
                    # Add result for competitor 1
                    results[match.competitor1_id].append(
                        MatchResult(
                            opponent_id=match.competitor2_id,
                            game_points=c1_game_pts,
                            opponent_game_points=c2_game_pts,
                            match_points=c1_match_pts,
                            games_won=c1_games_won,
                            is_bye=False,
                        )
                    )

                    # Add result for competitor 2 (only if it's a real competitor, not -1 for bye)
                    if match.competitor2_id in results:
                        results[match.competitor2_id].append(
                            MatchResult(
                                opponent_id=match.competitor1_id,
                                game_points=c2_game_pts,
                                opponent_game_points=c1_game_pts,
                                match_points=c2_match_pts,
                                games_won=c2_games_won,
                                is_bye=False,
                            )
                        )
                else:
                    # Handle bye
                    bye_mp = (
                        match.bye_match_points
                        if match.bye_match_points is not None
                        else self.scoring.bye_match_points
                    )
                    results[match.competitor1_id].append(
                        MatchResult(
                            opponent_id=None,
                            game_points=c1_game_pts,
                            opponent_game_points=0,
                            match_points=bye_mp,
                            games_won=0,
                            is_bye=True,
                        )
                    )

        # Build CompetitorScore objects
        competitor_scores = {}
        for comp_id, match_results in results.items():
            total_match_points = sum(mr.match_points for mr in match_results)
            total_game_points = sum(mr.game_points for mr in match_results)

            competitor_scores[comp_id] = CompetitorScore(
                competitor_id=comp_id,
                match_points=total_match_points,
                game_points=total_game_points,
                match_results=match_results,
            )

        return competitor_scores


# Kept for backwards compatibility - prefer using ScoringSystem directly
def standard_match_points(
    c1_game_points: float, c2_game_points: float
) -> Tuple[int, int]:
    """Standard system: 2 points for win, 1 for draw, 0 for loss."""
    return STANDARD_SCORING.match_points(c1_game_points, c2_game_points)


def three_one_zero_match_points(
    c1_game_points: float, c2_game_points: float
) -> Tuple[int, int]:
    """Alternative system: 3 points for win, 1 for draw, 0 for loss."""
    from heltour.tournament_core.scoring import THREE_ONE_ZERO_SCORING

    return THREE_ONE_ZERO_SCORING.match_points(c1_game_points, c2_game_points)


# Helper functions for common tournament formats
def create_single_game_match(p1_id: int, p2_id: int, result: GameResult) -> Match:
    """Create a match with a single game (common for individual tournaments).

    In individual tournaments, the player ID is the competitor ID.
    """
    # For individual tournaments, player ID equals competitor ID
    player1 = Player(p1_id, p1_id)
    player2 = Player(p2_id, p2_id)
    game = Game(player1, player2, result)
    return Match(p1_id, p2_id, [game])


def create_bye_match(competitor_id: int, games_per_match: int = 1) -> Match:
    """Create a bye match."""
    # For a bye, we might still need to know how many games would have been played
    # to calculate the appropriate game points
    #
    # For team tournaments: team bye = draw-equivalent scoring (half points)
    # For individual tournaments: player bye = win (full points)
    if games_per_match > 1:
        # Team tournament: bye should give draw-equivalent points (half the boards)
        # Create half wins, half draws to achieve 50% scoring
        games = []
        for i in range(games_per_match):
            # For bye games, create dummy players
            player = Player(i, competitor_id)  # Use board number as player ID
            bye_player = Player(-1, -1)  # Bye opponent
            if i < games_per_match // 2:
                games.append(Game(player, bye_player, GameResult.P1_WIN))
            else:
                games.append(Game(player, bye_player, GameResult.DRAW))
    else:
        # Individual tournament: bye = full win
        player = Player(competitor_id, competitor_id)
        bye_player = Player(-1, -1)
        games = [
            Game(player, bye_player, GameResult.P1_WIN) for _ in range(games_per_match)
        ]

    return Match(competitor_id, -1, games, is_bye=True, games_per_match=games_per_match)


def create_scored_bye_match(
    competitor_id: int, game_points: float, match_points: int
) -> Match:
    """Create a bye match with explicit game and match point values.

    Used when bye type is known (e.g. from PlayerBye records) and the default
    scoring-system-derived values would be incorrect.
    """
    return Match(
        competitor_id,
        -1,
        [],
        is_bye=True,
        bye_game_points=game_points,
        bye_match_points=match_points,
    )


def create_team_match(
    team1_id: int,
    team2_id: int,
    board_results: List[Tuple[int, int, GameResult]],
    player_team_mapping: Optional[Dict[int, int]] = None,
) -> Match:
    """
    Create a team match with multiple boards.

    Args:
        team1_id: First team's ID
        team2_id: Second team's ID
        board_results: List of (player1_id, player2_id, result) for each board
                      If player_team_mapping is provided, players can be in any order
                      If not provided, assumes player1 belongs to team1, player2 to team2
        player_team_mapping: Optional dict mapping player_id to team_id
    """
    games = []
    for p1_id, p2_id, result in board_results:
        if player_team_mapping:
            # Use the mapping to determine which team each player belongs to
            # Special case: -1 means no player (forfeit)
            p1_team = -1 if p1_id == -1 else player_team_mapping.get(p1_id, team1_id)
            p2_team = -1 if p2_id == -1 else player_team_mapping.get(p2_id, team2_id)
            player1 = Player(p1_id, p1_team)
            player2 = Player(p2_id, p2_team)
        else:
            # Legacy behavior: assume player1 is from team1, player2 from team2
            player1 = Player(p1_id, team1_id)
            player2 = Player(p2_id, team2_id)
        games.append(Game(player1, player2, result))
    return Match(team1_id, team2_id, games)


def create_tournament_from_matches(
    competitors: List[int],
    matches_with_rounds: List[Tuple[int, Match]],
    scoring: ScoringSystem = STANDARD_SCORING,
) -> Tournament:
    """Create a tournament from a list of (round_number, match) tuples.

    This is a convenience function for tests and backward compatibility.
    """
    # Group matches by round
    rounds_dict = defaultdict(list)
    for round_num, match in matches_with_rounds:
        rounds_dict[round_num].append(match)

    # Create Round objects
    rounds = [Round(num, matches) for num, matches in sorted(rounds_dict.items())]

    return Tournament(competitors, rounds, scoring)
