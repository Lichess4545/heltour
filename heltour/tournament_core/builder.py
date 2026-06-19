"""
Builder for creating tournament structures with a fluent API.

This module provides a builder class for creating tournament_core structures
with both low-level and high-level fluent APIs. It supports both team and
individual tournaments without database dependencies.
"""

from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass, field
from heltour.tournament_core.structure import (
    Tournament,
    Round,
    Match,
    Game,
    Player,
    GameResult,
    TournamentFormat,
    create_single_game_match,
    create_team_match,
    create_bye_match,
)
from heltour.tournament_core.scoring import ScoringSystem, STANDARD_SCORING
from heltour.tournament_core.knockout import (
    generate_knockout_seedings_traditional,
    generate_knockout_seedings_adjacent,
    get_knockout_stage_name,
    validate_bracket_size
)


@dataclass
class TournamentMetadata:
    """Metadata for the tournament (not part of core structure)."""

    league_name: str = ""
    league_tag: str = ""
    season_name: str = ""
    competitor_type: str = "lone"  # "lone" or "team"
    boards: Optional[int] = None

    # For tracking players/teams by name
    teams: Dict[str, Dict] = field(default_factory=dict)  # name -> team info
    players: Dict[str, int] = field(default_factory=dict)  # name -> player id

    # League settings (for database compatibility)
    league_settings: Dict = field(default_factory=dict)
    season_settings: Dict = field(default_factory=dict)


