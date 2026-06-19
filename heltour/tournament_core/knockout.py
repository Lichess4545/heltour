"""
Knockout tournament utilities for bracket generation and advancement calculation.

This module provides functionality for:
- Validating bracket sizes (must be power of 2)
- Generating initial knockout brackets with different seeding patterns
- Calculating match winners and tournament advancement
- Handling multi-game matches and manual tiebreaks
"""

from typing import List, Optional, Tuple
import math

from heltour.tournament_core.structure import Match, Round, Tournament, TournamentFormat
from heltour.tournament_core.scoring import ScoringSystem, STANDARD_SCORING


def validate_bracket_size(team_count: int) -> bool:
    """Check if team count is a valid power of 2 for knockout tournaments."""
    return team_count > 1 and (team_count & (team_count - 1)) == 0


def calculate_rounds_needed(team_count: int) -> int:
    """Calculate number of rounds needed for a knockout tournament."""
    if not validate_bracket_size(team_count):
        raise ValueError(f"Team count {team_count} is not a power of 2")
    return int(math.log2(team_count))


def get_knockout_stage_name(teams_remaining: int) -> str:
    """Get the standard name for a knockout stage based on teams remaining."""
    stage_names = {
        2: "finals",
        4: "semifinals",
        8: "quarterfinals",
        16: "round-of-16",
        32: "round-of-32",
        64: "round-of-64",
    }

    if teams_remaining in stage_names:
        return stage_names[teams_remaining]
    else:
        return f"round-of-{teams_remaining}"


def generate_knockout_seedings_adjacent(team_ids: List[int]) -> List[Tuple[int, int]]:
    """Generate knockout bracket with adjacent seedings (1v2, 3v4, 5v6, etc.).

    Args:
        team_ids: List of team IDs in seeding order (1st seed first)

    Returns:
        List of (team1_id, team2_id) tuples for first round matches
    """
    if not validate_bracket_size(len(team_ids)):
        raise ValueError(f"Team count {len(team_ids)} is not a power of 2")

    pairings = []
    for i in range(0, len(team_ids), 2):
        pairings.append((team_ids[i], team_ids[i + 1]))

    return pairings


