"""
Management command to seed a test team tournament with specific requirements:
- 13 teams (odd number)
- 4 boards per team
- Some teams with 3 players, some with 5 players
- No completed rounds or pairings (ready for testing)
"""

import random
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker

from heltour.tournament.builder import TournamentBuilder


class Command(BaseCommand):
    help = "Seed a test team tournament with 13 teams, 4 boards, and varying team sizes"

    def add_arguments(self, parser):
        parser.add_argument(
            "--league-name",
            type=str,
            default="Test League",
            help="Name of the test league (default: Test League)",
        )
        parser.add_argument(
            "--season-name",
            type=str,
            default="Test Season",
            help="Name of the test season (default: Test Season)",
        )
        parser.add_argument(
            "--rounds",
            type=int,
            default=7,
            help="Number of rounds in the tournament (default: 7)",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Clear existing test league data before creating new tournament",
        )

    def handle(self, *args, **options):
        fake = Faker()

        league_name = options["league_name"]
        season_name = options["season_name"]
        rounds = options["rounds"]

        if options["clear_existing"]:
            self._clear_test_data(league_name)

        self.stdout.write(
            self.style.WARNING(f"Creating {league_name} - {season_name}...")
        )

        try:
            with transaction.atomic():
                # Initialize tournament builder
                builder = TournamentBuilder()

                # Generate a unique league tag from the league name
                import re

                league_tag = re.sub(r"[^a-zA-Z0-9]", "", league_name.lower())[:20]
                if not league_tag:  # Fallback if no valid characters
                    league_tag = "testleague"

                # Create league and season
                builder.league(
                    league_name,
                    league_tag.upper(),
                    "team",
                    # Set tiebreaks: game points, EGGSB, buchholz (match points are primary, not a tiebreak)
                    team_tiebreak_1="game_points",
                    team_tiebreak_2="eggsb",
                    team_tiebreak_3="buchholz",
                    team_tiebreak_4="",
                )
                builder.season(
                    league_tag.upper(),
                    season_name,
                    rounds=rounds,
                    boards=4,
                    start_date=timezone.now() - timezone.timedelta(days=1),
                    round_duration=timezone.timedelta(days=7),
                    is_active=True,
                    is_completed=False,
                    registration_open=False,
                    nominations_open=False,
                )

                # Generate team data with varying sizes
                team_configs = self._generate_team_configs()
                player_generator = TestPlayerGenerator(fake)

                # Create teams with players
                for team_config in team_configs:
                    team_name = team_config["name"]
                    num_players = team_config["players"]

                    # Generate players for this team
                    players = player_generator.generate_team_players(
                        num_players, team_name
                    )

                    # Add team with players
                    builder.team(team_name, *players)

                # Build the tournament (creates database objects)
                tournament_structure = builder.build()
                season = builder.current_season

                # Summary
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Created test tournament: {league_name} - {season_name}"
                    )
                )
                self.stdout.write(f"  - {len(team_configs)} teams")
                self.stdout.write(f"  - {rounds} rounds planned")
                self.stdout.write(f"  - 4 boards per team")

                # Show team composition
                self.stdout.write("\nTeam composition:")
                for team_config in team_configs:
                    self.stdout.write(
                        f"  - {team_config['name']}: {team_config['players']} players"
                    )

                self.stdout.write(f"\nSeason ID: {season.id}")
                self.stdout.write(
                    "Use 'generate_random_results {season_id}' to simulate round results"
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error creating tournament: {str(e)}"))
            raise

    def _generate_team_configs(self):
        """Generate team configurations with varying player counts."""
        team_configs = []

        # Team names inspired by chess and strategy
        team_names = [
            "Royal Knights",
            "Swift Bishops",
            "Mighty Rooks",
            "Golden Queens",
            "Silver Kings",
            "Lightning Pawns",
            "Thunder Masters",
            "Storm Tacticians",
            "Fire Dragons",
            "Ice Warriors",
            "Shadow Legends",
            "Crystal Eagles",
            "Quantum Lions",
        ]

        # Configure team sizes: some with 3, some with 5, most with 4
        team_sizes = [
            3,
            3,  # 2 teams with 3 players (minimum for 4 boards)
            5,
            5,
            5,  # 3 teams with 5 players
            4,
            4,
            4,
            4,
            4,
            4,
            4,
            4,  # 8 teams with standard 4 players
        ]

        for i, (name, size) in enumerate(zip(team_names, team_sizes)):
            team_configs.append({"name": name, "players": size})

        return team_configs

    def _clear_test_data(self, league_name):
        """Clear existing test tournament data."""
        from heltour.tournament.models import League

        try:
            league = League.objects.get(name=league_name)

            # Count related objects before deletion
            seasons = league.season_set.all()
            season_count = seasons.count()

            if season_count > 0:
                self.stdout.write(f"Clearing existing '{league_name}' data...")
                self.stdout.write(f"  - {season_count} seasons")

                # Delete seasons (cascades to teams, players, pairings, etc.)
                seasons.delete()
                self.stdout.write("  - Related data cleared")

            # Delete the league itself
            league.delete()
            self.stdout.write("  - League deleted")

        except League.DoesNotExist:
            # No existing data to clear
            pass


class TestPlayerGenerator:
    """Generate test players for tournament teams."""

    def __init__(self, fake):
        self.fake = fake
        self.used_names = set()

    def generate_team_players(self, count: int, team_prefix: str) -> list:
        """Generate players for a team with chess-themed names."""
        players = []

        # Chess-themed first names and adjectives
        chess_names = [
            "Magnus",
            "Garry",
            "Bobby",
            "Anatoly",
            "Vladimir",
            "Viswanathan",
            "Fabiano",
            "Hikaru",
            "Levon",
            "Wesley",
            "Maxime",
            "Sergey",
            "Ding",
            "Ian",
            "Teimour",
            "Alexander",
            "Pentala",
            "Anish",
            "Shakhriyar",
            "Sam",
            "Richárd",
            "Jan-Krzysztof",
            "Alireza",
            "Nodirbek",
        ]

        chess_adjectives = [
            "Tactical",
            "Strategic",
            "Sharp",
            "Solid",
            "Dynamic",
            "Positional",
            "Aggressive",
            "Defensive",
            "Creative",
            "Precise",
            "Quick",
            "Patient",
        ]

        for i in range(count):
            # Create unique player name
            base_name = random.choice(chess_names)
            adjective = random.choice(chess_adjectives)

            # Make it unique
            attempts = 0
            while attempts < 50:
                if attempts == 0:
                    player_name = f"{base_name}_{team_prefix.replace(' ', '')}"
                else:
                    player_name = f"{adjective}{base_name}_{team_prefix.replace(' ', '')}_{attempts}"

                if player_name not in self.used_names:
                    self.used_names.add(player_name)
                    break
                attempts += 1
            else:
                # Fallback
                player_name = (
                    f"Player{len(self.used_names)}_{team_prefix.replace(' ', '')}"
                )
                self.used_names.add(player_name)

            # Generate rating with some variation
            # Higher-rated players on lower boards generally
            board_modifier = (count - i) * 50  # Earlier players get higher ratings
            base_rating = 1600 + random.randint(-200, 300) + board_modifier
            rating = max(1200, min(2400, base_rating))

            players.append((player_name, rating))

        return players

