"""
Management command to seed a knockout tournament with specific requirements:
- Configurable number of teams (must be power of 2)
- Traditional or adjacent seeding
- Team or individual tournaments
- Automatic bracket generation
"""

import random
import math
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from faker import Faker

from heltour.tournament.builder import TournamentBuilder


class Command(BaseCommand):
    help = "Seed a knockout tournament with configurable teams and seeding"

    def add_arguments(self, parser):
        parser.add_argument(
            "--teams",
            type=int,
            default=8,
            help="Number of teams/players (must be power of 2, default: 8)",
        )
        parser.add_argument(
            "--tournament-type",
            choices=["team", "individual"],
            default="team",
            help="Tournament type: team or individual (default: team)",
        )
        parser.add_argument(
            "--seeding-style",
            choices=["traditional", "adjacent"],
            default="traditional",
            help="Seeding style: traditional (1v16, 2v15...) or adjacent (1v2, 3v4...) (default: traditional)",
        )
        parser.add_argument(
            "--games-per-match",
            type=int,
            default=1,
            help="Number of games per knockout match (default: 1)",
        )
        parser.add_argument(
            "--matches-per-stage",
            type=int,
            default=1,
            help="Number of matches per stage (1=single elimination, 2=return matches, 3=best of 3, etc.) (default: 1)",
        )
        parser.add_argument(
            "--boards",
            type=int,
            default=4,
            help="Number of boards per team (team tournaments only, default: 4)",
        )
        parser.add_argument(
            "--league-name",
            type=str,
            default="Knockout Championship",
            help="Name of the knockout league (default: Knockout Championship)",
        )
        parser.add_argument(
            "--season-name",
            type=str,
            default="Spring Knockout",
            help="Name of the knockout season (default: Spring Knockout)",
        )
        parser.add_argument(
            "--generate-bracket",
            action="store_true",
            help="Automatically generate knockout bracket and first round pairings",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Clear existing knockout league data before creating new tournament",
        )
        parser.add_argument(
            "--rounds",
            type=int,
            help="Number of rounds to play (default: calculate from teams for full elimination)",
        )

    def handle(self, *args, **options):
        fake = Faker()

        teams_count = options["teams"]
        tournament_type = options["tournament_type"]
        seeding_style = options["seeding_style"]
        games_per_match = options["games_per_match"]
        matches_per_stage = options["matches_per_stage"]
        boards = options["boards"]
        league_name = options["league_name"]
        season_name = options["season_name"]
        generate_bracket = options["generate_bracket"]
        clear_existing = options["clear_existing"]
        custom_rounds = options.get("rounds")

        # Validate teams count is power of 2
        if not self._is_power_of_2(teams_count):
            raise CommandError(
                f"Number of teams ({teams_count}) must be a power of 2 (e.g., 2, 4, 8, 16, 32)"
            )

        if options["clear_existing"]:
            self._clear_knockout_data(league_name)

        # Calculate number of rounds
        if custom_rounds:
            rounds = custom_rounds
            max_rounds = int(math.log2(teams_count))
            if rounds > max_rounds:
                raise CommandError(f"Cannot have {rounds} rounds with {teams_count} teams (max: {max_rounds})")
        else:
            rounds = int(math.log2(teams_count))

        self.stdout.write(
            self.style.WARNING(f"Creating {league_name} - {season_name}...")
        )
        self.stdout.write(
            f"  - {teams_count} {tournament_type}{'s' if tournament_type == 'team' else 's'}"
        )
        if custom_rounds:
            remaining_teams = teams_count // (2 ** rounds)
            self.stdout.write(f"  - {rounds} rounds (stops at {remaining_teams} teams)")
        else:
            self.stdout.write(f"  - {rounds} rounds ({self._get_stage_names(teams_count)})")
        self.stdout.write(f"  - {seeding_style.title()} seeding")
        self.stdout.write(
            f"  - {games_per_match} game{'s' if games_per_match > 1 else ''} per match"
        )
        if matches_per_stage > 1:
            match_type = "Return matches" if matches_per_stage == 2 else f"Best of {matches_per_stage}"
            self.stdout.write(f"  - {match_type} ({matches_per_stage} matches per stage)")
        else:
            self.stdout.write("  - Single elimination")
        if tournament_type == "team":
            self.stdout.write(f"  - {boards} boards per team")

        try:
            with transaction.atomic():
                # Initialize tournament builder
                builder = TournamentBuilder()

                # Create league and season with knockout configuration
                competitor_type = "team" if tournament_type == "team" else "lone"
                
                # Choose pairing type based on matches per stage
                pairing_type = "knockout-multi" if matches_per_stage > 1 else "knockout-single"

                # Generate league tag from league name
                league_tag = league_name.upper().replace(" ", "").replace("-", "")[:20]

                builder.league(
                    league_name,
                    league_tag,
                    competitor_type,
                    # Set knockout-specific settings
                    pairing_type=pairing_type,
                    knockout_seeding_style=seeding_style,
                    knockout_games_per_match=games_per_match,
                    # Set tiebreaks for team tournaments
                    **(
                        {
                            "team_tiebreak_1": "game_points",
                            "team_tiebreak_2": "sonneborn_berger",
                            "team_tiebreak_3": "buchholz",
                            "team_tiebreak_4": "games_won",
                        }
                        if tournament_type == "team"
                        else {}
                    ),
                )

                builder.knockout_format(
                    seeding_style=seeding_style, 
                    games_per_match=games_per_match,
                    matches_per_stage=matches_per_stage
                )

                season_kwargs = {
                    "rounds": rounds,
                    "start_date": timezone.now() - timezone.timedelta(days=1),
                    "round_duration": timezone.timedelta(days=7),
                    "is_active": True,
                    "is_completed": False,
                    "registration_open": False,
                    "nominations_open": False,
                }

                if tournament_type == "team":
                    season_kwargs["boards"] = boards

                builder.season(league_tag, season_name, **season_kwargs)

                # Generate teams/players
                if tournament_type == "team":
                    self._generate_teams(builder, teams_count, boards, fake)
                else:
                    self._generate_players(builder, teams_count, fake)

                # Build the tournament (creates database objects)
                tournament_structure = builder.build()
                season = builder.current_season

                # Generate knockout bracket if requested
                bracket = None
                if generate_bracket:
                    from heltour.tournament.pairinggen import generate_knockout_bracket

                    try:
                        bracket = generate_knockout_bracket(season)
                        self.stdout.write(
                            self.style.SUCCESS("✓ Knockout bracket and first round pairings generated")
                        )
                        self.stdout.write(f"  - Bracket size: {bracket.bracket_size}")
                        self.stdout.write(f"  - Seeding style: {bracket.seeding_style}")
                        self.stdout.write(f"  - Matches per stage: {bracket.matches_per_stage}")
                        self.stdout.write("  - First round match pairings created and ready to play")

                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"Failed to generate bracket: {str(e)}")
                        )

                # Summary
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Created knockout tournament: {league_name} - {season_name}"
                    )
                )
                self.stdout.write(f"  - Season ID: {season.id}")
                self.stdout.write(f"  - Tournament format: {rounds}-round knockout")

                if bracket:
                    # Show seeding order
                    from heltour.tournament.models import KnockoutSeeding

                    seedings = KnockoutSeeding.objects.filter(bracket=bracket).order_by(
                        "seed_number"
                    )

                    self.stdout.write(f"\nSeeding order ({seeding_style}):")
                    for seeding in seedings[:8]:  # Show first 8 seeds
                        if tournament_type == "team":
                            competitor_name = (
                                seeding.team.name if seeding.team else "BYE"
                            )
                        else:
                            competitor_name = (
                                seeding.player.lichess_username
                                if seeding.player
                                else "BYE"
                            )
                        self.stdout.write(
                            f"  {seeding.seed_number:2d}. {competitor_name}"
                        )

                    if seedings.count() > 8:
                        self.stdout.write(f"  ... and {seedings.count() - 8} more")

                    self.stdout.write(
                        f"\nUse 'generate_random_results {season.id}' to simulate knockout matches"
                    )
                else:
                    self.stdout.write(
                        f"\nUse '--generate-bracket' to create knockout bracket"
                    )
                    self.stdout.write(
                        f"Or use admin interface to generate bracket manually"
                    )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error creating knockout tournament: {str(e)}")
            )
            raise

    def _is_power_of_2(self, n):
        """Check if n is a power of 2."""
        return n > 0 and (n & (n - 1)) == 0

    def _get_stage_names(self, teams_count):
        """Get stage names for the tournament."""
        rounds = int(math.log2(teams_count))
        if rounds == 1:
            return "Finals"
        elif rounds == 2:
            return "Semifinals, Finals"
        elif rounds == 3:
            return "Quarterfinals, Semifinals, Finals"
        elif rounds == 4:
            return "Round of 16, Quarterfinals, Semifinals, Finals"
        elif rounds == 5:
            return "Round of 32, Round of 16, Quarterfinals, Semifinals, Finals"
        else:
            stage_names = []
            for r in range(1, rounds + 1):
                remaining = teams_count // (2 ** (r - 1))
                if remaining == 4:
                    stage_names.append("Semifinals")
                elif remaining == 2:
                    stage_names.append("Finals")
                elif remaining == 8:
                    stage_names.append("Quarterfinals")
                elif remaining == 16:
                    stage_names.append("Round of 16")
                elif remaining == 32:
                    stage_names.append("Round of 32")
                else:
                    stage_names.append(f"Round of {remaining}")
            return ", ".join(stage_names)

    def _generate_teams(self, builder, teams_count, boards, fake):
        """Generate teams for team tournament."""
        team_generator = KnockoutTeamGenerator(fake)

        # Generate team configurations
        for i in range(teams_count):
            team_name = team_generator.generate_team_name(i + 1)

            # Generate players for this team (always 4 for consistency in knockout)
            players = team_generator.generate_team_players(boards, team_name)

            # Add team with players
            builder.team(team_name, *players)

    def _generate_players(self, builder, players_count, fake):
        """Generate players for individual tournament."""
        player_generator = KnockoutPlayerGenerator(fake)

        for i in range(players_count):
            player_name, rating = player_generator.generate_player(i + 1)
            builder.player(player_name, rating)

    def _clear_knockout_data(self, league_name):
        """Clear existing knockout tournament data."""
        from heltour.tournament.models import League

        try:
            league = League.objects.get(name=league_name)

            # Count related objects before deletion
            seasons = league.season_set.all()
            season_count = seasons.count()

            if season_count > 0:
                self.stdout.write(f"Clearing existing '{league_name}' data...")
                self.stdout.write(f"  - {season_count} seasons")

                # Delete seasons (cascades to teams, players, pairings, brackets, etc.)
                seasons.delete()
                self.stdout.write("  - Related data cleared")

            # Delete the league itself
            league.delete()
            self.stdout.write("  - League deleted")

        except League.DoesNotExist:
            # No existing data to clear
            pass


