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
from django.db.models import Q
from django.utils import timezone

from heltour.tournament import lichessapi
from heltour.tournament.lichessapi import default_headers
from heltour.tournament.models import (
    Player,
    PlayerPairing,
    PlayerPresenceEvent,
    get_gamelink_from_gameid,
    is_fide_rating_type,
    logger,
)

# Lichess accepts up to 500 usernames per /api/stream/games-by-users
# connection. Chunk a little under so we have headroom; multiple chunks
# spawn parallel stream threads.
WATCHER_MAX_USERNAMES = 500
REFRESH_INTERVAL_SECONDS = 60
INACTIVITY_TIMEOUT_SECONDS = 10 * 60
INITIAL_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 300
RATE_LIMIT_BACKOFF_SECONDS = 60
PRESENCE_POLL_INTERVAL_SECONDS = 60

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


def _chunked(seq: list, size: int) -> Iterable[list]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _fetch_ply_count(game_id: str) -> int:
    """Best-effort SAN-based ply count for a finished game. Returns 0 on any
    failure rather than raising — the caller treats 0 as "unknown" and won't
    overwrite a previously-stored higher count."""
    try:
        meta = lichessapi.get_game_meta(game_id, priority=1, timeout=300)
    except Exception:
        logger.exception("watcher: failed to fetch game meta for %s", game_id)
        return 0
    moves = meta.get("moves") or ""
    return len(moves.split())


# ---------------------------------------------------------------------------
# Database side-effects.


PAIRINGS_PER_CHUNK = WATCHER_MAX_USERNAMES // 2


