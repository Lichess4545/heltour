"""Compatibility shim — DTO builders moved to
``heltour.api.round_management.dto_builders``.
"""

from heltour.api.round_management.dto_builders import (  # noqa: F401
    captains_for_round,
    captains_for_team_pairing,
    fide_name,
    gender,
    lone_player_pairing_to_match,
    team_pairing_to_team_match,
    team_player_pairing_to_match,
)
