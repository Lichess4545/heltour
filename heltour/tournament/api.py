from django.http import HttpResponse, JsonResponse
import re
from models import *

def api_token_required(view_func):
    def _wrapped_view_func(request, *args, **kwargs):
        if not 'HTTP_AUTHORIZATION' in request.META:
            return HttpResponse('Unauthorized', status=401)
        match = re.match('\s*Token\s*(\w+)\s*', request.META['HTTP_AUTHORIZATION'])
        if match is None or len(ApiKey.objects.filter(secret_token=match.group(1))) == 0:
            return HttpResponse('Unauthorized', status=401)
        return view_func(request, *args, **kwargs)     
    return _wrapped_view_func

@api_token_required
def find_pairing_by_player(request, player):
    try:
        most_recent_round = Round.objects.order_by('-season__start_date', '-season__id', '-number')[0]
    except IndexError:
        return JsonResponse({'pairing': None, 'error': 'no_data'})
    return _find_pairing_by_player(most_recent_round, player)

@api_token_required
def find_pairing_by_season_player(request, season_id, player):
    try:
        most_recent_round = Round.objects.filter(season_id=season_id).order_by('-number')[0]
    except IndexError:
        return JsonResponse({'pairing': None, 'error': 'no_data'})
    return _find_pairing_by_player(most_recent_round, player)

def _find_pairing_by_player(round_, player):
    pairings = Pairing.objects.filter(team_pairing__round=round_, white__lichess_username__iexact=player)
    pairings |= Pairing.objects.filter(team_pairing__round=round_, black__lichess_username__iexact=player)
    return _find_pairing_result(pairings)

@api_token_required
def find_pairing_by_white_black(request, white, black):
    try:
        most_recent_round = Round.objects.order_by('-season__start_date', '-season__id', '-number')[0]
    except IndexError:
        return JsonResponse({'pairing': None, 'error': 'no_data'})
    return _find_pairing_by_white_black(most_recent_round, white, black)

@api_token_required
def find_pairing_by_season_white_black(request, season_id, white, black):
    try:
        most_recent_round = Round.objects.filter(season_id=season_id).order_by('-number')[0]
    except IndexError:
        return JsonResponse({'pairing': None, 'error': 'no_data'})
    return _find_pairing_by_white_black(most_recent_round, white, black)

def _find_pairing_by_white_black(round_, white, black):
    pairings = Pairing.objects.filter(team_pairing__round=round_, white__lichess_username__iexact=white, black__lichess_username__iexact=black)
    if len(pairings) == 0:
        # Try switching colors as a fallback
        pairings = Pairing.objects.filter(team_pairing__round=round_, white__lichess_username__iexact=black, black__lichess_username__iexact=white)
    return _find_pairing_result(pairings)

def _find_pairing_result(pairings):
    if len(pairings) == 0:
        return JsonResponse({'pairing': None, 'error': 'not_found'})
    if len(pairings) > 1:
        return JsonResponse({'pairing': None, 'error': 'ambiguous'})
    p = pairings[0]
    return JsonResponse({'pairing': {
        'season_id': p.team_pairing.round.season.id,
        'white_team': p.team_pairing.white_team.name if p.board_number % 2 == 1 else p.team_pairing.black_team.name,
        'white_team_number': p.team_pairing.white_team.number if p.board_number % 2 == 1 else p.team_pairing.black_team.number,
        'black_team': p.team_pairing.black_team.name if p.board_number % 2 == 1 else p.team_pairing.white_team.name,
        'black_team_number': p.team_pairing.black_team.number if p.board_number % 2 == 1 else p.team_pairing.white_team.number,
        'white': p.white.lichess_username,
        'white_rating': p.white.rating,
        'black': p.black.lichess_username,
        'black_rating': p.black.rating,
        'game_link': p.game_link,
        'result': p.result,
        'datetime': p.date_played,
    }})

@api_token_required
def update_pairing(request, season_id, white, black):
    return HttpResponse(white)
