"""
Team seeder for creating test teams.
"""

import random
from typing import List
from heltour.tournament.models import Team, TeamMember, Season, SeasonPlayer
from .base import BaseSeeder


class TeamSeeder(BaseSeeder):
    """Seeder for creating Team objects."""

    # Team name components for generation
    ADJECTIVES = [
        "Royal",
        "Swift",
        "Mighty",
        "Silent",
        "Golden",
        "Silver",
        "Crimson",
        "Azure",
        "Fierce",
        "Noble",
        "Ancient",
        "Modern",
        "Tactical",
        "Strategic",
        "Dynamic",
        "Lightning",
        "Thunder",
        "Storm",
        "Fire",
        "Ice",
        "Shadow",
        "Brilliant",
    ]

    NOUNS = [
        "Knights",
        "Bishops",
        "Rooks",
        "Queens",
        "Kings",
        "Pawns",
        "Masters",
        "Tacticians",
        "Strategists",
        "Defenders",
        "Attackers",
        "Gladiators",
        "Warriors",
        "Champions",
        "Legends",
        "Eagles",
        "Lions",
        "Tigers",
        "Dragons",
        "Phoenix",
        "Falcons",
        "Sharks",
        "Wolves",
    ]

    def seed(self, season: Season, **kwargs) -> List[Team]:
        """Create teams for a team league season."""
        teams = []

        if not season.league.is_team_league():
            return teams

        # Get approved season players
        season_players = list(
            SeasonPlayer.objects.filter(season=season, is_active=True).select_related(
                "player"
            )
        )

        if not season_players:
            return teams

        # Calculate number of teams based on players and boards
        boards = season.boards or 4
        num_teams = len(season_players) // boards  # Exactly one player per board

        # For Swiss tournaments, ensure we have enough teams
        # At least 2x the number of rounds, preferably more
        min_teams_needed = season.rounds * 2
        num_teams = max(num_teams, min_teams_needed)
        num_teams = min(
            num_teams, len(season_players) // boards
        )  # Can't exceed available players

        # Ensure even number of teams (no byes)
        if num_teams % 2 == 1:
            num_teams -= 1  # Make it even

        # Shuffle players for random distribution
        random.shuffle(season_players)

        # Create teams
        used_names = set()
        for i in range(num_teams):
            # Generate unique team name
            team_name = self._generate_team_name(used_names)
            used_names.add(team_name)

            team_data = {
                "season": season,
                "number": i + 1,
                "name": team_name,
                "is_active": True,
                "slack_channel": (
                    f"team-{season.tag}-{i+1}" if self.weighted_bool(0.7) else ""
                ),
            }
            team_data.update(kwargs)

            team = Team.objects.create(**team_data)
            teams.append(self._track_object(team))

            # Assign players to team - exactly one per board
            players_needed = boards
            team_players = season_players[:players_needed]
            season_players = season_players[players_needed:]

            # Sort by rating to assign boards
            team_players.sort(
                key=lambda sp: sp.player.rating_for(season.league), reverse=True
            )

            # Create team members for all boards
            for board_num, sp in enumerate(team_players[:boards], 1):
                TeamMember.objects.create(
                    team=team,
                    player=sp.player,
                    board_number=board_num,
                    is_captain=board_num == 1,  # First board is captain
                    is_vice_captain=board_num == 2,  # Second board is vice-captain
                )

            # Note: In this system, alternates are handled separately via the Alternate model
            # They are not TeamMembers. Extra team players beyond the board count
            # would typically be handled through the alternates system.

        return teams

    def _generate_team_name(self, used_names: set) -> str:
        """Generate a unique team name."""
        attempts = 0
        while attempts < 100:
            adj = random.choice(self.ADJECTIVES)
            noun = random.choice(self.NOUNS)
            name = f"{adj} {noun}"

            if name not in used_names:
                return name

            # Try with a number suffix
            for i in range(2, 10):
                name_with_num = f"{name} {i}"
                if name_with_num not in used_names:
                    return name_with_num

            attempts += 1

        # Fallback to timestamp-based name
        return f"Team {self.fake.uuid4()[:8]}"
