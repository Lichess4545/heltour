"""Compatibility shim — schemas have moved into per-domain modules.

Round-management DTOs live in ``heltour.api.round_management.schemas``;
event-setup DTOs in ``heltour.api.event_setup.schemas``. Re-exported
here only to keep external imports working.
"""

from heltour.api.event_setup.schemas import CurrentRoundDTO  # noqa: F401
from heltour.api.round_management.schemas import (  # noqa: F401
    EventRoundDTO,
    EventSettingsDTO,
    MatchDTO,
    MatchPresenceDTO,
    PlayerPresenceDTO,
    PresenceEventDTO,
    RoundMatchesDTO,
    SetMatchResultRequest,
    TeamMatchDTO,
    ViewerDTO,
    WSMatchUpdate,
    WSMessage,
    WSPing,
    WSTeamMatchUpdate,
)
