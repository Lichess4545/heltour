"""Unified management command to seed TRF16 tournaments."""

import os
from django.core.management.base import BaseCommand, CommandError
from heltour.tournament.seeders import trf16_file_seeder
from heltour.tournament.models import League


class Command(BaseCommand):
    help = 'Seed tournament data from TRF16 files'

    def add_arguments(self, parser):
        # Tournament source - either predefined name or file path
        parser.add_argument(
            'tournament',
            type=str,
            help='Predefined tournament name (e.g., "friendship-cup", "championship2025") or path to TRF16 file'
        )
        
        parser.add_argument(
            '--league-tag',
            type=str,
            help='League tag (required for custom TRF16 files, optional for predefined tournaments)'
        )
        
        parser.add_argument(
            '--mode',
            type=str,
            default='complete',
            choices=['teams', 'round1', 'round1_results', 'complete'],
            help='Seeding mode: teams only, round 1 pairings, round 1 results, or complete tournament'
        )
        
        parser.add_argument(
            '--use-existing-league',
            action='store_true',
            help='Use existing league if found (otherwise creates new season)'
        )
        
        parser.add_argument(
            '--list',
            action='store_true',
            help='List available predefined tournaments'
        )

    def handle(self, *args, **options):
        # Handle --list option
        if options['list']:
            self.list_tournaments()
            return
        
        tournament_arg = options['tournament']
        mode = options['mode']
        use_existing = options['use_existing_league']
        
        # Get predefined tournaments
        predefined = trf16_file_seeder.get_predefined_tournaments()
        
        # Determine TRF16 file path and league tag
        if tournament_arg in predefined:
            # Using predefined tournament
            trf16_path = predefined[tournament_arg]
            league_tag = options['league_tag'] or tournament_arg
            self.stdout.write(f"Using predefined tournament: {tournament_arg}")
        elif os.path.exists(tournament_arg):
            # Using custom file
            trf16_path = tournament_arg
            league_tag = options['league_tag']
            if not league_tag:
                # Try to generate a reasonable default from filename
                basename = os.path.basename(tournament_arg)
                if basename.endswith('.trf'):
                    league_tag = basename[:-4]
                else:
                    raise CommandError('--league-tag is required when using a custom TRF16 file')
        else:
            # Neither predefined nor valid file
            available = ', '.join(sorted(predefined.keys()))
            raise CommandError(
                f'Tournament "{tournament_arg}" not found.\n'
                f'Available predefined tournaments: {available}\n'
                f'Or provide a valid path to a TRF16 file.'
            )
        
        # Check if we should use existing league
        existing_league = None
        if use_existing:
            try:
                existing_league = League.objects.get(tag=league_tag)
                self.stdout.write(f'Using existing league: {existing_league.name}')
            except League.DoesNotExist:
                self.stdout.write('No existing league found, will create new one')
        
        # Execute based on mode
        try:
            if mode == 'teams':
                season = trf16_file_seeder.seed_teams_only(
                    trf16_path, league_tag, existing_league
                )
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully seeded teams for {season.name}')
                )
                
            elif mode == 'round1':
                season = trf16_file_seeder.seed_partial_tournament(
                    trf16_path, league_tag, 
                    num_rounds=1, include_results=False, 
                    existing_league=existing_league
                )
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully seeded teams and round 1 pairings for {season.name}')
                )
                
            elif mode == 'round1_results':
                season = trf16_file_seeder.seed_partial_tournament(
                    trf16_path, league_tag,
                    num_rounds=1, include_results=True,
                    existing_league=existing_league
                )
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully seeded teams and round 1 with results for {season.name}')
                )
                
            elif mode == 'complete':
                season = trf16_file_seeder.seed_complete_tournament(
                    trf16_path, league_tag, existing_league
                )
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully seeded complete tournament: {season.name}')
                )
                
            # Show URL
            self.stdout.write(
                f'\nView the tournament at: http://localhost:8000/{league_tag}/'
            )
                
        except Exception as e:
            raise CommandError(f'Error seeding tournament: {str(e)}')
    
    def list_tournaments(self):
        """List available predefined tournaments."""
        predefined = trf16_file_seeder.get_predefined_tournaments()
        
        if not predefined:
            self.stdout.write('No predefined tournaments found.')
            return
        
        self.stdout.write('Available predefined tournaments:\n')
        for name, path in sorted(predefined.items()):
            # Try to read tournament name from file
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    if first_line.startswith('012'):
                        tournament_name = first_line[4:].strip()
                        self.stdout.write(f'  {name:<20} - {tournament_name}')
                    else:
                        self.stdout.write(f'  {name:<20}')
            except Exception:
                self.stdout.write(f'  {name:<20}')
        
        self.stdout.write('\nUsage: python manage.py seed_trf16_tournament <tournament_name>')