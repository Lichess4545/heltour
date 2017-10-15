import requests
import time
import worker
from django.core.cache import cache
from django.http.response import HttpResponse, JsonResponse
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt

def _do_lichess_api_call(redis_key, path, method, post_data, params, priority, max_retries, retry_count=0):
    url = "https://lichess.org/%s" % path

    try:
        if method == 'POST':
            r = requests.post(url, params=params, data=post_data)
        else:
            r = requests.get(url, params)

        if r.status_code == 200:
            # Success
            cache.set(redis_key, r.text, timeout=60)
            time.sleep(2)
            return
    except:
        r = None

    # Failure
    if retry_count >= max_retries:
        cache.set(redis_key, '', timeout=60)
    else:
        # Retry
        worker.queue_work(priority, _do_lichess_api_call, redis_key, path, method, post_data, params, priority, max_retries, retry_count + 1)

    if r is not None and r.status_code == 429:
        # Too many requests
        time.sleep(60)
    else:
        time.sleep(2)

@csrf_exempt
def lichess_api_call(request, path):
    params = request.GET.dict()
    priority = int(params.pop('priority', 0))
    max_retries = int(params.pop('max_retries', 3))
    redis_key = get_random_string(length=16)
    worker.queue_work(priority, _do_lichess_api_call, redis_key, path, request.method, request.body, params, priority, max_retries)
    return HttpResponse(redis_key)

@csrf_exempt
def watch(request):
    game_ids = request.body.split(',')
    result = worker.watch_games(game_ids)
    return JsonResponse({'result': result})

@csrf_exempt
def watch_add(request):
    game_id = request.body
    worker.add_watch(game_id)
    return JsonResponse({'ok': True})
