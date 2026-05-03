from fastapi import APIRouter

from heltour.api.deps import in_thread
from heltour.api.event_setup.schemas import CurrentRoundDTO
from heltour.api.event_setup.service import current_round_sync
from heltour.api.shared.paths import SlugPath

router = APIRouter()


@router.get(
    "/leagues/{league_tag}/current-round",
    response_model=CurrentRoundDTO,
    responses={404: {"description": "Not found"}},
)
async def current_round(league_tag: SlugPath) -> CurrentRoundDTO:
    return await in_thread(current_round_sync, league_tag)
