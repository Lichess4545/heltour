from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from heltour.api.auth import (
    Viewer,
    can_change_pairing_sync,
    get_viewer_and_user,
)
from heltour.api.deps import in_thread
from heltour.api.match_dto import (
    captains_for_round,
    lone_player_pairing_to_match,
    team_pairing_to_team_match,
    team_player_pairing_to_match,
)
from heltour.api.presence import build_presence_for_round
from heltour.api.schemas import (
    CurrentRoundDTO,
    EventRoundDTO,
    EventSettingsDTO,
    MatchDTO,
    MatchPresenceDTO,
    RoundMatchesDTO,
    SetMatchResultRequest,
    TeamMatchDTO,
    ViewerDTO,
)

# Mirror of `RESULT_OPTIONS` in heltour/tournament/models.py:2409. Kept
# in the API layer too so the endpoint can validate without importing
# Django at import time. Empty string is allowed to clear the result.
_VALID_RESULTS: frozenset[str] = frozenset(
    {"", "1-0", "0-1", "1/2-1/2", "1X-0F", "0F-1X", "0F-0F", "1/2Z-1/2Z"}
)

# Django SlugField charset. Constraining path params to this rejects NUL
# bytes and other oddities at the FastAPI layer with a 422 instead of
# letting them reach Postgres (which raises on NUL → 500).
_SLUG_PATTERN = r"^[-a-zA-Z0-9_]+$"
_SlugPath = Annotated[str, Path(pattern=_SLUG_PATTERN, max_length=64)]

router = APIRouter()


def _build_round_matches(rnd, viewer: Viewer, user) -> RoundMatchesDTO:
    """Build a RoundMatchesDTO for a Round model instance.

    Terminology note: the public API uses terms.md vocabulary. The Django
    ``Season`` model is exposed as ``event``; ``TeamPairing`` as Team Match;
    ``TeamPlayerPairing`` / ``LonePlayerPairing`` as Match (a Player Match
    inside a Team Match for the team form, a standalone Match otherwise).
    """
    from heltour.tournament.models import (
        LonePlayerPairing,
        TeamPairing,
        TeamPlayerPairing,
    )

    is_team = rnd.season.boards is not None
    league = rnd.season.league

    matches: list[MatchDTO] = []
    team_matches: list[TeamMatchDTO] = []

    if is_team:
        tp_qs = (
            TeamPairing.objects.filter(round_id=rnd.pk)
            .select_related("white_team", "black_team")
            .order_by("pairing_order")
        )
        for tm in tp_qs:
            team_matches.append(team_pairing_to_team_match(tm))

        captains = captains_for_round(rnd)
        team_player_qs = (
            TeamPlayerPairing.objects.filter(team_pairing__round_id=rnd.pk)
            .select_related("white", "black", "team_pairing")
            .order_by("team_pairing__pairing_order", "board_number")
        )
        for tp in team_player_qs:
            matches.append(team_player_pairing_to_match(tp, league, captains))
    else:
        lone_qs = (
            LonePlayerPairing.objects.filter(round_id=rnd.pk)
            .select_related("white", "black")
            .order_by("pairing_order", "id")
        )
        for lp in lone_qs:
            matches.append(lone_player_pairing_to_match(lp, league))

    can_change = can_change_pairing_sync(user, league)
    viewer_dto = ViewerDTO(
        is_authenticated=viewer.is_authenticated,
        can_edit_pairings=can_change,
        can_view_presence_log=can_change,
    )
    presence_events: dict[int, MatchPresenceDTO] = (
        build_presence_for_round(rnd) if can_change else {}
    )

    return RoundMatchesDTO(
        round_id=rnd.pk,
        round_number=rnd.number,
        event_tag=rnd.season.tag,
        event_name=rnd.season.name,
        league_tag=rnd.season.league.tag,
        is_completed=rnd.is_completed,
        is_team=is_team,
        settings=_event_settings(rnd.season),
        rounds=_event_rounds(rnd.season),
        matches=matches,
        team_matches=team_matches,
        viewer=viewer_dto,
        presence_events=presence_events,
    )


def _event_rounds(season) -> list[EventRoundDTO]:
    from heltour.tournament.models import Round

    rounds = Round.objects.filter(season=season).order_by("number")
    return [
        EventRoundDTO(
            round_id=r.pk,
            round_number=r.number,
            is_completed=r.is_completed,
            is_published=r.publish_pairings,
        )
        for r in rounds
    ]


def _event_settings(season) -> EventSettingsDTO:
    """Resolve the `EventSettings` for an Event (Season). Today everything
    here is sourced from the parent League; if any of these later move
    onto Season itself the resolution stays in this single function.
    """
    return EventSettingsDTO(
        use_fide_information=bool(season.league.show_fide_names),
    )


def _round_matches_by_id_sync(round_id: int, viewer: Viewer, user) -> RoundMatchesDTO:
    from heltour.tournament.models import Round

    try:
        rnd = Round.objects.select_related("season__league").get(pk=round_id)
    except Round.DoesNotExist:
        raise HTTPException(status_code=404, detail="round not found")
    return _build_round_matches(rnd, viewer, user)


