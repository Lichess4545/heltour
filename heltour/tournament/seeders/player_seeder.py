"""
Player seeder for creating test players.
"""

import random
from datetime import timedelta
from typing import List
from django.contrib.auth.models import User
from heltour.tournament.models import Player, League
from .base import BaseSeeder


class PlayerSeeder(BaseSeeder):
    """Seeder for creating Player objects."""

    def seed(
        self, count: int = 20, leagues: List[League] = None, **kwargs
    ) -> List[Player]:
        """Create test players with ratings for different leagues."""
        players = []

        # Get all leagues if none specified
        if leagues is None:
            leagues = League.objects.all()

        for i in range(count):
            # Create unique username
            base_username = self.lichess_username()
            lichess_username = base_username
            suffix = 1

            while Player.objects.filter(
                lichess_username__iexact=lichess_username
            ).exists():
                lichess_username = f"{base_username}{suffix}"
                suffix += 1

            # Determine player strength (affects all ratings)
            strength_factor = random.random()  # 0-1, higher is stronger

            # Create timezone offset as a timedelta
            timezone_hours = random.choice([-8, -7, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3])

            player_data = {
                "lichess_username": lichess_username,
                "email": self.fake.email(),
                "is_active": self.weighted_bool(0.95),
                "slack_user_id": self.fake.uuid4() if self.weighted_bool(0.7) else "",
                "timezone_offset": (
                    timedelta(hours=timezone_hours) if self.weighted_bool(0.8) else None
                ),
            }
            player_data.update(kwargs)

            # Set ratings based on league rating types and player strength
            rating_base = {
                "classical": 1600,
                "rapid": 1550,
                "blitz": 1500,
                "bullet": 1450,
                "correspondence": 1650,
            }

            rating_variance = 400  # +/- from base

            # Build profile data in Lichess API format
            profile = {"perfs": {}}

            # Set a general rating for the deprecated rating field
            player_data["rating"] = None
            player_data["games_played"] = None

            for rating_type in [
                "classical",
                "rapid",
                "blitz",
                "bullet",
                "correspondence",
            ]:
                base = rating_base.get(rating_type, 1500)
                # Calculate rating based on strength factor
                player_rating = int(
                    base + (strength_factor - 0.5) * 2 * rating_variance
                )
                player_rating = max(
                    800, min(2400, player_rating)
                )  # Clamp to reasonable range

                games = (
                    random.randint(0, 500)
                    if not self.weighted_bool(0.2)
                    else random.randint(0, 19)
                )
                provisional = games < 20

                profile["perfs"][rating_type] = {
                    "rating": player_rating,
                    "games": games,
                    "rd": 60 if not provisional else 150,  # Rating deviation
                    "prog": random.randint(-50, 50),  # Recent progress
                    "prov": provisional,
                }

                # Set the main rating to classical if not set
                if rating_type == "classical" and player_data["rating"] is None:
                    player_data["rating"] = player_rating
                    player_data["games_played"] = games

            player_data["profile"] = profile

            # Determine account status
            if self.weighted_bool(0.05):  # 5% closed
                player_data["account_status"] = "closed"
            elif self.weighted_bool(0.03):  # 3% engine
                player_data["account_status"] = "engine"
            else:
                player_data["account_status"] = ""

            player = Player.objects.create(**player_data)

            # Create associated Django user for some players (for login testing)
            if self.weighted_bool(0.1):  # 10% have user accounts
                user = User.objects.create_user(
                    username=player.lichess_username.lower(),
                    email=player.email,
                    password="testpass123",
                )
                # Link player to user (you may need to check how this is done in your codebase)

            players.append(self._track_object(player))

        return players

    def seed_titled_players(self, count: int = 5) -> List[Player]:
        """Create some titled players for realism."""
        titles = ["GM", "IM", "FM", "WGM", "WIM", "CM", "WFM", "NM"]
        players = []

        for i in range(count):
            title = self.random_choice(titles)
            username = f"{title}{self.fake.last_name()}{random.randint(1, 99)}"

            # Titled players have higher ratings
            classical_rating = self.chess_rating(2200, 2600)
            rapid_rating = self.chess_rating(2150, 2550)
            blitz_rating = self.chess_rating(2100, 2500)

            player_data = {
                "lichess_username": username,
                "email": self.fake.email(),
                "is_active": True,
                "rating": classical_rating,
                "games_played": random.randint(100, 1000),
                "profile": {
                    "perfs": {
                        "classical": {
                            "rating": classical_rating,
                            "games": random.randint(100, 1000),
                            "rd": 45,
                            "prog": random.randint(-20, 50),
                            "prov": False,
                        },
                        "rapid": {
                            "rating": rapid_rating,
                            "games": random.randint(100, 1000),
                            "rd": 45,
                            "prog": random.randint(-20, 50),
                            "prov": False,
                        },
                        "blitz": {
                            "rating": blitz_rating,
                            "games": random.randint(200, 2000),
                            "rd": 45,
                            "prog": random.randint(-20, 50),
                            "prov": False,
                        },
                        "bullet": {
                            "rating": self.chess_rating(2050, 2450),
                            "games": random.randint(100, 1500),
                            "rd": 50,
                            "prog": random.randint(-30, 30),
                            "prov": False,
                        },
                    }
                },
            }

            player = Player.objects.create(**player_data)
            players.append(self._track_object(player))

        return players
