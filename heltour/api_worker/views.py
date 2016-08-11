import requests
import time
import worker
from django.core.cache import cache
from django.http.response import HttpResponse
from django.utils.crypto import get_random_string

def _api_request(url):
    r = requests.get(url)
    if r.status_code == 200:
        return r.text
    elif r.status_code == 429:
        time.sleep(60)
    else:
        time.sleep(2)
    # Retry once
    return requests.get(url).text

def _do_lichess_api_call(redis_key, path):
    url = "https://en.lichess.org/api/%s" % path
    result = _api_request(url)
    cache.set(redis_key, result, timeout=60)
    time.sleep(2)

def lichess_api_call(request, path):
    priority = int(request.GET.get('priority', 0))
    redis_key = get_random_string(length=16)
    worker.queue_work(priority, _do_lichess_api_call, redis_key, path)
    return HttpResponse(redis_key)