class TournamentBuilder:
    """Builder for creating tournament structures easily."""

    def __init__(
        self,
        competitors: Optional[List[int]] = None,
        scoring: ScoringSystem = STANDARD_SCORING,
    ):
        """Initialize with optional list of competitor IDs."""
        self.competitors = competitors or []
        self.tournament = Tournament(competitors=self.competitors, scoring=scoring)
        self.current_round = None
        self.metadata = TournamentMetadata()
        self._next_player_id = 1
        self._next_team_id = 1
        self._games_per_match = 1  # Default for backwards compatibility
        self._knockout_seedings = {}  # name -> seed order for knockout brackets

    # High-level fluent API methods (matching database TournamentBuilder)

    def league(
        self, name: str, tag: str, type: str = "lone", **kwargs
    ) -> "TournamentBuilder":
        """Define league metadata."""
        self.metadata.league_name = name
        self.metadata.league_tag = tag
        self.metadata.competitor_type = type
        self.metadata.league_settings = kwargs
        return self

    def season(
        self,
        league_tag: str,
        name: str,
        rounds: int = 3,
        boards: Optional[int] = None,
        **kwargs,
    ) -> "TournamentBuilder":
        """Define season metadata."""
        self.metadata.season_name = name
        self.metadata.boards = boards
        self.metadata.season_settings = {"rounds": rounds, **kwargs}
        return self

    def team(
        self, name: str, *players: Union[str, Tuple[str, int]], **kwargs
    ) -> "TournamentBuilder":
        """Add a team with players."""
        team_id = self._next_team_id
        self._next_team_id += 1

        # Store team metadata
        team_info = {"id": team_id, "name": name, "players": [], **kwargs}

        # Process players
        for p in players:
            if isinstance(p, tuple):
                player_name, rating = p
            else:
                player_name = p
                rating = 1500

            player_id = self._get_or_create_player_id(player_name)
            team_info["players"].append(
                {"name": player_name, "id": player_id, "rating": rating}
            )

        self.metadata.teams[name] = team_info
        
        # Set competitor type to team
        self.metadata.competitor_type = "team"

        # Add team to competitors
        if team_id not in self.competitors:
            self.competitors.append(team_id)
        if team_id not in self.tournament.competitors:
            self.tournament.competitors.append(team_id)

        return self

    def player(self, name: str, rating: int = 1500, **kwargs) -> "TournamentBuilder":
        """Add a player (for lone tournaments)."""
        player_id = self._get_or_create_player_id(name)

        # Add to competitors if not already there
        if player_id not in self.competitors:
            self.competitors.append(player_id)
        if player_id not in self.tournament.competitors:
            self.tournament.competitors.append(player_id)

        return self

    def round(self, number: int, auto_pair: bool = False) -> "TournamentBuilder":
        """Start a round with optional automatic pairing."""
        return self.add_round(number)

    def game(
        self, white_name: str, black_name: str, result: str
    ) -> "TournamentBuilder":
        """Play a game between two named players."""
        white_id = self.metadata.players.get(white_name)
        black_id = self.metadata.players.get(black_name)

        if white_id is None or black_id is None:
            raise ValueError(
                f"Player not found: {white_name if white_id is None else black_name}"
            )

        return self.add_game(white_id, black_id, result)

    def match(
        self, white_team: str, black_team: str, *results: str
    ) -> "TournamentBuilder":
        """Play a team match between two named teams."""
        white_team_info = self.metadata.teams.get(white_team)
        black_team_info = self.metadata.teams.get(black_team)

        if not white_team_info or not black_team_info:
            raise ValueError(
                f"Team not found: {white_team if not white_team_info else black_team}"
            )

        # Build board results
        board_results = []
        for i, result in enumerate(results):
            white_has_player = i < len(white_team_info["players"])
            black_has_player = i < len(black_team_info["players"])

            # Handle forfeits when one team doesn't have a player
            if result in ["1X-0F", "0F-1X"]:
                # Skip special forfeit handling if both teams have players
                if not (white_has_player and black_has_player):
                    # Determine who should have white/black on this board
                    if i % 2 == 0:  # Even boards: Team A (white_team) has white
                        if white_has_player and not black_has_player:
                            # Team A has player, Team B forfeits
                            board_results.append(
                                (
                                    white_team_info["players"][i]["id"],
                                    -1,  # No opponent
                                    "1X-0F",
                                )
                            )
                        elif black_has_player and not white_has_player:
                            # Team B has player, Team A forfeits
                            board_results.append(
                                (
                                    -1,  # No opponent
                                    black_team_info["players"][i]["id"],
                                    "0F-1X",
                                )
                            )
                    else:  # Odd boards: Team B (black_team) has white
                        if white_has_player and not black_has_player:
                            # Team A has player (as black), Team B forfeits (no white)
                            board_results.append(
                                (
                                    -1,  # No opponent (white)
                                    white_team_info["players"][i][
                                        "id"
                                    ],  # Team A player as black
                                    "0F-1X",
                                )
                            )
                        elif black_has_player and not white_has_player:
                            # Team B has player (as white), Team A forfeits (no black)
                            board_results.append(
                                (
                                    black_team_info["players"][i][
                                        "id"
                                    ],  # Team B player as white
                                    -1,  # No opponent (black)
                                    "1X-0F",
                                )
                            )
                    continue  # Forfeit handled, skip to next board

            # Skip if this isn't a forfeit and one team lacks a player
            if not (white_has_player and black_has_player) and result not in [
                "1X-0F",
                "0F-1X",
            ]:
                break

            # Both teams have players - normal handling
            if white_has_player and black_has_player:
                # Alternate colors by board
                if i % 2 == 0:  # Even boards (0, 2, 4...): white team gets white
                    white_player = white_team_info["players"][i]["id"]
                    black_player = black_team_info["players"][i]["id"]
                else:  # Odd boards (1, 3, 5...): black team gets white
                    white_player = black_team_info["players"][i]["id"]
                    black_player = white_team_info["players"][i]["id"]

                # Store the result exactly as provided - no flipping!
                board_results.append((white_player, black_player, result))

        # Build player to team mapping
        player_team_map = {}
        for player in white_team_info["players"]:
            player_team_map[player["id"]] = white_team_info["id"]
        for player in black_team_info["players"]:
            player_team_map[player["id"]] = black_team_info["id"]
        
        return self.add_team_match_with_mapping(
            white_team_info["id"], black_team_info["id"], board_results, player_team_map
        )

    def complete(self) -> "TournamentBuilder":
        """Complete the current round (for API compatibility)."""
        # Add automatic byes if configured
        if self.current_round and self.metadata.boards:
            self.auto_byes(self.metadata.boards)
        elif self.current_round:
            self.auto_byes()
        return self

    def calculate(self) -> "TournamentBuilder":
        """Calculate standings (no-op for pure structures)."""
        return self

    def simulate_results(self) -> "TournamentBuilder":
        """Simulate results (no-op for pure structures)."""
        return self

    # Knockout-specific fluent API methods

    def knockout_format(self) -> "TournamentBuilder":
        """Set tournament format to knockout."""
        self.tournament.format = TournamentFormat.KNOCKOUT
        return self

    def games_per_match(self, count: int) -> "TournamentBuilder":
        """Set the number of games per match (for multi-game knockout matches)."""
        if count < 1:
            raise ValueError("Games per match must be at least 1")
        self._games_per_match = count
        return self

    def bracket_seeding(
        self, teams: List[str], format: str = "traditional"
    ) -> "TournamentBuilder":
        """Set initial seedings for knockout bracket.
        
        Args:
            teams: List of team names in seeding order (1st seed first)
            format: "traditional" (1v32) or "adjacent" (1v2)
        """
        if format not in ["traditional", "adjacent"]:
            raise ValueError(f"Unknown seeding format: {format}")
        
        if not validate_bracket_size(len(teams)):
            raise ValueError(f"Team count {len(teams)} is not a power of 2")
        
        # Store seeding order
        for i, team_name in enumerate(teams):
            self._knockout_seedings[team_name] = i + 1  # 1-indexed seeds
        
        # Generate and add first round based on format
        self._generate_knockout_bracket(teams, format)
        return self

    def knockout_stage(self, stage_name: str) -> "TournamentBuilder":
        """Set the knockout stage name for the current round."""
        if self.current_round:
            # Create new round with knockout stage
            updated_round = Round(
                number=self.current_round.number,
                matches=self.current_round.matches,
                knockout_stage=stage_name
            )
            # Replace current round
            if self.tournament.rounds and self.tournament.rounds[-1] == self.current_round:
                self.tournament.rounds[-1] = updated_round
            self.current_round = updated_round
        return self

    def manual_tiebreak(
        self, competitor1: str, competitor2: str, value: float
    ) -> "TournamentBuilder":
        """Set manual tiebreak value for a specific match.
        
        Args:
            competitor1: First competitor name
            competitor2: Second competitor name  
            value: Tiebreak value (positive = competitor1 wins, negative = competitor2 wins)
        """
        if not self.current_round:
            raise ValueError("Must add a round before setting manual tiebreaks")
        
        # Find the match between these competitors
        comp1_id = self._get_competitor_id(competitor1)
        comp2_id = self._get_competitor_id(competitor2)
        
        for i, match in enumerate(self.current_round.matches):
            if ((match.competitor1_id == comp1_id and match.competitor2_id == comp2_id) or
                (match.competitor1_id == comp2_id and match.competitor2_id == comp1_id)):
                # Update match with manual tiebreak
                updated_match = Match(
                    competitor1_id=match.competitor1_id,
                    competitor2_id=match.competitor2_id,
                    games=match.games,
                    is_bye=match.is_bye,
                    games_per_match=match.games_per_match,
                    manual_tiebreak_value=value if match.competitor1_id == comp1_id else -value
                )
                self.current_round.matches[i] = updated_match
                break
        else:
            raise ValueError(f"No match found between {competitor1} and {competitor2}")
        
        return self

    # Multi-match knockout methods

    def multi_match_knockout(self, matches_per_stage: int) -> "TournamentBuilder":
        """Set up multi-match knockout tournament (e.g., return matches with color switching).
        
        Args:
            matches_per_stage: Number of matches each pair plays before elimination
                              (1 = single elimination, 2 = return matches, etc.)
        """
        if matches_per_stage < 1:
            raise ValueError("Matches per stage must be at least 1")
            
        self.tournament.format = TournamentFormat.KNOCKOUT
        self.tournament.matches_per_stage = matches_per_stage
        self.tournament.current_match_number = 1
        return self

    def complete_current_match_set(self) -> "TournamentBuilder":
        """Mark current match set as complete for all teams.
        
        This is used in simulation to indicate all teams have finished
        their current match number and next match set can be generated.
        """
        # This is primarily for simulation/testing purposes
        # In practice, matches are completed by adding game results
        return self

    def generate_next_match_set(self) -> "TournamentBuilder":
        """Generate the next set of matches with color switching.
        
        Can only be called when all teams have completed their current match.
        Creates return matches with colors flipped from original matches.
        """
        if not self.current_round:
            raise ValueError("Must have a current round to generate next match set")
            
        # Use the multi-match module to generate next match set
        from heltour.tournament_core.multi_match import can_generate_next_match_set, generate_next_match_set
        
        round_number = self.current_round.number
        
        if not can_generate_next_match_set(self.tournament, round_number):
            raise ValueError("Cannot generate next match set - not all teams completed current match")
            
        self.tournament = generate_next_match_set(self.tournament, round_number)
        
        # Update current round reference
        self.current_round = self.tournament.rounds[round_number - 1]
        
        return self

    def simulate_multi_match_stage(self, stage_results: List[Tuple[str, str]]) -> "TournamentBuilder":
        """Simulate results for a complete multi-match stage.
        
        Args:
            stage_results: List of (winner_name, loser_name) tuples for each team pair
        """
        if not self.current_round:
            raise ValueError("Must have a current round to simulate")
            
        if self.tournament.matches_per_stage == 1:
            # Single match - just use regular match simulation
            for winner, loser in stage_results:
                self.match(winner, loser, "1-0")
        else:
            # Multi-match stage - simulate all matches for each pair
            from heltour.tournament_core.multi_match import get_multi_match_stage_status
            
            # For simulation, we'll create results for each match number
            for match_number in range(1, self.tournament.matches_per_stage + 1):
                # Generate/simulate results for this match number
                for winner, loser in stage_results:
                    if match_number == 1:
                        # First match - use normal colors
                        self.match(winner, loser, "1-0")
                    else:
                        # Return matches - colors are already flipped by generate_next_match_set
                        # So the "winner" is still the overall winner but may be black in return match
                        self.match(winner, loser, "0-1")  # Winner wins as black in return match
                        
                # Generate next match set if not the last match
                if match_number < self.tournament.matches_per_stage:
                    self.generate_next_match_set()
                    
        return self

    # Low-level API methods (original TournamentBuilder interface)

    def add_round(self, round_number: int) -> "TournamentBuilder":
        """Add a new round to the tournament."""
        self.current_round = Round(number=round_number)
        self.tournament.rounds.append(self.current_round)
        return self

    def add_game(
        self, player1_id: int, player2_id: int, result: str
    ) -> "TournamentBuilder":
        """Add a single game match to the current round.

        Args:
            player1_id: First player ID
            player2_id: Second player ID
            result: Result string like '1-0', '1/2-1/2', '0-1'
        """
        if not self.current_round:
            raise ValueError("Must add a round before adding games")

        result_map = {
            "1-0": GameResult.P1_WIN,
            "1/2-1/2": GameResult.DRAW,
            "0-1": GameResult.P2_WIN,
            "1X-0F": GameResult.P1_FORFEIT_WIN,
            "0F-1X": GameResult.P2_FORFEIT_WIN,
            "0F-0F": GameResult.DOUBLE_FORFEIT,
            "+": GameResult.P1_FORFEIT_WIN,  # TRF forfeit win notation
            "-": GameResult.P2_FORFEIT_WIN,  # TRF forfeit loss notation
        }

        game_result = result_map.get(result)
        if not game_result:
            raise ValueError(f"Invalid result: {result}")

        # For knockout tournaments, find existing match and add game
        if self.tournament.format == TournamentFormat.KNOCKOUT:
            # Find existing match between these players
            target_match = None
            for i, match in enumerate(self.current_round.matches):
                if ((match.competitor1_id == player1_id and match.competitor2_id == player2_id) or
                    (match.competitor1_id == player2_id and match.competitor2_id == player1_id)):
                    target_match = (i, match)
                    break
            
            if target_match is not None:
                match_index, existing_match = target_match
                
                # Create the new game
                player1_obj = Player(player1_id, player1_id)
                player2_obj = Player(player2_id, player2_id)
                
                # Ensure consistent player order in games within the match
                if existing_match.competitor1_id == player1_id:
                    new_game = Game(player1_obj, player2_obj, game_result)
                else:
                    # Flip the game result if player order is swapped
                    flipped_result = game_result
                    if game_result == GameResult.P1_WIN:
                        flipped_result = GameResult.P2_WIN
                    elif game_result == GameResult.P2_WIN:
                        flipped_result = GameResult.P1_WIN
                    new_game = Game(player2_obj, player1_obj, flipped_result)
                
                # Update match with new game
                updated_match = Match(
                    competitor1_id=existing_match.competitor1_id,
                    competitor2_id=existing_match.competitor2_id,
                    games=existing_match.games + [new_game],
                    is_bye=existing_match.is_bye,
                    games_per_match=existing_match.games_per_match,
                    manual_tiebreak_value=existing_match.manual_tiebreak_value
                )
                self.current_round.matches[match_index] = updated_match
                return self
        
        # Default behavior: create single-game match (for Swiss or single-game knockout)
        player1_obj = Player(player1_id, player1_id) 
        player2_obj = Player(player2_id, player2_id)
        game = Game(player1_obj, player2_obj, game_result)
        
        match = Match(
            competitor1_id=player1_id,
            competitor2_id=player2_id,
            games=[game],
            games_per_match=1
        )
        self.current_round.matches.append(match)
        return self

    def add_team_match(
        self, team1_id: int, team2_id: int, board_results: List[Tuple[int, int, str]]
    ) -> "TournamentBuilder":
        """Add a team match to the current round.

        Args:
            team1_id: First team ID
            team2_id: Second team ID
            board_results: List of (player1_id, player2_id, result_str) for each board
        """
        if not self.current_round:
            raise ValueError("Must add a round before adding matches")

        result_map = {
            "1-0": GameResult.P1_WIN,
            "1/2-1/2": GameResult.DRAW,
            "0-1": GameResult.P2_WIN,
            "1X-0F": GameResult.P1_FORFEIT_WIN,
            "0F-1X": GameResult.P2_FORFEIT_WIN,
            "0F-0F": GameResult.DOUBLE_FORFEIT,
            "+": GameResult.P1_FORFEIT_WIN,  # TRF forfeit win notation
            "-": GameResult.P2_FORFEIT_WIN,  # TRF forfeit loss notation
        }

        # Convert string results to GameResult enums
        converted_results = []
        for p1_id, p2_id, result_str in board_results:
            game_result = result_map.get(result_str)
            if not game_result:
                raise ValueError(f"Invalid result: {result_str}")
            converted_results.append((p1_id, p2_id, game_result))

        match = create_team_match(team1_id, team2_id, converted_results)
        # Update with games_per_match
        updated_match = Match(
            competitor1_id=match.competitor1_id,
            competitor2_id=match.competitor2_id,
            games=match.games,
            is_bye=match.is_bye,
            games_per_match=self._games_per_match
        )
        self.current_round.matches.append(updated_match)
        return self

    def add_team_match_with_mapping(
        self,
        team1_id: int,
        team2_id: int,
        board_results: List[Tuple[int, int, str]],
        player_team_mapping: Dict[int, int],
    ) -> "TournamentBuilder":
        """Add a team match with player-to-team mapping.
        
        Args:
            team1_id: First team ID
            team2_id: Second team ID
            board_results: List of (player1_id, player2_id, result_str) 
            player_team_mapping: Dict mapping player_id to team_id
        """
        if not self.current_round:
            raise ValueError("Must add a round before adding matches")

        result_map = {
            "1-0": GameResult.P1_WIN,
            "1/2-1/2": GameResult.DRAW,
            "0-1": GameResult.P2_WIN,
            "1X-0F": GameResult.P1_FORFEIT_WIN,
            "0F-1X": GameResult.P2_FORFEIT_WIN,
            "0F-0F": GameResult.DOUBLE_FORFEIT,
            "+": GameResult.P1_FORFEIT_WIN,  # TRF forfeit win notation
            "-": GameResult.P2_FORFEIT_WIN,  # TRF forfeit loss notation
        }

        # Convert string results to GameResult enums
        converted_results = []
        for p1_id, p2_id, result_str in board_results:
            game_result = result_map.get(result_str)
            if not game_result:
                raise ValueError(f"Invalid result: {result_str}")
            converted_results.append((p1_id, p2_id, game_result))

        # For knockout tournaments, find existing match and update it
        if self.tournament.format == TournamentFormat.KNOCKOUT:
            # Find existing match between these teams
            # In multi-match scenarios, prefer exact order match (for return matches)
            target_match = None
            
            # First, try to find exact order match
            for i, existing_match in enumerate(self.current_round.matches):
                if existing_match.competitor1_id == team1_id and existing_match.competitor2_id == team2_id:
                    target_match = (i, existing_match)
                    break
            
            # If no exact match found, look for reverse order match
            if target_match is None:
                for i, existing_match in enumerate(self.current_round.matches):
                    if existing_match.competitor1_id == team2_id and existing_match.competitor2_id == team1_id:
                        target_match = (i, existing_match)
                        break
            
            if target_match is not None:
                match_index, existing_match = target_match
                
                # Create the team match with results
                new_match = create_team_match(team1_id, team2_id, converted_results, player_team_mapping)
                
                # Update with existing match properties
                updated_match = Match(
                    competitor1_id=existing_match.competitor1_id,
                    competitor2_id=existing_match.competitor2_id,
                    games=new_match.games,  # Use new games
                    is_bye=existing_match.is_bye,
                    games_per_match=existing_match.games_per_match,
                    manual_tiebreak_value=existing_match.manual_tiebreak_value
                )
                self.current_round.matches[match_index] = updated_match
                return self
        
        # Default behavior: create new match (for Swiss tournaments)
        match = create_team_match(team1_id, team2_id, converted_results, player_team_mapping)
        # Update with games_per_match
        updated_match = Match(
            competitor1_id=match.competitor1_id,
            competitor2_id=match.competitor2_id,
            games=match.games,
            is_bye=match.is_bye,
            games_per_match=self._games_per_match
        )
        self.current_round.matches.append(updated_match)
        return self

    def add_bye(
        self, competitor_id: int, games_per_match: int = None
    ) -> "TournamentBuilder":
        """Add a bye for a competitor in the current round."""
        if not self.current_round:
            raise ValueError("Must add a round before adding byes")

        # Use instance games_per_match if not specified
        if games_per_match is None:
            games_per_match = self._games_per_match

        match = create_bye_match(competitor_id, games_per_match)
        self.current_round.matches.append(match)
        return self

    def auto_byes(self, games_per_match: int = None) -> "TournamentBuilder":
        """Automatically add byes for competitors who haven't played in current round."""
        if not self.current_round:
            raise ValueError("Must add a round before adding byes")

        # Use instance games_per_match if not specified
        if games_per_match is None:
            games_per_match = self._games_per_match

        # Find who has already played
        played = set()
        for match in self.current_round.matches:
            played.add(match.competitor1_id)
            if match.competitor2_id != -1:  # -1 is bye opponent
                played.add(match.competitor2_id)

        # Add byes for those who haven't played
        for comp_id in self.tournament.competitors:
            if comp_id not in played:
                self.add_bye(comp_id, games_per_match)

        return self

    def build(self) -> Tournament:
        """Return the built tournament."""
        # Add name mappings to the tournament for assertion purposes
        tournament = self.tournament

        # Build name to ID mapping based on competitor type
        if self.metadata.competitor_type == "team":
            tournament.name_to_id = {
                team_info["name"]: team_info["id"]
                for team_info in self.metadata.teams.values()
            }
        else:
            # For individual tournaments, use player names
            tournament.name_to_id = self.metadata.players.copy()

        return tournament

    # Helper methods

    def _get_or_create_player_id(self, name: str) -> int:
        """Get or create a player ID for a named player."""
        if name not in self.metadata.players:
            self.metadata.players[name] = self._next_player_id
            self._next_player_id += 1
        return self.metadata.players[name]

    def _get_competitor_id(self, name: str) -> int:
        """Get competitor ID for a name (team or player)."""
        if self.metadata.competitor_type == "team":
            team_info = self.metadata.teams.get(name)
            if not team_info:
                raise ValueError(f"Team not found: {name}")
            return team_info["id"]
        else:
            player_id = self.metadata.players.get(name)
            if player_id is None:
                raise ValueError(f"Player not found: {name}")
            return player_id

    def _generate_knockout_bracket(self, teams: List[str], format: str) -> None:
        """Generate first round knockout bracket and add to tournament."""
        # Get team IDs in seeding order
        team_ids = [self._get_competitor_id(name) for name in teams]
        
        # Generate pairings
        if format == "traditional":
            pairings = generate_knockout_seedings_traditional(team_ids)
        else:  # adjacent
            pairings = generate_knockout_seedings_adjacent(team_ids)
        
        # Create first round if not already created
        stage_name = get_knockout_stage_name(len(teams))
        if not self.current_round:
            self.add_round(1)
        self.knockout_stage(stage_name)
        
        # Add matches for each pairing
        for team1_id, team2_id in pairings:
            match = Match(
                competitor1_id=team1_id,
                competitor2_id=team2_id,
                games=[],  # Will be filled when results are added
                games_per_match=self._games_per_match
            )
            self.current_round.matches.append(match)
