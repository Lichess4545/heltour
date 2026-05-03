from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class MatchDTO(BaseModel):
    """A single Match. In team Events this is a Player Match (one board of a
    Team Match); in lone Events it's a standalone Match.

    ``*_username`` is the lichess handle (canonical identity, used for links
    to lichess.org/@/<handle>). ``*_fide_name`` is the player's FIDE name
    when known. ``*_rating`` is league-resolved (snapshot at game time when
    available, falling back to the player's current league rating).
    ``*_gender`` is the raw choice value (``male`` / ``female`` /
    ``non-binary`` / ``not-represented`` / ``prefer-not-disclose`` / ``""``).
    """

    id: int
    white_username: str | None
    black_username: str | None
    white_fide_name: str | None
    black_fide_name: str | None
    white_rating: int | None
    black_rating: int | None
    white_gender: str | None
    black_gender: str | None
    white_is_captain: bool
    black_is_captain: bool
    result: str
    game_link: str
    board_number: int | None
    team_match_id: int | None


class TeamMatchDTO(BaseModel):
    """A Team Match (Django ``TeamPairing``). Holds the two teams and the
    aggregated score; the actual board pairings (Player Matches) are in
    ``RoundMatchesDTO.matches`` linked via ``MatchDTO.team_match_id``.
    """

    id: int
    pairing_order: int
    white_team_name: str
    white_team_number: int
    black_team_name: str | None
    black_team_number: int | None
    white_score: float
    black_score: float
    is_bye: bool


class EventRoundDTO(BaseModel):
    """Summary of one round in an Event, used by the round navigator at the
    top of round-scoped pages. ``is_published`` mirrors the Django
    ``Round.publish_pairings`` flag — pairings are visible to the public
    only when this is true; the UI fades unpublished (future) rounds.
    """

    round_id: int
    round_number: int
    is_completed: bool
    is_published: bool


class EventSettingsDTO(BaseModel):
    """Display / behaviour preferences resolved for an Event (Season).

    Bag of flags rather than scattering each setting onto every DTO that
    needs them. Today a few items live on `League` (e.g. `show_fide_names`,
    `rating_type`); over time some may move to `Season`. Either way, the
    UI consumes them through this single object so callers don't need to
    track which model owns which flag.
    """

    use_fide_information: bool


class ViewerDTO(BaseModel):
    """Permission flags for the current request's viewer, scoped to one round.

    A bag of booleans rather than a single role string so we can grow new
    surfaces (move history, tagging, etc.) without renumbering enum values.
    Today both flags are gated on the same Django permission
    (`tournament.change_pairing` against the league); we keep them
    separate so the UI doesn't have to know that.
    """

    is_authenticated: bool
    can_edit_pairings: bool
    can_view_presence_log: bool


class PresenceEventDTO(BaseModel):
    """One entry in the staff-visible presence log next to a player.

    Mirrors `PlayerPresenceEvent` (heltour/tournament/models.py:4374) — the
    same shape the legacy popover renders.
    """

    timestamp: str
    event_type: str
    event_type_display: str
    game_id: str | None


class PlayerPresenceDTO(BaseModel):
    """Presence info for one player on one match (board pairing).

    `was_online` answers "did this player appear online during the round
    at all?" — the legacy template's "Online during round" header. The
    `events` list is ordered ascending by timestamp.
    """

    was_online: bool
    plies_played: int
    events: list[PresenceEventDTO]


class MatchPresenceDTO(BaseModel):
    """Presence pair — one entry per side of a single match. Keyed on the
    round-level map by `match.id` (= the PlayerPairing pk). `null` for a
    side means there's no player on that side (bye / unfilled board).
    """

    white: PlayerPresenceDTO | None
    black: PlayerPresenceDTO | None


class RoundMatchesDTO(BaseModel):
    round_id: int
    round_number: int
    event_tag: str
    event_name: str
    league_tag: str
    is_completed: bool
    is_team: bool
    settings: EventSettingsDTO
    # All rounds in the Event, ordered by `round_number`. Used by the round
    # navigator so callers don't need a second request to render it.
    rounds: list[EventRoundDTO]
    matches: list[MatchDTO]
    team_matches: list[TeamMatchDTO]
    # Per-request, viewer-specific. Always present; flags are false for
    # anonymous viewers, in which case `presence_events` is also empty.
    viewer: ViewerDTO
    # Map of `match.id` → presence pair. Empty for viewers without
    # `can_view_presence_log` — the API is the boundary, not the UI.
    presence_events: dict[int, MatchPresenceDTO]


class CurrentRoundDTO(BaseModel):
    league_tag: str
    event_tag: str
    event_name: str
    round_id: int
    round_number: int


class SetMatchResultRequest(BaseModel):
    """Body of the staff-only `PUT /v1/matches/{id}/result` endpoint.

    Empty string clears the result. Any other value must be one of
    ``RESULT_OPTIONS`` from `heltour/tournament/models.py:2409`; the route
    rejects anything else with a 422.
    """

    result: str


class WSMatchUpdate(BaseModel):
    """One Match (board pairing) changed. Carries the *full* current state
    so the client can replace the row with the message contents — no need
    to refetch and no patch-merge logic for individual fields.
    """

    type: Literal["match.update"] = "match.update"
    round_id: int
    match: MatchDTO


class WSTeamMatchUpdate(BaseModel):
    """One Team Match (parent of board pairings) changed — typically score
    aggregates after a board's result was set. Carries the full current
    state of the Team Match.
    """

    type: Literal["team_match.update"] = "team_match.update"
    round_id: int
    team_match: TeamMatchDTO


class WSPing(BaseModel):
    type: Literal["ping"] = "ping"


WSMessage = Annotated[
    Union[WSMatchUpdate, WSTeamMatchUpdate, WSPing],
    Field(discriminator="type"),
]
