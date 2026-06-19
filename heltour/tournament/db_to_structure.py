"""
Transform database models to tournament_core structure representation.

This module provides functions to convert Django ORM models from heltour.tournament
into the clean tournament_core structure for tiebreak calculations and analysis.
"""

from collections import defaultdict
from typing import Optional

from heltour.tournament.models import (
    KnockoutSeeding,
    LonePlayerPairing,
    PlayerBye,
    SeasonPlayer,
    Team,
    TeamBye,
    TeamMultiMatchProgress,
    TeamPairing,
)
from heltour.tournament_core.multi_match import (
    _find_match_by_pairing_order_and_match_number,
    _get_current_match_number_from_matches,
    get_multi_match_stage_status,
)
from heltour.tournament_core.scoring import STANDARD_SCORING, ScoringSystem
from heltour.tournament_core.structure import (
    GameResult,
    Match,
    Round,
    Tournament,
    TournamentFormat,
    create_bye_match,
    create_scored_bye_match,
    create_single_game_match,
    create_team_match,
)


def calculate_team_pairing_scores(team_pairing):
    """Calculate the correct scores for a team pairing based on board results.

    This is the single source of truth for team pairing score calculation.
    Used by both db_to_structure conversion and TeamPairing.refresh_points().

    Args:
        team_pairing: A TeamPairing model instance

    Returns:
        tuple: (white_points, black_points, white_wins, black_wins)
    """
    white_team_points = 0.0
    black_team_points = 0.0
    white_team_wins = 0
    black_team_wins = 0

    # Get team member player IDs for efficient lookup
    white_team_player_ids = set(
        team_pairing.white_team.teammember_set.values_list("player_id", flat=True)
    )
    black_team_player_ids = set(
        team_pairing.black_team.teammember_set.values_list("player_id", flat=True)
    )

    for board_pairing in (
        team_pairing.teamplayerpairing_set.all().nocache().order_by("board_number")
    ):
        # Skip boards with no result
        if not board_pairing.result:
            continue

        # Get the piece-color scores (white's perspective)
        white_score = board_pairing.white_score() or 0
        black_score = board_pairing.black_score() or 0

        # Skip if no actual score (both 0)
        if white_score == 0 and black_score == 0:
            continue

        # For each non-None player, determine which team they're on
        if board_pairing.white_id:
            if board_pairing.white_id in white_team_player_ids:
                # White pieces player is on white team
                white_team_points += white_score
                if white_score == 1:
                    white_team_wins += 1
            elif board_pairing.white_id in black_team_player_ids:
                # White pieces player is on black team
                black_team_points += white_score
                if white_score == 1:
                    black_team_wins += 1

        if board_pairing.black_id:
            if board_pairing.black_id in white_team_player_ids:
                # Black pieces player is on white team
                white_team_points += black_score
                if black_score == 1:
                    white_team_wins += 1
            elif board_pairing.black_id in black_team_player_ids:
                # Black pieces player is on black team
                black_team_points += black_score
                if black_score == 1:
                    black_team_wins += 1

    return white_team_points, black_team_points, white_team_wins, black_team_wins


def _result_to_game_result(
    result_str: str, colors_reversed: bool = False
) -> Optional[GameResult]:
    """Convert database result string to GameResult enum.

    Args:
        result_str: The result string from the database (e.g., '1-0', '1/2-1/2', '0-1')
        colors_reversed: Whether the colors are reversed in the pairing

    Returns:
        GameResult enum value or None if result is empty/invalid
    """
    if not result_str:
        return None

    # Map database results to GameResult enum
    result_map = {
        "1-0": GameResult.P1_WIN,
        "1/2-1/2": GameResult.DRAW,
        "0-1": GameResult.P2_WIN,
        "1X-0F": GameResult.P1_FORFEIT_WIN,
        "0F-1X": GameResult.P2_FORFEIT_WIN,
        "0F-0F": GameResult.DOUBLE_FORFEIT,
    }

    game_result = result_map.get(result_str)
    if game_result is None:
        return None

    # Reverse the result if colors are reversed
    if colors_reversed:
        if game_result == GameResult.P1_WIN:
            game_result = GameResult.P2_WIN
        elif game_result == GameResult.P2_WIN:
            game_result = GameResult.P1_WIN
        elif game_result == GameResult.P1_FORFEIT_WIN:
            game_result = GameResult.P2_FORFEIT_WIN
        elif game_result == GameResult.P2_FORFEIT_WIN:
            game_result = GameResult.P1_FORFEIT_WIN

    return game_result


