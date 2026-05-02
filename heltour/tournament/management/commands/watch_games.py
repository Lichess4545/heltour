"""Long-running game watcher.

Subscribes to Lichess's `/api/stream/games-by-users` ndjson stream for the
players in active pairings and updates each `PlayerPairing`'s `game_link`,
`tv_state`, and `result` as games start and end. Replaces the periodic
`update_tv_state` polling loop.

Run as its own process (the `litour-watcher` container in production):

    python manage.py watch_games

The process reconnects with exponential backoff if the stream drops, refreshes
the username list every minute, and exits cleanly on SIGTERM/SIGINT.
"""

from __future__ import annotations

import json
import signal
import threading
from typing import Callable, Iterable, Iterator

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from heltour.tournament.lichessapi import default_headers
from heltour.tournament.models import (
    PlayerPairing,
    SeasonPlayer,
    get_gamelink_from_gameid,
    is_fide_rating_type,
    logger,
)

# Lichess accepts up to 1000 usernames per stream connection; keep some margin.
WATCHER_MAX_USERNAMES = 900
REFRESH_INTERVAL_SECONDS = 60
INACTIVITY_TIMEOUT_SECONDS = 10 * 60
INITIAL_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 300
RATE_LIMIT_BACKOFF_SECONDS = 60

DRAW_STATUSES = frozenset({"draw", "stalemate", "insufficientMaterialClaim"})
LIVE_STATUSES = frozenset({"created", "started"})

EventHandler = Callable[[dict], None]


# ---------------------------------------------------------------------------
# Pure helpers — no I/O, easy to test.


def _stream_url() -> str:
    return f"{settings.LICHESS_DOMAIN}api/stream/games-by-users"


def _result_for_event(status: str | None, winner: str | None) -> str | None:
    if status in DRAW_STATUSES:
        return "1/2-1/2"
    # "timeout" denotes a claim-victory which the league does not honor.
    if status in LIVE_STATUSES or status == "timeout":
        return None
    if winner == "white":
        return "1-0"
    if winner == "black":
        return "0-1"
    return None


def _event_matches_league(event: dict, league) -> bool:
    clock = event.get("clock") or {}
    if clock.get("initial") != league.time_control_initial():
        return False
    if clock.get("increment") != league.time_control_increment():
        return False
    perf = event.get("perf")
    if perf and not _perf_matches_rating_type(perf, league.rating_type):
        return False
    if event.get("rated") is not True:
        return False
    return True


def _perf_matches_rating_type(perf: str, rating_type: str) -> bool:
    if perf == rating_type:
        return True
    # FIDE rating types ("fide", "fide_standard", "fide_rapid", "fide_blitz")
    # mean "the league counts toward FIDE ratings"; the underlying lichess
    # game is still a regular standard/rapid/blitz/classical game.
    if is_fide_rating_type(rating_type):
        return perf in {"standard", "rapid", "blitz", "classical"}
    return False