class KnockoutTeamGenerator:
    """Generate teams for knockout tournaments."""

    def __init__(self, fake):
        self.fake = fake
        self.used_names = set()
        self.team_counter = 0

    def generate_team_name(self, seed_number):
        """Generate a unique team name with knockout tournament theme."""
        # Knockout tournament themed team names
        knockout_names = [
            "Elimination Eagles",
            "Bracket Breakers",
            "Final Four",
            "Championship Charge",
            "Knockout Kings",
            "Sudden Death",
            "Winner Takes All",
            "Last Stand Legion",
            "Tournament Titans",
            "Bracket Busters",
            "Crown Chasers",
            "Victory Vanguard",
            "Championship Chess",
            "Elite Eight",
            "Sweet Sixteen",
            "Final Frontier",
            "Decisive Dragons",
            "Ultimate Warriors",
            "Apex Legends",
            "Summit Seekers",
            "Peak Performers",
            "Elite Eagles",
            "Champion Challengers",
            "Victory Vikings",
            "Tournament Terrors",
            "Bracket Blazers",
            "Final Force",
            "Crown Crushers",
            "Elimination Elite",
            "Knockout Knights",
            "Championship Crew",
            "Victory Vultures",
        ]

        # Start with preset names, then generate if needed
        if seed_number <= len(knockout_names):
            base_name = knockout_names[seed_number - 1]
        else:
            # Generate fallback names
            adjectives = [
                "Mighty",
                "Elite",
                "Supreme",
                "Ultimate",
                "Royal",
                "Legendary",
                "Epic",
                "Grand",
            ]
            nouns = [
                "Warriors",
                "Champions",
                "Masters",
                "Heroes",
                "Legends",
                "Titans",
                "Eagles",
                "Dragons",
            ]
            base_name = f"{random.choice(adjectives)} {random.choice(nouns)}"

        # Ensure uniqueness
        attempts = 0
        team_name = base_name
        while team_name in self.used_names and attempts < 50:
            attempts += 1
            team_name = f"{base_name} {attempts}"

        self.used_names.add(team_name)
        return team_name

    def generate_team_players(self, count: int, team_name: str) -> list:
        """Generate players for a knockout team."""
        players = []

        # Strong player names for knockout tournaments
        strong_names = [
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
            "Alireza",
            "Nodirbek",
            "Leinier",
        ]

        for i in range(count):
            # Use strong names with team suffix
            base_name = strong_names[i % len(strong_names)]
            team_suffix = team_name.replace(" ", "").replace("'", "")[:8]
            player_name = f"{base_name}_{team_suffix}_{i+1}"

            # Generate competitive ratings for knockout (higher than swiss)
            # Board 1 gets highest rating, board 4 gets lowest
            base_rating = 2000 - (i * 100)  # Board 1: ~2000, Board 4: ~1700
            rating_variance = random.randint(-100, 150)
            rating = max(1400, min(2400, base_rating + rating_variance))

            players.append((player_name, rating))

        return players


