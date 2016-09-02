import requests
import time
import worker
from django.core.cache import cache
from django.http.response import HttpResponse
from django.utils.crypto import get_random_string

def _do_lichess_api_call(redis_key, path, params, priority, max_retries, retry_count=0):
    url = "https://en.lichess.org/%s" % path
    r = requests.get(url, params)

    if r.status_code == 200:
        # Success
        cache.set(redis_key, r.text, timeout=60)
        time.sleep(2)
        return

    # Failure
    if retry_count >= max_retries:
        cache.set(redis_key, '', timeout=60)
    else:
        # Retry
        worker.queue_work(priority, _do_lichess_api_call, redis_key, path, params, priority, max_retries, retry_count + 1)

    if r.status_code == 429:
        # Too many requests
        time.sleep(60)
    else:
        time.sleep(2)

def lichess_api_call(request, path):
    params = request.GET.dict()
    priority = int(params.pop('priority', 0))
    max_retries = int(params.pop('max_retries', 3))
    redis_key = get_random_string(length=16)
    worker.queue_work(priority, _do_lichess_api_call, redis_key, path, params, priority, max_retries)
    return HttpResponse(redis_key)
