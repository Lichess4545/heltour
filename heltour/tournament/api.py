from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import re
import json
from models import *

# API methods expect an HTTP header in the form:
# Authorization: Token abc123
# where "abc123" is the secret token of an API key in the database

def api_token_required(view_func):
    def _wrapped_view_func(request, *args, **kwargs):
        if not 'HTTP_AUTHORIZATION' in request.META:
            return HttpResponse('Unauthorized', status=401)
        match = re.match('\s*Token\s*(\w+)\s*', request.META['HTTP_AUTHORIZATION'])
        if match is None or len(ApiKey.objects.filter(secret_token=match.group(1))) == 0:
            return HttpResponse('Unauthorized', status=401)
        return view_func(request, *args, **kwargs)     
    return _wrapped_view_func

def _get_latest_round(season_id):
    if season_id is None:
        return Round.objects.order_by('-season__start_date', '-season__id', '-number')[0]
    else:
        return Round.objects.filter(season_id=season_id).order_by('-number')[0]

def _get_pairings(round_, player=None, white=None, black=None):
    pairings = Pairing.objects.filter(team_pairing__round=round_)
    if player is not None:
        pairings = pairings.filter(white__lichess_username__iexact=player) | pairings.filter(black__lichess_username__iexact=player)
    pairings_snapshot = pairings
    if white is not None:
        pairings = pairings.filter(white__lichess_username__iexact=white)
    if black is not None:
        pairings = pairings.filter(black__lichess_username__iexact=black)
    # Try switching colors as a fallback
    if len(pairings) == 0:
        pairings = pairings_snapshot
        if white is not None:
            pairings = pairings.filter(black__lichess_username__iexact=white)
        if black is not None:
            pairings = pairings.filter(white__lichess_username__iexact=black)
    return pairings

@api_token_required
def find_pairing(request):
    try:
        player = request.GET.get('player', None)
        white = request.GET.get('white', None)
        black = request.GET.get('black', None)
        season_id = int(request.GET.get('season', None))
    except ValueError:
        return HttpResponse('Bad request', status=400)
    
    try:
        round_ = _get_latest_round(season_id)
    except IndexError:
        return JsonResponse({'pairing': None, 'error': 'no_data'})
    
    pairings = _get_pairings(round_, player, white, black)
    
    if len(pairings) == 0:
        return JsonResponse({'pairing': None, 'error': 'not_found'})
    if len(pairings) > 1:
        return JsonResponse({'pairing': None, 'error': 'ambiguous'})
    
    p = pairings[0]
    
    return JsonResponse({'pairing': {
        'season_id': p.team_pairing.round.season.id,
        'white_team': p.white_team().name,
        'white_team_number': p.white_team().number,
        'black_team': p.black_team().name,
        'black_team_number': p.black_team().number,
        'white': p.white.lichess_username,
        'white_rating': p.white.rating,
        'black': p.black.lichess_username,
        'black_rating': p.black.rating,
        'game_link': p.game_link,
        'result': p.result,
        'datetime': p.date_played,
    }})

@csrf_exempt
@api_token_required
def update_pairing(request):
    try:
        player = request.GET.get('player', None)
        white = request.GET.get('white', None)
        black = request.GET.get('black', None)
        season_id = int(request.GET.get('season', None))
        data = json.loads(request.body)
    except ValueError:
        return HttpResponse('Bad request', status=400)
    
    try:
        round_ = _get_latest_round(season_id)
    except IndexError:
        return JsonResponse({'updated': 0, 'error': 'no_data'})

    pairings = _get_pairings(round_, player, white, black)

    if len(pairings) == 0:
        return JsonResponse({'updated': 0, 'error': 'not_found'})
    if len(pairings) > 1:
        return JsonResponse({'updated': 0, 'error': 'ambiguous'})
    
    p = pairings[0]
    
    if 'game_link' in data:
        p.game_link = data['game_link']
    if 'result' in data:
        p.result = data['result']
    p.save()
    
    return JsonResponse({'updated': 1})
