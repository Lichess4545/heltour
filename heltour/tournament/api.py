from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import re
import json
from models import *
from django.utils.html import strip_tags

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

    team_player_pairing = pairings[0]
    player_pairing = team_player_pairing.player_pairing

    return JsonResponse({'pairing': {
        'season_id': team_player_pairing.team_pairing.round.season.id,
        'white_team': team_player_pairing.white_team().name,
        'white_team_number': team_player_pairing.white_team().number,
        'black_team': team_player_pairing.black_team().name,
        'black_team_number': team_player_pairing.black_team().number,
        'white': player_pairing.white.lichess_username,
        'white_rating': player_pairing.white.rating,
        'black': player_pairing.black.lichess_username,
        'black_rating': player_pairing.black.rating,
        'game_link': player_pairing.game_link,
        'result': player_pairing.result,
        'datetime': player_pairing.scheduled_time,
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

    team_player_pairing = pairings[0]
    player_pairing = team_player_pairing.player_pairing

    if game_link is not None:
        player_pairing.game_link = game_link
    if result is not None:
        player_pairing.result = result
    player_pairing.save()

    return JsonResponse({'updated': 1})

def _get_latest_round(season_id):
    if season_id is None:
        return Round.objects.filter(publish_pairings=True, is_completed=False).order_by('-season__start_date', '-season__id', '-number')[0]
    else:
        return Round.objects.filter(season_id=season_id, publish_pairings=True, is_completed=False).order_by('-number')[0]

def _get_pairings(round_, player=None, white=None, black=None, color_fallback=False):
    pairings = TeamPlayerPairing.objects.filter(team_pairing__round=round_)
    if player is not None:
        pairings = pairings.filter(player_pairing__white__lichess_username__iexact=player) | pairings.filter(player_pairing__black__lichess_username__iexact=player)
    pairings_snapshot = pairings
    if white is not None:
        pairings = pairings.filter(player_pairing__white__lichess_username__iexact=white)
    if black is not None:
        pairings = pairings.filter(player_pairing__black__lichess_username__iexact=black)
    if color_fallback and len(pairings) == 0:
        pairings = pairings_snapshot
        if white is not None:
            pairings = pairings.filter(player_pairing__black__lichess_username__iexact=white)
        if black is not None:
            pairings = pairings.filter(player_pairing__white__lichess_username__iexact=black)
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
        else:
            seasons = seasons.filter(is_active=True)

        season = seasons[0]
    except IndexError:
        return JsonResponse({'season_id': None, 'players': None, 'teams': None, 'error': 'no_data'})

    season_players = season.seasonplayer_set.all()
    teams = season.team_set.order_by('number').all()

    return JsonResponse({
        'season_id': season.pk,
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
        'alternates': [{
            'board_number': board_number,
            'usernames': [alt.season_player.player.lichess_username for alt in sorted(Alternate.objects.filter(season_player__season=season, board_number=board_number), key=lambda alt: alt.priority_date())]
        } for board_number in season.board_number_list()]
    })

@csrf_exempt
@api_token_required
def assign_alternate(request):
    try:
        season_id = request.POST.get('season', None)
        if season_id is not None:
            season_id = int(season_id)
        round_num = request.POST.get('round', None)
        if round_num is not None:
            round_num = int(round_num)
        team_num = request.POST.get('team', None)
        if team_num is not None:
            team_num = int(team_num)
        board_num = request.POST.get('board', None)
        if board_num is not None:
            board_num = int(board_num)
        player_name = request.POST.get('player', None)
    except ValueError:
        return HttpResponse('Bad request', status=400)

    if team_num is None or board_num is None or player_name is None:
        return HttpResponse('Bad request', status=400)

    try:
        latest_round = _get_latest_round(season_id)
        season = latest_round.season
        if round_num is None:
            round_ = latest_round
        else:
            round_ = season.round_set.filter(number=round_num)[0]
        team = season.team_set.filter(number=team_num)[0]
        player = Player.objects.filter(lichess_username__iexact=player_name).first()
    except IndexError:
        return JsonResponse({'updated': 0, 'error': 'no_data'})

    if player is None:
        return JsonResponse({'updated': 0, 'error': 'player_not_found'})

    if round_.is_completed:
        return JsonResponse({'updated': 0, 'error': 'round_over'})

    alternate = Alternate.objects.filter(season_player__season=season, season_player__player=player, board_number=board_num).first()
    member_playing_up = team.teammember_set.filter(player=player, board_number__gte=board_num).first()
    if alternate is None and member_playing_up is None:
        return JsonResponse({'updated': 0, 'error': 'not_an_alternate'})

    AlternateAssignment.objects.update_or_create(round=round_, team=team, board_number=board_num, defaults={'player': player})

    return JsonResponse({'updated': 1})

@csrf_exempt
@api_token_required
def set_availability(request):
    try:
        season_id = request.POST.get('season', None)
        if season_id is not None:
            season_id = int(season_id)
        round_num = request.POST.get('round', None)
        if round_num is not None:
            round_num = int(round_num)
        player_name = request.POST.get('player', None)
        is_available = request.POST.get('available', None)
        if is_available == 'true':
            is_available = True
        elif is_available == 'false':
            is_available = False
        else:
            raise ValueError
    except ValueError:
        return HttpResponse('Bad request', status=400)

    try:
        latest_round = _get_latest_round(season_id)
        season = latest_round.season
        if round_num is None:
            round_ = latest_round
        else:
            round_ = season.round_set.filter(number=round_num)[0]
        player = Player.objects.filter(lichess_username__iexact=player_name).first()
    except IndexError:
        return JsonResponse({'updated': 0, 'error': 'no_data'})

    if player is None:
        return JsonResponse({'updated': 0, 'error': 'player_not_found'})

    if round_.is_completed:
        return JsonResponse({'updated': 0, 'error': 'round_over'})

    PlayerAvailability.objects.update_or_create(round=round_, player=player, defaults={'is_available': is_available})

    return JsonResponse({'updated': 1})

@api_token_required
def league_document(request):
    try:
        league_tag = request.GET.get('league', None)
        type_ = request.GET.get('type', None)
        strip_html = request.GET.get('strip_html', None) == 'true'
    except ValueError:
        return HttpResponse('Bad request', status=400)
    
    if league_tag is None or type_ is None:
        return HttpResponse('Bad request', status=400)
    
    league_doc = LeagueDocument.objects.filter(league__tag=league_tag, type=type_).first()
    if league_doc is None:
        return JsonResponse({'name': None, 'content': None, 'error': 'not_found'})
    
    document = league_doc.document
    content = document.content
    if strip_html:
        content = strip_tags(content)
    
    return JsonResponse({
         'name': document.name,
         'content': content
     })
