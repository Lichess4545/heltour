"""Builders for `MatchDTO` / `TeamMatchDTO` from Django ORM instances.

Used by the round-management HTTP routes (initial-page render) and by
the pub/sub signal layer (live updates). Sharing the construction here
means the WS payload is structurally identical to a fresh GET — the UI
can treat a streamed `match.update` exactly like a refetch of one row.
"""

from __future__ import annotations

from heltour.api.round_management.schemas import MatchDTO, TeamMatchDTO


def fide_name(player) -> str | None:
    if player is None:
        return None
    name = (player.fide_profile or {}).get("name")
    return name if name else None


def gender(player) -> str | None:
    if player is None:
        return None
    return player.gender or None


def captains_for_round(round_obj) -> set[tuple[int, int]]:
    """Set of `(team_id, player_id)` pairs that are captains in this round's
    season. One query per round; the caller passes the result to each
    `team_player_pairing_to_match` invocation to answer the per-board
    captain question without further DB hits.
    """
    from heltour.tournament.models import TeamMember

    return set(
        TeamMember.objects.filter(
            team__season=round_obj.season,
            is_captain=True,
        ).values_list("team_id", "player_id")
    )


def captains_for_team_pairing(team_pairing) -> set[tuple[int, int]]:
    """Same as `captains_for_round` but scoped to a single Team Match's
    two teams — used on signal-time updates where we don't need to scan
    the whole season.
    """
    from heltour.tournament.models import TeamMember

    team_ids = [team_pairing.white_team_id]
    if team_pairing.black_team_id is not None:
        team_ids.append(team_pairing.black_team_id)
    return set(
        TeamMember.objects.filter(team_id__in=team_ids, is_captain=True).values_list(
            "team_id", "player_id"
        )
    )


def _is_captain(captains: set[tuple[int, int]], team_id: int | None, player) -> bool:
    if player is None or team_id is None:
        return False
    return (team_id, player.pk) in captains


def team_player_pairing_to_match(
    tp, league, captains: set[tuple[int, int]] | None = None
) -> MatchDTO:
    captains = captains if captains is not None else set()
    # The white-team's player holds white pieces on odd boards, black on
    # even; flip when figuring out which team each player belongs to.
    odd_board = tp.board_number % 2 == 1
    white_pieces_team_id = (
        tp.team_pairing.white_team_id if odd_board else tp.team_pairing.black_team_id
    )
    black_pieces_team_id = (
        tp.team_pairing.black_team_id if odd_board else tp.team_pairing.white_team_id
    )
    return MatchDTO(
        id=tp.pk,
        white_username=tp.white.lichess_username if tp.white else None,
        black_username=tp.black.lichess_username if tp.black else None,
        white_fide_name=fide_name(tp.white),
        black_fide_name=fide_name(tp.black),
        white_rating=tp.white_rating_display(league),
        black_rating=tp.black_rating_display(league),
        white_gender=gender(tp.white),
        black_gender=gender(tp.black),
        white_is_captain=_is_captain(captains, white_pieces_team_id, tp.white),
        black_is_captain=_is_captain(captains, black_pieces_team_id, tp.black),
        result=tp.result,
        game_link=tp.game_link,
        board_number=tp.board_number,
        team_match_id=tp.team_pairing_id,
    )


def lone_player_pairing_to_match(lp, league) -> MatchDTO:
    return MatchDTO(
        id=lp.pk,
        white_username=lp.white.lichess_username if lp.white else None,
        black_username=lp.black.lichess_username if lp.black else None,
        white_fide_name=fide_name(lp.white),
        black_fide_name=fide_name(lp.black),
        white_rating=lp.white_rating_display(league),
        black_rating=lp.black_rating_display(league),
        white_gender=gender(lp.white),
        black_gender=gender(lp.black),
        white_is_captain=False,
        black_is_captain=False,
        result=lp.result,
        game_link=lp.game_link,
        board_number=None,
        team_match_id=None,
    )


def team_pairing_to_team_match(tm) -> TeamMatchDTO:
    return TeamMatchDTO(
        id=tm.pk,
        pairing_order=tm.pairing_order,
        white_team_name=tm.white_team.name,
        white_team_number=tm.white_team.number,
        black_team_name=tm.black_team.name if tm.black_team_id else None,
        black_team_number=tm.black_team.number if tm.black_team_id else None,
        white_score=float(tm.white_points),
        black_score=float(tm.black_points),
        is_bye=tm.black_team_id is None,
    )
