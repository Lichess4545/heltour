"""
Round seeder for creating test rounds.
"""

from typing import List
from django.utils import timezone
from heltour.tournament.models import Round, Season
from .base import BaseSeeder


class RoundSeeder(BaseSeeder):
    """Seeder for creating Round objects."""

    def seed(self, season: Season, **kwargs) -> List[Round]:
        """Create rounds for a season if they don't exist."""
        rounds = []

        # Get existing rounds for this season
        existing_rounds = list(Round.objects.filter(season=season).order_by("number"))

        # If we already have all rounds, return them
        if len(existing_rounds) != season.rounds:
            raise RuntimeError(
                "The seeder is broken: rounds are automatically created when the season is"
            )

        # Create missing rounds
        for round_obj in existing_rounds:
            rounds.append(self._track_object(round_obj))

            # Set round states based on season state
            if season.is_completed or round_obj.end_date < timezone.now():
                round_obj.is_completed = True
                round_obj.publish_pairings = True
            elif round_obj.start_date < timezone.now():
                round_obj.publish_pairings = True
            round_obj.save()

        return rounds
