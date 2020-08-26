import logging
import requests
import time
from . import worker
from django.core.cache import cache
from django.http.response import HttpResponse, JsonResponse
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

logger = logging.getLogger(__name__)

def _get_lichess_api_token():
    try:
        with open(settings.LICHESS_API_TOKEN_FILE_PATH) as fin:
            return fin.read().strip()
    except IOError:
        return None

def _do_lichess_api_call(redis_key, path, method, post_data, params, priority, max_retries, format,
                         retry_count=0):
    url = "https://lichess.org/%s" % path
    token = _get_lichess_api_token()

    logger.info('API call: %s' % url)

    try:
        headers = {}
        if token:
            headers['Authorization'] = 'Bearer %s' % token
        if format:
            headers['Accept'] = format
        if method == 'POST':
            r = requests.post(url, params=params, data=post_data, headers=headers)
        else:
            r = requests.get(url, params, headers=headers)

        if r.status_code == 429:
            logger.info('API 429, sleeping for a minute')
            time.sleep(60) # Abide by the API rules

        if r.status_code >= 400 and r.status_code <= 500:
            logger.info('API Client Error[url:%s]: %s: %s', url, r.status_code, r.text)
            cache.set(redis_key, f'CLIENT-ERROR: {r.text}', timeout=60)
            time.sleep(2)
            return

        if r.status_code == 200:
            # Success
            logger.info('API success')
            cache.set(redis_key, r.text, timeout=60)
            time.sleep(2)
            return

        logger.warning('API status code %s: %s' % (r.status_code, r.text))

    except Exception as e:
        logger.error('API unexpected error %s: %s' % (path, e))
        r = None

    # Failure
    if retry_count >= max_retries:
        logger.error('API exceeded maximum retries for %s' % path)
        cache.set(redis_key, '', timeout=60)
    else:
        # Retry
        logger.warning('API queuing retry for %s' % path)
        worker.queue_work(priority, _do_lichess_api_call, redis_key, path, method, post_data,
                          params, priority, max_retries, format, retry_count + 1)

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
    format = params.pop('format', None)
    redis_key = get_random_string(length=16)

    # support either a form encoded body or a raw body
    post_data = request.POST.dict()
    if len(post_data) == 0:
        post_data = request.body.decode('utf-8')

    worker.queue_work(priority, _do_lichess_api_call, redis_key, path, request.method,
                      post_data, params, priority, max_retries, format)
    return HttpResponse(redis_key)


@csrf_exempt
def watch(request):
    game_ids = request.body.decode('utf-8').split(',')
    result = worker.watch_games(game_ids)
    return JsonResponse({'result': result})


@csrf_exempt
def watch_add(request):
    game_id = request.body.decode('utf-8')
    worker.add_watch(game_id)
    return JsonResponse({'ok': True})