def team_tournament_to_structure(season) -> Tournament:
    """Convert a team tournament season to tournament_core structure.

    Args:
        season: A Season model instance from the database

    Returns:
        Tournament object with all rounds, matches, and games
    """
    # Get all teams in the season
    teams = list(Team.objects.filter(season=season).values_list("id", flat=True))

    # Determine tournament format
    format_type = TournamentFormat.KNOCKOUT if season.league.pairing_type in ['knockout-single', 'knockout-multi'] else TournamentFormat.SWISS

    # Get all completed rounds ordered by number
    rounds = []
    for round_obj in season.round_set.filter(is_completed=True).order_by("number"):
        matches = []

        # Get all team pairings for this round
        for team_pairing in (
            TeamPairing.objects.filter(round=round_obj)
            .select_related("white_team", "black_team")
            .prefetch_related("teamplayerpairing_set")
        ):

            # Get all board pairings for this team match
            board_results = []
            board_pairings = list(
                team_pairing.teamplayerpairing_set.all().order_by("board_number")
            )

            # Team tournaments must have board pairings to calculate results
            if not board_pairings:
                raise ValueError(
                    f"TeamPairing between {team_pairing.white_team} and {team_pairing.black_team} "
                    f"in round {round_obj.number} has no board pairings. "
                    "Team tournaments require individual board results."
                )

            for board_pairing in board_pairings:
                # Handle forfeit wins where one player is missing
                if not board_pairing.white_id and not board_pairing.black_id:
                    continue  # Skip completely empty boards

                game_result = _result_to_game_result(
                    board_pairing.result, board_pairing.colors_reversed
                )
                if game_result is None:
                    continue  # Skip games without results

                # Simply use the white/black player IDs as they are
                # Player1 is whoever has white pieces, Player2 has black pieces
                player1_id = board_pairing.white_id or -1  # -1 for forfeit
                player2_id = board_pairing.black_id or -1  # -1 for forfeit

                board_results.append((player1_id, player2_id, game_result))

            if board_results:
                # Build player to team mapping
                player_team_mapping = {}

                # Get all team members
                for tm in team_pairing.white_team.teammember_set.all():
                    player_team_mapping[tm.player_id] = team_pairing.white_team_id

                for tm in team_pairing.black_team.teammember_set.all():
                    player_team_mapping[tm.player_id] = team_pairing.black_team_id

                # Create match with knockout-specific properties
                match = create_team_match(
                    team_pairing.white_team_id,
                    team_pairing.black_team_id,
                    board_results,
                    player_team_mapping,
                )
                
                # For knockout tournaments, add manual tiebreak and games per match
                if format_type == TournamentFormat.KNOCKOUT:
                    games_per_match = season.league.knockout_games_per_match or 1
                    manual_tiebreak = team_pairing.manual_tiebreak_value
                    
                    # Create match with knockout properties
                    match = Match(
                        competitor1_id=match.competitor1_id,
                        competitor2_id=match.competitor2_id,
                        games=match.games,
                        is_bye=match.is_bye,
                        games_per_match=games_per_match,
                        manual_tiebreak_value=manual_tiebreak
                    )
                
                matches.append(match)

        # Add bye matches for teams with TeamBye records
        for team_bye in TeamBye.objects.filter(round=round_obj).select_related("team"):
            # Team tournaments must have a valid boards count
            boards = season.boards
            if not boards or boards <= 0:
                raise ValueError(
                    f"Season {season} has invalid boards count: {boards}. "
                    "Team tournaments require a positive boards count."
                )
            matches.append(create_bye_match(team_bye.team_id, boards))

        if matches:
            knockout_stage = round_obj.knockout_stage if format_type == TournamentFormat.KNOCKOUT else None
            rounds.append(Round(round_obj.number, matches, knockout_stage))

    # Create the tournament with appropriate format
    return Tournament(teams, rounds, STANDARD_SCORING, format_type)


