"""
Management command to seed a test lone (individual Swiss) tournament.

Creates a league, season, and players ready for pairing generation via the admin.
"""

import random
import re

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from heltour.tournament.builder import TournamentBuilder


CHESS_FIRST_NAMES = [
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
    "Richard",
    "Alireza",
    "Nodirbek",
    "Dommaraju",
]


class Command(BaseCommand):
    help = "Seed a test lone (individual Swiss) tournament with players ready for pairing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--league-name",
            type=str,
            default="Lone Test League",
            help="Name of the test league (default: Lone Test League)",
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
            help="Number of rounds (default: 7)",
        )
        parser.add_argument(
            "--players",
            type=int,
            default=400,
            help="Number of players (default: 400)",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Clear existing test league data before creating",
        )
        parser.add_argument(
            "--pairing-type",
            type=str,
            default="swiss-dutch",
            choices=["swiss-dutch", "swiss-dutch-baku-accel"],
            help="Pairing algorithm (default: swiss-dutch)",
        )

    def handle(self, *args, **options):
        league_name = options["league_name"]
        season_name = options["season_name"]
        rounds = options["rounds"]
        num_players = options["players"]
        pairing_type = options["pairing_type"]

        if options["clear_existing"]:
            self._clear_test_data(league_name)

        self.stdout.write(
            self.style.WARNING(f"Creating {league_name} - {season_name}...")
        )

        try:
            with transaction.atomic():
                builder = TournamentBuilder()

                league_tag = re.sub(r"[^a-zA-Z0-9]", "", league_name.lower())[:20]
                if not league_tag:
                    league_tag = "lonetestleague"

                builder.league(
                    league_name,
                    league_tag.upper(),
                    "lone",
                    pairing_type=pairing_type,
                    lone_tiebreak_1="head_to_head",
                    lone_tiebreak_2="buchholz_cut1",
                    lone_tiebreak_3="buchholz",
                    lone_tiebreak_4="games_won",
                    lone_tiebreak_5="games_with_black",
                )
                builder.season(
                    league_tag.upper(),
                    season_name,
                    rounds=rounds,
                    start_date=timezone.now() - timezone.timedelta(days=1),
                    round_duration=timezone.timedelta(days=7),
                    is_active=True,
                    is_completed=False,
                    registration_open=False,
                    nominations_open=False,
                )

                players = _generate_players(num_players)
                self.stdout.write(f"Generated {len(players)} player names")

                for name, rating in players:
                    builder.player(name, rating)

                player_count = len(builder.core_builder.metadata.players)
                self.stdout.write(f"Builder registered {player_count} players")

                builder.build()
                season = builder.current_season

                # Verify actual DB counts
                from heltour.tournament.models import SeasonPlayer, LonePlayerScore

                sp_count = SeasonPlayer.objects.filter(season=season).count()
                score_count = LonePlayerScore.objects.filter(
                    season_player__season=season
                ).count()

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created: {league_name} - {season_name}"
                    )
                )
                self.stdout.write(f"  - {sp_count} season players (DB verified)")
                self.stdout.write(f"  - {score_count} player scores (DB verified)")
                self.stdout.write(f"  - {rounds} rounds")
                self.stdout.write(f"  - Pairing: {pairing_type}")
                self.stdout.write(f"\nSeason ID: {season.id}")
                self.stdout.write(
                    "\nNext steps:"
                    "\n  1. Admin > Rounds > select Round 1 > Generate Pairings"
                    f"\n  2. python manage.py generate_random_results {season.id}"
                    "\n  3. Repeat for subsequent rounds"
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
            raise

    def _clear_test_data(self, league_name):
        from heltour.tournament.models import League, Player, SeasonPlayer

        try:
            league = League.objects.get(name=league_name)
        except League.DoesNotExist:
            return

        # Collect players tied to this league's seasons before deleting anything
        season_ids = league.season_set.values_list("id", flat=True)
        player_ids = set(
            SeasonPlayer.objects.filter(season_id__in=season_ids).values_list(
                "player_id", flat=True
            )
        )

        # Delete seasons (cascades registrations, season players, pairings, etc.)
        season_count = league.season_set.count()
        if season_count > 0:
            self.stdout.write(f"Clearing '{league_name}' ({season_count} seasons)...")
            league.season_set.all().delete()

        league.delete()

        # Delete orphaned players (no remaining season associations)
        if player_ids:
            orphaned = Player.objects.filter(id__in=player_ids).exclude(
                seasonplayer__isnull=False
            )
            orphan_count = orphaned.count()
            if orphan_count > 0:
                orphaned.delete()
                self.stdout.write(f"  - Removed {orphan_count} orphaned players")

        self.stdout.write("Cleared.")


def _generate_players(count: int) -> list[tuple[str, int]]:
    """Generate unique player names with varied ratings.

    Uses deterministic numbered names: Magnus_001, Garry_002, etc.
    Skips any username already in the database.
    """
    from heltour.tournament.models import Player

    existing = set(Player.objects.values_list("lichess_username", flat=True))
    players = []
    num_first_names = len(CHESS_FIRST_NAMES)

    for i in range(count):
        first = CHESS_FIRST_NAMES[i % num_first_names]
        number = (i // num_first_names) + 1
        name = f"{first}_{number:03d}"

        # If it collides with an existing DB player, append extra suffix
        if name in existing:
            suffix = 1
            while f"{name}_{suffix}" in existing:
                suffix += 1
            name = f"{name}_{suffix}"

        # Spread ratings: top seeds ~2200, bottom seeds ~1400
        rating_base = 1800 + int(200 * (1 - 2 * i / max(count - 1, 1)))
        rating = max(1200, min(2400, rating_base + random.randint(-100, 100)))
        players.append((name, rating))

    return players
