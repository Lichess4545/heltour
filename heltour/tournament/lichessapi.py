import requests
import re
import time
import json
from django.core.cache import cache
import logging
from heltour import settings

logger = logging.getLogger(__name__)


def _apicall(url, timeout=1800, check_interval=0.1, post_data=None):
    # Make a request to the local API worker to put the result of a lichess API call into the redis cache
    if post_data:
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
            raise ApiWorkerError('API worker returned HTTP %s for %s' % (r.status_code, url))
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
            raise ApiWorkerError('Timeout for %s' % url)

def _apicall_with_error_parsing(*args, **kwargs):
    result = _apicall(*args, **kwargs)
    if result == '':
        raise ApiWorkerError('API failure')
    if result.startswith("CLIENT-ERROR: "):
        raise ApiClientError(f'API failure: {result}')
    return result

def get_user_meta(lichess_username, priority=0, max_retries=5, timeout=1800):
    url = '%s/lichessapi/api/user/%s?priority=%s&max_retries=%s' % (
        settings.API_WORKER_HOST, lichess_username, priority, max_retries)
    result = _apicall_with_error_parsing(url, timeout)
    return json.loads(result)


def enumerate_user_metas(lichess_usernames, priority=0, max_retries=5, timeout=1800):
    url = '%s/lichessapi/api/users?with_moves=1&priority=%s&max_retries=%s' % (
        settings.API_WORKER_HOST, priority, max_retries)
    while len(lichess_usernames) > 0:
        batch = lichess_usernames[:300]
        result = _apicall_with_error_parsing(url, timeout, post_data=','.join(batch))
        for meta in json.loads(result):
            yield meta
        lichess_usernames = lichess_usernames[300:]


def enumerate_user_statuses(lichess_usernames, priority=0, max_retries=5, timeout=1800):
    url = '%s/lichessapi/api/users/status?priority=%s&max_retries=%s' % (
        settings.API_WORKER_HOST, priority, max_retries)
    while len(lichess_usernames) > 0:
        batch = lichess_usernames[:40]
        result = _apicall_with_error_parsing('%s&ids=%s' % (url, ','.join(batch)), timeout)
        for status in json.loads(result):
            yield status
        lichess_usernames = lichess_usernames[40:]


def enumerate_user_classical_rating_and_games_played(lichess_team_name, priority=0, max_retries=5,
                                                     timeout=1800):
    page = 1
    while True:
        url = '%s/lichessapi/api/user?team=%s&nb=100&page=%s&priority=%s&max_retries=%s' % (
            settings.API_WORKER_HOST, lichess_team_name, page, priority, max_retries)
        result = _apicall(url, timeout)
        if result == '':
            break
        paginator = json.loads(result)['paginator']

        for user_info in paginator['currentPageResults']:
            classical = user_info['perfs']['classical']
            yield (user_info['username'], classical['rating'], classical['games'])

        page += 1
        if page > paginator['nbPages']:
            break


def get_pgn_with_cache(gameid, priority=0, max_retries=5, timeout=1800):
    result = cache.get('pgn_%s' % gameid)
    if result is not None:
        return result
    url = '%s/lichessapi/game/export/%s.pgn?priority=%s&max_retries=%s' % (
        settings.API_WORKER_HOST, gameid, priority, max_retries)
    result = _apicall_with_error_parsing(url, timeout)
    cache.set('pgn_%s' % gameid, result, 60 * 60 * 24)  # Cache the PGN for 24 hours
    return result


def get_game_meta(gameid, priority=0, max_retries=5, timeout=1800):
    url = '%s/lichessapi/game/export/%s?priority=%s&max_retries=%s&format=application/json' % (
        settings.API_WORKER_HOST, gameid, priority, max_retries)
    result = _apicall_with_error_parsing(url, timeout)
    return json.loads(result)


def get_latest_game_metas(*, lichess_username, since, number, opponent, variant, priority=0, max_retries=5, timeout=1800):
    url = (f'{settings.API_WORKER_HOST}/lichessapi/api/games/user/{lichess_username}?since={since}&max={number}'
           f'&vs={opponent}&perfType="{variant}"&ongoing=true&priority={priority}&max_retries={max_retries}&format=application/x-ndjson')
    result = _apicall_with_error_parsing(url, timeout)
    return [json.loads(g) for g in result.split('\n') if g.strip()]


