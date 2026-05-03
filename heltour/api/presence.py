"""Builders for the staff-only presence section of `RoundMatchesDTO`.

Mirrors `_build_presence_events_map` in `heltour/tournament/views.py:552`
so the API surface matches what the legacy template renders. Caller is
responsible for the permission check; this module unconditionally builds
the events when called and returns an empty dict when there's nothing to
show.
"""

from __future__ import annotations

from heltour.api.schemas import (
    MatchPresenceDTO,
    PlayerPresenceDTO,
    PresenceEventDTO,
)


def build_presence_for_round(round_obj) -> dict[int, MatchPresenceDTO]:
    from heltour.tournament.models import (
        LonePlayerPairing,
        PlayerPairing,
        PlayerPresenceEvent,
        TeamPlayerPairing,
    )

    events_qs = (
        PlayerPresenceEvent.objects.filter(round=round_obj)
        .select_related("player")
        .order_by("timestamp")
    )
    by_pair_player: dict[tuple[int, int], list[PresenceEventDTO]] = {}
    online_players: set[int] = set()
    for ev in events_qs:
        if ev.pairing_id is None:
            continue
        dto = PresenceEventDTO(
            timestamp=ev.timestamp.isoformat(),
            event_type=ev.event_type,
            event_type_display=ev.get_event_type_display(),
            game_id=ev.game_id or None,
        )
        by_pair_player.setdefault((ev.pairing_id, ev.player_id), []).append(dto)
        if ev.event_type == "online":
            online_players.add(ev.player_id)

    # Resolve pairings in this round across the three concrete subclasses.
    # `plies_played` lives on the base PlayerPairing, so a single base-table
    # query gets it for both team and lone forms.
    team_pp_ids = list(
        TeamPlayerPairing.objects.filter(team_pairing__round=round_obj).values_list(
            "pk", flat=True
        )
    )
    lone_pp_ids = list(
        LonePlayerPairing.objects.filter(round=round_obj).values_list("pk", flat=True)
    )
    pp_qs = PlayerPairing.objects.filter(
        pk__in=team_pp_ids + lone_pp_ids
    ).values("pk", "white_id", "black_id", "plies_played")

    out: dict[int, MatchPresenceDTO] = {}
    for row in pp_qs:
        pk = row["pk"]
        plies = row["plies_played"] or 0
        white_id = row["white_id"]
        black_id = row["black_id"]
        out[pk] = MatchPresenceDTO(
            white=_player_presence(
                pk, white_id, plies, by_pair_player, online_players
            ),
            black=_player_presence(
                pk, black_id, plies, by_pair_player, online_players
            ),
        )
    return out


def _player_presence(
    pairing_id: int,
    player_id: int | None,
    plies_played: int,
    by_pair_player: dict[tuple[int, int], list[PresenceEventDTO]],
    online_players: set[int],
) -> PlayerPresenceDTO | None:
    if player_id is None:
        return None
    return PlayerPresenceDTO(
        was_online=player_id in online_players,
        plies_played=plies_played,
        events=by_pair_player.get((pairing_id, player_id), []),
    )
