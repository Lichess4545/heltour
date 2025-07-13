"""
Season seeder for creating test seasons.
"""

import random
from typing import List
from django.utils import timezone
from heltour.tournament.models import Season, League
from .base import BaseSeeder


class SeasonSeeder(BaseSeeder):
    """Seeder for creating Season objects."""

    def seed(self, leagues: List[League] = None, **kwargs) -> List[Season]:
        """Create test seasons in various states."""
        seasons = []

        if leagues is None:
            leagues = League.objects.all()

        if not leagues:
            raise ValueError("No leagues found. Please create leagues first.")

        season_configs = [
            {
                "name_suffix": "Completed Season",
                "is_completed": True,
                "is_active": False,
                "registration_open": False,
                "nominations_open": False,
                "start_offset_days": -120,  # Started 4 months ago
                "rounds": 8,
            },
            {
                "name_suffix": "Current Season",
                "is_completed": False,
                "is_active": True,
                "registration_open": False,
                "nominations_open": True,
                "start_offset_days": -35,  # Started 5 weeks ago
                "rounds": 8,
            },
            {
                "name_suffix": "Upcoming Season",
                "is_completed": False,
                "is_active": False,
                "registration_open": True,
                "nominations_open": False,
                "start_offset_days": 14,  # Starts in 2 weeks
                "rounds": 8,
            },
            {
                "name_suffix": "Planning Season",
                "is_completed": False,
                "is_active": False,
                "registration_open": False,
                "nominations_open": False,
                "start_offset_days": 60,  # Starts in 2 months
                "rounds": 10,
            },
        ]

        for league in leagues:
            # Determine number of boards for team leagues
            boards = 4 if league.is_team_league() else None

            for i, config in enumerate(season_configs):
                season_name = f"{league.name} {config['name_suffix']}"
                season_tag = f"{league.tag}-s{i+1}"

                # Calculate start date
                start_date = timezone.now() + timezone.timedelta(
                    days=config["start_offset_days"]
                )

                season_data = {
                    "league": league,
                    "name": season_name,
                    "tag": season_tag,
                    "start_date": start_date,
                    "rounds": config["rounds"],
                    "round_duration": timezone.timedelta(days=7),
                    "boards": boards,
                    "playoffs": (
                        0 if config["is_completed"] else random.choice([0, 0, 0, 6])
                    ),  # Most have no playoffs
                    "is_active": config["is_active"],
                    "is_completed": config["is_completed"],
                    "registration_open": config["registration_open"],
                    "nominations_open": config["nominations_open"],
                }
                season_data.update(kwargs)

                season = Season.objects.create(**season_data)

                seasons.append(self._track_object(season))

        return seasons