# Sends a mail on lichess
def send_mail(lichess_username, subject, text, priority=0, max_retries=5, timeout=1800):
    url = '%s/lichessapi/inbox/%s?priority=%s&max_retries=%s' % (
        settings.API_WORKER_HOST, lichess_username, priority, max_retries)
    post_data = {'text': '%s\n%s' % (subject, text)}
    result = _apicall_with_error_parsing(url, timeout, post_data=post_data)
    if result != 'ok':
        logger.error('Error sending mail: %s' % result)

def watch_games(game_ids):
    try:
        url = '%s/watch/' % (settings.API_WORKER_HOST)
        r = requests.post(url, data=','.join(game_ids))
        return r.json()['result']
    except Exception:
        logger.exception('Error watching games')
        return []


def add_watch(game_id):
    try:
        url = '%s/watch/add/' % (settings.API_WORKER_HOST)
        requests.post(url, data=game_id)
    except Exception:
        logger.exception('Error adding watch')


# HTTP headers used to send non-API requests to lichess
_headers = {'Accept': 'application/vnd.lichess.v1+json'}

def get_peak_rating(lichess_username, perf_type):
    # This doesn't actually use the API proper, so it doesn't need the worker
    try:
        response = requests.get(
            settings.LICHESS_DOMAIN + '@/%s/perf/%s' % (lichess_username, perf_type),
            headers=_headers)
        if response.status_code != 200:
            logger.error('Received status %s when trying to retrieve peak rating on lichess: %s' % (
                response.status_code, response.text))
            return None
        try:
            return response.json()['stat']['highest']['int']
        # the KeyError below is caused by players who never had their rating established,
        # so lichess does not consider them to have a recorded highest rating. it can be ignored.
        except KeyError:
            return None
    except Exception:
        logger.exception('Error retrieving peak rating for %s' % lichess_username)
        return None


def bulk_start_games(tokens, clock, increment, clockstart, variant, leaguename, priority=0, max_retries=0, timeout=30):
    # tokens, clock.limit, clock.increment, days, pairAt, startClocksAt, rated, variant, fen, message, rules
    # tokens: white1:black1,white2:black2,...
    # clock.limit: in seconds
    # pairAt/startClocksAt: Unix timestamp in milliseconds
    # message: has {opponent} and {game} placeholders.
    # rules: noAbort,noRematch,noGiveTime,noClaimWin,noEarlyDraw
    url = f'{settings.API_WORKER_HOST}/lichessapi/api/bulk-pairing?priority={priority}&max_retries={max_retries}&content=application/x-www-form-urlencoded'
    post = f'players={tokens}&clock.limit={clock}&clock.increment={increment}&startClocksAt={clockstart}&rated=true&variant={variant}&message=Hello! Your {leaguename} game with {{opponent}} is ready. Please join it at {{game}}. Clocks will start in about 5 minutes.&rules=noClaimWin'
    try:
        logger.info(f'[INFO] trying tokens: {tokens}')
        result = _apicall_with_error_parsing(url=url, timeout=timeout, post_data=post)
        return json.loads(result)
    except ApiClientError as err:
        e = str(err)
        if "tokens" in e:
            bad_token_search = re.search('"tokens":\{"[A-z0-9_]+"', e)
            if bad_token_search is not None:
                bad_token = e[(bad_token_search.start()+11):(bad_token_search.end()-1)]
                logger.info(f'[INFO] Removing bad token: {bad_token}')
                # remove bad token + the good token paired with it, remove potential superfluous comma
                new_tokens = re.sub('^,', '', re.sub(f'(^|,)([A-z0-9_]*:)?{bad_token}(:[A-z0-9_]*)?', '', tokens))
                logger.info(f'[INFO] new tokens: {new_tokens}')
                # if there are still tokens to be paired, retry.
                if len(new_tokens) > 1:
                    result = bulk_start_games(new_tokens, clock, increment, clockstart, variant, leaguename, priority, max_retries, timeout)
                    return result
        else:
            logger.exception(f'Error starting games for {leaguenames}')
    except Exception:
        logger.exception(f'Error starting games for {leaguename}')



class ApiWorkerError(Exception):
    pass

class ApiClientError(ApiWorkerError):
    pass