def lone_tournament_to_structure(season) -> Tournament:
    """Convert an individual (lone) tournament season to tournament_core structure.

    Args:
        season: A Season model instance from the database

    Returns:
        Tournament object with all rounds, matches, and games
    """
    # Get all players in the season
    players = list(
        SeasonPlayer.objects.filter(season=season).values_list("player_id", flat=True)
    )

    # Determine tournament format
    format_type = TournamentFormat.KNOCKOUT if season.league.pairing_type in ['knockout-single', 'knockout-multi'] else TournamentFormat.SWISS

    # Get all completed rounds ordered by number
    rounds = []
    for round_obj in season.round_set.filter(is_completed=True).order_by("number"):
        matches = []

        # Get all player pairings for this round
        for pairing in LonePlayerPairing.objects.filter(round=round_obj).select_related(
            "white", "black"
        ):
            if not pairing.white_id or not pairing.black_id:
                continue  # Skip empty pairings

            game_result = _result_to_game_result(
                pairing.result, pairing.colors_reversed
            )
            if game_result is None:
                continue  # Skip games without results

            match = create_single_game_match(
                pairing.white_id, pairing.black_id, game_result
            )
            
            # For knockout tournaments, add games per match (always 1 for individual)
            if format_type == TournamentFormat.KNOCKOUT:
                match = Match(
                    competitor1_id=match.competitor1_id,
                    competitor2_id=match.competitor2_id,
                    games=match.games,
                    is_bye=match.is_bye,
                    games_per_match=1,
                    manual_tiebreak_value=None  # Individual knockout doesn't use manual tiebreaks
                )
            
            matches.append(match)

        # Add byes for players that didn't play (Swiss only)
        if format_type == TournamentFormat.SWISS:
            players_that_played = set()
            for match in matches:
                players_that_played.add(match.competitor1_id)
                players_that_played.add(match.competitor2_id)

            byes = {
                b.player_id: b
                for b in PlayerBye.objects.filter(round=round_obj)
            }

            for player_id in players:
                if player_id not in players_that_played:
                    bye = byes.get(player_id)
                    if bye:
                        gp = bye.score()  # 0, 0.5, or 1
                    else:
                        gp = 0.0  # no pairing, no bye record → 0 pts

                    mp = 2 if gp >= 1.0 else (1 if gp > 0 else 0)
                    matches.append(create_scored_bye_match(player_id, gp, mp))

        if matches:
            knockout_stage = round_obj.knockout_stage if format_type == TournamentFormat.KNOCKOUT else None
            rounds.append(Round(round_obj.number, matches, knockout_stage))

    # Create the tournament with appropriate format
    return Tournament(players, rounds, STANDARD_SCORING, format_type)


def season_to_tournament_structure(
    season, scoring: Optional[ScoringSystem] = None
) -> Tournament:
    """Convert any season (team or individual) to tournament_core structure.

    This is the main entry point for converting database models to the clean
    tournament structure used for calculations.

    Args:
        season: A Season model instance from the database
        scoring: Optional custom scoring system (defaults to STANDARD_SCORING)

    Returns:
        Tournament object with all rounds, matches, and games
    """
    if season.league.is_team_league():
        tournament = team_tournament_to_structure(season)
    else:
        tournament = lone_tournament_to_structure(season)

    # Override scoring if provided
    if scoring:
        tournament.scoring = scoring

    return tournament


