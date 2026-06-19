"""
Reset cached pairing ratings for a league so they can be repopulated.

Nulls out white_rating/black_rating on all PlayerPairings across every
season in the given league. The hourly populate_historical_ratings celery
task will then repopulate them with the correct rating type.

This is useful when ratings were cached incorrectly (e.g. Lichess ratings
stored for a FIDE-rated league).

Usage:
    python manage.py recalculate_ratings <league_tag>
"""

from django.core.management.base import BaseCommand, CommandError

from heltour.tournament.models import (
    League,
    LonePlayerPairing,
    PlayerPairing,
    TeamPlayerPairing,
)


class Command(BaseCommand):
    help = "Reset cached pairing ratings for a league so they can be repopulated"

    def add_arguments(self, parser):
        parser.add_argument("league_tag", type=str, help="Tag (slug) of the league")

    def handle(self, *args, **options):
        league_tag = options["league_tag"]
        try:
            league = League.objects.get(tag=league_tag)
        except League.DoesNotExist:
            raise CommandError(f"League with tag '{league_tag}' does not exist")

        self.stdout.write(
            f"League: {league.name} (tag={league.tag})\n"
            f"Rating type: {league.rating_type}\n"
            f"Competitor type: {league.competitor_type}\n"
        )

        if league.competitor_type == "team":
            pairing_ids = TeamPlayerPairing.objects.filter(
                team_pairing__round__season__league=league
            ).values_list("playerpairing_ptr_id", flat=True)
        else:
            pairing_ids = LonePlayerPairing.objects.filter(
                round__season__league=league
            ).values_list("playerpairing_ptr_id", flat=True)

        pairings_updated = PlayerPairing.objects.filter(id__in=pairing_ids).update(
            white_rating=None, black_rating=None
        )
        self.stdout.write(f"Cleared {pairings_updated} pairing rating(s)")

        self.stdout.write(
            self.style.SUCCESS(
                "\nDone. The populate_historical_ratings task will repopulate these."
            )
        )
