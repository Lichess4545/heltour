"""
Tournament builder that extends the core builder with database persistence.

This module provides a TournamentBuilder that wraps tournament_core.builder
and adds database persistence capabilities for testing and seeding.
"""

import random
from typing import Union, Tuple

from heltour.tournament_core.builder import TournamentBuilder as CoreTournamentBuilder
from heltour.tournament.structure_to_db import structure_to_db


def simulate_game_result(
    white_rating: int,
    black_rating: int,
    allow_forfeit: bool = True,
    forfeit_rate: float = 0.05,
) -> str:
    """Simulate a game result based on ratings.

    Args:
        white_rating: White player's rating
        black_rating: Black player's rating
        allow_forfeit: Whether to allow forfeit results
        forfeit_rate: Probability of a forfeit (default 5%)

    Returns:
        Result string: '1-0', '1/2-1/2', '0-1', '1X-0F', '0F-1X', or '0F-0F'
    """
    # Small chance of forfeit
    if allow_forfeit and random.random() < forfeit_rate:
        forfeit_type = random.random()
        if forfeit_type < 0.4:
            return "1X-0F"  # Black forfeits
        elif forfeit_type < 0.8:
            return "0F-1X"  # White forfeits
        else:
            return "0F-0F"  # Both forfeit

    # Calculate expected score using Elo formula
    exp_white = 1 / (1 + 10 ** ((black_rating - white_rating) / 400))

    # Add some randomness
    rand = random.random()

    # Adjust probabilities for more realistic results
    if rand < exp_white - 0.1:
        return "1-0"
    elif rand < exp_white + 0.1:
        return "1/2-1/2"
    else:
        return "0-1"


