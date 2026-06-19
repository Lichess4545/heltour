"""
Tiebreak calculation functions for tournaments.

These functions calculate various tiebreak scores used to determine standings
when competitors have equal match points. They are designed to work with both
team and individual tournaments.
"""

from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MatchResult:
    """Represents the result of a single match for a competitor."""

    opponent_id: Optional[int]  # None for byes
    game_points: float  # Game points scored in this match
    opponent_game_points: float  # Game points opponent scored
    match_points: int  # Match points earned (2 for win, 1 for draw, 0 for loss)
    games_won: int = 0  # Number of individual games won (for team tournaments)
    is_bye: bool = False  # Whether this was a bye


@dataclass(frozen=True)
class CompetitorScore:
    """Final scores and match history for a competitor."""

    competitor_id: int
    match_points: int
    game_points: float
    match_results: List[MatchResult] = field(default_factory=list)


def calculate_sonneborn_berger(
    competitor_score: CompetitorScore, all_scores: Dict[int, CompetitorScore]
) -> float:
    """
    Calculate Sonneborn-Berger score.

    The Sonneborn-Berger score is the sum of defeated opponents' scores plus
    half the sum of drawn opponents' scores.

    Args:
        competitor_score: The competitor's score data
        all_scores: Dictionary mapping competitor IDs to their final scores

    Returns:
        The Sonneborn-Berger score
    """
    sb_score = 0.0

    for result in competitor_score.match_results:
        if result.is_bye or result.opponent_id is None:
            continue

        opponent_score = all_scores.get(result.opponent_id)
        if opponent_score is None:
            continue

        if result.match_points == 2:  # Win
            sb_score += opponent_score.match_points
        elif result.match_points == 1:  # Draw
            sb_score += opponent_score.match_points / 2.0

    return sb_score


def calculate_eggsb(
    competitor_score: CompetitorScore, all_scores: Dict[int, CompetitorScore]
) -> float:
    """
    Calculate Extended Game-Game Sonneborn-Berger (EGGSB) for teams.

    EGGSB = Sum of (Total GP opponent × GP scored against that opponent)

    This is one of the four Extended Sonneborn-Berger variants defined by FIDE
    for team tournaments. For bye rounds, per FIDE Article 16.4, the virtual
    opponent has the same total game points as the participant themselves.

    Args:
        competitor_score: The competitor's score data
        all_scores: Dictionary mapping competitor IDs to their final scores

    Returns:
        The EGGSB score
    """
    eggsb_score = 0.0

    for result in competitor_score.match_results:
        if result.is_bye or result.opponent_id is None:
            # Per FIDE Article 16.4: virtual opponent has same total GP as the participant
            # EGGSB contribution = participant's total GP × GP scored in bye round
            eggsb_score += competitor_score.game_points * result.game_points
            continue

        opponent_score = all_scores.get(result.opponent_id)
        if opponent_score is None:
            continue

        # Total GP opponent × GP scored against that opponent
        eggsb_score += opponent_score.game_points * result.game_points

    return eggsb_score


def calculate_emmsb(
    competitor_score: CompetitorScore, all_scores: Dict[int, CompetitorScore]
) -> float:
    """
    Calculate Extended Match-Match Sonneborn-Berger (EMMSB) for teams.

    EMMSB = Sum of (Total MP opponent × MP scored against that opponent)

    Args:
        competitor_score: The competitor's score data
        all_scores: Dictionary mapping competitor IDs to their final scores

    Returns:
        The EMMSB score
    """
    emmsb_score = 0.0

    for result in competitor_score.match_results:
        if result.is_bye or result.opponent_id is None:
            continue

        opponent_score = all_scores.get(result.opponent_id)
        if opponent_score is None:
            continue

        # Total MP opponent × MP scored against that opponent
        emmsb_score += opponent_score.match_points * result.match_points

    return emmsb_score


def calculate_emgsb(
    competitor_score: CompetitorScore, all_scores: Dict[int, CompetitorScore]
) -> float:
    """
    Calculate Extended Match-Game Sonneborn-Berger (EMGSB) for teams.

    EMGSB = Sum of (Total MP opponent × GP scored against that opponent)

    Args:
        competitor_score: The competitor's score data
        all_scores: Dictionary mapping competitor IDs to their final scores

    Returns:
        The EMGSB score
    """
    emgsb_score = 0.0

    for result in competitor_score.match_results:
        if result.is_bye or result.opponent_id is None:
            continue

        opponent_score = all_scores.get(result.opponent_id)
        if opponent_score is None:
            continue

        # Total MP opponent × GP scored against that opponent
        emgsb_score += opponent_score.match_points * result.game_points

    return emgsb_score