def get_watch_chunks(
    pairings_per_chunk: int = PAIRINGS_PER_CHUNK,
) -> list[list[str]]:
    """Username chunks to feed into `/api/stream/games-by-users`.

    Finds rounds that still have at least one pairing with no result,
    then takes *all* pairings in those rounds (resolved or not) and
    slices them into groups of `pairings_per_chunk`. Each chunk's
    usernames are the union of its pairings' two players, lowercased
    and sorted.

    Why slice by pairing: lichess only delivers a game event to a
    stream connection that has *both* sides subscribed. Slicing by
    pairing keeps both sides of every pairing in the same chunk by
    construction. Ordering by primary key keeps chunk membership stable
    while a round is open — a single pairing finishing doesn't reshuffle
    the chunks, so we don't restart streams unnecessarily.

    Default chunk size is `WATCHER_MAX_USERNAMES // 2` (250 pairings →
    at most 500 usernames), staying under lichess's per-connection cap.
    """
    lone_round_ids = set(
        PlayerPairing.objects.filter(
            loneplayerpairing__round__is_completed=False,
            loneplayerpairing__round__publish_pairings=True,
            loneplayerpairing__round__season__is_completed=False,
            result="",
        )
        .values_list("loneplayerpairing__round_id", flat=True)
        .distinct()
        .nocache()
    )
    lone_round_ids.discard(None)

    team_round_ids = set(
        PlayerPairing.objects.filter(
            teamplayerpairing__team_pairing__round__is_completed=False,
            teamplayerpairing__team_pairing__round__publish_pairings=True,
            teamplayerpairing__team_pairing__round__season__is_completed=False,
            result="",
        )
        .values_list("teamplayerpairing__team_pairing__round_id", flat=True)
        .distinct()
        .nocache()
    )
    team_round_ids.discard(None)

    if not lone_round_ids and not team_round_ids:
        return []

    pairings = list(
        PlayerPairing.objects.filter(
            Q(loneplayerpairing__round_id__in=lone_round_ids)
            | Q(teamplayerpairing__team_pairing__round_id__in=team_round_ids)
        )
        .select_related("white", "black")
        .order_by("pk")
        .nocache()
    )

    chunks: list[list[str]] = []
    for slice_ in _chunked(pairings, pairings_per_chunk):
        names: set[str] = set()
        for p in slice_:
            if p.white:
                names.add(p.white.lichess_username.lower())
            if p.black:
                names.add(p.black.lichess_username.lower())
        if names:
            chunks.append(sorted(names))
    return chunks


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
        expected_modified = pairing.date_modified
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
            if existing_link != new_link:
                return False
            updated = PlayerPairing.objects.filter(
                pk=pairing.pk,
                date_modified=expected_modified,
            ).update(
                game_link="",
                tv_state="default",
                plies_played=0,
                date_modified=timezone.now(),
            )
            if updated:
                logger.info(
                    "watcher: updating pairing %s from game %s (status=%s)",
                    pairing.pk,
                    game_id,
                    status,
                )
                return True
            logger.info(
                "watcher: pairing %s changed since fetch, skipping abort",
                pairing.pk,
            )
            continue

        # PlayerPairing.save() resets tv_state -> "default" and plies_played -> 0
        # whenever game_link changes; we replicate that here since .update()
        # bypasses save().
        link_changed = pairing.game_link != new_link
        base_tv_state = "default" if link_changed else pairing.tv_state
        base_plies = 0 if link_changed else pairing.plies_played

        desired_tv_state = base_tv_state
        if " " in moves:
            desired_tv_state = "has_moves"
        result = _result_for_event(status, winner)
        desired_result = ""
        if result is not None:
            desired_result = result
            desired_tv_state = "hide"

        # The /api/stream/games-by-users payload does not carry a `moves`
        # field, so use whatever `event["moves"]` happened to give us as a
        # floor and fetch authoritative SAN from /game/export/{id} once the
        # game finishes. Without this fetch, plies_played stays at 0 in
        # production.
        ply_count = len(moves.split()) if moves else 0
        if result is not None and ply_count == 0:
            ply_count = _fetch_ply_count(game_id)
        desired_plies = max(base_plies, ply_count)

        update_fields = {
            "game_link": new_link,
            "tv_state": desired_tv_state,
            "plies_played": desired_plies,
            "date_modified": timezone.now(),
        }
        if desired_result:
            update_fields["result"] = desired_result
        if link_changed:
            # PlayerPairing.save() also clears stored ratings on link change so
            # the rating-backfill task re-fetches them from the new game.
            update_fields["white_rating"] = None
            update_fields["black_rating"] = None

        updated = PlayerPairing.objects.filter(
            pk=pairing.pk,
            date_modified=expected_modified,
        ).update(**update_fields)
        if not updated:
            logger.info(
                "watcher: pairing %s changed since fetch, skipping update",
                pairing.pk,
            )
            continue

        # PlayerPairing.save() refreshes the parent TeamPairing's match score
        # whenever a result changes; do it here since .update() bypasses save().
        if desired_result and hasattr(pairing, "teamplayerpairing"):
            tp = pairing.teamplayerpairing.team_pairing
            tp.refresh_points()
            tp.save()

        logger.info(
            "watcher: updated pairing %s from game %s "
            "(status=%s result=%s tv_state=%s link=%s)",
            pairing.pk,
            game_id,
            status,
            desired_result or "(unset)",
            desired_tv_state,
            new_link,
        )
        return True

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
# Presence polling.


def _resolve_player_context(uname: str) -> tuple[Player | None, PlayerPairing | None, object | None]:
    """Resolve the player and best-effort active pairing/round for `uname`.

    Returns (player, pairing, round). Either pairing or round may be None
    when the player has no pending pairing in an active round.
    """
    player = (
        Player.objects.filter(lichess_username__iexact=uname).nocache().first()
    )
    if player is None:
        return None, None, None
    pairing = (
        PlayerPairing.objects.filter(
            Q(white=player) | Q(black=player), result=""
        )
        .filter(
            Q(
                loneplayerpairing__round__is_completed=False,
                loneplayerpairing__round__publish_pairings=True,
            )
            | Q(
                teamplayerpairing__team_pairing__round__is_completed=False,
                teamplayerpairing__team_pairing__round__publish_pairings=True,
            )
        )
        .order_by("-pk")
        .nocache()
        .first()
    )
    round_ = pairing.get_round() if pairing else None
    return player, pairing, round_


