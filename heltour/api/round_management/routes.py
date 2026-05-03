"""HTTP routes for the round-management domain.

Routes are thin: each one validates the path, resolves the viewer, and
hands off to a sync service function via ``in_thread``. The DTO shape
is identical for the initial fetch and for streamed websocket updates
so the UI replaces a row with whatever it receives — no diffing.
"""

from fastapi import APIRouter, Depends

from heltour.api.deps import in_thread
from heltour.api.round_management.schemas import (
    MatchDTO,
    RoundMatchesDTO,
    SetMatchResultRequest,
)
from heltour.api.round_management.service import (
    round_matches_by_id_sync,
    round_matches_by_slug_sync,
    set_match_result_sync,
)
from heltour.api.shared.auth import Viewer, get_viewer_and_user
from heltour.api.shared.paths import SlugPath

router = APIRouter()

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
    return await in_thread(round_matches_by_id_sync, round_id, viewer, user)


@router.get(
    "/leagues/{league_tag}/events/{event_tag}/rounds/{round_number}/matches",
    response_model=RoundMatchesDTO,
    responses=_NOT_FOUND_RESPONSE,
)
async def round_matches_by_slug(
    league_tag: SlugPath,
    event_tag: SlugPath,
    round_number: int,
    viewer_and_user: tuple[Viewer, object | None] = Depends(get_viewer_and_user),
) -> RoundMatchesDTO:
    viewer, user = viewer_and_user
    return await in_thread(
        round_matches_by_slug_sync, league_tag, event_tag, round_number, viewer, user
    )


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
    return await in_thread(set_match_result_sync, match_id, body.result, viewer, user)
