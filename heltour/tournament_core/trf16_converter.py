"""
Converter from TRF16 format to tournament structure.

This module provides functionality to convert parsed TRF16 data into
our tournament_core structures, suitable for use with TournamentBuilder.
"""

from typing import Dict, List, Tuple, Optional
from heltour.tournament_core.trf16 import (
    TRF16Parser,
    TRF16Header,
    TRF16Player,
    TRF16Team,
    TRF16Pairing,
)
from heltour.tournament_core.builder import TournamentBuilder


class TRF16Converter:
    """Convert TRF16 data to tournament structures."""

    def __init__(self, trf16_content: str):
        """Initialize with TRF16 content."""
        self.parser = TRF16Parser(trf16_content)
        self.header: Optional[TRF16Header] = None
        self.players: Dict[int, TRF16Player] = {}
        self.teams: Dict[str, TRF16Team] = {}

    def parse(self):
        """Parse the TRF16 content."""
        self.header, self.players, self.teams = self.parser.parse_all()
        self.parser.update_board_numbers()

    def create_tournament_builder(self, league_tag: str = "TRF16") -> TournamentBuilder:
        """Create a TournamentBuilder with teams and players from TRF16.

        Args:
            league_tag: Tag for the league (default: "TRF16")
        """
        if not self.header:
            self.parse()

        builder = TournamentBuilder()

        # Set up league and season
        league_name = self.header.tournament_name

        # Configure tiebreaks based on TRF16 format
        # EGGSB BH:MP = Extended Game-Game Sonneborn-Berger, Buchholz, Match Points
        builder.league(
            name=league_name,
            tag=league_tag,
            type="team",  # TRF16 team format
            # Tiebreaks: Match points primary, then Game points, EGGSB, Buchholz
            team_tiebreak_1="game_points",  # After match points, use game points
            team_tiebreak_2="eggsb",  # EGGSB - Extended Game-Game Sonneborn-Berger
            team_tiebreak_3="buchholz",  # BH - Buchholz
            team_tiebreak_4="head_to_head",  # Additional tiebreak
        )

        # Determine boards per team
        max_boards = max(len(team.player_ids) for team in self.teams.values())

        builder.season(
            league_tag=league_tag,
            name=f"{league_name} {self.header.start_date.year}",
            rounds=self.header.num_rounds,
            boards=max_boards,
        )

        # Add teams and players
        self._add_teams_and_players(builder)

        return builder

    def add_rounds_to_builder_v2(
        self,
        builder: TournamentBuilder,
        rounds_to_add: Optional[List[int]] = None,
        boards_per_match: int = 6,
    ):
        """Add round pairings using ground-up two-pass approach.

        Pass 1: Parse individual player round data
        Pass 2: Aggregate into proper team vs team matches without synthetic opponents

        Args:
            builder: TournamentBuilder instance
            rounds_to_add: List of round numbers to add. If None, adds all rounds.
            boards_per_match: Number of boards per team match for bye scoring (default: 6)
        """
        if rounds_to_add is None:
            rounds_to_add = list(range(1, self.header.num_rounds + 1))

        for round_num in rounds_to_add:
            self._add_round_v2(builder, round_num, boards_per_match)

    def _add_round_v2(
        self, builder: TournamentBuilder, round_number: int, boards_per_match: int = 6
    ):
        """Ground-up approach: two-pass conversion from individual player data to team matches."""
        builder.round(round_number)

        # Pass 1: Parse individual player round data for all teams
        all_team_round_data = {}
        for team_name in builder.metadata.teams.keys():
            team_round_data = self._parse_team_round_data_v2(team_name, round_number)
            all_team_round_data[team_name] = team_round_data

        # Pass 2: Create team matches from aggregated data
        processed_teams = set()

        for team_name, team_round_data in all_team_round_data.items():
            if team_name in processed_teams:
                continue

            team_info = builder.metadata.teams[team_name]
            team_id = team_info["id"]

            if team_round_data["is_bye"]:
                # Team bye: no players played
                builder.add_bye(team_id, boards_per_match)
                processed_teams.add(team_name)
            else:
                # Team played: find opponent and create match
                opponent_team = team_round_data["primary_opponent"]

                if (
                    opponent_team
                    and opponent_team in all_team_round_data
                    and opponent_team not in processed_teams
                ):
                    # Create team vs team match
                    opponent_team_info = builder.metadata.teams[opponent_team]
                    opponent_id = opponent_team_info["id"]

                    # Create board results for the team match
                    # Ensure board results have team_name's players first (for correct scoring)
                    board_results = self._create_team_match_board_results(
                        team_name,
                        opponent_team,
                        team_round_data,
                        all_team_round_data[opponent_team],
                        first_team_name=team_name,  # Pass which team should be first
                    )

                    if board_results:
                        builder.add_team_match(team_id, opponent_id, board_results)
                        processed_teams.add(team_name)
                        processed_teams.add(opponent_team)
                else:
                    # No valid opponent or opponent already processed - treat as bye
                    builder.add_bye(team_id, boards_per_match)
                    processed_teams.add(team_name)

        builder.complete()

    def _parse_team_round_data_v2(self, team_name: str, round_number: int) -> Dict:
        """Parse round data for a single team (Pass 1)."""
        if team_name not in self.teams:
            return {"is_bye": True, "primary_opponent": None, "player_results": []}

        team = self.teams[team_name]
        player_results = []
        opponent_teams = {}
        has_any_games = False

        for player_id in team.player_ids:
            if player_id not in self.players:
                continue

            player = self.players[player_id]
            if round_number > len(player.results):
                continue

            opponent_id, color, result = player.results[round_number - 1]

            # Skip byes
            if opponent_id is None and color == "-" and result == "-":
                continue

            # Handle forfeit wins/losses
            if opponent_id == 0 and color == "-":
                if result == "+":
                    # Forfeit win
                    has_any_games = True
                    player_results.append(
                        {
                            "player_id": player_id,
                            "opponent_id": 0,
                            "color": color,
                            "result": result,
                            "opponent_team": "FORFEIT",
                        }
                    )
                # Forfeit losses (result == "-") don't count as games
                continue

            # Handle regular games
            if opponent_id and color in ["w", "b"]:
                has_any_games = True
                opponent_team = self._find_player_team(opponent_id)

                player_results.append(
                    {
                        "player_id": player_id,
                        "opponent_id": opponent_id,
                        "color": color,
                        "result": result,
                        "opponent_team": opponent_team,
                    }
                )

                if opponent_team:
                    opponent_teams[opponent_team] = (
                        opponent_teams.get(opponent_team, 0) + 1
                    )

        # Determine primary opponent (team we played most games against)
        primary_opponent = None
        if opponent_teams:
            primary_opponent = max(opponent_teams, key=opponent_teams.get)

        return {
            "is_bye": not has_any_games,
            "primary_opponent": primary_opponent,
            "player_results": player_results,
        }

    def _create_team_match_board_results(
        self,
        team1_name: str,
        team2_name: str,
        team1_data: Dict,
        team2_data: Dict,
        first_team_name: str,
    ) -> List[Tuple[int, int, str]]:
        """Create board results for a team vs team match (Pass 2).

        Returns board results where first_team_name's players are always in the
        first position, ensuring correct team scoring in the match structure.
        """
        board_results = []

        # Get team player sets for identification
        team1_players = set()
        team2_players = set()

        if team1_name in self.teams:
            team1_players = set(self.teams[team1_name].player_ids)
        if team2_name in self.teams:
            team2_players = set(self.teams[team2_name].player_ids)

        # Determine which team should be first
        if first_team_name == team1_name:
            first_team_players = team1_players
            second_team_players = team2_players
        else:
            first_team_players = team2_players
            second_team_players = team1_players

        # Find games between these two teams from both perspectives
        team1_games = [
            p for p in team1_data["player_results"] if p["opponent_team"] == team2_name
        ]
        team2_games = [
            p for p in team2_data["player_results"] if p["opponent_team"] == team1_name
        ]

        # Process all games, ensuring team1 players are always first
        all_games = team1_games + team2_games
        processed_pairs = set()

        for game in all_games:
            player_id = game["player_id"]
            opponent_id = game["opponent_id"]
            color = game["color"]
            result = game["result"]

            # Skip if we've already processed this player pair
            if (player_id, opponent_id) in processed_pairs or (
                opponent_id,
                player_id,
            ) in processed_pairs:
                continue
            processed_pairs.add((player_id, opponent_id))

            # Convert TRF result to standard format from this player's perspective
            standard_result = self._convert_trf_result_to_standard_format(result)

            # Determine which team this player belongs to and ensure first_team players are first
            if player_id in first_team_players:
                # This player is from the first team - they should be in first position
                # The result is from this player's perspective, keep it as-is
                board_results.append((player_id, opponent_id, standard_result))
            elif player_id in second_team_players:
                # This player is from the second team - first team player should be first
                # The result is from second team player's perspective, need to flip it
                flipped_result = self._flip_game_result(standard_result)
                board_results.append((opponent_id, player_id, flipped_result))

        # Handle forfeit wins from both teams, ensuring first_team players are first
        forfeit_games_team1 = [
            p for p in team1_data["player_results"] if p["opponent_team"] == "FORFEIT"
        ]
        forfeit_games_team2 = [
            p for p in team2_data["player_results"] if p["opponent_team"] == "FORFEIT"
        ]

        # Process all forfeit games
        for forfeit in forfeit_games_team1:
            player_id = forfeit["player_id"]
            if player_id in first_team_players:
                # First team forfeit win
                board_results.append((player_id, 0, "1X-0F"))
            else:
                # This shouldn't happen but handle it
                board_results.append((0, player_id, "0F-1X"))

        for forfeit in forfeit_games_team2:
            player_id = forfeit["player_id"]
            if player_id in first_team_players:
                # First team forfeit win
                board_results.append((player_id, 0, "1X-0F"))
            else:
                # Second team forfeit win, but put it in second position
                board_results.append((0, player_id, "0F-1X"))

        return board_results

    def _convert_trf_result_to_standard_format(self, result: str) -> str:
        """Convert TRF16 result to standard tournament format."""
        if result == "1":
            return "1-0"
        elif result == "0":
            return "0-1"
        elif result == "=" or result == "1/2":
            return "1/2-1/2"
        elif result == "+":
            return "1X-0F"  # Win by forfeit
        elif result == "-":
            return "0F-1X"  # Loss by forfeit
        else:
            return result  # Already in standard format or unknown

    def _flip_game_result(self, result: str) -> str:
        """Flip a game result when changing perspective (white <-> black)."""
        if result == "1-0":
            return "0-1"
        elif result == "0-1":
            return "1-0"
        elif result == "1X-0F":
            return "0F-1X"
        elif result == "0F-1X":
            return "1X-0F"
        else:
            return result  # Draws and other results stay the same

    def add_rounds_to_builder(
        self,
        builder: TournamentBuilder,
        rounds_to_add: Optional[List[int]] = None,
        boards_per_match: int = 6,
    ):
        """Add round pairings and results to the builder.

        Args:
            builder: TournamentBuilder instance
            rounds_to_add: List of round numbers to add. If None, adds all rounds.
            boards_per_match: Number of boards per team match for bye scoring (default: 6)
        """
        if rounds_to_add is None:
            rounds_to_add = list(range(1, self.header.num_rounds + 1))

        for round_num in rounds_to_add:
            self._add_round(builder, round_num, boards_per_match)

    def _add_teams_and_players(self, builder: TournamentBuilder):
        """Add all teams and their players to the builder."""
        # Create mapping of player line numbers to player data
        player_by_line = self.players

        # First, add all individual players with their actual IDs
        # This ensures the builder uses the correct player IDs
        for player_id, player in player_by_line.items():
            # Set the player ID mapping in the builder
            builder.metadata.players[player.name] = player_id
            if builder._next_player_id <= player_id:
                builder._next_player_id = player_id + 1

        # Add each team
        for team_name, team in self.teams.items():
            # Collect players for this team
            team_players = []

            for player_id in team.player_ids:
                if player_id in player_by_line:
                    player = player_by_line[player_id]
                    # Add as (name, rating) tuple
                    team_players.append((player.name, player.rating))

            # Add team with all its players
            if team_players:
                builder.team(team_name, *team_players)

    def _add_round(
        self, builder: TournamentBuilder, round_number: int, boards_per_match: int = 6
    ):
        """Add a single round's results for team-based Swiss tournament."""
        builder.round(round_number)

        # In this tournament format, teams don't play as complete units against other teams.
        # Instead, individual players are paired Swiss-style, but team standings are calculated
        # by aggregating individual results. Each team gets ONE result per round.

        for team_name, team_info in builder.metadata.teams.items():
            team_id = team_info["id"]

            # Calculate this team's aggregate result for the round
            team_round_data = self._calculate_single_team_round_result(
                team_name, round_number
            )

            if team_round_data["is_bye"]:
                # Team had a bye this round
                # Use specified boards_per_match for bye scoring
                builder.add_bye(team_id, boards_per_match)
            else:
                # Team played games - aggregate them into a single team result
                board_results = team_round_data["board_results"]

                if board_results:
                    # Calculate team's aggregate performance
                    wins = sum(1 for _, _, result in board_results if result == "1-0")
                    draws = sum(
                        1 for _, _, result in board_results if result == "1/2-1/2"
                    )
                    losses = sum(1 for _, _, result in board_results if result == "0-1")

                    # Determine if team won, lost, or drew the round overall
                    team_score = wins + 0.5 * draws
                    total_games = wins + draws + losses

                    if total_games == 0:
                        continue  # No games played

                    # Create a team match against a synthetic opponent representing "the field"
                    # Use a consistent synthetic opponent ID
                    synthetic_opponent_id = -1

                    # Create board results for the team match
                    # Use the actual individual results but against the synthetic opponent
                    synthetic_board_results = board_results.copy()
                    # Replace the opponent IDs with our synthetic opponent
                    for i, (player_id, _, result) in enumerate(synthetic_board_results):
                        synthetic_board_results[i] = (
                            player_id,
                            synthetic_opponent_id,
                            result,
                        )

                    builder.add_team_match(
                        team_id, synthetic_opponent_id, synthetic_board_results
                    )

        builder.complete()

    def _parse_player_round_data(
        self, round_number: int
    ) -> Dict[int, Tuple[Optional[int], str, str]]:
        """Parse individual player results for a specific round.

        Returns:
            Dict[player_id] = (opponent_id, color, result)
        """
        player_data = {}

        for player_id, player in self.players.items():
            if round_number <= len(player.results):
                result_data = player.results[round_number - 1]
                opponent_id, color, result = result_data
                player_data[player_id] = (opponent_id, color, result)
            else:
                # Player has no result for this round
                player_data[player_id] = (None, "-", "-")

        return player_data

    def _create_team_matches_from_player_data(
        self,
        builder: TournamentBuilder,
        round_number: int,
        player_round_data: Dict[int, Tuple[Optional[int], str, str]],
        boards_per_match: int,
    ):
        """Create aggregated team results from individual player data.

        This is a Swiss tournament where players are paired individually,
        but team standings are calculated by aggregating individual results.
        Each team gets exactly ONE result per round.
        """
        for team_name, team_info in builder.metadata.teams.items():
            team_id = team_info["id"]
            team = self.teams[team_name]

            # Check if this team has a bye (all players have "0000 - -")
            if self._team_has_bye_in_round_from_data(team, player_round_data):
                builder.add_bye(team_id, boards_per_match)
                continue

            # Aggregate this team's individual results for the round
            team_board_results = self._aggregate_team_results_for_round(
                team, player_round_data
            )

            if team_board_results:
                # Find the primary opponent team (the one we played the most games against)
                primary_opponent = self._find_primary_opponent_team(team_board_results)

                if primary_opponent and primary_opponent != team_name:
                    # Valid opponent team found
                    opponent_team_info = builder.metadata.teams[primary_opponent]
                    opponent_team_id = opponent_team_info["id"]

                    builder.add_team_match(
                        team_id, opponent_team_id, team_board_results
                    )
                else:
                    # No valid opponent or playing against self - treat as team bye
                    builder.add_bye(team_id, boards_per_match)
            else:
                # No board results - treat as team bye
                builder.add_bye(team_id, boards_per_match)

    def _team_has_bye_in_round_from_data(
        self,
        team: TRF16Team,
        player_round_data: Dict[int, Tuple[Optional[int], str, str]],
    ) -> bool:
        """Check if a team has a bye based on player round data."""
        for player_id in team.player_ids:
            if player_id in player_round_data:
                opponent_id, color, result = player_round_data[player_id]
                # If any player has a real pairing (not "0000 - -"), team doesn't have bye
                if opponent_id is not None or color != "-" or result != "-":
                    return False
        return True

    def _aggregate_team_results_for_round(
        self,
        team: TRF16Team,
        player_round_data: Dict[int, Tuple[Optional[int], str, str]],
    ) -> List[Tuple[int, int, str]]:
        """Aggregate individual player results into team board results."""
        board_results = []

        for player_id in team.player_ids:
            if player_id in player_round_data:
                opponent_id, color, result = player_round_data[player_id]

                # Skip byes
                if opponent_id is None and color == "-" and result == "-":
                    continue

                # Handle forfeits
                if opponent_id == 0 and color == "-":
                    if result == "+":
                        # Forfeit win - create dummy opponent
                        board_results.append((player_id, 0, "1X-0F"))
                    continue

                # Handle regular games
                if opponent_id and color in ["w", "b"]:
                    game_result = self._convert_trf_result_to_standard(result, color)

                    if color == "w":  # This player is white
                        board_results.append((player_id, opponent_id, game_result))
                    else:  # This player is black, flip to maintain white-first convention
                        flipped_result = game_result
                        if game_result == "1-0":
                            flipped_result = "0-1"
                        elif game_result == "0-1":
                            flipped_result = "1-0"
                        elif game_result == "1X-0F":
                            flipped_result = "0F-1X"
                        elif game_result == "0F-1X":
                            flipped_result = "1X-0F"
                        board_results.append((opponent_id, player_id, flipped_result))

        return board_results

    def _find_primary_opponent_team(
        self, board_results: List[Tuple[int, int, str]]
    ) -> Optional[str]:
        """Find the primary opponent team from board results."""
        if not board_results:
            return None

        # Count games against each opponent team
        opponent_team_counts = {}

        for white_player, black_player, result in board_results:
            # Skip forfeits (opponent_id = 0)
            if black_player == 0:
                continue

            opponent_team = self._find_player_team(black_player)
            if opponent_team:
                opponent_team_counts[opponent_team] = (
                    opponent_team_counts.get(opponent_team, 0) + 1
                )

        if not opponent_team_counts:
            # No valid opponents found (all forfeits or invalid)
            return None

        # Return the team we played the most games against
        return max(opponent_team_counts, key=opponent_team_counts.get)

    def _find_opponent_teams(
        self,
        team: TRF16Team,
        player_round_data: Dict[int, Tuple[Optional[int], str, str]],
    ) -> set[str]:
        """Find which team(s) this team played against in the round."""
        opponent_teams = set()

        for player_id in team.player_ids:
            if player_id in player_round_data:
                opponent_id, color, result = player_round_data[player_id]

                # Skip byes and forfeits
                if opponent_id is None or opponent_id == 0:
                    continue

                # Find which team the opponent belongs to
                opponent_team = self._find_player_team(opponent_id)
                if opponent_team and opponent_team != team.name:
                    opponent_teams.add(opponent_team)

        return opponent_teams

    def _create_board_results_for_teams(
        self,
        team1_name: str,
        team2_name: str,
        player_round_data: Dict[int, Tuple[Optional[int], str, str]],
    ) -> List[Tuple[int, int, str]]:
        """Create board results for a match between two teams."""
        board_results = []
        team1 = self.teams[team1_name]
        team2 = self.teams[team2_name]

        # Find all games between players from these two teams
        team_games = []

        for player1_id in team1.player_ids:
            if player1_id in player_round_data:
                opponent_id, color, result = player_round_data[player1_id]

                # Check if opponent belongs to team2
                if opponent_id and self._find_player_team(opponent_id) == team2_name:
                    # Convert TRF result to standard format
                    game_result = self._convert_trf_result_to_standard(result, color)

                    if color == "w":  # player1 is white
                        team_games.append((player1_id, opponent_id, game_result))
                    else:  # player1 is black, flip the result
                        flipped_result = game_result
                        if game_result == "1-0":
                            flipped_result = "0-1"
                        elif game_result == "0-1":
                            flipped_result = "1-0"
                        elif game_result == "1X-0F":
                            flipped_result = "0F-1X"
                        elif game_result == "0F-1X":
                            flipped_result = "1X-0F"
                        team_games.append((opponent_id, player1_id, flipped_result))

        # Handle forfeits (opponent_id = 0)
        for player1_id in team1.player_ids:
            if player1_id in player_round_data:
                opponent_id, color, result = player_round_data[player1_id]

                if opponent_id == 0 and color == "-" and result == "+":
                    # Forfeit win - need to find an opponent from team2 who forfeited
                    for player2_id in team2.player_ids:
                        if player2_id in player_round_data:
                            opp_opponent_id, opp_color, opp_result = player_round_data[
                                player2_id
                            ]
                            if (
                                opp_opponent_id == 0
                                and opp_color == "-"
                                and opp_result == "-"
                            ):
                                # Found the forfeit pair
                                team_games.append((player1_id, player2_id, "1X-0F"))
                                break

        return team_games

    def _convert_trf_result_to_standard(self, result: str, color: str) -> str:
        """Convert TRF16 result to standard format."""
        if result == "1":
            return "1-0"
        elif result == "0":
            return "0-1"
        elif result == "1/2" or result == "=":
            return "1/2-1/2"
        elif result == "+":
            return "1X-0F"  # Win by forfeit
        elif result == "-":
            return "0F-1X"  # Loss by forfeit
        else:
            return result  # Already in standard format or unknown

    def _group_pairings_by_actual_teams(
        self, pairings: List[TRF16Pairing], round_number: int
    ) -> Dict[Tuple[str, str], List[Tuple[int, int, str]]]:
        """Group pairings by actual team matchups.

        In a Swiss team tournament, we need to determine which teams are actually
        playing each other by looking at the player pairings.
        """
        # First, collect all team-to-team games
        team_connections = {}  # (team1, team2) -> count of games between them
        all_pairings = []  # Store all valid pairings

        for pairing in pairings:
            white_player = self.players.get(pairing.white_player_id)
            black_player = self.players.get(pairing.black_player_id)

            if not white_player or not black_player:
                continue

            white_team = self._find_player_team(pairing.white_player_id)
            black_team = self._find_player_team(pairing.black_player_id)

            if white_team and black_team and white_team != black_team:
                team_key = tuple(sorted([white_team, black_team]))
                if team_key not in team_connections:
                    team_connections[team_key] = 0
                team_connections[team_key] += 1

                all_pairings.append((pairing, white_team, black_team))

        # Find the primary team matchup (the one with the most games)
        if not team_connections:
            return {}

        primary_matchup = max(team_connections.items(), key=lambda x: x[1])
        primary_teams = primary_matchup[0]

        # Group board results for the primary matchup
        team_matches = {}
        board_results = []

        for pairing, white_team, black_team in all_pairings:
            team_key = tuple(sorted([white_team, black_team]))
            if team_key == primary_teams:
                # This is part of the main team match
                result = pairing.result

                # Convert draw notation
                if result == "=":
                    result = "1/2-1/2"

                # Determine board order based on team alphabetical order
                if white_team == primary_teams[0]:
                    # White team is first alphabetically
                    board_results.append(
                        (pairing.white_player_id, pairing.black_player_id, result)
                    )
                else:
                    # Black team is first alphabetically, flip result
                    flipped_result = result
                    if result == "1-0":
                        flipped_result = "0-1"
                    elif result == "0-1":
                        flipped_result = "1-0"
                    board_results.append(
                        (
                            pairing.black_player_id,
                            pairing.white_player_id,
                            flipped_result,
                        )
                    )

        if board_results:
            team_matches[primary_teams] = board_results

        return team_matches

    def _group_pairings_by_teams(
        self, pairings: List[TRF16Pairing], round_number: int = 1
    ) -> Dict[Tuple[str, str], List[Tuple[int, str]]]:
        """Group individual pairings into team matches for a specific round.

        For team tournaments, we pair teams based on actual player pairings.
        Only pairings from the current round should be included.

        Args:
            pairings: List of individual pairings for this specific round
            round_number: Round number (needed for forfeit handling)

        Returns:
            Dict mapping (white_team, black_team) to list of (board_number, result)
        """

        # Collect team-to-team pairings for this round only
        team_to_team = {}  # (white_team, black_team) -> list of games

        for pairing in pairings:

            white_player = self.players.get(pairing.white_player_id)
            black_player = self.players.get(pairing.black_player_id)

            # Handle forfeit wins (opponent ID is 0) - skip these in the normal pairing logic
            is_forfeit_win = pairing.black_player_id == 0 and pairing.result == "1X-0F"
            if is_forfeit_win:
                continue  # Handle forfeits separately

            if not white_player or not black_player:
                continue

            white_team = self._find_player_team(pairing.white_player_id)
            black_team = self._find_player_team(pairing.black_player_id)

            if white_team and black_team and white_team != black_team:
                # Create team match key (sorted to be consistent)
                team_key = tuple(sorted([white_team, black_team]))

                if team_key not in team_to_team:
                    team_to_team[team_key] = []

                # Determine which team is "white" in this match
                if white_team == team_key[0]:
                    # White team is first in sorted order
                    team_to_team[team_key].append(
                        {
                            "white_player_id": pairing.white_player_id,
                            "black_player_id": pairing.black_player_id,
                            "result": pairing.result,
                        }
                    )
                else:
                    # Black team is first in sorted order, flip colors and result
                    flipped_result = pairing.result
                    if flipped_result == "1-0":
                        flipped_result = "0-1"
                    elif flipped_result == "0-1":
                        flipped_result = "1-0"
                    elif flipped_result == "1X-0F":
                        flipped_result = "0F-1X"
                    elif flipped_result == "0F-1X":
                        flipped_result = "1X-0F"

                    team_to_team[team_key].append(
                        {
                            "white_player_id": pairing.black_player_id,
                            "black_player_id": pairing.white_player_id,
                            "result": flipped_result,
                        }
                    )

        # Convert to the expected format for team matches
        team_matches = {}

        for (team1, team2), games in team_to_team.items():
            # Store player info for later use - key by round and teams
            if not hasattr(self, "_board_players"):
                self._board_players = {}

            round_key = (round_number, team1, team2)
            board_results = []
            self._board_players[round_key] = {}

            for i, game in enumerate(games):
                board_num = i + 1
                board_results.append((board_num, game["result"]))

                # Store player mapping for this board
                self._board_players[round_key][board_num] = (
                    game["white_player_id"],
                    game["black_player_id"],
                )

            team_matches[(team1, team2)] = board_results

        return team_matches

    def _calculate_team_round_results(self, round_number: int) -> Dict[str, Dict]:
        """Calculate aggregate results for each team in a specific round.

        Returns dict mapping team_name to:
        {
            "is_bye": bool,
            "games": List[str],  # List of game results for team players
            "player_ids": List[int]  # List of player IDs who played
        }
        """
        team_results = {}

        # Initialize all teams
        for team_name in self.teams:
            team_results[team_name] = {"is_bye": True, "games": [], "player_ids": []}

        # Check each player's result for this round
        for player_id, player in self.players.items():
            if round_number <= len(player.results):
                result_data = player.results[round_number - 1]
                opponent_id, color, result = result_data

                # Find which team this player belongs to
                team_name = self._find_player_team(player_id)
                if not team_name:
                    continue

                # Check if player had a bye or played a game
                if opponent_id is None and color == "-" and result == "-":
                    # Player had a bye - team bye status remains True
                    continue
                elif opponent_id == 0 and color == "-":
                    # Forfeit result
                    if result == "+":
                        # Forfeit win
                        team_results[team_name]["is_bye"] = False
                        team_results[team_name]["games"].append("1X-0F")
                        team_results[team_name]["player_ids"].append(player_id)
                    # Note: forfeit losses ("-") don't create games
                elif opponent_id and color in ["w", "b"]:
                    # Regular game
                    team_results[team_name]["is_bye"] = False

                    # Convert result to standard format
                    if result == "1":
                        game_result = "1-0"
                    elif result == "0":
                        game_result = "0-1"
                    elif result == "1/2":
                        game_result = "1/2-1/2"
                    else:
                        # Handle other forfeit results
                        game_result = result

                    team_results[team_name]["games"].append(game_result)
                    team_results[team_name]["player_ids"].append(player_id)

        return team_results

    def _calculate_single_team_round_result(
        self, team_name: str, round_number: int
    ) -> Dict:
        """Calculate results for a single team in a specific round.

        Returns:
        {
            "is_bye": bool,
            "board_results": List[Tuple[int, int, str]]  # (white_player_id, opponent_id, result)
        }
        """
        if team_name not in self.teams:
            return {"is_bye": True, "board_results": []}

        team = self.teams[team_name]
        board_results = []
        has_any_games = False

        # Check each player on this team
        for player_id in team.player_ids:
            if player_id not in self.players:
                continue

            player = self.players[player_id]
            if round_number > len(player.results):
                continue

            result_data = player.results[round_number - 1]
            opponent_id, color, result = result_data

            # Skip byes
            if opponent_id is None and color == "-" and result == "-":
                continue

            # Handle forfeit wins
            if opponent_id == 0 and color == "-" and result == "+":
                has_any_games = True
                board_results.append((player_id, -1, "1X-0F"))  # Win by forfeit
                continue

            # Skip forfeit losses
            if opponent_id == 0 and color == "-" and result == "-":
                continue

            # Handle regular games
            if opponent_id and color in ["w", "b"]:
                has_any_games = True

                # Convert result to standard format
                if result == "1":
                    game_result = "1-0"
                elif result == "0":
                    game_result = "0-1"
                elif result == "1/2" or result == "=":
                    game_result = "1/2-1/2"
                else:
                    game_result = result

                board_results.append((player_id, -1, game_result))

        return {"is_bye": not has_any_games, "board_results": board_results}

    def _find_player_team(self, player_id: int) -> Optional[str]:
        """Find which team a player belongs to."""
        for team_name, team in self.teams.items():
            if player_id in team.player_ids:
                return team_name
        return None

    def _team_has_bye_in_round(self, team_name: str, round_number: int) -> bool:
        """Check if a team has a bye in a specific round.

        A team has a bye if all its players have "0000 - -" results for that round.
        """
        if team_name not in self.teams:
            return False

        team = self.teams[team_name]

        # Check all players on this team
        for player_id in team.player_ids:
            if player_id in self.players:
                player = self.players[player_id]
                if round_number <= len(player.results):
                    # Round results are 0-indexed, so round_number - 1
                    round_result = player.results[round_number - 1]
                    opponent_id, color, result = round_result

                    # If any player has a real pairing (not "0000 - -"), team doesn't have bye
                    if opponent_id is not None or color != "-" or result != "-":
                        return False

        return True

    def get_team_standings_after_round(
        self, round_number: int
    ) -> Dict[str, Dict[str, float]]:
        """Calculate team standings after a specific round.

        Returns:
            Dict mapping team name to {'match_points': float, 'game_points': float}
        """
        # This would calculate standings based on parsed results
        # Useful for validating against TRF16's reported standings
        standings = {}

        # Initialize standings for each team
        for team_name in self.teams:
            standings[team_name] = {"match_points": 0.0, "game_points": 0.0}

        # Process results up to the specified round
        # Implementation would go here

        return standings
