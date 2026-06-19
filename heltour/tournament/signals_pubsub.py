"""Redis pub/sub fan-out for live UI updates.

When a board pairing's result/game_link changes (or its players are swapped),
publishes a `match.update` event carrying the full current `MatchDTO` to
the `matches:round:{round_id}` channel. The FastAPI WebSocket layer
forwards that payload verbatim to subscribed browsers, which replace the
matching row in-place — no refetch, no diffing.

Team-match-level changes (score aggregates after a result is set) emit a
companion `team_match.update` event on the same channel.
"""

import json
import logging

import redis
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


def _publish(channel: str, payload: dict) -> None:
    try:
        _get_client().publish(channel, json.dumps(payload))
    except Exception:
        logger.exception("pubsub publish failed channel=%s", channel)


def _publish_match_update(match_dto, round_id: int) -> None:
    _publish(
        f"matches:round:{round_id}",
        {
            "type": "match.update",
            "round_id": round_id,
            "match": match_dto.model_dump(mode="json"),
        },
    )


def _publish_team_match_update(team_match_dto, round_id: int) -> None:
    _publish(
        f"matches:round:{round_id}",
        {
            "type": "team_match.update",
            "round_id": round_id,
            "team_match": team_match_dto.model_dump(mode="json"),
        },
    )


def _connect():
    from heltour.api.round_management.dto_builders import (
        captains_for_team_pairing,
        lone_player_pairing_to_match,
        team_pairing_to_team_match,
        team_player_pairing_to_match,
    )
    from heltour.tournament.models import (
        LonePlayerPairing,
        PlayerPairing,
        TeamPairing,
        TeamPlayerPairing,
    )

    def _round_for(instance):
        # Multi-table inheritance: instance may be the base PlayerPairing
        # or a subclass; reverse OneToOne relations let us reach the round
        # either way. Return (round_obj, league, concrete_pairing) — the
        # concrete subclass is needed so the DTO builders see the right
        # model fields (board_number, team_pairing_id, etc.).
        if isinstance(instance, TeamPlayerPairing):
            tp = instance.team_pairing
            return tp.round, tp.round.season.league, instance
        if isinstance(instance, LonePlayerPairing):
            return instance.round, instance.round.season.league, instance
        if hasattr(instance, "teamplayerpairing"):
            tpp = instance.teamplayerpairing
            return tpp.team_pairing.round, tpp.team_pairing.round.season.league, tpp
        if hasattr(instance, "loneplayerpairing"):
            lp = instance.loneplayerpairing
            return lp.round, lp.round.season.league, lp
        return None

    def _emit_match(instance) -> None:
        # Only emit when something visible changed — avoids a publish on
        # every save (e.g. unrelated admin edits).
        changed = (
            instance.result != instance.initial_result
            or instance.game_link != instance.initial_game_link
            or instance.white_id != instance.initial_white_id
            or instance.black_id != instance.initial_black_id
        )
        if not changed:
            return
        resolved = _round_for(instance)
        if resolved is None:
            logger.debug("no round for pairing=%s; skipping pubsub", instance.pk)
            return
        rnd, league, concrete = resolved
        if isinstance(concrete, TeamPlayerPairing):
            captains = captains_for_team_pairing(concrete.team_pairing)
            dto = team_player_pairing_to_match(concrete, league, captains)
        else:
            dto = lone_player_pairing_to_match(concrete, league)
        _publish_match_update(dto, rnd.pk)

    @receiver(post_save, sender=PlayerPairing, dispatch_uid="api_pp_event")
    def _base(sender, instance, **kwargs):
        _emit_match(instance)

    @receiver(post_save, sender=TeamPlayerPairing, dispatch_uid="api_team_pp_event")
    def _team(sender, instance, **kwargs):
        _emit_match(instance)

    @receiver(post_save, sender=LonePlayerPairing, dispatch_uid="api_lone_pp_event")
    def _lone(sender, instance, **kwargs):
        _emit_match(instance)

    @receiver(post_save, sender=TeamPairing, dispatch_uid="api_team_pairing_event")
    def _team_match(sender, instance, **kwargs):
        # TeamPairing.save recomputes white_points/black_points whenever a
        # child board's result changes; we publish the resulting aggregate
        # so the team-match header score in the UI updates without needing
        # to refetch the round.
        try:
            dto = team_pairing_to_team_match(instance)
        except Exception:
            logger.exception("failed to build TeamMatchDTO pk=%s", instance.pk)
            return
        _publish_team_match_update(dto, instance.round_id)


_connect()
