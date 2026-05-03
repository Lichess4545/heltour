from __future__ import annotations

# ^ needed for annotating str|None and int|None prior to python 3.10
import requests
import time
import json
from datetime import datetime, timedelta, timezone as dt_timezone
from platform import python_version

import django
from django.core.cache import cache
from django.utils import timezone
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def default_headers() -> dict[str, str]:
    """Canonical request headers (User-Agent) for outbound calls to Lichess."""
    version = getattr(settings, "HELTOUR_VERSION", "dev") or "dev"
    return {
        "User-Agent": (
            f"Litour (heltour/{version}; "
            f"django/{django.get_version()}; python/{python_version()})"
        ),
    }

SYSTEM_TOKEN_CHECK_CACHE_KEY = "system_api_token_check"
SYSTEM_TOKEN_CHECK_TTL_SECONDS = 300


def _apicall(
    url: str,
    timeout: int = 1800,
    check_interval: float = 0.1,
    post_data: str = "",
    post: bool = False,
) -> str:
    # Make a request to the local API worker to put the result of a lichess API call into the redis cache
    if post_data or post:
        r = requests.post(url, data=post_data)
    else:
        r = requests.get(url)
    if r.status_code != 200:
        # Retry once
        if post_data:
            r = requests.post(url, data=post_data)
        else:
            r = requests.get(url)
        if r.status_code != 200:
            raise ApiWorkerError(
                "API worker returned HTTP %s for %s" % (r.status_code, url)
            )
    # This is the key we'll use to obtain the result, which may not be set yet
    redis_key = r.text

    # Wait until the result is set in redis (with a timeout)
    time_spent = 0
    while True:
        result = cache.get(redis_key)
        if result is not None:
            return result
        time.sleep(check_interval)
        time_spent += check_interval
        if time_spent >= timeout:
            raise ApiWorkerError("Timeout for %s" % url)


def _apicall_with_error_parsing(*args, **kwargs) -> str:
    result = _apicall(*args, **kwargs)
    if result == "":
        raise ApiWorkerError("API failure")
    if result.startswith("CLIENT-ERROR: "):
        raise ApiClientError(f"API failure: {result}")
    return result


def test_oauth_token(token):
    url = (
        f"{settings.API_WORKER_HOST}/lichessapi/api/token/test?content_type=text/plain"
    )
    result = _apicall_with_error_parsing(url=url, post=True, post_data=token)
    return json.loads(result)


