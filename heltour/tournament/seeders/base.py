"""
Base seeder class with common functionality.
"""

import random
from typing import Any, List
from faker import Faker
from django.utils import timezone


class BaseSeeder:
    """Base class for all seeders with common functionality."""

    def __init__(self, fake: Faker = None):
        self.fake = fake or Faker()
        self.created_objects: List[Any] = []

    def seed(self, count: int = 1, **kwargs) -> List[Any]:
        """Seed the database with the specified number of objects."""
        raise NotImplementedError("Subclasses must implement seed()")

    def _track_object(self, obj: Any) -> Any:
        """Track created objects for cleanup or reference."""
        self.created_objects.append(obj)
        return obj

    def get_created_objects(self) -> List[Any]:
        """Get all objects created by this seeder."""
        return self.created_objects

    def clear_created_objects(self):
        """Clear the list of created objects."""
        self.created_objects = []

    def random_choice(self, choices: List[Any]) -> Any:
        """Safely choose a random item from a list."""
        if not choices:
            return None
        return random.choice(choices)

    def random_subset(
        self, choices: List[Any], min_size: int = 0, max_size: int = None
    ) -> List[Any]:
        """Get a random subset of items from a list."""
        if not choices:
            return []

        max_size = max_size or len(choices)
        size = random.randint(min_size, min(max_size, len(choices)))
        return random.sample(choices, size)

    def weighted_bool(self, true_weight: float = 0.5) -> bool:
        """Return True with the given probability."""
        return random.random() < true_weight

    def future_date(self, days_ahead: int = 30) -> timezone.datetime:
        """Generate a future date within the specified days."""
        return timezone.now() + timezone.timedelta(days=random.randint(1, days_ahead))

    def past_date(self, days_ago: int = 30) -> timezone.datetime:
        """Generate a past date within the specified days."""
        return timezone.now() - timezone.timedelta(days=random.randint(1, days_ago))

    def lichess_username(self) -> str:
        """Generate a realistic Lichess-style username."""
        formats = [
            lambda: self.fake.user_name(),
            lambda: f"{self.fake.first_name()}{random.randint(1, 999)}",
            lambda: f"{self.fake.last_name()}{self.fake.first_name()[:3]}",
            lambda: f"{self.fake.word()}{random.randint(10, 99)}",
            lambda: f"{self.fake.word()}_{self.fake.word()}",
        ]
        username = random.choice(formats)()
        # Ensure username meets Lichess requirements
        return username[:20].replace(" ", "_")

    def chess_rating(self, min_rating: int = 800, max_rating: int = 2400) -> int:
        """Generate a realistic chess rating with normal distribution."""
        # Most players cluster around 1500-1700
        mean = 1500
        std_dev = 200
        rating = int(random.gauss(mean, std_dev))
        return max(min_rating, min(rating, max_rating))
