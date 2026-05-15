"""
Management command to generate random results for the current round of a season.

This command takes a season ID and generates random results for all pairings
in the current round that don't already have results.
"""

import random
from django.core.management.base import BaseCommand, CommandError

from heltour.tournament.models import (
    Season,
    Round,
    LonePlayerPairing,
)
from heltour.tournament.builder import simulate_game_result


class Command(BaseCommand):
    help = "Generate random results for current round pairings in a season"

    def add_arguments(self, parser):
        parser.add_argument(
            "season_id",
            type=int,
            help="Season ID to generate results for",
        )
        parser.add_argument(
            "--round-number",
            type=int,
            help="Specific round number (default: current/latest round)",
        )
        parser.add_argument(
            "--forfeit-rate",
            type=float,
            default=0.05,
            help="Probability of forfeit results (default: 0.05 = 5%%)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing results (default: skip games with results)",
        )
        parser.add_argument(
            "--pairing-id",
            type=int,
            help=(
                "Only generate results for a single pairing (one match). For "
                "team leagues this is a TeamPairing id; for individual leagues "
                "a LonePlayerPairing id. Auto-advancement is skipped so you can "
                "progress one match at a time."
            ),
        )
        parser.add_argument(
            "--match-number",
            type=int,
            help=(
                "Only generate results for one match of a multi-match knockout "
                "stage, across every bracket (1 = all of match 1, 2 = all of "
                "match 2, ...). This is the match number within the stage, not "
                "the round number. Auto-advancement is skipped."
            ),
        )

    def handle(self, *args, **options):
        season_id = options["season_id"]
        round_number = options.get("round_number")
        forfeit_rate = options["forfeit_rate"]
        dry_run = options["dry_run"]
        overwrite = options["overwrite"]
        pairing_id = options.get("pairing_id")
        match_number = options.get("match_number")
        if pairing_id is not None and match_number is not None:
            raise CommandError("Use either --pairing-id or --match-number, not both")
        targeted = pairing_id is not None or match_number is not None

        try:
            season = Season.objects.get(id=season_id)
        except Season.DoesNotExist:
            raise CommandError(f"Season with ID {season_id} does not exist")

        self.stdout.write(f"Processing season: {season.name} ({season.league.name})")

        # Find the target round
        if round_number:
            try:
                target_round = Round.objects.get(season=season, number=round_number)
            except Round.DoesNotExist:
                raise CommandError(
                    f"Round {round_number} does not exist for season {season_id}"
                )
        else:
            # Use the latest round
            target_round = (
                Round.objects.filter(season=season).order_by("-number").first()
            )
            if not target_round:
                raise CommandError(f"No rounds found for season {season_id}")

        self.stdout.write(f"Target round: {target_round.number}")

        # Validate targeting options, if given
        if pairing_id is not None:
            if season.league.competitor_type == "team":
                from heltour.tournament.models import TeamPairing

                exists = TeamPairing.objects.filter(
                    id=pairing_id, round=target_round
                ).exists()
            else:
                exists = LonePlayerPairing.objects.filter(
                    id=pairing_id, round=target_round
                ).exists()
            if not exists:
                raise CommandError(
                    f"Pairing {pairing_id} is not in round {target_round.number} "
                    f"of season {season_id}"
                )
            self.stdout.write(f"Targeting single pairing: {pairing_id}")
        elif match_number is not None:
            if match_number < 1:
                raise CommandError("--match-number must be >= 1")
            self.stdout.write(
                f"Targeting match {match_number} of the stage (all brackets)"
            )

        # Check if this is a knockout tournament
        is_knockout = season.league.pairing_type.startswith("knockout")

        # Generate results based on league type and tournament format
        if season.league.competitor_type == "team":
            results_generated = self._generate_team_results(
                target_round, forfeit_rate, dry_run, overwrite, is_knockout,
                pairing_id, match_number,
            )
        else:
            results_generated = self._generate_lone_results(
                target_round, forfeit_rate, dry_run, overwrite, is_knockout,
                pairing_id, match_number,
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: Would generate {results_generated} results"
                )
            )
        else:
            if results_generated > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Generated {results_generated} random results"
                    )
                )

                # Clear cache and update team/player scores
                from django.core.cache import cache

                cache.clear()
                self.stdout.write("Cache cleared")

                # Update team/player scores
                season.calculate_scores()
                self.stdout.write("✓ Scores updated")

                # For knockout tournaments, try to advance to next round
                if is_knockout:
                    if targeted:
                        self.stdout.write(
                            "Skipping auto-advancement (--pairing-id / "
                            "--match-number targets only part of the round). "
                            "Advance via the dashboard, or rerun without a "
                            "targeting option once the round is complete."
                        )
                    else:
                        # Force refresh of all team pairing data before advancement check
                        from django.db import transaction
                        transaction.commit()  # Ensure all changes are committed
                        self._try_advance_knockout(target_round, season, dry_run)
            else:
                self.stdout.write(
                    "No results generated (all games already have results)"
                )

    def _filter_to_match_number(self, pairings, match_number, get_pair_key):
        """Return the subset of `pairings` that are match `match_number` of the stage.

        Match number within a multi-match stage is derived from pairing_order:
        pairings are laid out match-by-match, so with N unique competitor pairs
        the first N pairings are match 1, the next N are match 2, and so on.
        """
        from heltour.tournament_core.multi_match import (
            get_match_number_from_pairing_order,
        )

        pairings = list(pairings)
        unique_pairs = {
            key for key in (get_pair_key(p) for p in pairings) if key is not None
        }
        total_pairs = len(unique_pairs) or 1
        return [
            p
            for p in pairings
            if get_match_number_from_pairing_order(p.pairing_order, total_pairs)
            == match_number
        ]

    def _generate_team_results(
        self, round_obj, forfeit_rate, dry_run, overwrite, is_knockout=False,
        pairing_id=None, match_number=None
    ):
        """Generate results for team tournament board pairings."""
        from heltour.tournament.models import TeamPairing

        results_generated = 0

        team_pairings = TeamPairing.objects.filter(round=round_obj).prefetch_related(
            "teamplayerpairing_set__white", "teamplayerpairing_set__black"
        )
        if pairing_id is not None:
            team_pairings = team_pairings.filter(id=pairing_id)
        elif match_number is not None:
            target_ids = [
                p.id
                for p in self._filter_to_match_number(
                    TeamPairing.objects.filter(round=round_obj),
                    match_number,
                    lambda p: (
                        tuple(sorted([p.white_team_id, p.black_team_id]))
                        if p.black_team_id
                        else None
                    ),
                )
            ]
            team_pairings = team_pairings.filter(id__in=target_ids)

        self.stdout.write(f"Found {team_pairings.count()} team pairings")

        if is_knockout:
            self.stdout.write("  (Knockout tournament - generating decisive results)")

        for team_pairing in team_pairings:
            # Skip bye pairings in knockout
            if is_knockout and team_pairing.black_team_id is None:
                continue
            board_pairings = team_pairing.teamplayerpairing_set.order_by("board_number")

            pairing_results = []
            boards_processed = 0

            for board_pairing in board_pairings:
                # Skip if result already exists and not overwriting
                if board_pairing.result and not overwrite:
                    continue

                # Handle missing players (assign forfeit results)
                if board_pairing.white is None and board_pairing.black is None:
                    result = "0F-0F"  # Double forfeit
                elif board_pairing.white is None:
                    result = "0F-1X"  # Black wins by forfeit
                elif board_pairing.black is None:
                    result = "1X-0F"  # White wins by forfeit
                else:
                    # Generate result for normal pairing
                    white_rating = board_pairing.white.rating or 1500
                    black_rating = board_pairing.black.rating or 1500
                    result = simulate_game_result(
                        white_rating,
                        black_rating,
                        allow_forfeit=True,
                        forfeit_rate=forfeit_rate,
                    )

                pairing_results.append(
                    {
                        "board": board_pairing.board_number,
                        "white": (
                            board_pairing.white.lichess_username
                            if board_pairing.white
                            else "MISSING"
                        ),
                        "black": (
                            board_pairing.black.lichess_username
                            if board_pairing.black
                            else "MISSING"
                        ),
                        "result": result,
                        "pairing": board_pairing,
                    }
                )
                boards_processed += 1

            if boards_processed > 0:
                # For single-match knockout tournaments, ensure decisive results (avoid ties)
                # Multi-match knockouts allow ties and handle them at the aggregate level
                try:
                    from heltour.tournament.models import KnockoutBracket
                    bracket = KnockoutBracket.objects.get(season=round_obj.season)
                    is_multi_match = bracket.matches_per_stage > 1
                except KnockoutBracket.DoesNotExist:
                    is_multi_match = False
                    
                if is_knockout and not is_multi_match and not dry_run:
                    self._ensure_knockout_decisive_result(team_pairing, pairing_results)

                self.stdout.write(
                    f"  {team_pairing.white_team.name} vs {team_pairing.black_team.name}:"
                )

                for result_info in pairing_results:
                    self.stdout.write(
                        f"    Board {result_info['board']}: "
                        f"{result_info['white']} vs {result_info['black']} = "
                        f"{result_info['result']}"
                    )

                    if not dry_run:
                        result_info["pairing"].result = result_info["result"]
                        result_info["pairing"].save()

                results_generated += boards_processed

                # Show team match result for knockout
                if is_knockout:
                    if not dry_run:
                        team_pairing.refresh_points()
                        team_pairing.save()
                    white_points = sum(
                        self._result_to_points(r["result"], True)
                        for r in pairing_results
                    )
                    black_points = sum(
                        self._result_to_points(r["result"], False)
                        for r in pairing_results
                    )
                    winner = (
                        "White"
                        if white_points > black_points
                        else "Black" if black_points > white_points else "TIE"
                    )
                    self.stdout.write(
                        f"    → Match result: {white_points:.1f} - {black_points:.1f} ({winner} wins)"
                    )

                    # For single-match knockouts, add manual tiebreak if tied
                    # Multi-match knockouts only add tiebreaks after ALL matches complete
                    if winner == "TIE" and not dry_run and not is_multi_match:
                        # Randomly assign tiebreak winner
                        tiebreak_winner = random.choice([1.0, -1.0])
                        team_pairing.manual_tiebreak_value = tiebreak_winner
                        team_pairing.save()
                        # Refresh points immediately after setting tiebreak
                        team_pairing.refresh_points()
                        team_pairing.save()
                        winner_name = "White" if tiebreak_winner > 0 else "Black"
                        self.stdout.write(
                            f"    → Tiebreak: {winner_name} wins (random tiebreak applied)"
                        )

        # Update all team pairing points for this round (not just current one)
        if not dry_run and results_generated > 0:
            self.stdout.write("Refreshing team pairing points...")
            
            # For multi-match knockout tournaments, we need to aggregate scores across all matches
            # between the same team pairs before determining winners
            if is_knockout:
                try:
                    from heltour.tournament.models import KnockoutBracket
                    bracket = KnockoutBracket.objects.get(season=round_obj.season)
                    is_multi_match = bracket.matches_per_stage > 1
                except KnockoutBracket.DoesNotExist:
                    is_multi_match = False
                
                if is_multi_match:
                    self._refresh_multi_match_scores(team_pairings, round_obj)
                else:
                    # Single match - use regular refresh
                    for tp in team_pairings:
                        tp.refresh_points()
                        tp.save()
            else:
                # Non-knockout - use regular refresh
                for tp in team_pairings:
                    tp.refresh_points()
                    tp.save()
            
            self.stdout.write(
                f"✓ Refreshed points for {len(team_pairings)} team pairings"
            )

        return results_generated

    def _refresh_multi_match_scores(self, team_pairings, target_round):
        """Refresh scores for multi-match knockout tournaments by aggregating across all matches per team pair."""
        from collections import defaultdict
        from heltour.tournament.models import KnockoutBracket
        
        # Get the bracket to determine matches_per_stage
        try:
            bracket = KnockoutBracket.objects.get(season=target_round.season)
        except KnockoutBracket.DoesNotExist:
            # Fallback to regular refresh if no bracket
            for tp in team_pairings:
                tp.refresh_points()
                tp.save()
            return
        
        # Group pairings by team pair (using sorted team IDs as key)
        team_pair_groups = defaultdict(list)
        for tp in team_pairings:
            # Create a consistent key for team pairs regardless of white/black assignment
            team_key = tuple(sorted([tp.white_team.id, tp.black_team.id]))
            team_pair_groups[team_key].append(tp)
        
        self.stdout.write(f"  Processing {len(team_pair_groups)} unique team pairs across {len(team_pairings)} pairings")
        
        for team_key, pairings in team_pair_groups.items():
            # Calculate aggregate scores across all matches for this team pair
            team1_id, team2_id = team_key
            total_team1_points = 0.0
            total_team2_points = 0.0
            
            for pairing in pairings:
                # Refresh individual pairing points first
                pairing.refresh_points()
                
                # Add to aggregate based on which team is which
                if pairing.white_team.id == team1_id:
                    total_team1_points += pairing.white_points or 0.0
                    total_team2_points += pairing.black_points or 0.0
                else:
                    total_team1_points += pairing.black_points or 0.0
                    total_team2_points += pairing.white_points or 0.0
            
            # Determine aggregate winner
            if total_team1_points > total_team2_points:
                aggregate_winner = team1_id
            elif total_team2_points > total_team1_points:
                aggregate_winner = team2_id
            else:
                aggregate_winner = None  # Tie
            
            # Apply aggregate results to the primary pairing (lowest pairing_order)
            primary_pairing = min(pairings, key=lambda p: p.pairing_order)
            
            if aggregate_winner is None:
                # Tied - need manual tiebreak ONLY if this is the final match of the stage
                # First, check if all matches between these teams are complete
                all_matches_complete = all(
                    (p.white_points is not None and p.black_points is not None) 
                    for p in pairings
                )
                
                if all_matches_complete and len(pairings) == bracket.matches_per_stage:
                    # All matches complete and tied - apply tiebreak
                    if primary_pairing.manual_tiebreak_value is None:
                        tiebreak_winner = random.choice([1.0, -1.0])
                        primary_pairing.manual_tiebreak_value = tiebreak_winner
                        winner_name = primary_pairing.white_team.name if (
                            (primary_pairing.white_team.id == team1_id and tiebreak_winner > 0) or
                            (primary_pairing.black_team.id == team1_id and tiebreak_winner < 0)
                        ) else primary_pairing.black_team.name
                        self.stdout.write(
                            f"  → Multi-match aggregate TIED: {primary_pairing.white_team.name} vs {primary_pairing.black_team.name} "
                            f"({total_team1_points:.1f}-{total_team2_points:.1f}) - {winner_name} wins by tiebreak"
                        )
                else:
                    # Not all matches complete yet - don't apply tiebreak
                    self.stdout.write(
                        f"  → Multi-match partial: {primary_pairing.white_team.name} vs {primary_pairing.black_team.name} "
                        f"({total_team1_points:.1f}-{total_team2_points:.1f}) - {len(pairings)}/{bracket.matches_per_stage} matches complete"
                    )
            else:
                # Clear winner - no tiebreak needed
                winner_name = primary_pairing.white_team.name if (
                    (primary_pairing.white_team.id == aggregate_winner) 
                ) else primary_pairing.black_team.name
                self.stdout.write(
                    f"  → Multi-match result: {primary_pairing.white_team.name} vs {primary_pairing.black_team.name} "
                    f"({total_team1_points:.1f}-{total_team2_points:.1f}) - {winner_name} wins"
                )
            
            # Save all pairings
            for pairing in pairings:
                pairing.save()

    def _generate_lone_results(
        self, round_obj, forfeit_rate, dry_run, overwrite, is_knockout=False,
        pairing_id=None, match_number=None
    ):
        """Generate results for individual tournament pairings."""
        results_generated = 0

        lone_pairings = LonePlayerPairing.objects.filter(
            round=round_obj
        ).select_related("white", "black")
        if pairing_id is not None:
            lone_pairings = lone_pairings.filter(id=pairing_id)
        elif match_number is not None:
            target_ids = [
                p.id
                for p in self._filter_to_match_number(
                    LonePlayerPairing.objects.filter(round=round_obj),
                    match_number,
                    lambda p: (
                        tuple(sorted([p.white_id, p.black_id]))
                        if p.black_id
                        else None
                    ),
                )
            ]
            lone_pairings = lone_pairings.filter(id__in=target_ids)

        self.stdout.write(f"Found {lone_pairings.count()} individual pairings")

        if is_knockout:
            self.stdout.write("  (Knockout tournament - no draws allowed)")

        for pairing in lone_pairings:
            # Skip bye pairings in knockout
            if is_knockout and pairing.black_id is None:
                continue
            # Skip if result already exists and not overwriting
            if pairing.result and not overwrite:
                continue

            # Generate result
            white_rating = pairing.white.rating or 1500
            black_rating = pairing.black.rating or 1500

            if is_knockout:
                # Force decisive results in knockout (no draws)
                result = self._generate_knockout_result(
                    white_rating, black_rating, forfeit_rate
                )
            else:
                result = simulate_game_result(
                    white_rating,
                    black_rating,
                    allow_forfeit=True,
                    forfeit_rate=forfeit_rate,
                )

            self.stdout.write(
                f"  {pairing.white.lichess_username} vs "
                f"{pairing.black.lichess_username} = {result}"
            )

            if not dry_run:
                pairing.result = result
                pairing.save()

            results_generated += 1

        return results_generated

    def _generate_knockout_result(self, white_rating, black_rating, forfeit_rate):
        """Generate a decisive result for knockout tournaments (no draws)."""
        # Small chance of forfeit
        if random.random() < forfeit_rate:
            forfeit_type = random.random()
            if forfeit_type < 0.5:
                return "1X-0F"  # Black forfeits
            else:
                return "0F-1X"  # White forfeits

        # Calculate expected score using Elo formula
        exp_white = 1 / (1 + 10 ** ((black_rating - white_rating) / 400))

        # Force decisive result (no draws in knockout)
        rand = random.random()
        if rand < exp_white:
            return "1-0"  # White wins
        else:
            return "0-1"  # Black wins

    def _result_to_points(self, result, is_white):
        """Convert game result to points for white or black player."""
        if result == "1-0":
            return 1.0 if is_white else 0.0
        elif result == "0-1":
            return 0.0 if is_white else 1.0
        elif result == "1/2-1/2":
            return 0.5
        elif result == "1X-0F":  # White wins by forfeit
            return 1.0 if is_white else 0.0
        elif result == "0F-1X":  # Black wins by forfeit
            return 0.0 if is_white else 1.0
        elif result == "0F-0F":  # Double forfeit
            return 0.0
        else:
            return 0.0

    def _ensure_knockout_decisive_result(self, team_pairing, pairing_results):
        """Ensure team match has a decisive result for knockout tournaments."""
        # Only apply this logic for single-match knockouts
        # Multi-match knockouts handle ties differently
        
        white_points = sum(
            self._result_to_points(r["result"], True) for r in pairing_results
        )
        black_points = sum(
            self._result_to_points(r["result"], False) for r in pairing_results
        )

        # If tied, change one draw to a win to create decisive result
        if white_points == black_points:
            # Find a draw to convert
            draws = [r for r in pairing_results if r["result"] == "1/2-1/2"]
            if draws:
                # Convert one draw to a win (favor higher-rated player)
                draw_to_change = draws[0]
                pairing_obj = draw_to_change["pairing"]

                if pairing_obj.white and pairing_obj.black:
                    white_rating = pairing_obj.white.rating or 1500
                    black_rating = pairing_obj.black.rating or 1500

                    # Higher rated player wins the "tiebreak"
                    if white_rating >= black_rating:
                        draw_to_change["result"] = "1-0"
                    else:
                        draw_to_change["result"] = "0-1"
                else:
                    # Random if no ratings
                    draw_to_change["result"] = random.choice(["1-0", "0-1"])

    def _try_advance_knockout(self, completed_round, season, dry_run):
        """Try to advance knockout tournament to next round."""
        from heltour.tournament.models import Round, KnockoutBracket

        # Check if this is a multi-match knockout tournament
        try:
            bracket = KnockoutBracket.objects.get(season=season)
            is_multi_match = bracket.matches_per_stage > 1
        except KnockoutBracket.DoesNotExist:
            is_multi_match = False

        if is_multi_match:
            self._try_advance_multi_match_knockout(completed_round, season, bracket, dry_run)
        else:
            self._try_advance_single_match_knockout(completed_round, season, dry_run)

    def _try_advance_single_match_knockout(self, completed_round, season, dry_run):
        """Try to advance single-match knockout tournament to next round."""
        from heltour.tournament.models import Round, TeamPairing
        from django.db.models import F

        # Don't mark round as completed yet if tied matches exist
        tied_pairings = TeamPairing.objects.filter(
            round=completed_round,
            white_points__isnull=False,
            black_points__isnull=False,
            manual_tiebreak_value__isnull=True
        ).filter(white_points=F('black_points'))
        
        if tied_pairings.exists():
            self.stdout.write(f"Found {tied_pairings.count()} tied pairings - cannot advance yet")
            for pairing in tied_pairings:
                self.stdout.write(f"  - {pairing.white_team.name} vs {pairing.black_team.name}: {pairing.white_points}-{pairing.black_points} (needs tiebreak)")
            return None
        
        # Check if round is complete and can advance
        if not completed_round.is_completed:
            # Mark round as completed
            completed_round.is_completed = True
            if not dry_run:
                completed_round.save()
            self.stdout.write(f"✓ Round {completed_round.number} marked as completed")

        # Debug: Check for tied matches before advancement
        if season.league.competitor_type == 'team':
            tied_pairings = TeamPairing.objects.filter(
                round=completed_round,
                white_points__isnull=False,
                black_points__isnull=False,
                manual_tiebreak_value__isnull=True
            ).filter(white_points=F('black_points'))
            
            if tied_pairings.exists():
                self.stdout.write(f"DEBUG: Found {tied_pairings.count()} tied pairings:")
                for pairing in tied_pairings:
                    self.stdout.write(f"  - {pairing.white_team.name} vs {pairing.black_team.name}: {pairing.white_points}-{pairing.black_points} (tiebreak: {pairing.manual_tiebreak_value})")
            else:
                self.stdout.write("DEBUG: No tied pairings found - should be able to advance")

        # Check if there are more rounds to play
        total_rounds = Round.objects.filter(season=season).count()
        if completed_round.number >= total_rounds:
            self.stdout.write("✓ Tournament complete! All rounds finished.")
            return

        # Try to advance to next round
        try:
            from heltour.tournament.pairinggen import advance_knockout_tournament

            if not dry_run:
                next_round = advance_knockout_tournament(completed_round)
                if next_round:
                    from heltour.tournament_core.knockout import get_knockout_stage_name
                    from heltour.tournament.models import KnockoutBracket

                    try:
                        bracket = KnockoutBracket.objects.get(season=season)
                        teams_remaining = bracket.bracket_size // (
                            2 ** (next_round.number - 1)
                        )
                        stage_name = get_knockout_stage_name(teams_remaining)
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Advanced to {stage_name} (Round {next_round.number})"
                            )
                        )

                        # Count new pairings
                        if season.league.competitor_type == "team":
                            from heltour.tournament.models import TeamPairing

                            new_pairings = TeamPairing.objects.filter(
                                round=next_round
                            ).count()
                        else:
                            new_pairings = LonePlayerPairing.objects.filter(
                                round=next_round
                            ).count()

                        self.stdout.write(f"  - {new_pairings} new matches created")
                        self.stdout.write(
                            f"  - Use 'generate_random_results {season.id} --round-number {next_round.number}' for next round"
                        )
                    except KnockoutBracket.DoesNotExist:
                        self.stdout.write(f"✓ Advanced to Round {next_round.number}")
                else:
                    self.stdout.write(
                        "Could not advance tournament (check for tied matches needing tiebreaks)"
                    )
            else:
                self.stdout.write(
                    "DRY RUN: Would attempt to advance tournament to next round"
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to advance tournament: {str(e)}")
            )

    def _try_advance_multi_match_knockout(self, completed_round, season, bracket, dry_run):
        """Try to advance multi-match knockout tournament."""
        from heltour.tournament.db_to_structure import knockout_bracket_to_structure
        from heltour.tournament_core.multi_match import can_generate_next_match_set, generate_next_match_set
        from heltour.tournament.models import TeamPairing
        from django.db.models import F
        
        # Debug: Check for tied matches before advancement
        if season.league.competitor_type == 'team':
            # Show all pairings in the round first
            all_pairings = TeamPairing.objects.filter(round=completed_round).order_by('pairing_order')
            self.stdout.write(f"DEBUG: All {all_pairings.count()} pairings in round {completed_round.number}:")
            for pairing in all_pairings:
                pairing.refresh_from_db()
                self.stdout.write(f"  - {pairing.white_team.name} vs {pairing.black_team.name}: {pairing.white_points}-{pairing.black_points} (tiebreak: {pairing.manual_tiebreak_value}) [ID: {pairing.id}, Order: {pairing.pairing_order}]")
            
            # Now check specifically for tied pairings
            tied_pairings = TeamPairing.objects.filter(
                round=completed_round,
                white_points__isnull=False,
                black_points__isnull=False,
                manual_tiebreak_value__isnull=True
            ).filter(white_points=F('black_points'))
            
            if tied_pairings.exists():
                self.stdout.write(f"DEBUG: Found {tied_pairings.count()} tied pairings in multi-match:")
                for pairing in tied_pairings:
                    pairing.refresh_from_db()  # Force refresh from database
                    self.stdout.write(f"  - {pairing.white_team.name} vs {pairing.black_team.name}: {pairing.white_points}-{pairing.black_points} (tiebreak: {pairing.manual_tiebreak_value}) [ID: {pairing.id}]")
            else:
                self.stdout.write("DEBUG: No tied pairings found in multi-match")
        
        # Convert to tournament structure to check status
        tournament = knockout_bracket_to_structure(bracket)
        
        # Debug: Show tournament state
        self.stdout.write(f"DEBUG: Tournament matches_per_stage = {tournament.matches_per_stage}")
        self.stdout.write(f"DEBUG: Tournament current_match_number = {tournament.current_match_number}")
        if tournament.rounds:
            latest_round = tournament.rounds[completed_round.number - 1]
            self.stdout.write(f"DEBUG: Round {completed_round.number} has {len(latest_round.matches)} matches")
            from heltour.tournament_core.multi_match import _get_total_pairs_in_round, _get_current_match_number
            total_pairs = _get_total_pairs_in_round(latest_round)
            current_match = _get_current_match_number(latest_round, total_pairs)
            self.stdout.write(f"DEBUG: Calculated total_pairs = {total_pairs}, current_match = {current_match}")
            self.stdout.write(f"DEBUG: Expected to be able to generate next match? {current_match < tournament.matches_per_stage}")
            
            # Show the matches in the round
            self.stdout.write(f"DEBUG: Matches in tournament structure:")
            for i, match in enumerate(latest_round.matches):
                completed = "completed" if len(match.games) > 0 else "pending"
                self.stdout.write(f"  Match {i+1}: {match.competitor1_id} vs {match.competitor2_id} ({completed}, {len(match.games)} games)")
        
        # Check if we can generate next match set for current round
        can_generate = can_generate_next_match_set(tournament, completed_round.number)
        self.stdout.write(f"DEBUG: can_generate_next_match_set = {can_generate}")
        
        # Debug why can_generate is False
        if not can_generate and tournament.rounds and completed_round.number <= len(tournament.rounds):
            from heltour.tournament_core.multi_match import _all_teams_completed_match, _count_completed_matches_for_match_number
            latest_round = tournament.rounds[completed_round.number - 1]
            total_pairs = _get_total_pairs_in_round(latest_round)
            current_match = _get_current_match_number(latest_round, total_pairs)
            all_completed = _all_teams_completed_match(latest_round, current_match, total_pairs)
            self.stdout.write(f"DEBUG: all_teams_completed_match({current_match}) = {all_completed}")
            self.stdout.write(f"DEBUG: current_match >= matches_per_stage: {current_match} >= {tournament.matches_per_stage} = {current_match >= tournament.matches_per_stage}")
            
            # Show match completion status
            completed_count = _count_completed_matches_for_match_number(latest_round.matches, current_match, total_pairs)
            self.stdout.write(f"DEBUG: completed matches for match {current_match}: {completed_count}/{total_pairs}")
        
        if can_generate:
            self.stdout.write(f"Match {tournament.current_match_number + 1} of {tournament.matches_per_stage} completed. Can generate next match set.")
            if not dry_run:
                # Use admin logic to generate next match set
                from heltour.tournament.admin import KnockoutBracketAdmin
                from django.contrib.admin.sites import AdminSite
                from django.http import HttpRequest
                
                # Mock admin request
                class MockUser:
                    def __init__(self):
                        self.is_authenticated = True
                        
                class MockRequest:
                    def __init__(self):
                        self.user = MockUser()
                        self._messages = []
                        
                    def _get_messages(self):
                        return self._messages
                
                # Create admin instance and generate next match set
                admin = KnockoutBracketAdmin(bracket.__class__, AdminSite())
                request = MockRequest()
                queryset = bracket.__class__.objects.filter(id=bracket.id)
                
                try:
                    admin.generate_next_match_set_action(request, queryset)
                    self.stdout.write(self.style.SUCCESS("✓ Generated next match set for current stage"))
                    
                    # Count new pairings in current round
                    if season.league.competitor_type == "team":
                        from heltour.tournament.models import TeamPairing
                        new_pairings = TeamPairing.objects.filter(round=completed_round).count()
                    else:
                        new_pairings = LonePlayerPairing.objects.filter(round=completed_round).count()
                    
                    current_match = tournament.current_match_number + 1 if tournament.current_match_number < bracket.matches_per_stage else bracket.matches_per_stage
                    self.stdout.write(f"  - Now playing match {current_match} of {bracket.matches_per_stage} for this stage")
                    self.stdout.write(f"  - {new_pairings} total pairings in round {completed_round.number}")
                    self.stdout.write(f"  - Use 'generate_random_results {season.id} --round-number {completed_round.number}' to continue")
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to generate next match set: {str(e)}"))
            else:
                self.stdout.write("DRY RUN: Would generate next match set for current stage")
        else:
            # Check if ALL matches for this stage are complete before advancing
            from heltour.tournament.models import TeamPairing
            stage_pairings = TeamPairing.objects.filter(round=completed_round)
            stage_matches_expected = len(set(
                tuple(sorted([p.white_team.id, p.black_team.id])) 
                for p in stage_pairings if p.black_team
            )) * bracket.matches_per_stage
            stage_matches_actual = stage_pairings.count()
            
            self.stdout.write(f"Stage status: {stage_matches_actual}/{stage_matches_expected} matches created")
            
            if stage_matches_actual >= stage_matches_expected:
                # All matches for this stage exist - check if we can advance to next round
                self.stdout.write("All matches for this stage created. Checking if stage is complete...")
                self._try_advance_single_match_knockout(completed_round, season, dry_run)
            else:
                # Still need more matches for this stage - should use dashboard to create them
                self.stdout.write(f"Stage incomplete: {stage_matches_expected - stage_matches_actual} more matches needed.")
                self.stdout.write("Use the dashboard 'Generate Next Match Set' button to continue.")
