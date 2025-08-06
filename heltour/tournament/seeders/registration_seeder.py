"""
Registration seeder for creating test registrations.
"""

import random
from typing import List
from heltour.tournament.models import (
    Registration,
    Season,
    Player,
    SeasonPlayer,
    Alternate,
)
from .base import BaseSeeder


class RegistrationSeeder(BaseSeeder):
    """Seeder for creating Registration objects."""

    def seed(
        self, season: Season, players: List[Player] = None, **kwargs
    ) -> List[Registration]:
        """Create registrations for a season."""
        registrations = []

        if players is None:
            players = list(Player.objects.filter(is_active=True))

        if not players:
            raise ValueError("No players found. Please create players first.")

        # Determine how many players to register based on season state
        # For team leagues, we need enough for proper Swiss tournaments
        if season.league.is_team_league():
            boards = season.boards or 4
            min_teams_needed = season.rounds * 2  # Swiss needs 2x rounds
            min_players_needed = min_teams_needed * boards

            if season.is_completed or season.is_active:
                # Need enough players for all teams
                num_registrations = min(
                    len(players), max(min_players_needed, len(players) - 5)
                )
            elif season.registration_open:
                # Open registration - some have registered
                num_registrations = min(
                    len(players),
                    random.randint(min_players_needed // 2, min_players_needed),
                )
            else:
                # Not open yet
                return []
        else:
            # Individual leagues
            if season.is_completed:
                num_registrations = min(len(players), random.randint(40, 60))
            elif season.is_active:
                num_registrations = min(len(players), random.randint(35, 50))
            elif season.registration_open:
                num_registrations = min(len(players), random.randint(15, 30))
            else:
                return []

        # Select random players to register
        selected_players = random.sample(players, num_registrations)

        for player in selected_players:
            # Check if already registered
            if Registration.objects.filter(
                season=season, player=player
            ).exists():
                continue

            # Determine registration status
            if season.registration_open:
                # Open registration - most are pending
                status_weights = [
                    ("pending", 0.7),
                    ("approved", 0.25),
                    ("rejected", 0.05),
                ]
            else:
                # Closed registration - most are approved
                status_weights = [
                    ("approved", 0.85),
                    ("rejected", 0.1),
                    ("pending", 0.05),
                ]

            status = self._weighted_choice(status_weights)

            reg_data = {
                "season": season,
                "player": player,
                "email": player.email,
                "status": status,
                "has_played_20_games": (
                    not player.provisional_for(season.league)
                    if hasattr(player, "provisional_for")
                    else True
                ),
                "can_commit": self.weighted_bool(0.95),
                "agreed_to_rules": True,
                "agreed_to_tos": True,
            }

            # Add preferences
            if self.weighted_bool(0.3):
                reg_data["friends"] = self._generate_friends_list(
                    selected_players, player
                )

            if self.weighted_bool(0.1):
                reg_data["avoid"] = self._generate_avoid_list(selected_players, player)

            # Alternate preference
            if season.league.is_team_league():
                reg_data["alternate_preference"] = random.choice(
                    [
                        "alternate",
                        "alternate",
                        "alternate",  # Most want to be alternates
                        "standby",
                        "standby",
                        "unavailable",
                    ]
                )

            # Weeks unavailable
            if self.weighted_bool(0.2):
                num_weeks = random.randint(1, 3)
                weeks = random.sample(range(1, season.rounds + 1), num_weeks)
                reg_data["weeks_unavailable"] = ",".join(map(str, sorted(weeks)))

            reg_data.update(kwargs)

            registration = Registration.objects.create(**reg_data)
            registrations.append(self._track_object(registration))

            # Create SeasonPlayer for approved registrations
            if status == "approved" and (season.is_active or season.is_completed):
                # Get player's rating for this league
                seed_rating = player.rating_for(season.league)

                sp = SeasonPlayer.objects.create(
                    season=season,
                    player=player,
                    is_active=self.weighted_bool(0.95),
                    games_missed=random.randint(0, 2) if season.is_completed else 0,
                    seed_rating=(
                        seed_rating if not season.league.is_team_league() else None
                    ),
                )

                # Some players are alternates
                if season.league.is_team_league() and self.weighted_bool(0.2):
                    Alternate.objects.create(
                        season_player=sp,
                        board_number=random.randint(1, season.boards or 4),
                    )

        return registrations

    def _weighted_choice(self, choices: List[tuple]) -> str:
        """Choose from weighted options."""
        total = sum(weight for _, weight in choices)
        r = random.uniform(0, total)
        upto = 0
        for choice, weight in choices:
            if upto + weight >= r:
                return choice
            upto += weight
        return choices[-1][0]

    def _generate_friends_list(self, players: List[Player], exclude: Player) -> str:
        """Generate a list of friends."""
        num_friends = random.randint(1, 3)
        potential_friends = [p for p in players if p != exclude]
        if not potential_friends:
            return ""

        friends = random.sample(
            potential_friends, min(num_friends, len(potential_friends))
        )
        return ", ".join(f.lichess_username for f in friends)

    def _generate_avoid_list(self, players: List[Player], exclude: Player) -> str:
        """Generate a list of players to avoid."""
        num_avoid = random.randint(1, 2)
        potential_avoid = [p for p in players if p != exclude]
        if not potential_avoid:
            return ""

        avoid = random.sample(potential_avoid, min(num_avoid, len(potential_avoid)))
        return ", ".join(a.lichess_username for a in avoid)
