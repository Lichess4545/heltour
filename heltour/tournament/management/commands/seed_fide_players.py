"""
Seed players with well-known FIDE IDs for manual testing of FIDE rating integration.

Creates a FIDE Standard league with an active season, registers players with
real FIDE IDs, and creates SeasonPlayers so the update_fide_ratings task can
pick them up. Idempotent — safe to re-run.

Usage:
    python manage.py seed_fide_players
    python manage.py seed_fide_players --league-tag my-fide  # custom league tag
    python manage.py seed_fide_players --no-league            # add to existing players only

After running:
    1. Run update_fide_ratings or force_update_all_fide_ratings celery task
    2. Check Player admin for fide_profile data
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from heltour.tournament.models import (
    League,
    Player,
    Registration,
    Season,
    SeasonPlayer,
)

WELL_KNOWN_FIDE_PLAYERS = [
    {
        "lichess_username": "DrNykterstein",
        "fide_id": "1503014",
        "name": "Magnus Carlsen",
    },
    {
        "lichess_username": "FairChess_on_YouTube",
        "fide_id": "5202213",
        "name": "Hikaru Nakamura",
    },
    {
        "lichess_username": "Bessjansen",
        "fide_id": "8603677",
        "name": "Alireza Firouzja",
    },
    {
        "lichess_username": "GMWSO",
        "fide_id": "623539",
        "name": "Wesley So",
    },
]


class Command(BaseCommand):
    help = "Seed players with well-known FIDE IDs for testing FIDE rating integration"

    def add_arguments(self, parser):
        parser.add_argument(
            "--league-tag",
            type=str,
            default="fide-test",
            help="Tag for the FIDE test league (default: fide-test)",
        )
        parser.add_argument(
            "--no-league",
            action="store_true",
            help="Only create/update players with FIDE IDs, skip league/season/registration",
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            players = self._upsert_players()

            if not options["no_league"]:
                league, season = self._upsert_league_and_season(options["league_tag"])
                self._upsert_registrations_and_season_players(players, season)

        self.stdout.write(self.style.SUCCESS("Done. Players seeded:"))
        for info in WELL_KNOWN_FIDE_PLAYERS:
            p = Player.objects.get(lichess_username__iexact=info["lichess_username"])
            profile_status = "has profile" if p.fide_profile else "no profile yet"
            self.stdout.write(
                f"  {info['name']:25s}  FIDE {info['fide_id']:>10s}  "
                f"lichess={info['lichess_username']:25s}  ({profile_status})"
            )

        self.stdout.write("")
        self.stdout.write("Next steps:")
        self.stdout.write(
            "  1. Run: from heltour.tournament.tasks import force_update_all_fide_ratings; "
            "force_update_all_fide_ratings()"
        )
        self.stdout.write("  2. Check Player admin for fide_profile data")

    def _upsert_players(self):
        players = []
        for info in WELL_KNOWN_FIDE_PLAYERS:
            player, created = Player.objects.update_or_create(
                lichess_username__iexact=info["lichess_username"],
                defaults={
                    "lichess_username": info["lichess_username"],
                    "fide_id": info["fide_id"],
                    "is_active": True,
                },
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"  {action} player: {info['lichess_username']}")
            players.append(player)
        return players

    def _upsert_league_and_season(self, league_tag):
        league, created = League.objects.update_or_create(
            tag=league_tag,
            defaults={
                "name": "FIDE Test League",
                "theme": "green",
                "competitor_type": "lone",
                "rating_type": "fide_standard",
            },
        )
        action = "Created" if created else "Updated"
        self.stdout.write(f"  {action} league: {league.name} ({league.tag})")

        season, created = Season.objects.update_or_create(
            league=league,
            tag=f"{league_tag}-s1",
            defaults={
                "name": "FIDE Test Season 1",
                "rounds": 3,
                "is_active": True,
                "is_completed": False,
                "registration_open": True,
            },
        )
        action = "Created" if created else "Updated"
        self.stdout.write(f"  {action} season: {season.name}")

        return league, season

    def _upsert_registrations_and_season_players(self, players, season):
        for player in players:
            reg, _ = Registration.objects.update_or_create(
                season=season,
                player=player,
                defaults={
                    "status": "approved",
                    "email": f"{player.lichess_username}@test.local",
                    "has_played_20_games": True,
                    "can_commit": True,
                    "agreed_to_rules": True,
                    "agreed_to_tos": True,
                    "alternate_preference": "full_time",
                    "fide_id": player.fide_id,
                },
            )
            SeasonPlayer.objects.update_or_create(
                season=season,
                player=player,
                defaults={"registration": reg, "is_active": True},
            )
