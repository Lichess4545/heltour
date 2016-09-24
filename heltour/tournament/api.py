from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import re
import json
from models import *
from django.utils.html import strip_tags
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST
from django.core.urlresolvers import reverse

# API methods expect an HTTP header in the form:
# Authorization: Token abc123
# where "abc123" is the secret token of an API key in the database

def require_api_token(view_func):
    def _wrapped_view_func(request, *args, **kwargs):
        if not 'HTTP_AUTHORIZATION' in request.META:
            return HttpResponse('Unauthorized', status=401)
        match = re.match('\s*Token\s*(\w+)\s*', request.META['HTTP_AUTHORIZATION'])
        if match is None or len(ApiKey.objects.filter(secret_token=match.group(1))) == 0:
            return HttpResponse('Unauthorized', status=401)
        return view_func(request, *args, **kwargs)
    return _wrapped_view_func

@require_GET
@require_api_token
def find_pairing(request):
    try:
        league_tag = request.GET.get('league', None)
        season_tag = request.GET.get('season', None)
        player = request.GET.get('player', None)
        white = request.GET.get('white', None)
        black = request.GET.get('black', None)
        scheduled = request.GET.get('scheduled', None)
        if scheduled == 'true':
            scheduled = True
        elif scheduled == 'false':
            scheduled = False
    except ValueError:
        return HttpResponse('Bad request', status=400)

    rounds = _get_active_rounds(league_tag, season_tag)
    if len(rounds) == 0:
        return JsonResponse({'pairings': None, 'error': 'no_matching_rounds'})

    pairings = []
    for r in rounds:
        pairings += list(_get_pairings(r, player, white, black, scheduled))

    if len(pairings) == 0:
        # Try alternate colors
        for r in rounds:
            pairings += list(_get_pairings(r, player, black, white, scheduled))

    return JsonResponse({'pairings': [_export_pairing(p) for p in pairings]})

def _export_pairing(p):
    if hasattr(p, 'teamplayerpairing'):
        return {
            'league': p.team_pairing.round.season.league.tag,
            'season': p.team_pairing.round.season.tag,
            'round': p.team_pairing.round.number,
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
            'datetime': p.scheduled_time,
        }
    else:
        return {
            'league': p.round.season.league.tag,
            'season': p.round.season.tag,
            'round': p.round.number,
            'white': p.white.lichess_username,
            'white_rating': p.white.rating,
            'black': p.black.lichess_username,
            'black_rating': p.black.rating,
            'game_link': p.game_link,
            'result': p.result,
            'datetime': p.scheduled_time,
        }

@csrf_exempt
@require_POST
@require_api_token
def update_pairing(request):
    try:
        league_tag = request.POST.get('league', None)
        season_tag = request.POST.get('season', None)
        white = request.POST.get('white', None)
        black = request.POST.get('black', None)
        game_link = request.POST.get('game_link', None)
        result = request.POST.get('result', None)
        datetime = request.POST.get('datetime', None)
        if datetime is not None:
            datetime = parse_datetime(datetime)
    except ValueError:
        return HttpResponse('Bad request', status=400)

    rounds = _get_active_rounds(league_tag, season_tag)
    if len(rounds) == 0:
        return JsonResponse({'updated': 0, 'error': 'no_matching_rounds'})

    pairings = []
    for r in rounds:
        pairings += _get_pairings(r, None, white, black)

    reversed = False
    if len(pairings) == 0:
        # Try alternate colors
        reversed = True
        for r in rounds:
            pairings += list(_get_pairings(r, None, black, white))

    if len(pairings) == 0:
        return JsonResponse({'updated': 0, 'error': 'not_found'})
    if len(pairings) > 1:
        return JsonResponse({'updated': 0, 'error': 'ambiguous'})

    pairing = pairings[0]

    if game_link is not None:
        pairing.game_link = game_link
    if result is not None:
        pairing.result = result
    if datetime is not None:
        pairing.scheduled_time = datetime
    pairing.save()

    return JsonResponse({'updated': 1, 'reversed': reversed})

