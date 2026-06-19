"""
Fluent assertion interface for testing tournament standings.

This module provides a clean, fluent way to assert tournament results and standings
for testing purposes. It works with the pure Python tournament_core structures.
"""

from typing import Dict, Optional, Union
from dataclasses import dataclass
from heltour.tournament_core.structure import Tournament, TournamentFormat
from heltour.tournament_core.tiebreaks import CompetitorScore, calculate_all_tiebreaks


# Use the built-in AssertionError for proper test framework integration


@dataclass
class StandingsAssertion:
    """Fluent interface for asserting tournament standings."""

    tournament: Tournament
    competitor_name: Optional[str] = None
    competitor_id: Optional[int] = None
    _name_to_id: Optional[Dict[str, int]] = None
    _id_to_name: Optional[Dict[int, str]] = None
    _results: Optional[Dict[int, CompetitorScore]] = None
    _tiebreaks: Optional[Dict[int, Dict[str, float]]] = None

    def __post_init__(self):
        """Calculate results once on initialization."""
        if self._results is None:
            self._results = self.tournament.calculate_results()

    def _ensure_mappings(self):
        """Ensure name to ID mappings are available."""
        if self._name_to_id is None:
            # In a real implementation, we'd need a way to map names to IDs
            # For now, we'll assume the tournament builder provides this mapping
            if hasattr(self.tournament, "name_to_id"):
                self._name_to_id = self.tournament.name_to_id
                self._id_to_name = {v: k for k, v in self._name_to_id.items()}
            else:
                # Default: treat competitor IDs as integers that can be used as names
                self._name_to_id = {
                    str(cid): cid for cid in self.tournament.competitors
                }
                self._id_to_name = {
                    cid: str(cid) for cid in self.tournament.competitors
                }

    def _get_competitor_id(self, name: str) -> int:
        """Convert competitor name to ID."""
        self._ensure_mappings()
        if name not in self._name_to_id:
            raise AssertionError(f"Competitor '{name}' not found in tournament")
        return self._name_to_id[name]

    def _get_competitor_score(self) -> CompetitorScore:
        """Get the score for the current competitor."""
        if self.competitor_id is None:
            raise AssertionError("No competitor selected for assertion")
        if self.competitor_id not in self._results:
            raise AssertionError(
                f"Competitor ID {self.competitor_id} not found in results"
            )
        return self._results[self.competitor_id]

    def _get_competitor_name(self) -> str:
        """Get the name of the current competitor."""
        self._ensure_mappings()
        if self.competitor_id is None:
            return "Unknown"
        return self._id_to_name.get(self.competitor_id, f"ID:{self.competitor_id}")

    def team(self, name: str) -> "CompetitorAssertion":
        """Select a team by name for assertions."""
        competitor_id = self._get_competitor_id(name)
        return CompetitorAssertion(
            tournament=self.tournament,
            competitor_name=name,
            competitor_id=competitor_id,
            _name_to_id=self._name_to_id,
            _id_to_name=self._id_to_name,
            _results=self._results,
            _tiebreaks=self._tiebreaks,
        )

    def player(self, name: str) -> "CompetitorAssertion":
        """Select a player by name for assertions (alias for team)."""
        return self.team(name)


class CompetitorAssertion(StandingsAssertion):
    """Assertions for a specific competitor."""

    def assert_(self) -> "CompetitorResultAssertion":
        """Start a chain of assertions for this competitor."""
        return CompetitorResultAssertion(
            tournament=self.tournament,
            competitor_name=self.competitor_name,
            competitor_id=self.competitor_id,
            _name_to_id=self._name_to_id,
            _id_to_name=self._id_to_name,
            _results=self._results,
            _tiebreaks=self._tiebreaks,
        )