def log_presence_event(
    uname: str,
    event_type: str,
    *,
    timestamp,
    game_id: str | None = None,
) -> PlayerPresenceEvent | None:
    """Append a `PlayerPresenceEvent` row. Returns None if the player is unknown."""
    player, pairing, round_ = _resolve_player_context(uname)
    if player is None:
        logger.info(
            "presence-poller: unknown player %s, skipping %s event",
            uname,
            event_type,
        )
        return None
    return PlayerPresenceEvent.objects.create(
        player=player,
        timestamp=timestamp,
        event_type=event_type,
        pairing=pairing,
        round=round_,
        game_id=game_id or "",
    )


class PresencePoller(threading.Thread):
    """Polls /api/users/status for active players and logs transitions.

    Runs alongside the stream threads inside the watcher process. Compares
    each tick's response against the previous snapshot and writes a
    `PlayerPresenceEvent` row for any online/offline or playing-game change.
    """

    def __init__(
        self,
        watcher: "Watcher",
        stop_event: threading.Event,
        poll_interval: float = PRESENCE_POLL_INTERVAL_SECONDS,
    ):
        super().__init__(name="presence-poller", daemon=True)
        self._watcher = watcher
        # `_stop` would shadow threading.Thread._stop(), which Python invokes
        # during thread teardown — keep our own attribute name.
        self._stop_event = stop_event
        self._poll_interval = poll_interval
        # last observed (online, playing_game_id) per lichess username.
        self._last: dict[str, tuple[bool, str | None]] = {}

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.exception("presence-poller: poll failed")
            finally:
                close_old_connections()
            if self._stop_event.wait(self._poll_interval):
                break

    def _poll_once(self) -> None:
        usernames = self._watcher.current_usernames()
        # Drop cache entries we're no longer polling so a future re-add
        # doesn't synthesize a stale transition.
        requested = {u.lower() for u in usernames}
        for stale in [u for u in self._last if u not in requested]:
            self._last.pop(stale, None)
        if not usernames:
            return
        statuses = list(
            lichessapi.enumerate_user_statuses_with_games(
                usernames, priority=1, timeout=60
            )
        )
        observed_at = timezone.now()
        for status in statuses:
            self._handle_status(status, observed_at)

    def _handle_status(self, status: dict, observed_at) -> None:
        uname = (status.get("id") or "").lower()
        if not uname:
            return
        online = bool(status.get("online"))
        game_id = status.get("playingId") or None
        prev = self._last.get(uname)

        if prev is None:
            # First sighting of this user. Only record an "online" event if
            # they're actually online — recording "offline" for every user
            # on watcher startup would flood the log.
            if online:
                log_presence_event(
                    uname, "online", timestamp=observed_at, game_id=game_id
                )
            if game_id:
                log_presence_event(
                    uname,
                    "playing_started",
                    timestamp=observed_at,
                    game_id=game_id,
                )
        else:
            prev_online, prev_game = prev
            if online != prev_online:
                log_presence_event(
                    uname,
                    "online" if online else "offline",
                    timestamp=observed_at,
                    game_id=game_id if online else prev_game,
                )
            if game_id != prev_game:
                if prev_game:
                    log_presence_event(
                        uname,
                        "playing_ended",
                        timestamp=observed_at,
                        game_id=prev_game,
                    )
                if game_id:
                    log_presence_event(
                        uname,
                        "playing_started",
                        timestamp=observed_at,
                        game_id=game_id,
                    )
        self._last[uname] = (online, game_id)


# ---------------------------------------------------------------------------
# Orchestration: refresh user list, manage one or more stream threads.


