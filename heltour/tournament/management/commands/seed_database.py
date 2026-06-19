"""
Management command to seed the database with test data using TournamentBuilder.
"""

import random
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker

from heltour.tournament.models import League
from heltour.tournament.seeders import LeagueSeeder, InviteCodeSeeder
from heltour.tournament.builder import TournamentBuilder


class Command(BaseCommand):
    help = "Seed the database with test data for development and testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--leagues",
            type=int,
            default=2,
            help="Number of leagues to create (default: 2)",
        )
        parser.add_argument(
            "--players",
            type=int,
            default=50,
            help="Number of players per tournament (default: 50)",
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
        parser.add_argument(
            "--no-clear",
            action="store_true",
            help="Don't clear existing data before seeding",
        )

    def handle(self, *args, **options):
        fake = Faker(options["locale"])

        # Adjust counts based on dataset size
        if options["minimal"]:
            num_leagues = 3  # team/open, individual/open, individual/invite_only
            num_players = 80  # Enough for teams
        elif options["full"]:
            num_leagues = 5  # Include various league types
            num_players = 100
        else:
            num_leagues = options["leagues"]
            num_players = options["players"]

        self.stdout.write(self.style.WARNING(f"Starting database seeding..."))
        
        # Clear existing data unless --no-clear is specified
        if not options["no_clear"]:
            self._clear_data()

        try:
            with transaction.atomic():
                # Initialize seeders for basic data
                league_seeder = LeagueSeeder(fake)
                invite_code_seeder = InviteCodeSeeder(fake)

                # 1. Create leagues
                self.stdout.write("Creating leagues...")
                leagues = league_seeder.seed(num_leagues)
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Created {len(leagues)} leagues")
                )

                # 2. Define season configurations
                season_configs = [
                    {
                        "name_suffix": "Completed Season",
                        "tag_suffix": "completed",
                        "is_completed": True,
                        "is_active": False,
                        "registration_open": False,
                        "nominations_open": False,
                        "start_date": timezone.now() - timezone.timedelta(days=120),
                        "rounds": 8,
                    },
                    {
                        "name_suffix": "Current Season",
                        "tag_suffix": "current",
                        "is_completed": False,
                        "is_active": True,
                        "registration_open": False,
                        "nominations_open": True,
                        "start_date": timezone.now() - timezone.timedelta(days=35),
                        "rounds": 8,
                    },
                    {
                        "name_suffix": "Upcoming Season",
                        "tag_suffix": "upcoming",
                        "is_completed": False,
                        "is_active": False,
                        "registration_open": True,
                        "nominations_open": False,
                        "start_date": timezone.now() + timezone.timedelta(days=14),
                        "rounds": 8,
                    },
                ]

                if options["full"]:
                    season_configs.append({
                        "name_suffix": "Planning Season",
                        "tag_suffix": "planning",
                        "is_completed": False,
                        "is_active": False,
                        "registration_open": False,
                        "nominations_open": False,
                        "start_date": timezone.now() + timezone.timedelta(days=60),
                        "rounds": 10,
                    })

                # 3. Create tournaments using TournamentBuilder
                all_seasons = []
                team_name_generator = TeamNameGenerator()
                player_name_generator = PlayerNameGenerator(fake)
                
                for league in leagues:
                    for i, season_config in enumerate(season_configs):
                        # Skip some configurations for minimal dataset
                        if options["minimal"] and i > 2:
                            continue
                        
                        self.stdout.write(
                            f"\nCreating {league.name} - {season_config['name_suffix']}..."
                        )
                        
                        # Create tournament using builder
                        builder = TournamentBuilder()
                        
                        # Use existing league
                        builder._existing_league = league
                        
                        # Call league method to set metadata properly
                        builder.league(league.name, league.tag, league.competitor_type)
                        
                        # Create season
                        season_name = f"{league.name} {season_config['name_suffix']}"
                        season_tag = f"{league.tag}-{season_config['tag_suffix']}"
                        boards = 4 if league.is_team_league() else None
                        
                        builder.season(
                            league.tag,
                            season_name,
                            rounds=season_config['rounds'],
                            boards=boards,
                            tag=season_tag,
                            start_date=season_config['start_date'],
                            round_duration=timezone.timedelta(days=7),
                            is_active=season_config.get('is_active', False),
                            is_completed=season_config.get('is_completed', False),
                            registration_open=season_config.get('registration_open', False),
                            nominations_open=season_config.get('nominations_open', False),
                        )
                        
                        # Generate player data for this tournament
                        player_data = player_name_generator.generate_players(
                            num_players, 
                            league.rating_type,
                            season_suffix=f"{league.tag}_{season_config['tag_suffix']}"
                        )
                        
                        # Add players/teams based on league type
                        if league.is_team_league():
                            # Calculate teams needed
                            num_teams = min(len(player_data) // boards, 16)
                            if num_teams % 2 == 1:
                                num_teams -= 1  # Even number for pairing
                            
                            # Sort players by rating for balanced teams
                            sorted_players = sorted(
                                player_data[:num_teams * boards],
                                key=lambda p: p['rating'],
                                reverse=True
                            )
                            
                            # Create teams with snake draft
                            for team_idx in range(num_teams):
                                team_name = team_name_generator.generate()
                                team_players = []
                                
                                for board in range(boards):
                                    if team_idx % 2 == 0:
                                        player_idx = team_idx + board * num_teams
                                    else:
                                        player_idx = (num_teams - 1 - team_idx) + board * num_teams
                                    
                                    if player_idx < len(sorted_players):
                                        player = sorted_players[player_idx]
                                        team_players.append((player['name'], player['rating']))
                                
                                builder.team(team_name, *team_players)
                        else:
                            # Add individual players
                            num_players_for_season = min(len(player_data), max(12, len(player_data) // 3))
                            for player in player_data[:num_players_for_season]:
                                builder.player(
                                    player['name'],
                                    rating=player['rating'],
                                    is_active=True
                                )
                        
                        # Build tournament structure
                        builder.build()
                        season = builder.current_season
                        all_seasons.append(season)
                        
                        # Generate rounds and pairings for active/completed seasons
                        if season_config.get('is_active') or season_config.get('is_completed'):
                            rounds_to_complete = (
                                season_config['rounds'] if season_config.get('is_completed') 
                                else max(1, season_config['rounds'] // 3)
                            )
                            
                            for round_num in range(1, rounds_to_complete + 1):
                                # For seeding, use manual pairing instead of JavaFo
                                # JavaFo can fail with certain tournament configurations
                                round_obj = builder.start_round(round_num, generate_pairings_auto=False)
                                
                                # Manually create simple pairings
                                if season.league.is_team_league():
                                    self._create_manual_team_pairings(round_obj)
                                else:
                                    self._create_manual_lone_pairings(round_obj)
                                
                                # Simulate results for completed rounds
                                if season_config.get('is_completed') or round_num < rounds_to_complete:
                                    builder.simulate_round_results(round_obj)
                                    builder.complete_round(round_obj)
                            
                            # Calculate final standings
                            builder.calculate_standings()
                        
                        # Summary for this season
                        league_type = "team" if league.is_team_league() else "individual"
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ Created {league_type} tournament with "
                                f"{season_config['rounds']} rounds"
                            )
                        )

                # 4. Create invite codes for all seasons
                self.stdout.write("\nCreating invite codes...")
                invite_codes = invite_code_seeder.seed(
                    captain_codes=10 if not options["minimal"] else 5,
                    seasons=all_seasons
                )
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Created {len(invite_codes)} invite codes")
                )

                # 5. Create team member codes for team leagues
                from heltour.tournament.models import Team
                all_teams = Team.objects.filter(season__in=all_seasons)
                if all_teams.exists():
                    team_codes = invite_code_seeder.seed_team_member_codes(
                        teams=list(all_teams),
                        codes_per_team=3 if not options["minimal"] else 2
                    )
                    if team_codes:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Created {len(team_codes)} team member codes"
                            )
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

    def _create_manual_team_pairings(self, round_obj):
        """Create simple manual pairings for team tournaments."""
        from heltour.tournament.models import Team, TeamPairing, TeamPlayerPairing, TeamBye
        
        teams = list(Team.objects.filter(
            season=round_obj.season, 
            is_active=True
        ).order_by('seed_rating'))
        
        # Simple pairing: pair adjacent teams
        paired = set()
        pairing_order = 1
        
        for i in range(0, len(teams) - 1, 2):
            if i + 1 < len(teams):
                white_team = teams[i]
                black_team = teams[i + 1]
                
                # Create team pairing
                team_pairing = TeamPairing.objects.create(
                    round=round_obj,
                    white_team=white_team,
                    black_team=black_team,
                    pairing_order=pairing_order
                )
                
                # Create board pairings
                white_members = list(white_team.teammember_set.order_by('board_number'))
                black_members = list(black_team.teammember_set.order_by('board_number'))
                
                for board_num in range(1, round_obj.season.boards + 1):
                    if board_num <= len(white_members) and board_num <= len(black_members):
                        # Alternate colors by board
                        if board_num % 2 == 1:
                            white_player = white_members[board_num - 1].player
                            black_player = black_members[board_num - 1].player
                        else:
                            white_player = black_members[board_num - 1].player
                            black_player = white_members[board_num - 1].player
                        
                        TeamPlayerPairing.objects.create(
                            team_pairing=team_pairing,
                            board_number=board_num,
                            white=white_player,
                            black=black_player,
                            result=""
                        )
                
                paired.add(white_team.id)
                paired.add(black_team.id)
                pairing_order += 1
        
        # Handle odd team with bye
        for team in teams:
            if team.id not in paired:
                TeamBye.objects.create(
                    round=round_obj,
                    team=team,
                    type='full-point-pairing-bye'
                )

    def _create_manual_lone_pairings(self, round_obj):
        """Create simple manual pairings for lone tournaments."""
        from heltour.tournament.models import SeasonPlayer, LonePlayerPairing, PlayerBye
        
        season_players = list(SeasonPlayer.objects.filter(
            season=round_obj.season,
            is_active=True
        ).select_related('player').order_by('-seed_rating'))
        
        # Simple pairing: pair adjacent players
        paired = set()
        pairing_order = 1
        
        for i in range(0, len(season_players) - 1, 2):
            if i + 1 < len(season_players):
                white_sp = season_players[i]
                black_sp = season_players[i + 1]
                
                LonePlayerPairing.objects.create(
                    round=round_obj,
                    white=white_sp.player,
                    black=black_sp.player,
                    pairing_order=pairing_order,
                    result=""
                )
                
                paired.add(white_sp.player_id)
                paired.add(black_sp.player_id)
                pairing_order += 1
        
        # Handle odd player with bye
        for sp in season_players:
            if sp.player_id not in paired:
                PlayerBye.objects.create(
                    round=round_obj,
                    player=sp.player,
                    type='full-point'
                )

    def _clear_data(self):
        """Clear existing tournament data."""
        from heltour.tournament.models import (
            League, Season, Player, Team, Registration,
            TeamPairing, LonePlayerPairing, TeamPlayerPairing,
            Round, InviteCode, TeamMember, SeasonPlayer,
            TeamScore, LonePlayerScore, PlayerBye, TeamBye,
        )
        
        self.stdout.write(self.style.WARNING("Clearing existing data..."))
        
        # Delete in dependency order
        models_to_clear = [
            TeamPlayerPairing,
            TeamPairing,
            LonePlayerPairing,
            PlayerBye,
            TeamBye,
            Round,
            TeamScore,
            LonePlayerScore,
            TeamMember,
            SeasonPlayer,
            Registration,
            InviteCode,
            Team,
            Season,
            Player,
            League,
        ]
        
        for model in models_to_clear:
            count = model.objects.count()
            if count > 0:
                model.objects.all().delete()
                self.stdout.write(f"  - Deleted {count} {model.__name__} records")

    def _print_summary(self):
        """Print summary of created data."""
        from heltour.tournament.models import (
            League,
            Season,
            Player,
            Team,
            Registration,
            PlayerPairing,
            InviteCode,
        )

        self.stdout.write("\nDatabase Summary:")
        self.stdout.write(f"  - Leagues: {League.objects.count()}")
        self.stdout.write(f"  - Seasons: {Season.objects.count()}")
        self.stdout.write(f"  - Players: {Player.objects.count()}")
        self.stdout.write(f"  - Teams: {Team.objects.count()}")
        self.stdout.write(f"  - Registrations: {Registration.objects.count()}")
        self.stdout.write(f"  - Invite Codes: {InviteCode.objects.count()}")
        
        # Count games from both pairing types
        from heltour.tournament.models import TeamPlayerPairing, LonePlayerPairing
        team_games = TeamPlayerPairing.objects.exclude(result="").count()
        lone_games = LonePlayerPairing.objects.exclude(result="").count()
        self.stdout.write(f"  - Games played: {team_games + lone_games}")

        # Show unused invite codes for manual testing
        invite_only_leagues = League.objects.filter(registration_mode="invite_only")
        if invite_only_leagues.exists():
            self.stdout.write("\nUnused invite codes for manual testing:")
            for league in invite_only_leagues:
                unused = InviteCode.objects.filter(
                    league=league,
                    used_by__isnull=True,
                    code_type="captain",
                    season__registration_open=True,
                )
                if unused.exists():
                    self.stdout.write(f"  {league.name}:")
                    for ic in unused[:5]:
                        self.stdout.write(f"    - {ic.code} (season: {ic.season.name})")

        # Show some sample players for testing
        self.stdout.write("\nSample players for testing:")
        for player in Player.objects.all()[:5]:
            rating = player.rating
            self.stdout.write(f"  - {player.lichess_username} (Rating: {rating})")


