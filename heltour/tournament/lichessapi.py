import requests
import time
import json
from django.core.cache import cache
import logging
from heltour import settings

logger = logging.getLogger(__name__)

def _apicall(url, timeout=120, check_interval=0.1, post_data=None):
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

def get_user_meta(lichess_username, priority=0, max_retries=3, timeout=120):
    url = '%s/lichessapi/api/user/%s?priority=%s&max_retries=%s' % (settings.API_WORKER_HOST, lichess_username, priority, max_retries)
    result = _apicall(url, timeout)
    if result == '':
        raise ApiWorkerError('API failure')
    return json.loads(result)

def enumerate_user_metas(lichess_usernames, priority=0, max_retries=3, timeout=120):
    url = '%s/lichessapi/api/users?with_moves=1&priority=%s&max_retries=%s' % (settings.API_WORKER_HOST, priority, max_retries)
    while len(lichess_usernames) > 0:
        batch = lichess_usernames[:300]
        result = _apicall(url, timeout, post_data=','.join(batch))
        if result == '':
            raise ApiWorkerError('API failure')
        for meta in json.loads(result):
            yield meta
        lichess_usernames = lichess_usernames[300:]

def enumerate_user_statuses(lichess_usernames, priority=0, max_retries=3, timeout=120):
    url = '%s/lichessapi/api/users/status?priority=%s&max_retries=%s' % (settings.API_WORKER_HOST, priority, max_retries)
    while len(lichess_usernames) > 0:
        batch = lichess_usernames[:40]
        result = _apicall('%s&ids=%s' % (url, ','.join(batch)), timeout)
        if result == '':
            raise ApiWorkerError('API failure')
        for status in json.loads(result):
            yield status
        lichess_usernames = lichess_usernames[40:]

def enumerate_user_classical_rating_and_games_played(lichess_team_name, priority=0, max_retries=3, timeout=120):
    page = 1
    while True:
        url = '%s/lichessapi/api/user?team=%s&nb=100&page=%s&priority=%s&max_retries=%s' % (settings.API_WORKER_HOST, lichess_team_name, page, priority, max_retries)
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

def get_pgn_with_cache(gameid, priority=0, max_retries=3, timeout=120):
    result = cache.get('pgn_%s' % gameid)
    if result is not None:
        return result
    url = '%s/lichessapi/game/export/%s.pgn?priority=%s&max_retries=%s' % (settings.API_WORKER_HOST, gameid, priority, max_retries)
    result = _apicall(url, timeout)
    if result == '':
        raise ApiWorkerError('API failure')
    cache.set('pgn_%s' % gameid, result, 60 * 60 * 24) # Cache the PGN for 24 hours
    return result

def get_game_meta(gameid, priority=0, max_retries=3, timeout=120):
    url = '%s/lichessapi/game/export/%s?priority=%s&max_retries=%s&format=application/json' % (settings.API_WORKER_HOST, gameid, priority, max_retries)
    result = _apicall(url, timeout)
    if result == '':
        raise ApiWorkerError('API failure')
    return json.loads(result)

def get_latest_game_metas(lichess_username, number, priority=0, max_retries=3, timeout=120):
    url = '%s/lichessapi/api/games/user/%s?max=%s&ongoing=true&priority=%s&max_retries=%s&format=application/x-ndjson' % (settings.API_WORKER_HOST, lichess_username, number, priority, max_retries)
    result = _apicall(url, timeout)
    if result == '':
        raise ApiWorkerError('API failure')
    return [json.loads(g) for g in result.split('\n') if g.strip()]

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

# Gets authentication cookies for the lichess service account
# Used to send lichess mails to players
def _login_cookies():
    login_cookies = cache.get('lichess_login_cookies')
    if login_cookies is None:
        # Read the credentials
        with open(settings.LICHESS_CREDS_FILE_PATH) as creds_file:
            lines = creds_file.readlines()
            creds = {'username': lines[0].strip(), 'password': lines[1].strip()}

        # Send a login request
        login_response = requests.post(settings.LICHESS_DOMAIN + 'login', data=creds, headers=_headers)
        if login_response.status_code != 200:
            logger.error('Received status %s when trying to log in to lichess' % login_response.status_code)
            return None

        # Save the cookies
        login_cookies = dict(login_response.cookies)
        cache.set('lichess_login_cookies', login_cookies, 60) # Cache cookies for 1 minute
    return login_cookies

# Sends a mail on lichess
def send_mail(lichess_username, subject, text):
    # This doesn't actually use the API proper, so it doesn't need the worker
    try:
        login_cookies = _login_cookies()
        if login_cookies is None:
            return False

        text = text + '\n\nThis is an automated message, do not reply.'
        mail_data = {'username': lichess_username, 'subject': subject, 'text': text}
        mail_response = requests.post(settings.LICHESS_DOMAIN + 'inbox/new', data=mail_data, headers=_headers, cookies=login_cookies)
        if mail_response.status_code != 200:
            logger.error('Received status %s when trying to send mail on lichess: %s' % (mail_response.status_code, mail_response.text))
            return False
        mail_json = mail_response.json()
        if 'ok' not in mail_json or mail_json['ok'] != True:
            logger.error('Error sending mail on lichess: %s' % (mail_response.text))
            return False

        return mail_json['id']
    except Exception:
        # Probably a configuration error
        if settings.DEBUG:
            print('Lichess mail to %s - [%s]:\n%s' % (lichess_username, subject, text))
        logger.exception('Error sending lichess mail to %s' % lichess_username)
        return False

def get_peak_rating(lichess_username, perf_type):
    # This doesn't actually use the API proper, so it doesn't need the worker
    try:
        response = requests.get(settings.LICHESS_DOMAIN + '@/%s/perf/%s' % (lichess_username, perf_type), headers=_headers)
        if response.status_code != 200:
            logger.error('Received status %s when trying to retrieve peak rating on lichess: %s' % (response.status_code, response.text))
            return None
        try:
            return response.json()['stat']['highest']['int']
        except KeyError:
            return 1500

    except Exception:
        logger.exception('Error retrieving peak rating for %s' % lichess_username)
        return None

class ApiWorkerError(Exception):
    pass
