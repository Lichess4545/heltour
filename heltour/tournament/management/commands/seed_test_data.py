import random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from heltour.tournament.models import (
    League,
    LonePlayerScore,
    Player,
    Round,
    Season,
    SeasonPlayer,
    Team,
    TeamMember,
    TeamScore,
)
from heltour.tournament.pairinggen import generate_pairings

TEAM_LEAGUE_TAG = "test-4545"
LONEWOLF_LEAGUE_TAG = "test-lonewolf"
CHESS960_LEAGUE_TAG = "test-960"

SEASON_TAG = "test-season-1"
SEASON_ROUNDS = 2
RESULT_CHOICES = ["1-0", "0-1", "1/2-1/2"]

CHESS_FIRST_NAMES = [
    "Magnus", "Garry", "Bobby", "Anatoly", "Vladimir", "Viswanathan",
    "Fabiano", "Hikaru", "Levon", "Wesley", "Maxime", "Sergey", "Ding",
    "Ian", "Teimour", "Alexander", "Pentala", "Anish", "Shakhriyar",
    "Sam", "Richard", "Alireza", "Nodirbek", "Dommaraju", "Judit",
    "Hou", "Ju", "Kateryna", "Aleksandra", "Nona",
]

TEAM_NAMES = [
    "Rusty Rooks", "Bold Bishops", "Knight Riders", "Queen's Gambit Club",
    "Endgame Enjoyers", "Zugzwang Zealots",
]


class Command(BaseCommand):
    help = (
        "Seed a small set of demo leagues for manual browsing/testing: a 4545-style "
        "team league and two LoneWolf-style individual Swiss leagues. heltour has no "
        "first-class Chess960/variant league type -- only League.rating_type='chess960' "
        "as a rating category, with no 960 starting-position or alternate game-creation "
        "support -- so the third league is the closest real equivalent: an individual "
        "Swiss league rated as Chess960, not a true variant implementation."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete previously seeded test leagues (by tag) before recreating them.",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self._flush()

        with transaction.atomic():
            self._seed_team_league()
            self._seed_lone_league(
                LONEWOLF_LEAGUE_TAG, "Test LoneWolf League", "classical", num_players=16
            )
            self._seed_lone_league(
                CHESS960_LEAGUE_TAG, "Test Chess960 League", "chess960", num_players=12
            )

    def _flush(self):
        for tag in (TEAM_LEAGUE_TAG, LONEWOLF_LEAGUE_TAG, CHESS960_LEAGUE_TAG):
            league = League.objects.filter(tag=tag).first()
            if league is not None:
                self.stdout.write(f"Flushing existing league '{tag}'...")
                league.delete()

    def _seed_team_league(self):
        if League.objects.filter(tag=TEAM_LEAGUE_TAG).exists():
            self.stdout.write(
                f"League '{TEAM_LEAGUE_TAG}' already exists, skipping "
                "(pass --flush to recreate)."
            )
            return

        league = League.objects.create(
            name="Test 4545 Team League",
            tag=TEAM_LEAGUE_TAG,
            description="Seeded team league for manual testing.",
            theme="blue",
            rating_type="classical",
            competitor_type="team",
            pairing_type="swiss-dutch",
            is_active=True,
        )
        season = Season.objects.create(
            league=league,
            name="Test Season 1",
            tag=SEASON_TAG,
            start_date=timezone.now() - timezone.timedelta(days=3),
            rounds=SEASON_ROUNDS,
            round_duration=timezone.timedelta(days=7),
            boards=4,
            is_active=True,
        )

        board_count = season.boards
        names = _unique_player_names(len(TEAM_NAMES) * board_count)
        name_iter = iter(names)
        for team_number, team_name in enumerate(TEAM_NAMES, start=1):
            team = Team.objects.create(season=season, number=team_number, name=team_name)
            TeamScore.objects.create(team=team)
            for board_number in range(1, board_count + 1):
                player = _create_player(next(name_iter), "classical")
                SeasonPlayer.objects.create(season=season, player=player)
                TeamMember.objects.create(
                    team=team,
                    player=player,
                    board_number=board_number,
                    is_captain=board_number == 1,
                )

        self._play_rounds(season)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded team league '{TEAM_LEAGUE_TAG}': {len(TEAM_NAMES)} teams, "
            f"{board_count} boards, {SEASON_ROUNDS} rounds."
        ))

    def _seed_lone_league(self, tag, name, rating_type, num_players):
        if League.objects.filter(tag=tag).exists():
            self.stdout.write(
                f"League '{tag}' already exists, skipping (pass --flush to recreate)."
            )
            return

        league = League.objects.create(
            name=name,
            tag=tag,
            description=f"Seeded individual Swiss league ({rating_type}) for manual testing.",
            theme="green" if rating_type != "chess960" else "red",
            rating_type=rating_type,
            competitor_type="individual",
            pairing_type="swiss-dutch",
            is_active=True,
        )
        season = Season.objects.create(
            league=league,
            name="Test Season 1",
            tag=SEASON_TAG,
            start_date=timezone.now() - timezone.timedelta(days=3),
            rounds=SEASON_ROUNDS,
            round_duration=timezone.timedelta(days=7),
            is_active=True,
        )

        for player_name in _unique_player_names(num_players):
            player = _create_player(player_name, rating_type)
            season_player = SeasonPlayer.objects.create(season=season, player=player)
            LonePlayerScore.objects.create(season_player=season_player)

        self._play_rounds(season)
        self.stdout.write(self.style.SUCCESS(
            f"Seeded individual league '{tag}': {num_players} players, "
            f"{SEASON_ROUNDS} rounds."
        ))

    def _play_rounds(self, season):
        round_1 = Round.objects.get(season=season, number=1)
        generate_pairings(round_1)
        for pairing in round_1.pairings:
            pairing.result = random.choice(RESULT_CHOICES)
            pairing.save()
        round_1.publish_pairings = True
        round_1.is_completed = True
        round_1.save()

        if season.rounds >= 2:
            round_2 = Round.objects.get(season=season, number=2)
            generate_pairings(round_2)
            round_2.publish_pairings = True
            round_2.save()


def _unique_player_names(count):
    used = set(Player.objects.values_list("lichess_username", flat=True))
    names = []
    index = 0
    while len(names) < count:
        first = CHESS_FIRST_NAMES[index % len(CHESS_FIRST_NAMES)]
        suffix = index // len(CHESS_FIRST_NAMES)
        candidate = f"{first}_{suffix}" if suffix else first
        index += 1
        if candidate in used or candidate in names:
            continue
        names.append(candidate)
    return names


def _create_player(username, rating_type):
    rating = random.randint(1200, 2200)
    player, created = Player.objects.get_or_create(
        lichess_username=username,
        defaults={
            "profile": {
                "perfs": {rating_type: {"rating": rating, "games": 50, "prov": False}}
            }
        },
    )
    if not created and player.profile is None:
        player.profile = {
            "perfs": {rating_type: {"rating": rating, "games": 50, "prov": False}}
        }
        player.save()
    return player
