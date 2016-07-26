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

@api_token_required
def find_pairing(request):
    try:
        season_id = request.GET.get('season', None)
        if season_id is not None:
            season_id = int(season_id)
        player = request.GET.get('player', None)
        white = request.GET.get('white', None)
        black = request.GET.get('black', None)
    except ValueError:
        return HttpResponse('Bad request', status=400)
    
    try:
        round_ = _get_latest_round(season_id)
    except IndexError:
        return JsonResponse({'pairing': None, 'error': 'no_data'})
    
    pairings = _get_pairings(round_, player, white, black, True)
    
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
        season_id = request.POST.get('season', None)
        if season_id is not None:
            season_id = int(season_id)
        white = request.POST.get('white', None)
        black = request.POST.get('black', None)
        game_link = request.POST.get('game_link', None)
        result = request.POST.get('result', None)
    except ValueError:
        return HttpResponse('Bad request', status=400)
    
    try:
        round_ = _get_latest_round(season_id)
    except IndexError:
        return JsonResponse({'updated': 0, 'error': 'no_data'})

    pairings = _get_pairings(round_, None, white, black, False)

    if len(pairings) == 0:
        return JsonResponse({'updated': 0, 'error': 'not_found'})
    if len(pairings) > 1:
        return JsonResponse({'updated': 0, 'error': 'ambiguous'})
    
    p = pairings[0]
    
    if game_link is not None:
        p.game_link = game_link
    if result is not None:
        p.result = result
    p.save()
    
    return JsonResponse({'updated': 1})

def _get_latest_round(season_id):
    if season_id is None:
        return Round.objects.order_by('-season__start_date', '-season__id', '-number')[0]
    else:
        return Round.objects.filter(season_id=season_id).order_by('-number')[0]

def _get_pairings(round_, player=None, white=None, black=None, color_fallback=False):
    pairings = Pairing.objects.filter(team_pairing__round=round_)
    if player is not None:
        pairings = pairings.filter(white__lichess_username__iexact=player) | pairings.filter(black__lichess_username__iexact=player)
    pairings_snapshot = pairings
    if white is not None:
        pairings = pairings.filter(white__lichess_username__iexact=white)
    if black is not None:
        pairings = pairings.filter(black__lichess_username__iexact=black)
    if color_fallback and len(pairings) == 0:
        pairings = pairings_snapshot
        if white is not None:
            pairings = pairings.filter(black__lichess_username__iexact=white)
        if black is not None:
            pairings = pairings.filter(white__lichess_username__iexact=black)
    return pairings

@api_token_required
def get_roster(request):
    try:
        league_tag = request.GET.get('league', None)
        season_id = request.GET.get('season', None)
        if season_id is not None:
            season_id = int(season_id)
    except ValueError:
        return HttpResponse('Bad request', status=400)
    
    try:
        seasons = Season.objects.order_by('-start_date', '-id')
        if league_tag is not None:
            seasons = seasons.filter(league__tag=league_tag)
        if season_id is not None:
            seasons = seasons.filter(pk=season_id)
        season = seasons[0]
    except IndexError:
        return JsonResponse({'pairing': None, 'error': 'no_data'})
    
    season_players = season.seasonplayer_set.all()
    teams = season.team_set.order_by('number').all()
    
    return JsonResponse({
        'players': [{
            'username': season_player.player.lichess_username,
            'rating': season_player.player.rating
        } for season_player in season_players],
        'teams': [{
            'name': team.name,
            'number': team.number,
            'players': [{
                'board_number': team_member.board_number,
                'username': team_member.player.lichess_username,
                'is_captain': team_member.is_captain
            } for team_member in team.teammember_set.order_by('board_number')]
        } for team in teams],
    })