def _get_active_rounds(league_tag, season_tag):
    rounds = Round.objects.filter(season__is_active=True, publish_pairings=True, is_completed=False).order_by('-season__start_date', '-season__id', '-number')
    if league_tag is not None:
        rounds = rounds.filter(season__league__tag=league_tag)
    if season_tag is not None:
        rounds = rounds.filter(season__tag=season_tag)
    return rounds

def _get_next_round(league_tag, season_tag, round_num):
    rounds = Round.objects.filter(season__is_active=True, is_completed=False).order_by('-season__start_date', '-season__id', 'number')
    if league_tag is not None:
        rounds = rounds.filter(season__league__tag=league_tag)
    if season_tag is not None:
        rounds = rounds.filter(season__tag=season_tag)
    next_round = rounds[0]
    season = next_round.season
    if round_num is None:
        return next_round
    else:
        return season.round_set.filter(number=round_num)[0]

def _get_pairings(round_, player=None, white=None, black=None, scheduled=None):
    pairings = _filter_pairings(TeamPlayerPairing.objects.filter(team_pairing__round=round_).nocache(), player, white, black, scheduled)
    pairings += _filter_pairings(LonePlayerPairing.objects.filter(round=round_).nocache(), player, white, black, scheduled)
    return pairings

def _filter_pairings(pairings, player=None, white=None, black=None, scheduled=None):
    if player is not None:
        white_pairings = pairings.filter(white__lichess_username__iexact=player)
        black_pairings = pairings.filter(black__lichess_username__iexact=player)
        pairings = white_pairings | black_pairings
    if white is not None:
        pairings = pairings.filter(white__lichess_username__iexact=white)
    if black is not None:
        pairings = pairings.filter(black__lichess_username__iexact=black)
    if scheduled == True:
        pairings = pairings.exclude(result='', scheduled_time=None)
    if scheduled == False:
        pairings = pairings.filter(result='', scheduled_time=None)
    return list(pairings)

@require_GET
@require_api_token
def get_roster(request):
    try:
        league_tag = request.GET.get('league', None)
        season_tag = request.GET.get('season', None)
    except ValueError:
        return HttpResponse('Bad request', status=400)

    try:
        seasons = Season.objects.order_by('-start_date', '-id')
        if league_tag is not None:
            seasons = seasons.filter(league__tag=league_tag)
        if season_tag is not None:
            seasons = seasons.filter(tag=season_tag)
        else:
            seasons = seasons.filter(is_active=True)

        season = seasons[0]
    except IndexError:
        return JsonResponse({'season_tag': None, 'players': None, 'teams': None, 'error': 'no_matching_rounds'})

    if season.league.competitor_type == 'team':
        return _team_roster(season)
    else:
        return _lone_roster(season)

def _team_roster(season):
    season_players = season.seasonplayer_set.select_related('player').nocache()
    teams = season.team_set.order_by('number').all()

    return JsonResponse({
        'league': season.league.tag,
        'season': season.tag,
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
            'usernames': [alt.season_player.player.lichess_username for alt in sorted(
                             Alternate.objects.filter(season_player__season=season, board_number=board_number),
                             key=lambda alt: alt.priority_date()
                         )]
        } for board_number in season.board_number_list()]
    })

def _lone_roster(season):
    season_players = season.seasonplayer_set.select_related('player').nocache()

    player_board = {}
    current_round = season.round_set.filter(publish_pairings=True, is_completed=False).first()
    if current_round is not None:
        for p in current_round.loneplayerpairing_set.all():
            player_board[p.white] = p.pairing_order
            player_board[p.black] = p.pairing_order

    return JsonResponse({
        'league': season.league.tag,
        'season': season.tag,
        'players': [{
            'username': season_player.player.lichess_username,
            'rating': season_player.player.rating,
            'board': player_board.get(season_player.player, None)
        } for season_player in season_players]
    })

