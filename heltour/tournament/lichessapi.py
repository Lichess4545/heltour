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

def get_user_classical_rating_and_games_played(lichess_username, priority=0):
    url = "%s/lichessapi/user/%s/?priority=%s" % (settings.API_WORKER_HOST, lichess_username, priority)
    user_info = json.loads(_apicall(url))
    classical = user_info["perfs"]["classical"]
    return (classical["rating"], classical["games"])

class ApiWorkerError(Exception):
    pass