def check_system_api_token() -> dict:
    # Calls lichess.org/api/token/test directly (not via api_worker) so this check
    # stays useful when api_worker is the thing that's broken. Cached for 5 min.
    cached = cache.get(SYSTEM_TOKEN_CHECK_CACHE_KEY)
    if cached is not None:
        return cached

    now = timezone.now()
    next_check_at = now + timedelta(seconds=SYSTEM_TOKEN_CHECK_TTL_SECONDS)
    token = (settings.LICHESS_API_TOKEN or "").strip()

    result: dict = {
        "checked_at": now,
        "next_check_at": next_check_at,
        "valid": False,
        "user_id": None,
        "scopes": [],
        "expires_at": None,
        "error": None,
    }

    if not token:
        result["error"] = "LICHESS_API_TOKEN is not configured"
        cache.set(SYSTEM_TOKEN_CHECK_CACHE_KEY, result, SYSTEM_TOKEN_CHECK_TTL_SECONDS)
        return result

    try:
        response = requests.post(
            "https://lichess.org/api/token/test",
            data=token,
            headers={"Content-Type": "text/plain"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        result["error"] = f"Request failed: {e}"
        cache.set(SYSTEM_TOKEN_CHECK_CACHE_KEY, result, SYSTEM_TOKEN_CHECK_TTL_SECONDS)
        return result
    except ValueError as e:
        result["error"] = f"Invalid response from lichess: {e}"
        cache.set(SYSTEM_TOKEN_CHECK_CACHE_KEY, result, SYSTEM_TOKEN_CHECK_TTL_SECONDS)
        return result

    info = data.get(token) if isinstance(data, dict) else None
    if info is None:
        result["error"] = "Token rejected by lichess"
    else:
        result["valid"] = True
        result["user_id"] = info.get("userId")
        scopes_str = info.get("scopes") or ""
        result["scopes"] = [s for s in scopes_str.split(",") if s]
        expires_ms = info.get("expires")
        if expires_ms:
            result["expires_at"] = datetime.fromtimestamp(
                expires_ms / 1000, tz=dt_timezone.utc
            )

    cache.set(SYSTEM_TOKEN_CHECK_CACHE_KEY, result, SYSTEM_TOKEN_CHECK_TTL_SECONDS)
    return result


def test_whoami():
    url = f"{settings.API_WORKER_HOST}/lichessapi/api/account"
    result = _apicall_with_error_parsing(url=url)
    return json.loads(result)


def get_user_meta(lichess_username, priority=0, max_retries=5, timeout=1800):
    url = "%s/lichessapi/api/user/%s?priority=%s&max_retries=%s" % (
        settings.API_WORKER_HOST,
        lichess_username,
        priority,
        max_retries,
    )
    result = _apicall_with_error_parsing(url, timeout)
    return json.loads(result)


def get_fide_player(fide_id, priority=0, max_retries=5, timeout=1800):
    url = "%s/lichessapi/api/fide/player/%s?priority=%s&max_retries=%s" % (
        settings.API_WORKER_HOST,
        fide_id,
        priority,
        max_retries,
    )
    result = _apicall_with_error_parsing(url, timeout)
    return json.loads(result)


def enumerate_user_metas(lichess_usernames, priority=0, max_retries=5, timeout=1800):
    url = "%s/lichessapi/api/users?&priority=%s&max_retries=%s" % (
        settings.API_WORKER_HOST,
        priority,
        max_retries,
    )
    while len(lichess_usernames) > 0:
        batch = lichess_usernames[:300]
        result = _apicall_with_error_parsing(url, timeout, post_data=",".join(batch))
        for meta in json.loads(result):
            yield meta
        lichess_usernames = lichess_usernames[300:]


def enumerate_user_statuses(lichess_usernames, priority=0, max_retries=5, timeout=1800):
    url = "%s/lichessapi/api/users/status?priority=%s&max_retries=%s" % (
        settings.API_WORKER_HOST,
        priority,
        max_retries,
    )
    while len(lichess_usernames) > 0:
        batch = lichess_usernames[:40]
        result = _apicall_with_error_parsing(
            "%s&ids=%s" % (url, ",".join(batch)), timeout
        )
        for status in json.loads(result):
            yield status
        lichess_usernames = lichess_usernames[40:]


def enumerate_user_statuses_with_games(
    lichess_usernames, priority=0, max_retries=5, timeout=1800
):
    url = "%s/lichessapi/api/users/status?withGameIds=true&priority=%s&max_retries=%s" % (
        settings.API_WORKER_HOST,
        priority,
        max_retries,
    )
    while len(lichess_usernames) > 0:
        batch = lichess_usernames[:40]
        result = _apicall_with_error_parsing(
            "%s&ids=%s" % (url, ",".join(batch)), timeout
        )
        for status in json.loads(result):
            yield status
        lichess_usernames = lichess_usernames[40:]


def get_pgn_with_cache(gameid, priority=0, max_retries=5, timeout=1800):
    result = cache.get("pgn_%s" % gameid)
    if result is not None:
        return result
    url = "%s/lichessapi/game/export/%s.pgn?priority=%s&max_retries=%s" % (
        settings.API_WORKER_HOST,
        gameid,
        priority,
        max_retries,
    )
    result = _apicall_with_error_parsing(url, timeout)
    cache.set("pgn_%s" % gameid, result, 60 * 60 * 24)  # Cache the PGN for 24 hours
    return result


def get_game_meta(gameid, priority=0, max_retries=5, timeout=1800):
    url = (
        "%s/lichessapi/game/export/%s?priority=%s&max_retries=%s&format=application/json"
        % (settings.API_WORKER_HOST, gameid, priority, max_retries)
    )
    result = _apicall_with_error_parsing(url, timeout)
    return json.loads(result)


def get_latest_game_metas(
    *,
    lichess_username,
    since,
    number,
    opponent,
    variant,
    priority=0,
    max_retries=5,
    timeout=1800,
):
    url = (
        f"{settings.API_WORKER_HOST}/lichessapi/api/games/user/{lichess_username}?since={since}&max={number}"
        f'&vs={opponent}&perfType="{variant}"&ongoing=true&priority={priority}&max_retries={max_retries}&format=application/x-ndjson'
    )
    result = _apicall_with_error_parsing(url, timeout)
    return [json.loads(g) for g in result.split("\n") if g.strip()]


# Sends a mail on lichess
def send_mail(lichess_username, subject, text, priority=0, max_retries=5, timeout=1800):
    url = "%s/lichessapi/inbox/%s?priority=%s&max_retries=%s" % (
        settings.API_WORKER_HOST,
        lichess_username,
        priority,
        max_retries,
    )
    post_data = {"text": "%s\n%s" % (subject, text)}
    result = _apicall_with_error_parsing(url, timeout, post_data=post_data)
    if result != "ok":
        logger.error("Error sending mail: %s" % result)


def watch_games(game_ids):
    try:
        url = "%s/watch/" % (settings.API_WORKER_HOST)
        r = requests.post(url, data=",".join(game_ids))
        return r.json()["result"]
    except Exception:
        logger.exception("Error watching games")
        return []


def add_watch(game_id):
    try:
        url = "%s/watch/add/" % (settings.API_WORKER_HOST)
        requests.post(url, data=game_id)
    except Exception:
        logger.exception("Error adding watch")


# HTTP headers used to send non-API requests to lichess
_headers = {"Accept": "application/vnd.lichess.v1+json"}


def get_peak_rating(lichess_username, perf_type):
    # This doesn't actually use the API proper, so it doesn't need the worker
    try:
        response = requests.get(
            settings.LICHESS_DOMAIN + "@/%s/perf/%s" % (lichess_username, perf_type),
            headers=_headers,
        )
        if response.status_code != 200:
            logger.error(
                "Received status %s when trying to retrieve peak rating on lichess: %s"
                % (response.status_code, response.text)
            )
            return None
        try:
            return response.json()["stat"]["highest"]["int"]
        # the KeyError below is caused by players who never had their rating established,
        # so lichess does not consider them to have a recorded highest rating. it can be ignored.
        except KeyError:
            return None
    except Exception:
        logger.exception("Error retrieving peak rating for %s" % lichess_username)
        return None


def get_admin_token(
    *,
    lichess_usernames: list[str],
    description: str = "Lichess Tournament Pairings",  # ideally tournament name
    priority: int = 0,
    max_retries: int = 0,
    timeout: int = 30,
) -> dict[str, str]:
    usernames = ",".join(lichess_usernames)
    url = (
        f"{settings.API_WORKER_HOST}/lichessapi/api/token/admin-challenge"
        f"?priority={priority}&max_retries={max_retries}&"
        f"content_type=application/x-www-form-urlencoded"
    )
    post = f"users={usernames}&description={description}"
    result = _apicall_with_error_parsing(url=url, timeout=timeout, post_data=post)
    return json.loads(result)


def bulk_start_games(
    *,
    tokens,
    clock,
    increment,
    do_clockstart,
    clockstart,
    clockstart_in,
    variant,
    leaguename,
    priority=0,
    max_retries=0,
    timeout=30,
):
    url = f"{settings.API_WORKER_HOST}/lichessapi/api/bulk-pairing?priority={priority}&max_retries={max_retries}&content_type=application/x-www-form-urlencoded"
    if do_clockstart:
        post = f"players={tokens}&clock.limit={clock}&clock.increment={increment}&startClocksAt={clockstart}&rated=true&variant={variant}&message=Hello! Your {leaguename} game with {{opponent}} is ready. Please join it at {{game}}%0AClocks will be started in {clockstart_in} minutes, but you can begin playing at any time.&rules=noClaimWin"
    else:
        post = f"players={tokens}&clock.limit={clock}&clock.increment={increment}&rated=true&variant={variant}&message=Hello! Your {leaguename} game with {{opponent}} is ready. Please join it at {{game}}&rules=noClaimWin"
    result = _apicall_with_error_parsing(url=url, timeout=timeout, post_data=post)
    return json.loads(result)


def bulk_start_clocks(
    *,
    bulkid: str,
    priority: int = 0,
    max_retries: int = 2,
    timeout: int = 30,
) -> dict[str, str]:
    url = (
        f"{settings.API_WORKER_HOST}/lichessapi/api/bulk-pairing/{bulkid}/start-clocks?"
        f"priority={priority}&max_retries={max_retries}&content_type="
        "application/x-www-form-urlencoded"
    )
    result = _apicall_with_error_parsing(url=url, timeout=timeout, post=True)
    return json.loads(result)


def update_or_create_broadcast(
    *,
    broadcast_id: str | None = None,
    name: str,
    nrounds: int = 8,
    format_: str = "Team Swiss",
    location: str = "lichess.org",
    tc: str = "45+45",
    infoplayers: str = "",
    website: str = "lichess4545.com",
    standings: str = "",
    markdown: str = "",
    showScores: bool = True,
    showRatingDiffs: bool = True,
    teamTable: bool = True,
    players: str = "",
    teams: str = "",
    grouping: str = "",
    priority: int = 0,
    max_retries: int = 2,
    timeout: int = 30,
) -> dict:
    infoformat = f"{nrounds}-round {format_}"
    postdict = {
        "name": name,
        "info.format": infoformat,
        "info.location": location,
        "info.tc": tc,
    }
    if infoplayers:
        postdict["info.players"] = infoplayers
    if standings:
        postdict["info.standings"] = standings
    if markdown:
        postdict["markdown"] = markdown
    if not showScores:  # lichess default is true
        postdict["showScores"] = "false"
    if not showRatingDiffs:  # lichess default is true
        postdict["showRatingDiffs"] = "false"
    if teamTable:  # lichess default is false
        postdict["teamTable"] = "true"
    if players:
        postdict["players"] = players
    if teams:
        postdict["teams"] = teams
    # needs token with web:mod permission, and presumably broadcast permssions on lichess
    if grouping:
        postdict["grouping"] = grouping
    post_data = "&".join("{}={}".format(*i) for i in postdict.items())
    pre_url = f"{settings.API_WORKER_HOST}/lichessapi/broadcast/"
    post_url = (
        f"?priority={priority}&max_retries={max_retries}&"
        "content_type=application/x-www-form-urlencoded&format=application/json"
    )
    url = (
        f"{pre_url}{broadcast_id}/edit{post_url}"
        if broadcast_id
        else f"{pre_url}new{post_url}"
    )
    result = _apicall_with_error_parsing(url=url, timeout=timeout, post_data=post_data)
    return json.loads(result)


def update_or_create_broadcast_round(
    *,
    broadcast_id: str = "",
    broadcast_round_id: str = "",
    round_number: int = 0,
    game_links: list[str] = [""],
    startsAt: int | None = None,
    startsAfterPrevious: bool = False,
    delay: int | None = None,
    status: str = "started",
    rated: int = True,
    priority: int = 0,
    max_retries: int = 2,
    timeout: int = 30,
) -> dict:
    if (not broadcast_id and not broadcast_round_id) or (
        broadcast_id and broadcast_round_id
    ):
        raise ValueError(
            "Need exactly one of either broadcast_id or broadcast_round_id"
        )
    if status not in ["new", "started", "finished"]:
        raise ValueError("status can only be new, started or finished")
    name = f"Round {round_number}"
    syncIds = " ".join(game_links)
    postdict = {
        "name": name,
        "syncIds": syncIds,
        "status": status,
    }
    if startsAt:
        postdict["startsAt"] = str(startsAt)
    if startsAfterPrevious:  # lichess default is false
        postdict["startsAfterPrevious"] = "true"
    if delay:
        postdict["delay"] = str(delay)
    if not rated:  # lichess default is true
        postdict["rated"] = "false"
    post_data = "&".join("{}={}".format(*i) for i in postdict.items())
    pre_url = f"{settings.API_WORKER_HOST}/lichessapi/broadcast/"
    post_url = (
        f"?priority={priority}&max_retries={max_retries}&"
        "content_type=application/x-www-form-urlencoded&format=application/json"
    )
    url = (
        f"{pre_url}{broadcast_id}/new{post_url}"
        if broadcast_id
        else f"{pre_url}round/{broadcast_round_id}/edit{post_url}"
    )
    result = _apicall_with_error_parsing(url=url, timeout=timeout, post_data=post_data)
    return json.loads(result)


class ApiWorkerError(Exception):
    pass


class ApiClientError(ApiWorkerError):
    pass
