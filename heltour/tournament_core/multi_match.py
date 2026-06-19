"""
Multi-match knockout tournament utilities.

This module provides functionality for knockout tournaments where each stage
consists of multiple matches between the same competitors (e.g., best-of-3 or
return matches with color switching).

Key concepts:
- Pairing order uses modular arithmetic to determine match number
- Global synchronization: ALL teams must complete match N before ANY team starts match N+1
- Color switching: Return matches automatically flip colors from original match
- Progressive generation: Subsequent matches only created when previous matches complete
"""

from typing import List, Optional, Tuple, Dict
import math

from heltour.tournament_core.structure import Match, Round, Tournament, TournamentFormat
from heltour.tournament_core.scoring import ScoringSystem, STANDARD_SCORING


def get_match_number_from_pairing_order(pairing_order: int, total_pairs: int) -> int:
    """Calculate which match number this pairing represents.
    
    Args:
        pairing_order: Sequential pairing order (1, 2, 3, 4, 5, 6, 7, 8...)
        total_pairs: Number of unique team pairs in the stage
        
    Returns:
        Match number (1, 2, 3...)
        
    Example:
        4 team pairs, pairing_order 1-4 = match 1, pairing_order 5-8 = match 2
    """
    if pairing_order < 1:
        raise ValueError("Pairing order must be >= 1")
    if total_pairs < 1:
        raise ValueError("Total pairs must be >= 1")
        
    return ((pairing_order - 1) // total_pairs) + 1


def get_original_pairing_order(pairing_order: int, total_pairs: int) -> int:
    """Get the original pairing order this return match is based on.
    
    Args:
        pairing_order: Sequential pairing order of a return match
        total_pairs: Number of unique team pairs in the stage
        
    Returns:
        Pairing order of the original match this is a return for
        
    Example:
        4 team pairs, pairing_order 5 (match 2) -> original pairing_order 1 (match 1)
    """
    if pairing_order < 1:
        raise ValueError("Pairing order must be >= 1")
    if total_pairs < 1:
        raise ValueError("Total pairs must be >= 1")
        
    match_number = get_match_number_from_pairing_order(pairing_order, total_pairs)
    if match_number == 1:
        return pairing_order
    else:
        return ((pairing_order - 1) % total_pairs) + 1


def get_pairing_order_for_match(original_pairing_order: int, match_number: int, total_pairs: int) -> int:
    """Calculate the pairing order for a specific match number of an original pairing.
    
    Args:
        original_pairing_order: The pairing order from match 1 (1, 2, 3, 4...)
        match_number: Which match number to get (1, 2, 3...)
        total_pairs: Number of unique team pairs in the stage
        
    Returns:
        Pairing order for the specified match number
        
    Example:
        original_pairing_order=2, match_number=2, total_pairs=4 -> returns 6
    """
    if original_pairing_order < 1 or original_pairing_order > total_pairs:
        raise ValueError(f"Original pairing order must be between 1 and {total_pairs}")
    if match_number < 1:
        raise ValueError("Match number must be >= 1")
    if total_pairs < 1:
        raise ValueError("Total pairs must be >= 1")
        
    return (match_number - 1) * total_pairs + original_pairing_order


def can_generate_next_match_set(tournament: Tournament, round_number: int) -> bool:
    """Check if ALL teams have completed their current match before generating next match set.
    
    Args:
        tournament: Tournament structure
        round_number: Round number to check (1-indexed)
        
    Returns:
        True if all teams completed current match and next match can be generated
    """
    if round_number < 1 or round_number > len(tournament.rounds):
        return False
        
    round_obj = tournament.rounds[round_number - 1]
    
    # For single-match tournaments, no subsequent matches to generate
    if tournament.matches_per_stage <= 1:
        return False
        
    # Calculate total pairs and current match number
    total_pairs = _get_total_pairs_in_round(round_obj)
    if total_pairs == 0:
        return False
        
    current_match_number = _get_current_match_number(round_obj, total_pairs)
    
    # If we're already at max matches, can't generate more
    if current_match_number >= tournament.matches_per_stage:
        return False
        
    # Check if all teams completed current match
    return _all_teams_completed_match(round_obj, current_match_number, total_pairs)


def generate_next_match_set(tournament: Tournament, round_number: int) -> Tournament:
    """Generate the next set of matches for a multi-match knockout round.
    
    Args:
        tournament: Current tournament structure
        round_number: Round number to generate next matches for (1-indexed)
        
    Returns:
        Updated tournament with next match set added
        
    Raises:
        ValueError: If next match set cannot be generated yet
    """
    if not can_generate_next_match_set(tournament, round_number):
        raise ValueError(f"Cannot generate next match set for round {round_number}")
        
    round_obj = tournament.rounds[round_number - 1]
    total_pairs = _get_total_pairs_in_round(round_obj)
    current_match_number = _get_current_match_number(round_obj, total_pairs)
    next_match_number = current_match_number + 1
    
    # Generate return matches with flipped colors
    new_matches = []
    
    for original_pairing_order in range(1, total_pairs + 1):
        # Find the original match
        original_match = _find_match_by_pairing_order(round_obj, original_pairing_order, total_pairs)
        if original_match is None:
            raise ValueError(f"Could not find original match for pairing order {original_pairing_order}")
            
        # Create return match with flipped colors
        return_match = Match(
            competitor1_id=original_match.competitor2_id,  # Flip colors
            competitor2_id=original_match.competitor1_id,
            games=[],  # Empty games list for new match
            is_bye=original_match.is_bye,
            games_per_match=original_match.games_per_match,
            manual_tiebreak_value=None,  # Reset manual tiebreak for new match
        )
        new_matches.append(return_match)
    
    # Create updated round with all matches
    updated_matches = round_obj.matches + new_matches
    updated_round = Round(
        number=round_obj.number,
        matches=updated_matches,
        knockout_stage=round_obj.knockout_stage,
    )
    
    # Update tournament
    new_rounds = (
        tournament.rounds[:round_number - 1]
        + [updated_round]
        + tournament.rounds[round_number:]
    )
    
    return Tournament(
        competitors=tournament.competitors,
        rounds=new_rounds,
        scoring=tournament.scoring,
        format=tournament.format,
        matches_per_stage=tournament.matches_per_stage,
        current_match_number=next_match_number,
    )


def calculate_multi_match_winners(matches: List[Match], total_pairs: int, matches_per_stage: int, scoring: ScoringSystem = STANDARD_SCORING) -> List[int]:
    """Calculate winners from a multi-match knockout round.
    
    Args:
        matches: All matches in the round
        total_pairs: Number of unique team pairs
        matches_per_stage: Total matches each pair should play
        scoring: Scoring system to use
        
    Returns:
        List of advancing competitor IDs
        
    Raises:
        ValueError: If not all matches are complete or winners can't be determined
    """
    if not is_multi_match_stage_complete(matches, total_pairs, matches_per_stage):
        raise ValueError("Cannot calculate winners - not all matches in stage are complete")
        
    winners = []
    
    for original_pairing_order in range(1, total_pairs + 1):
        # Collect all matches for this team pair
        pair_matches = []
        for match_number in range(1, matches_per_stage + 1):
            match = _find_match_by_pairing_order_and_match_number(
                matches, original_pairing_order, match_number, total_pairs
            )
            if match is None:
                raise ValueError(f"Missing match {match_number} for pair {original_pairing_order}")
            pair_matches.append(match)
        
        # Calculate aggregate winner
        winner_id = _calculate_aggregate_winner(pair_matches, scoring)
        if winner_id is None:
            raise ValueError(f"No clear winner for pair {original_pairing_order} - may need manual tiebreak")
        
        winners.append(winner_id)
    
    return winners


def is_multi_match_stage_complete(matches: List[Match], total_pairs: int, matches_per_stage: int) -> bool:
    """Check if all matches in a multi-match stage are complete.
    
    Args:
        matches: All matches in the round
        total_pairs: Number of unique team pairs  
        matches_per_stage: Total matches each pair should play
        
    Returns:
        True if all matches in the stage are complete
    """
    expected_total_matches = total_pairs * matches_per_stage
    
    # Check we have the right number of matches
    if len(matches) != expected_total_matches:
        return False
        
    # Check all matches have games and clear results
    for match in matches:
        if len(match.games) == 0:
            return False
        if match.winner_id() is None and match.manual_tiebreak_value is None:
            return False
            
    return True


def get_multi_match_stage_status(matches: List[Match], total_pairs: int, matches_per_stage: int) -> Dict:
    """Get detailed status of a multi-match stage.
    
    Returns:
        Dictionary with completion status information
    """
    if total_pairs == 0:
        return {
            'total_pairs': 0,
            'matches_per_stage': matches_per_stage,
            'current_match_number': 1,
            'completed_current_match': 0,
            'all_current_complete': True,
            'stage_complete': True,
        }
        
    current_match_number = _get_current_match_number_from_matches(matches, total_pairs)
    completed_current = _count_completed_matches_for_match_number(matches, current_match_number, total_pairs)
    
    return {
        'total_pairs': total_pairs,
        'matches_per_stage': matches_per_stage,
        'current_match_number': current_match_number,
        'completed_current_match': completed_current,
        'all_current_complete': completed_current == total_pairs,
        'stage_complete': is_multi_match_stage_complete(matches, total_pairs, matches_per_stage),
    }


# Private helper functions

def _get_total_pairs_in_round(round_obj: Round) -> int:
    """Calculate the number of unique team pairs in a round."""
    if not round_obj.matches:
        return 0
    
    # For multi-match tournaments, we need to determine how many unique pairs there are
    # The total matches should be divisible by the number of matches per stage
    total_matches = len(round_obj.matches)
    
    # Find unique competitor pairs
    unique_pairs = set()
    for match in round_obj.matches:
        # Create a normalized pair (smaller ID first for consistency)
        pair = tuple(sorted([match.competitor1_id, match.competitor2_id]))
        unique_pairs.add(pair)
    
    return len(unique_pairs)


def _get_current_match_number(round_obj: Round, total_pairs: int) -> int:
    """Determine the current match number being played."""
    if not round_obj.matches or total_pairs == 0:
        return 1
        
    return _get_current_match_number_from_matches(round_obj.matches, total_pairs)


def _get_current_match_number_from_matches(matches: List[Match], total_pairs: int) -> int:
    """Determine current match number from list of matches."""
    if not matches or total_pairs == 0:
        return 1
        
    # Calculate the highest match number based on total matches
    # If we have 4 matches and 2 pairs, that means 2 matches per pair = match number 2
    max_match_number = len(matches) // total_pairs
    return max_match_number if max_match_number > 0 else 1


def _all_teams_completed_match(round_obj: Round, match_number: int, total_pairs: int) -> bool:
    """Check if all teams completed a specific match number."""
    completed_count = _count_completed_matches_for_match_number(round_obj.matches, match_number, total_pairs)
    return completed_count == total_pairs


def _count_completed_matches_for_match_number(matches: List[Match], match_number: int, total_pairs: int) -> int:
    """Count how many matches are completed for a specific match number."""
    completed = 0
    
    for original_pairing_order in range(1, total_pairs + 1):
        match = _find_match_by_pairing_order_and_match_number(
            matches, original_pairing_order, match_number, total_pairs
        )
        if match and _is_match_complete(match):
            completed += 1
            
    return completed


def _find_match_by_pairing_order(round_obj: Round, pairing_order: int, total_pairs: int) -> Optional[Match]:
    """Find a match by its original pairing order in the round."""
    match_number = 1  # Looking for the original match
    return _find_match_by_pairing_order_and_match_number(
        round_obj.matches, pairing_order, match_number, total_pairs
    )


def _find_match_by_pairing_order_and_match_number(
    matches: List[Match], original_pairing_order: int, match_number: int, total_pairs: int
) -> Optional[Match]:
    """Find a match by original pairing order and match number."""
    target_index = get_pairing_order_for_match(original_pairing_order, match_number, total_pairs) - 1
    
    if 0 <= target_index < len(matches):
        return matches[target_index]
    return None


def _is_original_match(match: Match, all_matches: List[Match]) -> bool:
    """Check if this is an original match (not a return match)."""
    # For now, assume original matches are the first set in the list
    # This is a simplification - in practice we'd need more sophisticated logic
    total_matches = len(all_matches)
    if total_matches == 0:
        return False
        
    # Estimate total pairs by finding how matches are distributed
    # This is an approximation - actual implementation may need refinement
    match_index = all_matches.index(match)
    estimated_total_pairs = total_matches
    
    # Find the largest divisor that makes sense
    for possible_pairs in range(1, total_matches + 1):
        if total_matches % possible_pairs == 0:
            matches_per_stage = total_matches // possible_pairs
            if match_index < possible_pairs:
                return True
                
    return match_index == 0  # Fallback: first match is original


def _is_match_complete(match: Match) -> bool:
    """Check if a match is complete (has games with results)."""
    if len(match.games) == 0:
        return False
    if match.winner_id() is None and match.manual_tiebreak_value is None:
        return False
    return True


def _calculate_aggregate_winner(matches: List[Match], scoring: ScoringSystem) -> Optional[int]:
    """Calculate the winner across multiple matches between the same competitors."""
    if not matches:
        return None
        
    # Get competitor IDs from first match
    competitor1_id = matches[0].competitor1_id
    competitor2_id = matches[0].competitor2_id
    
    # Count wins for each competitor across all matches
    competitor1_wins = 0
    competitor2_wins = 0
    
    for match in matches:
        winner_id = match.winner_id(scoring)
        if winner_id == competitor1_id:
            competitor1_wins += 1
        elif winner_id == competitor2_id:
            competitor2_wins += 1
        # Draws/ties don't count as wins
        
    # Determine overall winner
    if competitor1_wins > competitor2_wins:
        return competitor1_id
    elif competitor2_wins > competitor1_wins:
        return competitor2_id
    else:
        # Check for manual tiebreak in the final match
        final_match = matches[-1]
        if final_match.manual_tiebreak_value is not None:
            if final_match.manual_tiebreak_value > 0:
                return competitor1_id
            elif final_match.manual_tiebreak_value < 0:
                return competitor2_id
        return None  # Tied, needs manual resolution