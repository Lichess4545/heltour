"""
TRF16 (FIDE Tournament Report Format) parser for team tournaments.

This module provides parsing capabilities for TRF16 format files, breaking down
the parsing into modular components that can be used independently.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import re


@dataclass
class TRF16Header:
    """Tournament header information from TRF16 format."""

    tournament_name: str
    city: str
    federation: str
    start_date: datetime
    end_date: datetime
    num_players: int
    num_rated_players: int
    num_teams: int
    tournament_type: str
    chief_arbiter: str
    deputy_arbiters: List[str]
    time_control: str
    num_rounds: int
    round_dates: List[datetime] = field(default_factory=list)


@dataclass
class TRF16Player:
    """Player information from TRF16 format."""

    team_number: int
    board_number: int
    title: str
    name: str
    rating: int
    federation: str
    fide_id: str
    birth_year: int
    points: float
    rank: int
    start_number: int = 0  # The player's start number from TRF16

    # Round results - list of (opponent_id, color, result) tuples
    # opponent_id is the line number in the file (starting from 1)
    # color is 'w' or 'b'
    # result is '1', '0', '1/2', '-', '+', etc.
    results: List[Tuple[Optional[int], str, str]] = field(default_factory=list)


@dataclass
class TRF16Team:
    """Team information parsed from TRF16 format."""

    name: str
    player_ids: List[int]  # Line numbers of players in this team


@dataclass
class TRF16Pairing:
    """A pairing in a round."""

    round_number: int
    board_number: int
    white_player_id: int  # Line number
    black_player_id: int  # Line number
    result: str  # '1-0', '0-1', '1/2-1/2', etc.


class TRF16Parser:
    """Parser for TRF16 tournament report format."""

    def __init__(self, content: str):
        """Initialize parser with TRF16 content."""
        self.lines = content.strip().split("\n")
        self.header: Optional[TRF16Header] = None
        self.players: Dict[int, TRF16Player] = {}  # line number -> player
        self.teams: Dict[str, TRF16Team] = {}  # team name -> team

    def parse_header(self) -> TRF16Header:
        """Parse the header section of the TRF16 file."""
        # Find header lines (start with 0XX)
        header_data = {}
        round_dates = []

        for line in self.lines:
            if not line.strip():
                continue

            # Check if it's a header line
            if len(line) >= 3 and line[:3].isdigit():
                code = line[:3]
                data = line[4:].strip() if len(line) > 4 else ""

                if code == "012":  # Tournament name
                    header_data["tournament_name"] = data
                elif code == "022":  # City
                    header_data["city"] = data
                elif code == "032":  # Federation
                    header_data["federation"] = data
                elif code == "042":  # Start date
                    header_data["start_date"] = self._parse_date(data)
                elif code == "052":  # End date
                    header_data["end_date"] = self._parse_date(data)
                elif code == "062":  # Number of players (rated)
                    parts = data.split()
                    header_data["num_players"] = int(parts[0])
                    if len(parts) > 1 and parts[1].startswith("("):
                        header_data["num_rated_players"] = int(parts[1][1:-1])
                elif code == "072":  # Number of rated players
                    header_data["num_rated_players"] = (
                        int(data) if data else header_data.get("num_rated_players", 0)
                    )
                elif code == "082":  # Number of teams
                    header_data["num_teams"] = int(data)
                elif code == "092":  # Tournament type
                    header_data["tournament_type"] = data
                elif code == "102":  # Chief arbiter
                    header_data["chief_arbiter"] = data
                elif code == "112":  # Deputy arbiters
                    header_data["deputy_arbiters"] = data.split(", ")
                elif code == "122":  # Time control
                    header_data["time_control"] = data
                elif code == "132":  # Round dates
                    # Parse round dates from the line
                    date_str = line[4:].strip()
                    dates = re.findall(r"\d{2}/\d{2}/\d{2}", date_str)
                    for date in dates:
                        round_dates.append(self._parse_date(date))
                elif code == "142":  # Number of rounds
                    header_data["num_rounds"] = int(data)

        self.header = TRF16Header(
            tournament_name=header_data.get("tournament_name", ""),
            city=header_data.get("city", ""),
            federation=header_data.get("federation", ""),
            start_date=header_data.get("start_date", datetime.now()),
            end_date=header_data.get("end_date", datetime.now()),
            num_players=header_data.get("num_players", 0),
            num_rated_players=header_data.get("num_rated_players", 0),
            num_teams=header_data.get("num_teams", 0),
            tournament_type=header_data.get("tournament_type", ""),
            chief_arbiter=header_data.get("chief_arbiter", ""),
            deputy_arbiters=header_data.get("deputy_arbiters", []),
            time_control=header_data.get("time_control", ""),
            num_rounds=header_data.get("num_rounds", 0),
            round_dates=round_dates,
        )

        return self.header

    def parse_players(self) -> Dict[int, TRF16Player]:
        """Parse all player entries from the TRF16 file."""
        # Find the player data section
        # Player line format starts with "001" followed by player start number

        for line in self.lines:
            if line.startswith("001") and len(line) > 8:
                player = self._parse_player_line(line)
                if player:
                    # Extract the start number (positions 4-8)
                    try:
                        start_number = int(line[4:8].strip())
                        # Use start number as key - this is what teams reference
                        self.players[start_number] = player
                        # Also store the start number in the player object
                        player.start_number = start_number
                    except ValueError:
                        # Skip lines where we can't extract start number
                        continue

        return self.players

    def parse_teams(self) -> Dict[str, TRF16Team]:
        """Parse team information from the TRF16 file."""
        for line in self.lines:
            if line.startswith("013"):
                # Remove the "013" prefix
                team_data = line[3:]

                # Look for multiple spaces (2 or more) to find where team name ends
                # This handles team names with numbers like "ΓΑΖΙ 1"
                import re

                match = re.search(r"  +", team_data)

                if match:
                    # Team name is everything before the multiple spaces
                    team_name = team_data[: match.start()].strip()
                    # Player IDs are in the part after the multiple spaces
                    player_ids_str = team_data[match.end() :]
                    # Extract all numeric values as player IDs
                    player_ids = [
                        int(pid) for pid in player_ids_str.split() if pid.isdigit()
                    ]

                    if team_name and player_ids:
                        self.teams[team_name] = TRF16Team(
                            name=team_name, player_ids=player_ids
                        )

        return self.teams

    def parse_round_pairings(self, round_number: int) -> List[TRF16Pairing]:
        """Parse pairings for a specific round."""
        if not self.players:
            self.parse_players()

        pairings = []

        # For each player, look at their result in the specified round
        for player_id, player in self.players.items():
            if round_number <= len(player.results):
                result_data = player.results[round_number - 1]
                opponent_id, color, result = result_data

                # Handle forfeits (opponent_id=0, color="-", result="+" or "-")
                if opponent_id == 0 and color == "-":
                    if result == "+":  # Forfeit win
                        pairing = TRF16Pairing(
                            round_number=round_number,
                            board_number=player.board_number,
                            white_player_id=player_id,
                            black_player_id=0,  # No opponent
                            result=self._convert_result_format(result),
                        )
                        pairings.append(pairing)
                    # Note: We don't create pairings for forfeit losses (result="-")
                    # because there's no actual game played

                # Handle normal games
                elif opponent_id and color == "w":  # White player
                    # Create pairing (only from white's perspective to avoid duplicates)
                    pairing = TRF16Pairing(
                        round_number=round_number,
                        board_number=player.board_number,
                        white_player_id=player_id,
                        black_player_id=opponent_id,
                        result=self._convert_result_format(result),
                    )
                    pairings.append(pairing)

        return pairings

    def parse_all(
        self,
    ) -> Tuple[TRF16Header, Dict[int, TRF16Player], Dict[str, TRF16Team]]:
        """Parse the entire TRF16 file."""
        header = self.parse_header()
        players = self.parse_players()
        teams = self.parse_teams()
        return header, players, teams

    # Helper methods

    def _parse_date(self, date_str: str) -> datetime:
        """Parse date from TRF16 format (YYYY/MM/DD or YY/MM/DD)."""
        try:
            # Try YYYY/MM/DD format first
            return datetime.strptime(date_str, "%Y/%m/%d")
        except ValueError:
            try:
                # Try DD/MM/YY format (as seen in round dates)
                return datetime.strptime(date_str, "%d/%m/%y")
            except ValueError:
                # Default to today if parsing fails
                return datetime.now()

    def _parse_player_line(self, line: str) -> Optional[TRF16Player]:
        """Parse a single player line."""
        # Player lines start with "001" followed by player data
        # Instead of fixed positions, we'll parse more intelligently

        if not line.startswith("001") or len(line) < 90:
            return None

        try:
            # Split the line into parts
            parts = line.split()

            # Basic validation - we need at least the core fields
            if len(parts) < 10:
                return None

            # Parse core fields
            # parts[0] = "001"
            player_number = int(parts[1])
            title = parts[2]  # m/f

            # Name handling - find where the name ends by looking for a 4-digit number (rating)
            name_parts = []
            idx = 3
            while idx < len(parts) and not (
                parts[idx].isdigit() and len(parts[idx]) == 4
            ):
                name_parts.append(parts[idx])
                idx += 1
            name = " ".join(name_parts)

            # After name, we should have: rating, federation, FIDE ID, birth date
            if idx >= len(parts):
                return None

            rating = int(parts[idx]) if parts[idx] != "0000" else 0
            idx += 1

            federation = parts[idx] if idx < len(parts) else ""
            idx += 1

            fide_id = parts[idx] if idx < len(parts) else ""
            idx += 1

            # Birth date (YYYY/MM/DD format) - might be missing
            birth_str = parts[idx] if idx < len(parts) else ""

            # Check if this looks like a birth date or if it's actually points
            if "/" in birth_str:
                # It's a birth date
                birth_year = (
                    int(birth_str.split("/")[0])
                    if birth_str.split("/")[0].isdigit()
                    else 0
                )
                idx += 1
            else:
                # Birth date is missing, this might be points already
                # Check if it looks like points (contains decimal point)
                if "." in birth_str:
                    # This is points, birth date was missing
                    birth_year = 0
                    # Don't increment idx, we'll parse this as points next
                else:
                    # Ambiguous - could be rank or year without slashes
                    # For now assume it's missing birth date if it doesn't have /
                    birth_year = 0
                    # Don't increment idx

            # Points (decimal)
            points = (
                float(parts[idx]) if idx < len(parts) and "." in parts[idx] else 0.0
            )
            if idx < len(parts) and "." in parts[idx]:
                idx += 1

            # Rank
            rank = int(parts[idx]) if idx < len(parts) and parts[idx].isdigit() else 0
            idx += 1

            # Parse round results - remaining parts should be opponent/result pairs
            results = []
            while idx < len(parts):
                if (
                    idx + 2 < len(parts)
                    and parts[idx] == "0000"
                    and parts[idx + 1] == "-"
                ):
                    # Could be a bye (0000 - -) or forfeit (0000 - + or 0000 - -)
                    if parts[idx + 2] == "-":
                        # Bye round
                        results.append((None, "-", "-"))
                    elif parts[idx + 2] == "+":
                        # Forfeit win
                        results.append((0, "-", "+"))
                    else:
                        # Unknown format, treat as bye
                        results.append((None, "-", "-"))
                    idx += 3
                elif idx + 2 < len(parts):
                    # Normal result: opponent_id color result
                    opponent_str = parts[idx]
                    color = parts[idx + 1]
                    result = parts[idx + 2]

                    if opponent_str.isdigit():
                        opponent_id = int(opponent_str)
                        results.append((opponent_id, color, result))
                    else:
                        results.append((None, "-", "-"))
                    idx += 3
                else:
                    # Not enough parts for a complete result
                    break

            return TRF16Player(
                team_number=player_number,  # Will be updated when we parse teams
                board_number=0,  # Will be set later
                title=title,
                name=name,
                rating=rating,
                federation=federation,
                fide_id=fide_id,
                birth_year=birth_year,
                points=points,
                rank=rank,
                results=results,
                start_number=player_number,
            )

        except (ValueError, IndexError) as e:
            # Silently skip lines that can't be parsed
            return None

    def _convert_result_format(self, result: str) -> str:
        """Convert TRF16 result format to standard format."""
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
            return ""  # Unknown or no result

    def update_board_numbers(self):
        """Update board numbers for all players based on team assignments."""
        if not self.teams or not self.players:
            return

        for team_name, team in self.teams.items():
            board = 1
            for player_id in team.player_ids:
                if player_id in self.players:
                    self.players[player_id].board_number = board
                    board += 1
