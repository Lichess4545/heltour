"""
Management command to seed the database with test data.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from faker import Faker

from heltour.tournament.seeders import (
    LeagueSeeder,
    PlayerSeeder,
    SeasonSeeder,
    RegistrationSeeder,
    TeamSeeder,
    RoundSeeder,
    PairingSeeder,
)


class Command(BaseCommand):
    help = "Seed the database with test data for development and testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--leagues",
            type=int,
            default=5,
            help="Number of leagues to create (default: 5)",
        )
        parser.add_argument(
            "--players",
            type=int,
            default=50,
            help="Number of players to create (default: 50)",
        )
        parser.add_argument(
            "--minimal",
            action="store_true",
            help="Create minimal dataset for quick testing",
        )
        parser.add_argument(
            "--full", action="store_true", help="Create full dataset with all features"
        )
        parser.add_argument(
            "--locale",
            type=str,
            default="en_US",
            help="Faker locale for data generation (default: en_US)",
        )

    def handle(self, *args, **options):
        fake = Faker(options["locale"])

        # Adjust counts based on dataset size
        if options["minimal"]:
            num_leagues = 2  # Create both team and individual league
            num_players = (
                80  # Enough for many teams (8 rounds * 2 * 4 boards = 64 minimum)
            )
        elif options["full"]:
            num_leagues = 5  # All 5 color schemes
            num_players = 100
        else:
            num_leagues = options["leagues"]
            num_players = options["players"]

        self.stdout.write(self.style.WARNING(f"Starting database seeding..."))

        try:
            with transaction.atomic():
                # Initialize seeders
                league_seeder = LeagueSeeder(fake)
                player_seeder = PlayerSeeder(fake)
                season_seeder = SeasonSeeder(fake)
                registration_seeder = RegistrationSeeder(fake)
                team_seeder = TeamSeeder(fake)
                round_seeder = RoundSeeder(fake)
                pairing_seeder = PairingSeeder(fake)

                # 1. Create leagues
                self.stdout.write("Creating leagues...")
                leagues = league_seeder.seed(num_leagues)
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Created {len(leagues)} leagues")
                )

                # 2. Create players
                self.stdout.write("Creating players...")
                players = player_seeder.seed(num_players, leagues=leagues)

                # Add some titled players for realism
                if options["full"]:
                    titled_players = player_seeder.seed_titled_players(5)
                    players.extend(titled_players)

                self.stdout.write(
                    self.style.SUCCESS(f"✓ Created {len(players)} players")
                )

                # 3. Create seasons for each league
                self.stdout.write("Creating seasons...")
                all_seasons = season_seeder.seed(leagues=leagues)
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Created {len(all_seasons)} seasons")
                )

                # 4. Process each season
                for season in all_seasons:
                    print(season)
                    league_type = (
                        "team" if season.league.is_team_league() else "individual"
                    )
                    self.stdout.write(f"\nProcessing {season.name} ({league_type})...")

                    # Create registrations
                    if (
                        season.registration_open
                        or season.is_active
                        or season.is_completed
                    ):
                        registrations = registration_seeder.seed(season, players)
                        self.stdout.write(
                            f"  ✓ Created {len(registrations)} registrations"
                        )

                    # Create teams for team leagues
                    if season.league.is_team_league() and (
                        season.is_active or season.is_completed
                    ):
                        teams = team_seeder.seed(season)
                        self.stdout.write(f"  ✓ Created {len(teams)} teams")

                    # Create rounds
                    rounds = round_seeder.seed(season)
                    self.stdout.write(f"  ✓ Created {len(rounds)} rounds")

                    # Create pairings for each round
                    total_pairings = 0
                    for round_obj in rounds:
                        if round_obj.is_completed or round_obj.publish_pairings:
                            pairings = pairing_seeder.seed(round_obj)
                            total_pairings += len(pairings)

                    if total_pairings > 0:
                        self.stdout.write(f"  ✓ Created {total_pairings} pairings")

                    # Calculate scores for active and completed seasons
                    if season.is_active or season.is_completed:
                        # For team leagues, ensure all teams have TeamScore objects
                        if season.league.is_team_league():
                            from heltour.tournament.models import Team, TeamScore

                            for team in Team.objects.filter(
                                season=season, is_active=True
                            ):
                                # This will create the TeamScore if it doesn't exist
                                team.get_teamscore()

                        season.calculate_scores()
                        self.stdout.write("  ✓ Calculated scores")

                        # Debug info
                        if season.league.is_team_league():
                            score_count = TeamScore.objects.filter(
                                team__season=season
                            ).count()
                            self.stdout.write(f"  → TeamScore objects: {score_count}")
                        else:
                            from heltour.tournament.models import LonePlayerScore

                            score_count = LonePlayerScore.objects.filter(
                                season_player__season=season
                            ).count()
                            self.stdout.write(
                                f"  → LonePlayerScore objects: {score_count}"
                            )

                # Summary
                self.stdout.write(self.style.SUCCESS("\n" + "=" * 50))
                self.stdout.write(
                    self.style.SUCCESS("Database seeding completed successfully!")
                )
                self._print_summary()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during seeding: {str(e)}"))
            raise

    def _print_summary(self):
        """Print summary of created data."""
        from heltour.tournament.models import (
            League,
            Season,
            Player,
            Team,
            Registration,
            PlayerPairing,
        )

        self.stdout.write("\nDatabase Summary:")
        self.stdout.write(f"  - Leagues: {League.objects.count()}")
        self.stdout.write(f"  - Seasons: {Season.objects.count()}")
        self.stdout.write(f"  - Players: {Player.objects.count()}")
        self.stdout.write(f"  - Teams: {Team.objects.count()}")
        self.stdout.write(f"  - Registrations: {Registration.objects.count()}")
        self.stdout.write(
            f'  - Games: {PlayerPairing.objects.exclude(game_link="").count()}'
        )

        # Show some sample players for testing
        self.stdout.write("\nSample players for testing:")
        # Get the first league to show ratings for
        first_league = League.objects.filter(rating_type="classical").first()
        if not first_league:
            first_league = League.objects.first()

        for player in Player.objects.all()[:5]:
            rating = player.rating_for(first_league) if first_league else "N/A"
            self.stdout.write(f"  - {player.lichess_username} (Rating: {rating})")