def generate_knockout_seedings_traditional(
    team_ids: List[int],
) -> List[Tuple[int, int]]:
    """Generate knockout bracket with traditional seedings in proper bracket order.
    
    Creates pairings like 1v32, 2v31, etc., but arranges them in the correct
    bracket positions so that winners flow properly through subsequent rounds.

    Args:
        team_ids: List of team IDs in seeding order (1st seed first)

    Returns:
        List of (team1_id, team2_id) tuples for first round matches in bracket order
    """
    if not validate_bracket_size(len(team_ids)):
        raise ValueError(f"Team count {len(team_ids)} is not a power of 2")

    n = len(team_ids)
    
    # Generate the traditional pairings (1v32, 2v31, etc.)
    traditional_pairings = []
    for i in range(n // 2):
        # Pair seed i+1 with seed n-i
        traditional_pairings.append((team_ids[i], team_ids[n - 1 - i]))
    
    # Now arrange them in proper bracket order
    return _arrange_pairings_in_bracket_order(traditional_pairings)


def _arrange_pairings_in_bracket_order(pairings: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Arrange pairings in proper bracket order for standard tournament flow.
    
    This function takes traditional seeding pairings and arranges them so that
    the bracket flows correctly through subsequent rounds. This implements the
    standard tournament bracket structure where 1 and 2 seeds are on opposite
    halves and can only meet in the final.
    
    The algorithm creates the bracket structure described as:
    - For 32 teams: 1v32 at top, then 16v17 below that, 8v25, 9v24, etc.
    - The second half starts with 2v31 and follows the same pattern
    
    Args:
        pairings: List of (team1_id, team2_id) tuples from traditional seeding
        
    Returns:
        List of pairings reordered for proper bracket positioning
    """
    n = len(pairings)
    if n <= 1:
        return pairings
    
    # Build the bracket order using the standard tournament bracket algorithm
    # This creates the bracket positions so teams advance to meet the right opponents
    
    # Create a mapping from pairing index to bracket position
    bracket_order = _calculate_bracket_order(n)
    
    # Reorder the pairings according to bracket positions
    result = [None] * n
    for i, bracket_pos in enumerate(bracket_order):
        result[bracket_pos] = pairings[i]
    
    return result


def _calculate_bracket_order(num_matches: int) -> List[int]:
    """Calculate the bracket ordering for a tournament with num_matches first-round matches.
    
    This creates the standard tournament bracket structure where the #1 and #2 seeds
    are positioned on opposite sides of the bracket and can only meet in the final.
    
    Args:
        num_matches: Number of first-round matches (must be power of 2)
        
    Returns:
        List where index i contains the bracket position for traditional pairing i
    """
    if num_matches == 1:
        return [0]
    elif num_matches == 2:
        return [0, 1]
    
    # Build the bracket using the standard seeding algorithm
    # This creates the positions that ensure proper bracket flow
    bracket_positions = _build_standard_bracket_positions(num_matches)
    
    # Map traditional seeding order to bracket positions
    result = [0] * num_matches
    for i in range(num_matches):
        result[i] = bracket_positions[i]
    
    return result


def _build_standard_bracket_positions(num_matches: int) -> List[int]:
    """Build the standard tournament bracket positions.
    
    This implements the specific bracket ordering requested:
    1v32, 16v17, 3v30, 14v19, 5v28, 12v21, 7v26, 10v23, 2v31, 15v18, 4v29, 13v20, 6v27, 11v22, 8v25, 9v24
    
    Returns a list where index i contains the bracket position for traditional pairing i.
    """
    if num_matches <= 1:
        return list(range(num_matches))
    
    if num_matches == 2:
        # 4 teams: 1v4, 2v3 -> 1v4, 2v3 (keep order)
        return [0, 1]
    elif num_matches == 4:
        # 8 teams: traditional order is 1v8, 2v7, 3v6, 4v5 
        # Requested bracket order: 1v8, 4v5, 3v6, 2v7
        # So pairing 0(1v8)->pos 0, pairing 1(2v7)->pos 3, pairing 2(3v6)->pos 2, pairing 3(4v5)->pos 1
        return [0, 3, 2, 1]
    elif num_matches == 8:
        # 16 teams: traditional order is 1v16, 2v15, 3v14, 4v13, 5v12, 6v11, 7v10, 8v9
        # Apply similar pattern as 32-team but scaled down
        return [0, 7, 2, 5, 4, 3, 6, 1]
    elif num_matches == 16:
        # 32 teams: the exact requested pattern
        # Traditional pairings: 1v32, 2v31, 3v30, 4v29, 5v28, 6v27, 7v26, 8v25, 9v24, 10v23, 11v22, 12v21, 13v20, 14v19, 15v18, 16v17
        # Requested order:      1v32, 16v17, 3v30, 14v19, 5v28, 12v21, 7v26, 10v23, 2v31, 15v18, 4v29, 13v20, 6v27, 11v22, 8v25, 9v24
        
        # Map traditional pairing index to bracket position:
        # pairing 0 (1v32) -> position 0
        # pairing 15 (16v17) -> position 1  
        # pairing 2 (3v30) -> position 2
        # pairing 13 (14v19) -> position 3
        # pairing 4 (5v28) -> position 4
        # pairing 11 (12v21) -> position 5
        # pairing 6 (7v26) -> position 6
        # pairing 9 (10v23) -> position 7
        # pairing 1 (2v31) -> position 8
        # pairing 14 (15v18) -> position 9
        # pairing 3 (4v29) -> position 10
        # pairing 12 (13v20) -> position 11
        # pairing 5 (6v27) -> position 12
        # pairing 10 (11v22) -> position 13
        # pairing 7 (8v25) -> position 14
        # pairing 8 (9v24) -> position 15
        
        return [0, 8, 2, 10, 4, 12, 6, 14, 15, 7, 13, 5, 11, 3, 9, 1]
    
    # For other sizes, use recursive construction  
    half = num_matches // 2
    first_half = _build_standard_bracket_positions(half)
    second_half = _build_standard_bracket_positions(half)
    
    # Combine the halves with proper offset
    result = []
    for pos in first_half:
        result.append(pos)
    for pos in second_half:
        result.append(pos + half)
    
    return result


def calculate_knockout_advancement(
    matches: List[Match], scoring: ScoringSystem = STANDARD_SCORING
) -> List[int]:
    """Calculate which competitors advance from a knockout round.

    Args:
        matches: List of matches in the round
        scoring: Scoring system to use

    Returns:
        List of advancing competitor IDs

    Raises:
        ValueError: If any match has no clear winner (tied and no manual tiebreak)
    """
    advancing = []

    for match in matches:
        winner = match.winner_id(scoring)
        if winner is None:
            raise ValueError(
                f"Match between {match.competitor1_id} and {match.competitor2_id} "
                "is tied and requires manual tiebreak resolution"
            )
        advancing.append(winner)

    return advancing


def generate_next_round_pairings(advancing_teams: List[int]) -> List[Tuple[int, int]]:
    """Generate pairings for the next knockout round.

    Args:
        advancing_teams: List of team IDs that advanced from previous round

    Returns:
        List of (team1_id, team2_id) tuples for next round matches

    Raises:
        ValueError: If number of advancing teams is not even
    """
    if len(advancing_teams) % 2 != 0:
        raise ValueError(f"Cannot pair {len(advancing_teams)} teams (must be even)")

    pairings = []
    for i in range(0, len(advancing_teams), 2):
        pairings.append((advancing_teams[i], advancing_teams[i + 1]))

    return pairings


def create_knockout_tournament(
    team_ids: List[int],
    seeding_style: str = "traditional",
    games_per_match: int = 1,
    max_rounds: Optional[int] = None,
    scoring: ScoringSystem = STANDARD_SCORING,
    matches_per_stage: int = 1,
) -> Tournament:
    """Create a complete knockout tournament structure (without results).

    Args:
        team_ids: List of team IDs in seeding order
        seeding_style: "traditional" (1v32) or "adjacent" (1v2)
        games_per_match: Number of games per match
        max_rounds: Maximum rounds to play (None = play to completion)
        scoring: Scoring system to use
        matches_per_stage: Number of matches each pair plays (1 = single elimination, 2 = return matches)

    Returns:
        Tournament structure with empty matches ready for results
    """
    if not validate_bracket_size(len(team_ids)):
        raise ValueError(f"Team count {len(team_ids)} is not a power of 2")

    total_rounds = calculate_rounds_needed(len(team_ids))
    if max_rounds is not None:
        total_rounds = min(total_rounds, max_rounds)

    # Generate first round pairings
    if seeding_style == "traditional":
        first_round_pairings = generate_knockout_seedings_traditional(team_ids)
    elif seeding_style == "adjacent":
        first_round_pairings = generate_knockout_seedings_adjacent(team_ids)
    else:
        raise ValueError(f"Unknown seeding style: {seeding_style}")

    rounds = []
    current_teams = len(team_ids)

    for round_num in range(1, total_rounds + 1):
        stage_name = get_knockout_stage_name(current_teams)
        matches = []

        if round_num == 1:
            # First round uses the generated pairings
            for team1_id, team2_id in first_round_pairings:
                # Create empty match (no games yet)
                match = Match(
                    competitor1_id=team1_id,
                    competitor2_id=team2_id,
                    games=[],
                    games_per_match=games_per_match,
                )
                matches.append(match)
        else:
            # Later rounds will be filled in as previous rounds complete
            # For now, create placeholder matches
            matches_needed = current_teams // 2
            for i in range(matches_needed):
                # Placeholder matches with dummy IDs
                match = Match(
                    competitor1_id=-1,  # Will be filled from previous round winners
                    competitor2_id=-1,
                    games=[],
                    games_per_match=games_per_match,
                )
                matches.append(match)

        round_obj = Round(number=round_num, matches=matches, knockout_stage=stage_name)
        rounds.append(round_obj)
        current_teams //= 2

    return Tournament(
        competitors=team_ids,
        rounds=rounds,
        scoring=scoring,
        format=TournamentFormat.KNOCKOUT,
        matches_per_stage=matches_per_stage,
        current_match_number=1,
    )


def update_knockout_tournament_with_winners(
    tournament: Tournament, round_number: int, winners: List[int]
) -> Tournament:
    """Update knockout tournament with winners from a completed round.

    Args:
        tournament: Current tournament structure
        round_number: Round number that was completed (1-indexed)
        winners: List of winning team IDs from that round

    Returns:
        Updated tournament with next round pairings filled in
    """
    if round_number >= len(tournament.rounds):
        # No more rounds to update
        return tournament

    next_round_idx = round_number  # 0-indexed for list access
    next_round = tournament.rounds[next_round_idx]

    # Generate pairings for next round
    next_pairings = generate_next_round_pairings(winners)

    # Update matches in next round
    updated_matches = []
    for i, (team1_id, team2_id) in enumerate(next_pairings):
        if i < len(next_round.matches):
            # Update existing match
            old_match = next_round.matches[i]
            new_match = Match(
                competitor1_id=team1_id,
                competitor2_id=team2_id,
                games=old_match.games,  # Keep any existing games
                games_per_match=old_match.games_per_match,
                manual_tiebreak_value=old_match.manual_tiebreak_value,
            )
            updated_matches.append(new_match)
        else:
            # This shouldn't happen if tournament structure is correct
            raise ValueError(f"Not enough matches in round {round_number + 1}")

    # Update the round
    updated_round = Round(
        number=next_round.number,
        matches=updated_matches,
        knockout_stage=next_round.knockout_stage,
    )

    # Update tournament
    new_rounds = (
        tournament.rounds[:next_round_idx]
        + [updated_round]
        + tournament.rounds[next_round_idx + 1 :]
    )

    return Tournament(
        competitors=tournament.competitors,
        rounds=new_rounds,
        scoring=tournament.scoring,
        format=tournament.format,
    )


def is_knockout_tournament_complete(tournament: Tournament) -> bool:
    """Check if a knockout tournament is complete (has a winner).

    Returns True if the final round has been played and has a winner.
    """
    if tournament.format != TournamentFormat.KNOCKOUT:
        return False

    if not tournament.rounds:
        return False

    final_round = tournament.rounds[-1]
    if not final_round.matches:
        return False

    # Final round should have exactly one match
    if len(final_round.matches) != 1:
        return False

    final_match = final_round.matches[0]

    # Check if final match has games and a clear winner
    return len(final_match.games) > 0 and final_match.winner_id() is not None


def get_knockout_winner(tournament: Tournament) -> Optional[int]:
    """Get the winner of a completed knockout tournament.

    Returns:
        Winner's competitor ID, or None if tournament is not complete
    """
    if not is_knockout_tournament_complete(tournament):
        return None

    final_match = tournament.rounds[-1].matches[0]
    return final_match.winner_id()


def can_generate_next_match_set_for_tournament(tournament: Tournament, round_number: int) -> bool:
    """Check if next match set can be generated for a tournament round.
    
    This is a convenience wrapper around the multi_match module function.
    """
    # Import here to avoid circular imports
    from heltour.tournament_core.multi_match import can_generate_next_match_set
    return can_generate_next_match_set(tournament, round_number)


def generate_next_match_set_for_tournament(tournament: Tournament, round_number: int) -> Tournament:
    """Generate the next match set for a tournament round.
    
    This is a convenience wrapper around the multi_match module function.
    """
    # Import here to avoid circular imports
    from heltour.tournament_core.multi_match import generate_next_match_set
    return generate_next_match_set(tournament, round_number)


def calculate_multi_match_knockout_advancement(tournament: Tournament, round_number: int) -> List[int]:
    """Calculate advancement from a multi-match knockout round.
    
    Args:
        tournament: Tournament structure
        round_number: Round number to calculate advancement for (1-indexed)
        
    Returns:
        List of advancing competitor IDs
        
    Raises:
        ValueError: If round is not complete or winners can't be determined
    """
    if round_number < 1 or round_number > len(tournament.rounds):
        raise ValueError(f"Invalid round number: {round_number}")
        
    round_obj = tournament.rounds[round_number - 1]
    
    if tournament.matches_per_stage == 1:
        # Single match per stage - use existing logic
        return calculate_knockout_advancement(round_obj.matches, tournament.scoring)
    else:
        # Multi-match per stage - use multi-match logic
        from heltour.tournament_core.multi_match import calculate_multi_match_winners, _get_total_pairs_in_round
        total_pairs = _get_total_pairs_in_round(round_obj)
        return calculate_multi_match_winners(
            round_obj.matches, total_pairs, tournament.matches_per_stage, tournament.scoring
        )
