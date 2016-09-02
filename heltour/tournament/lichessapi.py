import requests
import time
import json
from django.core.cache import cache

from heltour import settings

def _apicall(url, check_interval=0.1, timeout=120):
    # Make a request to the local API worker to put the result of a lichess API call into the redis cache
    r = requests.get(url)
    if r.status_code != 200:
        # Retry once
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

def get_user_classical_rating_and_games_played(lichess_username, priority=0, max_retries=3):
    url = '%s/lichessapi/api/user/%s?priority=%s&max_retries=%s' % (settings.API_WORKER_HOST, lichess_username, priority, max_retries)
    result = _apicall(url)
    if result == '':
        raise ApiWorkerError('API failure')
    user_info = json.loads(result)
    classical = user_info['perfs']['classical']
    return (classical['rating'], classical['games'])

def enumerate_user_classical_rating_and_games_played(lichess_team_name, priority=0, max_retries=3):
    page = 1
    while True:
        url = '%s/lichessapi/api/user?team=%s&nb=100&page=%s&priority=%s&max_retries=%s' % (settings.API_WORKER_HOST, lichess_team_name, page, priority, max_retries)
        result = _apicall(url)
        if result == '':
            break
        paginator = json.loads(result)['paginator']

        for user_info in paginator['currentPageResults']:
            classical = user_info['perfs']['classical']
            yield (user_info['username'], classical['rating'], classical['games'])

        page += 1
        if page > paginator['nbPages']:
            break

def get_pgn_with_cache(gameid, priority=0, max_retries=3):
    result = cache.get('pgn_%s' % gameid)
    if result is not None:
        return result
    url = '%s/lichessapi/game/export/%s.pgn?priority=%s&max_retries=%s' % (settings.API_WORKER_HOST, gameid, priority, max_retries)
    result = _apicall(url)
    if result == '':
        raise ApiWorkerError('API failure')
    cache.set('pgn_%s' % gameid, result, 60 * 60 * 24) # Cache the PGN for 24 hours
    return result

class ApiWorkerError(Exception):
    pass