class PlayerNameGenerator:
    """Generate unique player names with ratings."""
    
    def __init__(self, fake):
        self.fake = fake
        self.used_names = set()
        
    def generate_players(self, count: int, rating_type: str = "standard", season_suffix: str = "") -> list:
        """Generate player data with unique names and appropriate ratings."""
        players = []
        
        # Rating ranges based on type
        if rating_type == "classical":
            base_rating = 1800
            spread = 400
        elif rating_type == "rapid":
            base_rating = 1700
            spread = 350
        else:  # standard/blitz
            base_rating = 1600
            spread = 300
        
        for i in range(count):
            # Generate unique username
            attempts = 0
            while attempts < 100:
                username = self.fake.user_name()
                if season_suffix:
                    username = f"{username}_{season_suffix}"
                if username not in self.used_names:
                    self.used_names.add(username)
                    break
                attempts += 1
            else:
                # Fallback to numbered username
                username = f"player{i}_{season_suffix}"
                self.used_names.add(username)
            
            # Generate rating with normal distribution
            rating = int(random.gauss(base_rating, spread / 3))
            rating = max(800, min(2800, rating))  # Clamp to reasonable range
            
            players.append({
                'name': username,
                'rating': rating
            })
        
        return players


class TeamNameGenerator:
    """Generate unique team names."""
    
    ADJECTIVES = [
        "Royal", "Swift", "Mighty", "Silent", "Golden", "Silver", "Crimson", 
        "Azure", "Fierce", "Noble", "Ancient", "Modern", "Tactical", "Strategic",
        "Dynamic", "Lightning", "Thunder", "Storm", "Fire", "Ice", "Shadow", 
        "Brilliant", "Epic", "Legendary", "Mystic", "Valiant", "Iron", "Steel",
        "Crystal", "Quantum", "Cosmic", "Solar", "Lunar", "Arctic", "Blazing"
    ]

    NOUNS = [
        "Knights", "Bishops", "Rooks", "Queens", "Kings", "Pawns", "Masters",
        "Tacticians", "Strategists", "Defenders", "Attackers", "Gladiators",
        "Warriors", "Champions", "Legends", "Eagles", "Lions", "Tigers", 
        "Dragons", "Phoenix", "Falcons", "Sharks", "Wolves", "Guardians",
        "Crusaders", "Sentinels", "Titans", "Giants", "Wizards", "Sorcerers"
    ]
    
    def __init__(self):
        self.used_names = set()
    
    def generate(self) -> str:
        """Generate a unique team name."""
        attempts = 0
        while attempts < 100:
            adj = random.choice(self.ADJECTIVES)
            noun = random.choice(self.NOUNS)
            name = f"{adj} {noun}"
            
            if name not in self.used_names:
                self.used_names.add(name)
                return name
            
            attempts += 1
        
        # Fallback with number
        base_name = f"{random.choice(self.ADJECTIVES)} {random.choice(self.NOUNS)}"
        counter = 2
        while f"{base_name} {counter}" in self.used_names:
            counter += 1
        
        name = f"{base_name} {counter}"
        self.used_names.add(name)
        return name