class TournamentBuilder:
    """Fluent interface for building tournaments with database persistence.

    This builder extends the core TournamentBuilder to create database objects
    as needed for testing and seeding. It maintains the same API but adds
    database-specific functionality.
    """

    def __init__(self):
        self.core_builder = CoreTournamentBuilder()
        self._db_objects = None
        self.current_round = None
        self._round_number = 0
        self._completed_rounds = set()
        self._existing_league = None  # For when we're working with an existing league

    # Core builder delegation methods

    def league(
        self, name: str, tag: str, type: str = "lone", **kwargs
    ) -> "TournamentBuilder":
        """Create a league with additional configuration."""
        # If we have an existing league, just store its info in metadata
        if self._existing_league:
            self.core_builder.metadata.league_name = self._existing_league.name
            self.core_builder.metadata.league_tag = self._existing_league.tag
            self.core_builder.metadata.competitor_type = (
                self._existing_league.competitor_type
            )
            self.core_builder.metadata.league_settings = kwargs
        else:
            self.core_builder.league(name, tag, type, **kwargs)
        return self

    def knockout_format(
        self, seeding_style: str = "traditional", games_per_match: int = 1, matches_per_stage: int = 1
    ) -> "TournamentBuilder":
        """Configure league for knockout format with additional settings."""
        # Set tournament format
        if matches_per_stage > 1:
            self.core_builder.multi_match_knockout(matches_per_stage)
        else:
            self.core_builder.knockout_format()
        self.core_builder.games_per_match(games_per_match)
        
        # Store knockout-specific settings
        pairing_type = "knockout-multi" if matches_per_stage > 1 else "knockout-single"
        knockout_settings = {
            "knockout_seeding_style": seeding_style,
            "knockout_games_per_match": games_per_match,
            "pairing_type": pairing_type,
        }
            
        self.core_builder.metadata.league_settings.update(knockout_settings)
        return self

    def season(
        self, league_tag: str, name: str, rounds: int = 3, boards: int = None, **kwargs
    ) -> "TournamentBuilder":
        """Create a season with additional configuration."""
        # Store player ratings in metadata if provided
        if "player_ratings" in kwargs:
            player_ratings = kwargs.pop("player_ratings")
            if "player_kwargs" not in self.core_builder.metadata.season_settings:
                self.core_builder.metadata.season_settings["player_kwargs"] = {}
            for player_name, rating in player_ratings.items():
                player_id = self.core_builder._get_or_create_player_id(player_name)
                self.core_builder.metadata.season_settings["player_kwargs"][
                    player_id
                ] = {"rating": rating}

        self.core_builder.season(league_tag, name, rounds, boards, **kwargs)
        return self

    def team(
        self, name: str, *players: Union[str, Tuple[str, int]], **kwargs
    ) -> "TournamentBuilder":
        """Add a team with players (either names or (name, rating) tuples)."""
        self.core_builder.team(name, *players, **kwargs)
        return self

    def player(self, name: str, rating: int = 1500, **kwargs) -> "TournamentBuilder":
        """Add a player with rating."""
        # Store rating in metadata for database creation
        self.core_builder.player(name, rating, **kwargs)
        player_id = self.core_builder.metadata.players[name]
        if "player_kwargs" not in self.core_builder.metadata.season_settings:
            self.core_builder.metadata.season_settings["player_kwargs"] = {}
        self.core_builder.metadata.season_settings["player_kwargs"][player_id] = {
            "rating": rating,
            **kwargs,
        }
        return self

    def round(self, number: int, auto_pair: bool = False) -> "TournamentBuilder":
        """Start a round with optional automatic pairing."""
        self.core_builder.round(number, auto_pair)
        self._round_number = number
        return self

    def game(
        self, white_name: str, black_name: str, result: str
    ) -> "TournamentBuilder":
        """Play a game."""
        self.core_builder.game(white_name, black_name, result)
        return self

    def match(
        self, white_team: str, black_team: str, *results: str
    ) -> "TournamentBuilder":
        """Play a team match."""
        self.core_builder.match(white_team, black_team, *results)
        return self

    def complete(self) -> "TournamentBuilder":
        """Complete the current round."""
        self.core_builder.complete()
        self._completed_rounds.add(self._round_number)
        return self

    def calculate(self) -> "TournamentBuilder":
        """Calculate standings."""
        self.core_builder.calculate()
        # Ensure DB objects are built before calculating
        if self._db_objects is None:
            self._build_db_objects()
        # Recalculate scores in database
        self._db_objects["season"].calculate_scores()
        return self

    def build(self) -> "TournamentBuilder":
        """Build database objects and return self for chaining."""
        if self._db_objects is None:
            self._build_db_objects()
        return self

    # Database-specific methods

    def _build_db_objects(self):
        """Build database objects from the core structure."""
        if self._db_objects is not None:
            return

        # Build the tournament structure first
        tournament = self.core_builder.build()
        # Convert to database objects, using existing league if provided
        self._db_objects = structure_to_db(
            self.core_builder, existing_league=self._existing_league
        )
        # Update current round reference
        if self._round_number > 0 and self._round_number <= len(
            self._db_objects["rounds"]
        ):
            self.current_round = self._db_objects["rounds"][self._round_number - 1]

    def start_round(self, round_number: int, generate_pairings_auto: bool = False):
        """Start a round, optionally generating pairings with JavaFo."""
        from heltour.tournament.models import Round

        # Ensure DB objects exist
        if self._db_objects is None:
            self._build_db_objects()

        # Create a new round in the database
        round_obj = Round.objects.create(
            season=self._db_objects["season"], number=round_number, is_completed=False
        )

        # Generate pairings if requested
        if generate_pairings_auto:
            try:
                # Wrap in reversion context for pairing generation
                import reversion

                with reversion.create_revision():
                    reversion.set_comment("Test pairing generation")
                    from heltour.tournament.pairinggen import generate_pairings

                    generate_pairings(round_obj)
            except Exception as e:
                import traceback

                print(f"Failed to generate pairings: {e}")
                traceback.print_exc()

        self.current_round = round_obj
        self._round_number = round_number
        return round_obj

    def simulate_round_results(self, round_obj):
        """Simulate results for all pairings in a round."""
        from heltour.tournament.models import TeamPairing, LonePlayerPairing

        if not self._db_objects:
            return

        season = self._db_objects["season"]
        if season.league.competitor_type == "team":
            for pairing in TeamPairing.objects.filter(round=round_obj):
                for board_pairing in pairing.teamplayerpairing_set.order_by(
                    "board_number"
                ):
                    white_rating = board_pairing.white.rating or 1500
                    black_rating = board_pairing.black.rating or 1500
                    result = simulate_game_result(white_rating, black_rating)
                    board_pairing.result = result
                    board_pairing.save()
                pairing.refresh_points()
                pairing.save()
        else:
            for pairing in LonePlayerPairing.objects.filter(round=round_obj):
                white_rating = pairing.white.rating or 1500
                black_rating = pairing.black.rating or 1500
                result = simulate_game_result(white_rating, black_rating)
                pairing.result = result
                pairing.save()

    def complete_round(self, round_obj):
        """Complete a round, simulating results if needed."""
        from heltour.tournament.models import TeamPairing

        # If there are pairings without results, simulate them
        if self._db_objects and self._db_objects.get("season"):
            season = self._db_objects["season"]
            if season.league.competitor_type == "team":
                # Check if any pairings lack results
                pairings_without_results = (
                    TeamPairing.objects.filter(round=round_obj)
                    .filter(teamplayerpairing__result="")
                    .distinct()
                )
                if pairings_without_results.exists():
                    self.simulate_round_results(round_obj)

        # Mark the round as completed
        round_obj.is_completed = True
        round_obj.save()

        # Calculate scores after completing the round
        if self._db_objects and self._db_objects.get("season"):
            self._db_objects["season"].calculate_scores()

    def calculate_standings(self):
        """Calculate standings (alias for calculate)."""
        return self.calculate()

    # Compatibility properties

    @property
    def seasons(self):
        """Access seasons dictionary for compatibility."""
        if self._db_objects is None:
            self._build_db_objects()
        return {self.core_builder.metadata.season_name: self._db_objects["season"]}

    @property
    def current_season(self):
        """Access current season for compatibility."""
        if self._db_objects is None:
            self._build_db_objects()
        return self._db_objects["season"]

    @property
    def simulator(self):
        """Access simulator-like properties for compatibility."""
        if self._db_objects is None:
            self._build_db_objects()

        # Return an object that has leagues and seasons properties
        class SimulatorCompat:
            def __init__(self, db_objects, metadata):
                self.db_objects = db_objects
                self.metadata = metadata

            @property
            def leagues(self):
                return {self.metadata.league_tag: self.db_objects["league"]}

            @property
            def seasons(self):
                return {self.metadata.season_name: self.db_objects["season"]}

            @property
            def current_season(self):
                return self.db_objects["season"]

        return SimulatorCompat(self._db_objects, self.core_builder.metadata)

    # Backwards compatibility methods

    def simulate_results(self) -> "TournamentBuilder":
        """Simulate results for current round (no-op for compatibility)."""
        return self