def knockout_bracket_to_structure(knockout_bracket) -> Tournament:
    """Convert a KnockoutBracket model to tournament_core structure.
    
    This function creates a tournament structure from the KnockoutBracket,
    KnockoutSeeding, and Round/Pairing data.
    
    Args:
        knockout_bracket: KnockoutBracket model instance
        
    Returns:
        Tournament object representing the knockout bracket
    """
    # Get the season from the bracket
    season = knockout_bracket.season
    
    # Get seeded competitors in order
    seedings = KnockoutSeeding.objects.filter(
        bracket=knockout_bracket
    ).order_by('seed_number').select_related('team' if season.league.competitor_type == 'team' else None)
    
    if season.league.competitor_type == "team":
        competitors = [seeding.team.id for seeding in seedings]
    else:
        # For individual tournaments, we'd need to adapt this
        # For now, assume team tournaments
        competitors = [seeding.team.id for seeding in seedings]
    
    # Convert using the standard tournament conversion
    tournament = season_to_tournament_structure(season)

    # Create updated tournament with multi-match fields
    updated_tournament = Tournament(
        competitors=tournament.competitors,
        rounds=tournament.rounds,
        scoring=tournament.scoring,
        format=TournamentFormat.KNOCKOUT,
        matches_per_stage=knockout_bracket.matches_per_stage,
        current_match_number=_calculate_current_match_number(tournament.rounds, knockout_bracket.matches_per_stage)
    )
    
    return updated_tournament


def multi_match_knockout_to_structure(season) -> Tournament:
    """Convert a multi-match knockout tournament to tournament_core structure.
    
    This function handles the aggregation of multiple rounds with the same 
    pairings for multi-match knockout tournaments.
    
    Args:
        season: Season object for multi-match knockout tournament
        
    Returns:
        Tournament object with aggregated multi-match results
    """
    if season.league.pairing_type != 'knockout-multi':
        raise ValueError(f"Season {season} is not a multi-match knockout tournament")
    
    # Get base tournament structure
    tournament = season_to_tournament_structure(season)

    # Group rounds by knockout_multi_round_group
    round_groups = defaultdict(list)
    
    for round_obj in season.round_set.filter(is_completed=True).order_by("number"):
        group_id = round_obj.knockout_multi_round_group or f"single_{round_obj.number}"
        round_groups[group_id].append(round_obj)
    
    # Rebuild tournament with aggregated matches
    aggregated_rounds = []
    
    for group_id, group_rounds in round_groups.items():
        if len(group_rounds) == 1:
            # Single round - use as is
            round_obj = group_rounds[0]
            existing_round = next(
                (r for r in tournament.rounds if r.number == round_obj.number), 
                None
            )
            if existing_round:
                aggregated_rounds.append(existing_round)
        else:
            # Multiple rounds - aggregate them
            aggregated_round = _aggregate_multi_match_rounds(group_rounds, tournament, season)
            aggregated_rounds.append(aggregated_round)
    
    # Sort rounds by number
    aggregated_rounds.sort(key=lambda r: r.number)
    
    # Create new tournament with aggregated rounds
    return Tournament(
        competitors=tournament.competitors,
        rounds=aggregated_rounds,
        scoring=tournament.scoring,
        format=TournamentFormat.KNOCKOUT
    )


def _aggregate_multi_match_rounds(group_rounds, base_tournament, season):
    """Aggregate multiple rounds with same pairings into single round structure."""
    # Use the first round as the base
    base_round = min(group_rounds, key=lambda r: r.number)
    
    # Group pairings by teams
    pairing_groups = defaultdict(list)
    
    for round_obj in group_rounds:
        round_structure = next(
            (r for r in base_tournament.rounds if r.number == round_obj.number),
            None
        )
        if round_structure:
            for match in round_structure.matches:
                # Create a key for this pairing
                key = tuple(sorted([match.competitor1_id, match.competitor2_id]))
                pairing_groups[key].append(match)
    
    # Create aggregated matches
    aggregated_matches = []
    
    for pairing_key, matches in pairing_groups.items():
        if len(matches) == 1:
            # Single match - use as is but update games_per_match
            match = matches[0]
            aggregated_match = Match(
                competitor1_id=match.competitor1_id,
                competitor2_id=match.competitor2_id,
                games=match.games,
                is_bye=match.is_bye,
                games_per_match=season.league.knockout_games_per_match or len(matches),
                manual_tiebreak_value=match.manual_tiebreak_value
            )
            aggregated_matches.append(aggregated_match)
        else:
            # Multiple matches - aggregate games
            all_games = []
            manual_tiebreak = None
            
            # Ensure consistent competitor ordering
            first_match = matches[0]
            competitor1_id = first_match.competitor1_id
            competitor2_id = first_match.competitor2_id
            
            for match in matches:
                all_games.extend(match.games)
                if match.manual_tiebreak_value is not None:
                    manual_tiebreak = match.manual_tiebreak_value
            
            aggregated_match = Match(
                competitor1_id=competitor1_id,
                competitor2_id=competitor2_id,
                games=all_games,
                is_bye=first_match.is_bye,
                games_per_match=len(all_games),
                manual_tiebreak_value=manual_tiebreak
            )
            aggregated_matches.append(aggregated_match)
    
    return Round(
        number=base_round.number,
        matches=aggregated_matches,
        knockout_stage=base_round.knockout_stage
    )