def _round_matches_by_slug_sync(
    league_tag: str,
    event_tag: str,
    round_number: int,
    viewer: Viewer,
    user,
) -> RoundMatchesDTO:
    from heltour.tournament.models import Round

    try:
        rnd = Round.objects.select_related("season__league").get(
            season__league__tag=league_tag,
            season__tag=event_tag,
            number=round_number,
        )
    except Round.DoesNotExist:
        raise HTTPException(status_code=404, detail="round not found")
    return _build_round_matches(rnd, viewer, user)


def _current_round_sync(league_tag: str) -> CurrentRoundDTO:
    from heltour.tournament.models import League, Round

    try:
        league = League.objects.get(tag=league_tag)
    except League.DoesNotExist:
        raise HTTPException(status_code=404, detail="league not found")

    rnd = (
        Round.objects.filter(season__league=league, publish_pairings=True)
        .select_related("season")
        .order_by("is_completed", "-number")
        .first()
    )
    if rnd is None:
        raise HTTPException(status_code=404, detail="no published round")

    return CurrentRoundDTO(
        league_tag=league.tag,
        event_tag=rnd.season.tag,
        event_name=rnd.season.name,
        round_id=rnd.pk,
        round_number=rnd.number,
    )


_NOT_FOUND_RESPONSE = {404: {"description": "Not found"}}


@router.get(
    "/rounds/{round_id}/matches",
    response_model=RoundMatchesDTO,
    responses=_NOT_FOUND_RESPONSE,
)
async def round_matches_by_id(
    round_id: int,
    viewer_and_user: tuple[Viewer, object | None] = Depends(get_viewer_and_user),
) -> RoundMatchesDTO:
    viewer, user = viewer_and_user
    return await in_thread(_round_matches_by_id_sync, round_id, viewer, user)


@router.get(
    "/leagues/{league_tag}/events/{event_tag}/rounds/{round_number}/matches",
    response_model=RoundMatchesDTO,
    responses=_NOT_FOUND_RESPONSE,
)
async def round_matches_by_slug(
    league_tag: _SlugPath,
    event_tag: _SlugPath,
    round_number: int,
    viewer_and_user: tuple[Viewer, object | None] = Depends(get_viewer_and_user),
) -> RoundMatchesDTO:
    viewer, user = viewer_and_user
    return await in_thread(
        _round_matches_by_slug_sync, league_tag, event_tag, round_number, viewer, user
    )


@router.get(
    "/leagues/{league_tag}/current-round",
    response_model=CurrentRoundDTO,
    responses=_NOT_FOUND_RESPONSE,
)
async def current_round(league_tag: _SlugPath) -> CurrentRoundDTO:
    return await in_thread(_current_round_sync, league_tag)


def _set_match_result_sync(match_id: int, result: str, viewer: Viewer, user) -> MatchDTO:
    from heltour.tournament.models import LonePlayerPairing, TeamPlayerPairing

    if result not in _VALID_RESULTS:
        raise HTTPException(status_code=422, detail=f"invalid result: {result!r}")
    if not viewer.is_authenticated:
        raise HTTPException(status_code=401, detail="not authenticated")

    # Save the concrete subclass — Django admin does the same — so the
    # multi-table-inheritance save path runs, the team_pairing aggregate
    # refresh fires, and `post_save(sender=TeamPlayerPairing)` /
    # `post_save(sender=LonePlayerPairing)` reach `signals_pubsub.py`
    # where the WS fan-out lives. Saving the bare PlayerPairing parent
    # would update the row but skip the concrete-sender signal that the
    # publisher is registered against.
    try:
        concrete = (
            TeamPlayerPairing.objects.select_related(
                "white", "black", "team_pairing__round__season__league"
            ).get(pk=match_id)
        )
        league = concrete.team_pairing.round.season.league
        is_team = True
    except TeamPlayerPairing.DoesNotExist:
        try:
            concrete = LonePlayerPairing.objects.select_related(
                "white", "black", "round__season__league"
            ).get(pk=match_id)
        except LonePlayerPairing.DoesNotExist:
            raise HTTPException(status_code=404, detail="match not found")
        league = concrete.round.season.league
        is_team = False

    if not can_change_pairing_sync(user, league):
        raise HTTPException(status_code=403, detail="forbidden")

    concrete.result = result
    concrete.save()

    if is_team:
        captains = captains_for_round(concrete.team_pairing.round)
        return team_player_pairing_to_match(concrete, league, captains)
    return lone_player_pairing_to_match(concrete, league)


@router.put(
    "/matches/{match_id}/result",
    response_model=MatchDTO,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Forbidden — viewer lacks change_pairing perm"},
        404: {"description": "Match not found"},
        422: {"description": "Invalid result code"},
    },
)
async def set_match_result(
    match_id: int,
    body: SetMatchResultRequest,
    viewer_and_user: tuple[Viewer, object | None] = Depends(get_viewer_and_user),
) -> MatchDTO:
    viewer, user = viewer_and_user
    return await in_thread(_set_match_result_sync, match_id, body.result, viewer, user)