def calculate_egmsb(
    competitor_score: CompetitorScore, all_scores: Dict[int, CompetitorScore]
) -> float:
    """
    Calculate Extended Game-Match Sonneborn-Berger (EGMSB) for teams.

    EGMSB = Sum of (Total GP opponent × MP scored against that opponent)

    Args:
        competitor_score: The competitor's score data
        all_scores: Dictionary mapping competitor IDs to their final scores

    Returns:
        The EGMSB score
    """
    egmsb_score = 0.0

    for result in competitor_score.match_results:
        if result.is_bye or result.opponent_id is None:
            continue

        opponent_score = all_scores.get(result.opponent_id)
        if opponent_score is None:
            continue

        # Total GP opponent × MP scored against that opponent
        egmsb_score += opponent_score.game_points * result.match_points

    return egmsb_score


def calculate_buchholz(
    competitor_score: CompetitorScore,
    all_scores: Dict[int, CompetitorScore],
    use_game_points: bool = False,
) -> float:
    """
    Calculate Buchholz score.

    The Buchholz score is the sum of all opponents' scores.

    Args:
        competitor_score: The competitor's score data
        all_scores: Dictionary mapping competitor IDs to their final scores
        use_game_points: If True, use game_points instead of match_points (FIDE individual)

    Returns:
        The Buchholz score
    """
    score_attr = "game_points" if use_game_points else "match_points"
    buchholz = 0.0

    for result in competitor_score.match_results:
        if result.is_bye or result.opponent_id is None:
            buchholz += getattr(competitor_score, score_attr)
            continue

        opponent_score = all_scores.get(result.opponent_id)
        if opponent_score is None:
            continue

        buchholz += getattr(opponent_score, score_attr)

    return buchholz


def calculate_buchholz_cut1(
    competitor_score: CompetitorScore,
    all_scores: Dict[int, CompetitorScore],
    use_game_points: bool = False,
) -> float:
    """
    Calculate Buchholz Cut-1 score.

    Buchholz minus the lowest opponent score.

    Args:
        competitor_score: The competitor's score data
        all_scores: Dictionary mapping competitor IDs to their final scores
        use_game_points: If True, use game_points instead of match_points (FIDE individual)

    Returns:
        The Buchholz Cut-1 score
    """
    score_attr = "game_points" if use_game_points else "match_points"
    scores = []

    for result in competitor_score.match_results:
        if result.is_bye or result.opponent_id is None:
            scores.append(getattr(competitor_score, score_attr))
        else:
            opp = all_scores.get(result.opponent_id)
            if opp:
                scores.append(getattr(opp, score_attr))

    if scores:
        scores.sort()
        scores = scores[1:]  # drop lowest

    return sum(scores)


def calculate_head_to_head(
    competitor_score: CompetitorScore,
    tied_competitors: Set[int],
    all_scores: Dict[int, CompetitorScore],
    use_game_points: bool = False,
) -> float:
    """
    Calculate head-to-head score among tied competitors.

    The head-to-head score is the sum of points earned against
    other competitors who are tied on both match points and game points.

    Args:
        competitor_score: The competitor's score data
        tied_competitors: Set of competitor IDs that are tied with this competitor
        all_scores: Dictionary mapping competitor IDs to their final scores
        use_game_points: If True, use game_points instead of match_points (FIDE individual)

    Returns:
        The head-to-head score
    """
    # H2H only applies if every pair in the tied group has played each other
    for comp_id in tied_competitors:
        comp = all_scores.get(comp_id)
        if comp is None:
            continue
        opponents_played = {r.opponent_id for r in comp.match_results if not r.is_bye}
        expected = tied_competitors - {comp_id}
        if not expected.issubset(opponents_played):
            return 0.0

    h2h_score = 0.0

    for result in competitor_score.match_results:
        if result.is_bye or result.opponent_id is None:
            continue

        if result.opponent_id in tied_competitors:
            if use_game_points:
                h2h_score += result.game_points
            else:
                h2h_score += result.match_points

    return h2h_score


def calculate_games_won(competitor_score: CompetitorScore) -> int:
    """
    Calculate total games won.

    This is primarily used for team tournaments where each match consists
    of multiple games (boards).

    Args:
        competitor_score: The competitor's score data

    Returns:
        The total number of games won
    """
    return sum(result.games_won for result in competitor_score.match_results)