def _chunked(seq: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# ---------------------------------------------------------------------------
# Database side-effects.


def get_active_usernames() -> list[str]:
    """Lower-cased lichess usernames of active players in not-yet-completed seasons."""
    season_players = (
        SeasonPlayer.objects.filter(is_active=True, season__is_completed=False)
        .select_related("player")
        .nocache()
    )
    usernames: set[str] = set()
    for sp in season_players:
        if sp.player:
            usernames.add(sp.player.lichess_username.lower())
    return sorted(usernames)


def apply_event(event: dict) -> bool:
    """Match a Lichess game event to a pending pairing and update it.

    Returns True iff a pairing was modified. Quietly returns False on
    malformed events, missing matches, or league-config mismatches.
    """
    try:
        white_id = event["players"]["white"]["userId"].lower()
        black_id = event["players"]["black"]["userId"].lower()
        game_id = event["id"]
    except (KeyError, TypeError, AttributeError):
        logger.info("watcher: skipping malformed event %s", event)
        return False

    # Lichess sends both `status` (int code) and `statusName` (e.g. "mate",
    # "resign"). We match on the human-readable name.
    status = event.get("statusName")
    moves = event.get("moves") or ""
    winner = event.get("winner")
    new_link = get_gamelink_from_gameid(game_id)
    logger.info(
        "watcher: event %s vs %s game=%s status=%s",
        white_id,
        black_id,
        game_id,
        status,
    )

    candidates = list(
        PlayerPairing.objects.filter(
            white__lichess_username__iexact=white_id,
            black__lichess_username__iexact=black_id,
            result="",
        )
        .select_related("white", "black")
        .nocache()
    )
    if not candidates:
        logger.info(
            "watcher: no matching pairing for %s vs %s (game %s)",
            white_id,
            black_id,
            game_id,
        )
        return False

    for pairing in candidates:
        round_ = pairing.get_round()
        if round_ is None or round_.is_completed or not round_.publish_pairings:
            logger.info(
                "watcher: pairing %s skipped (round inactive)", pairing.pk
            )
            continue
        league = round_.season.league
        existing_link = pairing.game_link
        already_linked = bool(existing_link) and existing_link == new_link

        if not already_linked and not _event_matches_league(event, league):
            logger.info(
                "watcher: pairing %s skipped (league mismatch). "
                "event: tc=%s perf=%s rated=%s. "
                "league %s expects: tc=%s+%s perf=%s",
                pairing.pk,
                event.get("clock"),
                event.get("perf"),
                event.get("rated"),
                league.tag,
                league.time_control_initial(),
                league.time_control_increment(),
                league.rating_type,
            )
            continue

        if existing_link and existing_link != new_link:
            logger.info(
                "watcher: ignoring %s vs %s game %s (existing link %s)",
                white_id,
                black_id,
                game_id,
                existing_link,
            )
            return False

        if status == "aborted":
            if existing_link == new_link:
                pairing.game_link = ""
                pairing.tv_state = "default"
                logger.info(
                    "watcher: updating pairing %s from game %s (status=%s)",
                    pairing.pk,
                    game_id,
                    status,
                )
                pairing.save()
                return True
            return False

        # Two-phase save: PlayerPairing.save() resets tv_state to "default"
        # whenever game_link changes, so persist the link first and then the
        # tv_state/result derived from this event.
        link_changed = False
        if pairing.game_link != new_link:
            pairing.game_link = new_link
            pairing.save()
            pairing.initial_game_link = pairing.game_link
            link_changed = True

        desired_tv_state = pairing.tv_state
        desired_result = pairing.result
        if " " in moves:
            desired_tv_state = "has_moves"
        result = _result_for_event(status, winner)
        if result is not None:
            desired_result = result
            desired_tv_state = "hide"

        state_changed = (
            desired_tv_state != pairing.tv_state
            or desired_result != pairing.result
        )
        if state_changed:
            pairing.tv_state = desired_tv_state
            pairing.result = desired_result
            pairing.save()

        if link_changed or state_changed:
            logger.info(
                "watcher: updated pairing %s from game %s "
                "(status=%s result=%s tv_state=%s link=%s)",
                pairing.pk,
                game_id,
                status,
                pairing.result or "(unset)",
                pairing.tv_state,
                pairing.game_link,
            )
            return True
        return False

    return False


# ---------------------------------------------------------------------------
# Stream loop.


def _iter_events(response: requests.Response) -> Iterator[dict]:
    """Yield decoded events from a streaming ndjson response.

    Skips empty keepalive lines. Logs and skips invalid JSON; never raises
    for parser errors.
    """
    for raw in response.iter_lines():
        if not raw:
            logger.info("watcher: <- keepalive")
            continue
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        logger.info("watcher: <- %s", raw)
        try:
            yield json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("watcher: invalid json %r: %s", raw[:120], e)


def _open_stream(
    *,
    usernames: list[str],
    session: requests.Session,
) -> requests.Response:
    token = (settings.LICHESS_API_TOKEN or "").strip()
    headers = default_headers()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    logger.info(
        "watcher: -> POST %s with %d users: %s",
        _stream_url(),
        len(usernames),
        ",".join(usernames),
    )
    return session.post(
        _stream_url(),
        data=",".join(usernames),
        headers=headers,
        stream=True,
        timeout=(10, INACTIVITY_TIMEOUT_SECONDS),
    )


def stream_games(
    usernames: list[str],
    *,
    stop_event: threading.Event,
    on_event: EventHandler = apply_event,
    session: requests.Session | None = None,
    request_id: int = 0,
) -> None:
    """Stream Lichess game events for `usernames`, calling `on_event` per event.

    Reconnects with exponential backoff on transport errors; honours
    `stop_event` between attempts and after each event. Returns when
    `stop_event` is set. Per-event handler exceptions are logged but do not
    terminate the stream.
    """
    backoff = INITIAL_BACKOFF_SECONDS
    own_session = session is None
    if own_session:
        session = requests.Session()
    try:
        while not stop_event.is_set():
            try:
                logger.info(
                    "watcher[%s]: connecting (%d users)",
                    request_id,
                    len(usernames),
                )
                with _open_stream(usernames=usernames, session=session) as response:
                    if response.status_code == 401:
                        logger.error(
                            "watcher[%s]: unauthorized (401). Set LICHESS_API_TOKEN "
                            "to a token with stream scope and restart.",
                            request_id,
                        )
                        stop_event.set()
                        return
                    if response.status_code == 429:
                        backoff = max(backoff, RATE_LIMIT_BACKOFF_SECONDS)
                        logger.warning(
                            "watcher[%s]: rate limited (429)", request_id
                        )
                    else:
                        response.raise_for_status()
                        backoff = INITIAL_BACKOFF_SECONDS
                        logger.info("watcher[%s]: connected", request_id)
                        for event in _iter_events(response):
                            if stop_event.is_set():
                                break
                            try:
                                on_event(event)
                            except Exception:
                                logger.exception(
                                    "watcher[%s]: error processing event",
                                    request_id,
                                )
                            finally:
                                close_old_connections()
            except requests.exceptions.RequestException as e:
                logger.warning("watcher[%s]: connection error: %s", request_id, e)
            except Exception:
                logger.exception("watcher[%s]: unexpected error", request_id)
            finally:
                close_old_connections()

            if stop_event.is_set():
                break
            logger.info(
                "watcher[%s]: reconnecting in %ss", request_id, backoff
            )
            if stop_event.wait(backoff):
                break
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
    finally:
        if own_session:
            session.close()


# ---------------------------------------------------------------------------
# Orchestration: refresh user list, manage one or more stream threads.


class Watcher:
    """Periodically refreshes the active username list and manages streams."""

    def __init__(self, refresh_interval: float = REFRESH_INTERVAL_SECONDS):
        self.refresh_interval = refresh_interval
        self._stop = threading.Event()
        self._stream_stops: list[threading.Event] = []
        self._stream_threads: list[threading.Thread] = []
        self._current_usernames: list[str] = []

    def run(self) -> None:
        try:
            while not self._stop.is_set():
                self._tick()
                if self._stop.wait(self.refresh_interval):
                    break
        finally:
            self._stop_streams()

    def stop(self) -> None:
        self._stop.set()
        for ev in self._stream_stops:
            ev.set()

    def _tick(self) -> None:
        try:
            usernames = get_active_usernames()
        except Exception:
            logger.exception("watcher: failed to refresh usernames")
            return
        finally:
            close_old_connections()

        if usernames == self._current_usernames:
            return
        logger.info(
            "watcher: usernames changed (%d -> %d), restarting streams",
            len(self._current_usernames),
            len(usernames),
        )
        self._restart_streams(usernames)

    def _restart_streams(self, usernames: list[str]) -> None:
        self._stop_streams()
        self._current_usernames = usernames
        if not usernames:
            logger.info("watcher: no active players, idling")
            return
        for i, chunk in enumerate(_chunked(usernames, WATCHER_MAX_USERNAMES)):
            stop_event = threading.Event()
            t = threading.Thread(
                target=stream_games,
                kwargs={
                    "usernames": chunk,
                    "stop_event": stop_event,
                    "request_id": i,
                },
                name=f"watcher-{i}",
                daemon=True,
            )
            t.start()
            self._stream_stops.append(stop_event)
            self._stream_threads.append(t)

    def _stop_streams(self) -> None:
        for ev in self._stream_stops:
            ev.set()
        for t in self._stream_threads:
            t.join(timeout=5)
        self._stream_stops = []
        self._stream_threads = []


# ---------------------------------------------------------------------------
# Django entry point.


class Command(BaseCommand):
    help = (
        "Stream lichess games for active league players and update pairings "
        "in real time. Runs forever; supervise it as a separate process."
    )

    def handle(self, *args, **options):
        if not (settings.LICHESS_API_TOKEN or "").strip():
            raise SystemExit(
                "watch_games requires LICHESS_API_TOKEN to be set "
                "(the /api/stream/games-by-users endpoint requires authentication)."
            )
        watcher = Watcher()

        def shutdown(signum, _frame):
            logger.info("watcher: signal %s received, shutting down", signum)
            watcher.stop()

        signal.signal(signal.SIGTERM, shutdown)
        signal.signal(signal.SIGINT, shutdown)
        watcher.run()
