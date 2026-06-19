"""
Django management command to import TRF16 tournament data.

This command allows importing team tournament data from TRF16 format files,
useful for testing and seeding staging environments.
"""

import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from heltour.tournament_core.trf16_converter import TRF16Converter
from heltour.tournament.builder import TournamentBuilder
from heltour.tournament.models import League, Team


class Command(BaseCommand):
    help = "Import tournament data from TRF16 format file"

    def add_arguments(self, parser):
        parser.add_argument("trf16_file", type=str, help="Path to TRF16 file to import")
        parser.add_argument(
            "--league-tag",
            type=str,
            help="Override league tag (default: auto-generated from tournament name)",
        )
        parser.add_argument(
            "--season-name",
            type=str,
            help="Override season name (default: tournament name + year)",
        )
        parser.add_argument(
            "--rounds",
            type=str,
            help="Comma-separated list of rounds to import (default: all)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate without creating database objects",
        )
        parser.add_argument(
            "--create-pairings",
            action="store_true",
            help="Create pairings and results for imported rounds",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        trf16_path = options["trf16_file"]

        if not os.path.exists(trf16_path):
            raise CommandError(f"TRF16 file not found: {trf16_path}")

        # Read TRF16 content
        try:
            with open(trf16_path, "r", encoding="utf-8") as f:
                trf16_content = f.read()
        except Exception as e:
            raise CommandError(f"Error reading TRF16 file: {e}")

        # Parse TRF16
        self.stdout.write("Parsing TRF16 file...")
        converter = TRF16Converter(trf16_content)
        converter.parse()

        self.stdout.write(
            f"Found {len(converter.teams)} teams with {len(converter.players)} players"
        )
        self.stdout.write(f"Tournament: {converter.header.tournament_name}")
        self.stdout.write(f"Rounds: {converter.header.num_rounds}")

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run - no database changes made"))
            self._print_parsed_info(converter)
            return

        # Create tournament structure
        self.stdout.write("Creating tournament structure...")

        # Use database-backed builder
        builder = TournamentBuilder()

        # Set league and season info
        league_tag = options.get("league_tag") or converter._generate_league_tag(
            converter.header.tournament_name
        )
        season_name = (
            options.get("season_name")
            or f"{converter.header.tournament_name} {converter.header.start_date.year}"
        )

        # Check if league exists
        try:
            league = League.objects.get(tag=league_tag)
            self.stdout.write(f"Using existing league: {league.name}")
            builder._existing_league = league
        except League.DoesNotExist:
            self.stdout.write(f"Creating new league with tag: {league_tag}")

        builder.league(
            name=converter.header.tournament_name, tag=league_tag, type="team"
        )

        # Determine boards
        max_boards = max(len(team.player_ids) for team in converter.teams.values())

        builder.season(
            league_tag=league_tag,
            name=season_name,
            rounds=converter.header.num_rounds,
            boards=max_boards,
        )

        # Add teams and players
        self.stdout.write("Creating teams and players...")
        self._create_teams_and_players(builder, converter)

        # Build database objects
        builder.build()

        self.stdout.write(
            self.style.SUCCESS(
                f"Created league '{league_tag}' with season '{season_name}'"
            )
        )

        if options["create_pairings"]:
            # Determine which rounds to import
            if options["rounds"]:
                rounds_to_import = [
                    int(r.strip()) for r in options["rounds"].split(",")
                ]
            else:
                rounds_to_import = list(range(1, converter.header.num_rounds + 1))

            self.stdout.write(f"Importing rounds: {rounds_to_import}")

            for round_num in rounds_to_import:
                self.stdout.write(f"Creating round {round_num}...")
                self._import_round(builder, converter, round_num)

            self.stdout.write(self.style.SUCCESS("All rounds imported successfully"))

    def _create_teams_and_players(self, builder, converter):
        """Create teams and players in the builder."""
        for team_name, team in converter.teams.items():
            # Collect players for this team
            team_players = []

            for player_id in team.player_ids:
                if player_id in converter.players:
                    player = converter.players[player_id]
                    # Create player with name and rating
                    team_players.append((player.name, player.rating or 1500))

            if team_players:
                builder.team(team_name, *team_players)
                self.stdout.write(
                    f"  Created team '{team_name}' with {len(team_players)} players"
                )

    def _import_round(self, builder, converter, round_number):
        """Import a single round with pairings and results."""
        # Start the round
        round_obj = builder.start_round(round_number)

        # Get pairings from TRF16
        pairings = converter.parser.parse_round_pairings(round_number)

        # Group by teams
        team_matches = converter._group_pairings_by_teams(pairings)

        # Create team pairings
        from heltour.tournament.models import TeamPairing, TeamPlayerPairing

        pairing_order = 1
        for (white_team_name, black_team_name), board_results in team_matches.items():
            # Get team objects
            white_team = Team.objects.get(
                season=builder.current_season, name=white_team_name
            )
            black_team = Team.objects.get(
                season=builder.current_season, name=black_team_name
            )

            # Create team pairing
            team_pairing = TeamPairing.objects.create(
                round=round_obj,
                white_team=white_team,
                black_team=black_team,
                pairing_order=pairing_order,
            )

            # Create board pairings
            board_results.sort(key=lambda x: x[0])  # Sort by board number

            for board_num, result in board_results:
                # Find players for this board
                white_player = self._find_team_player(white_team, board_num)
                black_player = self._find_team_player(black_team, board_num)

                if white_player and black_player:
                    TeamPlayerPairing.objects.create(
                        team_pairing=team_pairing,
                        board_number=board_num,
                        white=white_player.player,
                        black=black_player.player,
                        result=result or "",
                    )

            # Refresh points
            team_pairing.refresh_points()
            team_pairing.save()

            pairing_order += 1

        # Complete the round
        builder.complete_round(round_obj)

    def _find_team_player(self, team, board_number):
        """Find a player on a specific board for a team."""
        try:
            return team.teammember_set.get(board_number=board_number)
        except:
            return None

    def _print_parsed_info(self, converter):
        """Print parsed information for dry run."""
        self.stdout.write("\nTeams:")
        for team_name, team in converter.teams.items():
            self.stdout.write(f"  {team_name}:")
            for player_id in team.player_ids:
                if player_id in converter.players:
                    player = converter.players[player_id]
                    self.stdout.write(
                        f"    Board {player.board_number}: {player.name} ({player.rating})"
                    )

        self.stdout.write(f"\nRounds: {converter.header.num_rounds}")
        for round_num in range(1, converter.header.num_rounds + 1):
            self.stdout.write(f"\n  Round {round_num}:")
            pairings = converter.parser.parse_round_pairings(round_num)
            team_matches = converter._group_pairings_by_teams(pairings)

            for (white_team, black_team), board_results in team_matches.items():
                board_results.sort(key=lambda x: x[0])
                results_str = " ".join(r[1] for r in board_results)
                self.stdout.write(f"    {white_team} vs {black_team}: {results_str}")