def build_competitor_scores(
    score_dict: Dict[Tuple[int, int], any],
    last_round_number: int,
    boards_per_match: Optional[int] = None,
) -> Dict[int, CompetitorScore]:
    """
    Build CompetitorScore objects from the raw score dictionary.

    Args:
        score_dict: Dictionary mapping (competitor_id, round_number) to score state
        last_round_number: The number of the last completed round
        boards_per_match: Number of boards per match (for team tournaments)

    Returns:
        Dictionary mapping competitor IDs to CompetitorScore objects
    """
    competitor_scores = {}

    # Get all unique competitor IDs
    competitor_ids = set()
    for (comp_id, round_num), _ in score_dict.items():
        competitor_ids.add(comp_id)

    for comp_id in competitor_ids:
        match_results = []
        previous_games_won = 0

        # Build match results for each round
        for round_num in range(1, last_round_number + 1):
            state = score_dict.get((comp_id, round_num))
            if state is None:
                continue

            # Only create a match result if there was actually a match/bye
            # Check if this round had any activity (match points > 0 or it was a bye)
            if not hasattr(state, "round_opponent"):
                continue

            # Calculate games won in this round
            current_games_won = state.games_won
            round_games_won = current_games_won - previous_games_won
            previous_games_won = current_games_won

            # Create match result
            is_bye = state.round_opponent is None
            match_result = MatchResult(
                opponent_id=state.round_opponent,
                game_points=state.round_points,
                opponent_game_points=state.round_opponent_points,
                match_points=state.round_match_points,
                games_won=round_games_won,
                is_bye=is_bye,
            )
            match_results.append(match_result)

        # Get final scores from the last round
        final_state = score_dict.get((comp_id, last_round_number))
        if final_state:
            competitor_scores[comp_id] = CompetitorScore(
                competitor_id=comp_id,
                match_points=final_state.match_points,
                game_points=final_state.game_points,
                match_results=match_results,
            )

    return competitor_scores


def calculate_all_tiebreaks(
    competitor_scores: Dict[int, CompetitorScore],
    tiebreak_order: List[str],
    use_game_points: bool = False,
) -> Dict[int, Dict[str, float]]:
    """
    Calculate all tiebreak scores for all competitors.

    Args:
        competitor_scores: Dictionary mapping competitor IDs to CompetitorScore objects
        tiebreak_order: List of tiebreak names to calculate
        use_game_points: If True, use game_points scale for buchholz/h2h (FIDE individual)

    Returns:
        Dictionary mapping competitor IDs to dictionaries of tiebreak scores
    """
    # Group competitors by match points and game points for head-to-head
    tied_groups: Dict[tuple, Set[int]] = {}
    for comp_id, score in competitor_scores.items():
        key = (score.match_points, score.game_points)
        if key not in tied_groups:
            tied_groups[key] = set()
        tied_groups[key].add(comp_id)

    # Calculate tiebreaks for each competitor
    tiebreak_scores: Dict[int, Dict[str, float]] = {}
    for comp_id, score in competitor_scores.items():
        tiebreaks: Dict[str, float] = {}

        for tiebreak_name in tiebreak_order:
            if tiebreak_name == "sonneborn_berger":
                tiebreaks["sonneborn_berger"] = calculate_sonneborn_berger(
                    score, competitor_scores
                )
            elif tiebreak_name == "eggsb":
                tiebreaks["eggsb"] = calculate_eggsb(score, competitor_scores)
            elif tiebreak_name == "emmsb":
                tiebreaks["emmsb"] = calculate_emmsb(score, competitor_scores)
            elif tiebreak_name == "emgsb":
                tiebreaks["emgsb"] = calculate_emgsb(score, competitor_scores)
            elif tiebreak_name == "egmsb":
                tiebreaks["egmsb"] = calculate_egmsb(score, competitor_scores)
            elif tiebreak_name == "buchholz":
                tiebreaks["buchholz"] = calculate_buchholz(
                    score, competitor_scores, use_game_points
                )
            elif tiebreak_name == "buchholz_cut1":
                tiebreaks["buchholz_cut1"] = calculate_buchholz_cut1(
                    score, competitor_scores, use_game_points
                )
            elif tiebreak_name == "head_to_head":
                tied_set = tied_groups.get(
                    (score.match_points, score.game_points), set()
                )
                tiebreaks["head_to_head"] = calculate_head_to_head(
                    score, tied_set, competitor_scores, use_game_points
                )
            elif tiebreak_name == "games_won":
                tiebreaks["games_won"] = calculate_games_won(score)
            elif tiebreak_name == "game_points":
                tiebreaks["game_points"] = score.game_points

        tiebreak_scores[comp_id] = tiebreaks

    return tiebreak_scores
