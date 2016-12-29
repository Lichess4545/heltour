import requests
import time
import json
from django.core.cache import cache
import logging
from heltour import settings

logger = logging.getLogger(__name__)

def _apicall(url, timeout=120, check_interval=0.1):
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

def get_user_info(lichess_username, priority=0, max_retries=3, timeout=120):
    url = '%s/lichessapi/api/user/%s?priority=%s&max_retries=%s' % (settings.API_WORKER_HOST, lichess_username, priority, max_retries)
    result = _apicall(url, timeout)
    if result == '':
        raise ApiWorkerError('API failure')
    return UserInfo(json.loads(result))

class UserInfo(object):
    def __init__(self, json):
        classical = json['perfs']['classical']
        self.rating = classical['rating']
        self.games_played = classical['games']
        self.is_engine = json.get('engine', False)
        self.is_booster = json.get('booster', False)
        self.status = 'engine' if self.is_engine else 'booster' if self.is_booster else 'normal'

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
    url = '%s/lichessapi/api/game/%s?priority=%s&max_retries=%s' % (settings.API_WORKER_HOST, gameid, priority, max_retries)
    result = _apicall(url, timeout)
    if result == '':
        raise ApiWorkerError('API failure')
    return json.loads(result)

def get_latest_game_metas(lichess_username, number, priority=0, max_retries=3, timeout=120):
    url = '%s/lichessapi/api/user/%s/games?nb=%s&priority=%s&max_retries=%s' % (settings.API_WORKER_HOST, lichess_username, number, priority, max_retries)
    result = _apicall(url, timeout)
    if result == '':
        raise ApiWorkerError('API failure')
    return json.loads(result)['currentPageResults']

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

        mail_data = {'username': lichess_username, 'subject': subject, 'text': text}
        mail_response = requests.post(settings.LICHESS_DOMAIN + 'inbox/new', data=mail_data, headers=_headers, cookies=login_cookies)
        if mail_response.status_code != 200:
            logger.error('Received status %s when trying to send mail on lichess: %s' % (mail_response.status_code, mail_response.text))
            return False
        mail_json = mail_response.json()
        if 'ok' not in mail_json or mail_json['ok'] != True:
            logger.error('Error sending mail on lichess: %s' % (mail_response.text))
            return False

        return True
    except Exception:
        # Probably a configuration error
        if settings.DEBUG:
            print 'Lichess mail to %s - [%s]:\n%s' % (lichess_username, subject, text)
        logger.exception('Error sending lichess mail to %s' % lichess_username)
        return False

class ApiWorkerError(Exception):
    pass