class KnockoutPlayerGenerator:
    """Generate individual players for knockout tournaments."""

    def __init__(self, fake):
        self.fake = fake
        self.used_names = set()

    def generate_player(self, seed_number):
        """Generate a knockout tournament player with appropriate strength."""
        # Elite player names for individual knockout
        elite_names = [
            "Magnus_Tactical",
            "Garry_Strategic",
            "Bobby_Aggressive",
            "Anatoly_Positional",
            "Vladimir_Sharp",
            "Viswanathan_Solid",
            "Fabiano_Precise",
            "Hikaru_Quick",
            "Levon_Creative",
            "Wesley_Dynamic",
            "Maxime_Patient",
            "Sergey_Calculative",
            "Ding_Intuitive",
            "Ian_Resourceful",
            "Teimour_Bold",
            "Alexander_Methodical",
            "Pentala_Inventive",
            "Anish_Flexible",
            "Shakhriyar_Determined",
            "Sam_Versatile",
            "Richárd_Analytical",
            "Alireza_Brilliant",
            "Nodirbek_Energetic",
            "Leinier_Powerful",
            "Levon_Tactical",
            "Maxime_Strategic",
            "Ian_Aggressive",
            "Teimour_Solid",
            "Pentala_Sharp",
            "Anish_Positional",
            "Shakhriyar_Creative",
            "Sam_Dynamic",
        ]

        # Use predefined name or generate one
        if seed_number <= len(elite_names):
            player_name = elite_names[seed_number - 1]
        else:
            # Generate fallback name
            titles = ["GM", "IM", "FM", "CM"]
            adjectives = ["Elite", "Pro", "Master", "Expert", "Ace", "Top"]
            player_name = (
                f"{random.choice(titles)}_{random.choice(adjectives)}_{seed_number}"
            )

        # Ensure uniqueness
        attempts = 0
        unique_name = player_name
        while unique_name in self.used_names and attempts < 50:
            attempts += 1
            unique_name = f"{player_name}_{attempts}"

        self.used_names.add(unique_name)

        # Generate competitive ratings (higher seeds get better ratings)
        # Seed 1 should be strongest, last seed should be weakest
        # But still competitive for knockout format
        if seed_number <= 4:
            # Top seeds: 2200-2400
            base_rating = 2300
            variance = random.randint(-100, 100)
        elif seed_number <= 8:
            # Upper seeds: 2000-2200
            base_rating = 2100
            variance = random.randint(-100, 100)
        elif seed_number <= 16:
            # Middle seeds: 1800-2000
            base_rating = 1900
            variance = random.randint(-100, 100)
        else:
            # Lower seeds: 1600-1800
            base_rating = 1700
            variance = random.randint(-100, 100)

        rating = max(1400, min(2500, base_rating + variance))

        return unique_name, rating