@csrf_exempt
@require_POST
@require_api_token
def assign_alternate(request):
    try:
        league_tag = request.POST.get('league', None)
        season_tag = request.POST.get('season', None)
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

    if team_num is None or board_num is None or not player_name:
        return HttpResponse('Bad request', status=400)

    try:
        round_ = _get_next_round(league_tag, season_tag, round_num)
        season = round_.season
        team = season.team_set.filter(number=team_num)[0]
        player = Player.objects.filter(lichess_username__iexact=player_name).first()
    except IndexError:
        return JsonResponse({'updated': 0, 'error': 'no_matching_rounds'})

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
@require_POST
@require_api_token
def set_availability(request):
    try:
        league_tag = request.POST.get('league', None)
        season_tag = request.POST.get('season', None)
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
        round_ = _get_next_round(league_tag, season_tag, round_num)
        player = Player.objects.filter(lichess_username__iexact=player_name).first()
    except IndexError:
        return JsonResponse({'updated': 0, 'error': 'no_matching_rounds'})

    if player is None:
        return JsonResponse({'updated': 0, 'error': 'player_not_found'})

    if round_.is_completed:
        return JsonResponse({'updated': 0, 'error': 'round_over'})

    PlayerAvailability.objects.update_or_create(round=round_, player=player, defaults={'is_available': is_available})

    return JsonResponse({'updated': 1})

@require_GET
@require_api_token
def get_league_moderators(request):
    try:
        league_tag = request.GET.get('league', None)
    except ValueError:
        return HttpResponse('Bad request', status=400)

    if not league_tag:
        return HttpResponse('Bad request', status=400)

    moderator_names = [lm.player.lichess_username for lm in LeagueModerator.objects.filter(league__tag=league_tag)]

    return JsonResponse({'moderators': moderator_names})

@require_GET
@require_api_token
def league_document(request):
    try:
        league_tag = request.GET.get('league', None)
        type_ = request.GET.get('type', None)
        strip_html = request.GET.get('strip_html', None) == 'true'
    except ValueError:
        return HttpResponse('Bad request', status=400)

    if not league_tag or not type_:
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

@require_GET
@require_api_token
def get_private_url(request):
    try:
        league_tag = request.GET.get('league', None)
        season_tag = request.GET.get('season', None)
        page = request.GET.get('page', None)
        user = request.GET.get('user', None)
    except ValueError:
        return HttpResponse('Bad request', status=400)

    if not user:
        return HttpResponse('Bad request', status=400)

    if page == 'nominate':
        if not league_tag:
            return HttpResponse('Bad request', status=400)

        auth = PrivateUrlAuth.objects.create(authenticated_user=user, expires=timezone.now() + timedelta(hours=1))
        if not season_tag:
            url = reverse('by_league:nominate_with_token', args=[league_tag, auth.secret_token])
        else:
            url = reverse('by_league:by_season:nominate', args=[league_tag, season_tag, auth.secret_token])
        url = request.build_absolute_uri(url)

        return JsonResponse({'url': url, 'expires': auth.expires})

    if page == 'schedule':
        if not league_tag:
            return HttpResponse('Bad request', status=400)

        auth = PrivateUrlAuth.objects.create(authenticated_user=user, expires=timezone.now() + timedelta(hours=1))
        url = reverse('by_league:edit_schedule_with_token', args=[league_tag, auth.secret_token])
        url = request.build_absolute_uri(url)

        return JsonResponse({'url': url, 'expires': auth.expires})

    return JsonResponse({'url': None, 'expires': None, 'error': 'invalid_page'})

@csrf_exempt
@require_POST
@require_api_token
def player_joined_slack(request):
    try:
        name = request.POST.get('name', None)
    except ValueError:
        return HttpResponse('Bad request', status=400)

    if not name:
        return HttpResponse('Bad request', status=400)
    try:
        player = Player.objects.get(lichess_username__iexact=name)
    except Player.DoesNotExist:
        return JsonResponse({'updated': 0, 'error': 'not_found'})

    player.in_slack_group = True
    player.save()

    return JsonResponse({'updated': 1})