def _calculate_current_match_number(rounds, matches_per_stage):
    """Calculate the current match number based on tournament rounds.
    
    This function uses the multi-match logic to determine which match number
    is currently being played based on the number of matches present.
    
    Args:
        rounds: List of Round objects
        matches_per_stage: Number of matches per stage from KnockoutBracket
        
    Returns:
        Current match number (1, 2, 3, ...)
    """
    if not rounds or matches_per_stage <= 1:
        return 1

    # Get matches from the most recent round
    latest_round = max(rounds, key=lambda r: r.number)
    if not latest_round.matches:
        return 1
        
    # Calculate total pairs from the number of original matches
    # This is an approximation - in practice we might need more sophisticated logic
    total_matches = len(latest_round.matches)
    estimated_total_pairs = total_matches // matches_per_stage if total_matches > 0 else 1
    
    if estimated_total_pairs == 0:
        return 1
        
    return _get_current_match_number_from_matches(latest_round.matches, estimated_total_pairs)


def update_multi_match_progress_from_tournament(tournament, bracket):
    """Update TeamMultiMatchProgress records based on tournament_core structure.
    
    This function creates or updates progress tracking records based on the
    current state of a tournament structure.
    
    Args:
        tournament: Tournament structure from tournament_core
        bracket: KnockoutBracket model instance
        
    Returns:
        Number of progress records created/updated
    """
    if tournament.matches_per_stage <= 1:
        return 0  # No multi-match progress to track
    
    records_updated = 0
    
    for round_obj in tournament.rounds:
        if not round_obj.matches:
            continue
            
        # Calculate stage status
        # Use the actual unique pairs, not the division logic
        total_pairs = len(set(
            tuple(sorted([match.competitor1_id, match.competitor2_id])) 
            for match in round_obj.matches
        ))
        if total_pairs == 0:
            continue
            
        stage_status = get_multi_match_stage_status(
            round_obj.matches, total_pairs, tournament.matches_per_stage
        )
        
        # Update progress for each team pair
        for original_pairing_order in range(1, total_pairs + 1):
            original_match = _find_match_by_pairing_order_and_match_number(
                round_obj.matches, original_pairing_order, 1, total_pairs
            )
            
            if original_match:
                try:
                    team_a = Team.objects.get(id=original_match.competitor1_id)
                    team_b = Team.objects.get(id=original_match.competitor2_id)
                    
                    # Update progress for team A
                    progress_a, created = TeamMultiMatchProgress.objects.update_or_create(
                        bracket=bracket,
                        team=team_a,
                        round_number=round_obj.number,
                        defaults={
                            'stage_name': round_obj.knockout_stage or f"round_{round_obj.number}",
                            'opponent_team': team_b,
                            'original_pairing_order': original_pairing_order,
                            'matches_completed': stage_status['completed_current_match'],
                            'total_matches_required': tournament.matches_per_stage,
                        }
                    )
                    
                    # Update progress for team B  
                    progress_b, created = TeamMultiMatchProgress.objects.update_or_create(
                        bracket=bracket,
                        team=team_b,
                        round_number=round_obj.number,
                        defaults={
                            'stage_name': round_obj.knockout_stage or f"round_{round_obj.number}",
                            'opponent_team': team_a,
                            'original_pairing_order': original_pairing_order,
                            'matches_completed': stage_status['completed_current_match'],
                            'total_matches_required': tournament.matches_per_stage,
                        }
                    )
                    
                    records_updated += 2
                    
                except Team.DoesNotExist:
                    # Skip if teams don't exist in database
                    continue
    
    return records_updated