class CompetitorResultAssertion(StandingsAssertion):
    """Fluent interface for asserting competitor results."""

    def wins(self, expected: int) -> "CompetitorResultAssertion":
        """Assert the number of wins."""
        score = self._get_competitor_score()
        actual_wins = sum(
            1 for mr in score.match_results if mr.match_points == 2 and not mr.is_bye
        )
        if actual_wins != expected:
            raise AssertionError(
                f"{self._get_competitor_name()} expected {expected} wins, got {actual_wins}"
            )
        return self

    def losses(self, expected: int) -> "CompetitorResultAssertion":
        """Assert the number of losses."""
        score = self._get_competitor_score()
        actual_losses = sum(
            1 for mr in score.match_results if mr.match_points == 0 and not mr.is_bye
        )
        if actual_losses != expected:
            raise AssertionError(
                f"{self._get_competitor_name()} expected {expected} losses, got {actual_losses}"
            )
        return self

    def draws(self, expected: int) -> "CompetitorResultAssertion":
        """Assert the number of draws."""
        score = self._get_competitor_score()
        actual_draws = sum(
            1 for mr in score.match_results if mr.match_points == 1 and not mr.is_bye
        )
        if actual_draws != expected:
            raise AssertionError(
                f"{self._get_competitor_name()} expected {expected} draws, got {actual_draws}"
            )
        return self

    def byes(self, expected: int) -> "CompetitorResultAssertion":
        """Assert the number of byes."""
        score = self._get_competitor_score()
        actual_byes = sum(1 for mr in score.match_results if mr.is_bye)
        if actual_byes != expected:
            raise AssertionError(
                f"{self._get_competitor_name()} expected {expected} byes, got {actual_byes}"
            )
        return self

    def match_points(self, expected: Union[int, float]) -> "CompetitorResultAssertion":
        """Assert the total match points."""
        score = self._get_competitor_score()
        if score.match_points != expected:
            raise AssertionError(
                f"{self._get_competitor_name()} expected {expected} match points, got {score.match_points}"
            )
        return self

    def game_points(self, expected: Union[int, float]) -> "CompetitorResultAssertion":
        """Assert the total game points."""
        score = self._get_competitor_score()
        # Allow small floating point differences
        if abs(score.game_points - expected) > 0.0001:
            raise AssertionError(
                f"{self._get_competitor_name()} expected {expected} game points, got {score.game_points}"
            )
        return self

    def games_won(self, expected: int) -> "CompetitorResultAssertion":
        """Assert the total number of games won (for team tournaments)."""
        score = self._get_competitor_score()
        actual_games_won = sum(mr.games_won for mr in score.match_results)
        if actual_games_won != expected:
            raise AssertionError(
                f"{self._get_competitor_name()} expected {expected} games won, got {actual_games_won}"
            )
        return self

    def tiebreak(
        self, name: str, expected: Union[int, float]
    ) -> "CompetitorResultAssertion":
        """Assert a specific tiebreak value."""
        # Calculate tiebreaks if not already done
        if self._tiebreaks is None:
            # Default tiebreak order including EGGSB
            tiebreak_order = [
                "sonneborn_berger",
                "eggsb",
                "buchholz",
                "head_to_head",
                "games_won",
                "game_points",
            ]
            self._tiebreaks = calculate_all_tiebreaks(self._results, tiebreak_order)

        if self.competitor_id not in self._tiebreaks:
            raise AssertionError(
                f"No tiebreak scores found for {self._get_competitor_name()}"
            )

        competitor_tiebreaks = self._tiebreaks[self.competitor_id]
        if name not in competitor_tiebreaks:
            raise AssertionError(
                f"Tiebreak '{name}' not calculated for {self._get_competitor_name()}"
            )

        actual = competitor_tiebreaks[name]
        # Allow small floating point differences
        if abs(actual - expected) > 0.0001:
            raise AssertionError(
                f"{self._get_competitor_name()} expected {expected} for {name} tiebreak, got {actual}"
            )
        return self

    def position(self, expected: int) -> "CompetitorResultAssertion":
        """Assert the final position in standings."""
        # Calculate standings with tiebreaks
        if self._tiebreaks is None:
            tiebreak_order = [
                "sonneborn_berger",
                "eggsb",
                "buchholz",
                "head_to_head",
                "games_won",
                "game_points",
            ]
            self._tiebreaks = calculate_all_tiebreaks(self._results, tiebreak_order)

        # Sort competitors by match points, game points, then tiebreaks
        standings = []
        for comp_id, score in self._results.items():
            tiebreak_values = []
            if comp_id in self._tiebreaks:
                for tb_name in [
                    "sonneborn_berger",
                    "eggsb",
                    "buchholz",
                    "head_to_head",
                    "games_won",
                ]:
                    tiebreak_values.append(self._tiebreaks[comp_id].get(tb_name, 0))

            standings.append(
                (
                    comp_id,
                    -score.match_points,  # Negative for reverse sort
                    -score.game_points,
                    [-tb for tb in tiebreak_values],  # Negative for reverse sort
                )
            )

        standings.sort(key=lambda x: (x[1], x[2], *x[3]))

        # Find position (1-based)
        actual_position = None
        for i, (comp_id, _, _, _) in enumerate(standings):
            if comp_id == self.competitor_id:
                actual_position = i + 1
                break

        if actual_position is None:
            raise AssertionError(
                f"Could not determine position for {self._get_competitor_name()}"
            )

        if actual_position != expected:
            raise AssertionError(
                f"{self._get_competitor_name()} expected position {expected}, got {actual_position}"
            )
        return self

    def advances_to_round(self, round_name: str) -> "CompetitorResultAssertion":
        """Assert that competitor advances to a specific knockout round.

        Args:
            round_name: Round name like "semifinals", "finals", etc.
        """
        if self.tournament.format != TournamentFormat.KNOCKOUT:
            raise AssertionError(
                "Tournament must be knockout format for advancement assertions"
            )

        # Find the round with this knockout stage name
        target_round = None
        for round in self.tournament.rounds:
            if round.knockout_stage == round_name:
                target_round = round
                break

        if target_round is None:
            raise AssertionError(f"Round '{round_name}' not found in tournament")

        # Check if competitor is in this round
        competitor_in_round = False
        for match in target_round.matches:
            if (
                match.competitor1_id == self.competitor_id
                or match.competitor2_id == self.competitor_id
            ):
                competitor_in_round = True
                break

        if not competitor_in_round:
            raise AssertionError(
                f"{self._get_competitor_name()} did not advance to {round_name}"
            )

        return self

    def eliminated_in_round(self, round_name: str) -> "CompetitorResultAssertion":
        """Assert that competitor was eliminated in a specific knockout round.

        Args:
            round_name: Round name like "quarterfinals", "semifinals", etc.
        """
        if self.tournament.format != TournamentFormat.KNOCKOUT:
            raise AssertionError(
                "Tournament must be knockout format for elimination assertions"
            )

        # Find the round with this knockout stage name
        elimination_round = None
        for round in self.tournament.rounds:
            if round.knockout_stage == round_name:
                elimination_round = round
                break

        if elimination_round is None:
            raise AssertionError(f"Round '{round_name}' not found in tournament")

        # Check if competitor lost in this round
        eliminated = False
        for match in elimination_round.matches:
            if (
                match.competitor1_id == self.competitor_id
                or match.competitor2_id == self.competitor_id
            ):
                winner = match.winner_id()
                if winner is not None and winner != self.competitor_id:
                    eliminated = True
                    break

        if not eliminated:
            raise AssertionError(
                f"{self._get_competitor_name()} was not eliminated in {round_name}"
            )

        return self

    def bracket_position(
        self, stage: str, match_number: int
    ) -> "CompetitorResultAssertion":
        """Assert competitor's position in a specific bracket stage.

        Args:
            stage: Knockout stage name like "quarterfinals", "semifinals"
            match_number: Match number within that stage (1-indexed)
        """
        if self.tournament.format != TournamentFormat.KNOCKOUT:
            raise AssertionError(
                "Tournament must be knockout format for bracket assertions"
            )

        # Find the round with this knockout stage name
        target_round = None
        for round in self.tournament.rounds:
            if round.knockout_stage == stage:
                target_round = round
                break

        if target_round is None:
            raise AssertionError(f"Knockout stage '{stage}' not found in tournament")

        if match_number < 1 or match_number > len(target_round.matches):
            raise AssertionError(
                f"Match number {match_number} out of range for {stage} (1-{len(target_round.matches)})"
            )

        # Check the specific match
        target_match = target_round.matches[match_number - 1]  # Convert to 0-indexed

        if (
            target_match.competitor1_id != self.competitor_id
            and target_match.competitor2_id != self.competitor_id
        ):
            raise AssertionError(
                f"{self._get_competitor_name()} not found in {stage} match {match_number}"
            )

        return self

    def wins_knockout_tournament(self) -> "CompetitorResultAssertion":
        """Assert that competitor wins the entire knockout tournament."""
        if self.tournament.format != TournamentFormat.KNOCKOUT:
            raise AssertionError("Tournament must be knockout format")

        from heltour.tournament_core.knockout import get_knockout_winner

        winner_id = get_knockout_winner(self.tournament)

        if winner_id != self.competitor_id:
            winner_name = "No winner" if winner_id is None else f"ID:{winner_id}"
            if winner_id is not None:
                self._ensure_mappings()
                winner_name = self._id_to_name.get(winner_id, f"ID:{winner_id}")

            raise AssertionError(
                f"{self._get_competitor_name()} did not win tournament (winner: {winner_name})"
            )

        return self


def assert_tournament(tournament: Tournament) -> StandingsAssertion:
    """Entry point for tournament assertions."""
    return StandingsAssertion(tournament)