class Watcher:
    """Periodically refreshes the watch chunks and manages stream threads.

    One stream thread per chunk. Each tick recomputes chunks from the
    DB; chunks whose membership is unchanged keep their existing thread,
    chunks that disappear are stopped, and new chunks start a fresh
    thread. Adding or finishing a single pairing doesn't restart all
    streams — only the chunks whose membership actually changed.
    """

    def __init__(self, refresh_interval: float = REFRESH_INTERVAL_SECONDS):
        self.refresh_interval = refresh_interval
        self._stop = threading.Event()
        # Membership (frozenset of usernames) -> (stop_event, thread).
        self._streams: dict[
            frozenset[str], tuple[threading.Event, threading.Thread]
        ] = {}
        self._current_usernames: list[str] = []
        self._usernames_lock = threading.Lock()
        self._presence_poller: PresencePoller | None = None
        self._presence_stop: threading.Event | None = None
        # Monotonic; new threads get a unique id so log lines stay
        # distinguishable across reconciliations.
        self._next_request_id = 0

    def run(self) -> None:
        try:
            self._start_presence_poller()
            while not self._stop.is_set():
                self._tick()
                if self._stop.wait(self.refresh_interval):
                    break
        finally:
            self._stop_all_streams()
            self._stop_presence_poller()

    def stop(self) -> None:
        self._stop.set()
        for stop_event, _t in self._streams.values():
            stop_event.set()
        if self._presence_stop is not None:
            self._presence_stop.set()

    def current_usernames(self) -> list[str]:
        """Thread-safe snapshot of the union of all current chunks."""
        with self._usernames_lock:
            return list(self._current_usernames)

    def _tick(self) -> None:
        try:
            chunks = get_watch_chunks()
        except Exception:
            logger.exception("watcher: failed to refresh watch chunks")
            return
        finally:
            close_old_connections()
        self._reconcile(chunks)

    def _reconcile(self, chunks: list[list[str]]) -> None:
        desired = {frozenset(c) for c in chunks if c}
        current = set(self._streams.keys())
        to_stop = current - desired
        to_start = desired - current

        usernames = sorted({u for c in chunks for u in c})
        with self._usernames_lock:
            self._current_usernames = usernames

        if to_stop:
            self._stop_chunks(to_stop)

        if to_start or to_stop:
            logger.info(
                "watcher: reconciled chunks (kept=%d started=%d stopped=%d users=%d)",
                len(current & desired),
                len(to_start),
                len(to_stop),
                len(usernames),
            )

        for key in to_start:
            chunk = sorted(key)
            stop_event = threading.Event()
            request_id = self._next_request_id
            self._next_request_id += 1
            t = threading.Thread(
                target=stream_games,
                kwargs={
                    "usernames": chunk,
                    "stop_event": stop_event,
                    "request_id": request_id,
                },
                name=f"watcher-{request_id}",
                daemon=True,
            )
            t.start()
            self._streams[key] = (stop_event, t)

        if not desired and not current:
            logger.info("watcher: no active players, idling")

    def _stop_chunks(self, keys: Iterable[frozenset[str]]) -> None:
        threads: list[threading.Thread] = []
        for key in list(keys):
            entry = self._streams.pop(key, None)
            if entry is None:
                continue
            stop_event, t = entry
            stop_event.set()
            threads.append(t)
        for t in threads:
            t.join(timeout=5)

    def _stop_all_streams(self) -> None:
        self._stop_chunks(list(self._streams.keys()))

    def _start_presence_poller(self) -> None:
        self._presence_stop = threading.Event()
        self._presence_poller = PresencePoller(self, self._presence_stop)
        self._presence_poller.start()

    def _stop_presence_poller(self) -> None:
        if self._presence_stop is not None:
            self._presence_stop.set()
        if self._presence_poller is not None:
            self._presence_poller.join(timeout=5)
        self._presence_poller = None
        self._presence_stop = None


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
