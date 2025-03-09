from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
import re
import json
import reversion
from .models import *
from django.utils.html import strip_tags
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST
from django.urls import reverse
from heltour.tournament import uptime


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

    league = League.objects.filter(tag=league_tag).first()
    return JsonResponse({'pairings': [_export_pairing(p, league) for p in pairings]})


def _export_pairing(p, league):
    if isinstance(p, TeamPlayerPairing):
        return {
            'league': p.team_pairing.round.season.league.tag,
            'season': p.team_pairing.round.season.tag,
            'round': p.team_pairing.round.number,
            'white_team': p.white_team().name,
            'white_team_number': p.white_team().number,
            'black_team': p.black_team().name,
            'black_team_number': p.black_team().number,
            'white': p.white.lichess_username,
            'white_rating': p.white_rating_display(league),
            'black': p.black.lichess_username,
            'black_rating': p.black_rating_display(league),
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
            'white_rating': p.white_rating_display(league),
            'black': p.black.lichess_username,
            'black_rating': p.black_rating_display(league),
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
    initial_game_link = pairing.game_link
    initial_result = pairing.result

    if game_link is not None:
        pairing.game_link = game_link
    if result is not None:
        pairing.result = result
    if datetime is not None:
        pairing.scheduled_time = datetime

    with reversion.create_revision():
        reversion.set_comment('API: update_pairing')
        pairing.save()

    return JsonResponse({'updated': 1, 'reversed': reversed,
                         'white': pairing.white.lichess_username,
                         'black': pairing.black.lichess_username,
                         'game_link_changed': initial_game_link != pairing.game_link,
                         'result_changed': initial_result != pairing.result})


def _get_active_rounds(league_tag, season_tag):
    rounds = Round.objects.filter(season__is_active=True, publish_pairings=True,
                                  is_completed=False).order_by('-season__start_date', '-season__id',
                                                               '-number')
    if league_tag is not None:
        rounds = rounds.filter(season__league__tag=league_tag)
    if season_tag is not None:
        rounds = rounds.filter(season__tag=season_tag)
    return rounds


def _get_next_round(league_tag, season_tag, round_num):
    rounds = Round.objects.filter(season__is_active=True, is_completed=False).order_by(
        '-season__start_date', '-season__id', 'number')
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
    pairings = _filter_pairings(TeamPlayerPairing.objects.filter(team_pairing__round=round_)
                                .select_related('white', 'black',
                                                'team_pairing__round__season__league',
                                                'team_pairing__white_team',
                                                'team_pairing__black_team')
                                .nocache(),
                                player, white, black, scheduled)
    pairings += _filter_pairings(LonePlayerPairing.objects.filter(round=round_)
                                 .select_related('white', 'black', 'round__season__league')
                                 .nocache(),
                                 player, white, black, scheduled)
    return pairings


def _filter_pairings(pairings, player=None, white=None, black=None, scheduled=None):
    pairings = pairings.exclude(white=None).exclude(black=None)
    if player is not None:
        white_pairings = pairings.filter(white__lichess_username__iexact=player)
        black_pairings = pairings.filter(black__lichess_username__iexact=player)
        pairings = white_pairings | black_pairings
    if white is not None:
        pairings = pairings.filter(white__lichess_username__iexact=white) | pairings.filter(
            white__slack_user_id__iexact=white)
    if black is not None:
        pairings = pairings.filter(black__lichess_username__iexact=black) | pairings.filter(
            black__slack_user_id__iexact=black)
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
        return JsonResponse(
            {'season_tag': None, 'players': None, 'teams': None, 'error': 'no_matching_rounds'})

    if season.league.is_team_league():
        return _team_roster(season)
    else:
        return _lone_roster(season)


def _team_roster(season):
    league = season.league
    teams = season.team_set.order_by('number').all()

    all_alternates = sorted(Alternate.objects.filter(season_player__season=season).select_related(
        'season_player__player', 'season_player__registration').nocache(),
                            key=lambda alt: alt.priority_date())
    all_teammembers = TeamMember.objects.filter(team__season=season).select_related(
        'player').order_by('board_number').nocache()
    players = sorted({alt.season_player.player for alt in all_alternates} | {tm.player for tm in
                                                                             all_teammembers})

    return JsonResponse({
        'league': season.league.tag,
        'season': season.tag,
        'players': [{
            'username': player.lichess_username,
            'rating': player.rating_for(league)
        } for player in players],
        'teams': [{
            'name': team.name,
            'number': team.number,
            'slack_channel': team.slack_channel,
            'players': [{
                'board_number': team_member.board_number,
                'username': team_member.player.lichess_username,
                'is_captain': team_member.is_captain
            } for team_member in all_teammembers if team_member.team_id == team.pk]
        } for team in teams],
        'alternates': [{
            'board_number': board_number,
            'usernames': [alt.season_player.player.lichess_username for alt in all_alternates if
                          alt.board_number == board_number]
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
            'rating': season_player.player.rating_for(season.league),
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

    alternate = Alternate.objects.filter(season_player__season=season, season_player__player=player,
                                         board_number=board_num).first()
    member_playing_up = team.teammember_set.filter(player=player,
                                                   board_number__gte=board_num).first()
    if alternate is None and member_playing_up is None:
        return JsonResponse({'updated': 0, 'error': 'not_an_alternate'})

    AlternateAssignment.objects.update_or_create(round=round_, team=team, board_number=board_num,
                                                 defaults={'player': player,
                                                           'replaced_player': None})

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
        season_player = SeasonPlayer.objects.filter(player=player, season=round_.season).first()
    except IndexError:
        return JsonResponse({'updated': 0, 'error': 'no_matching_rounds'})

    if player is None:
        return JsonResponse({'updated': 0, 'error': 'player_not_found'})

    if round_.is_completed:
        return JsonResponse({'updated': 0, 'error': 'round_over'})
    
    if season_player.card_color == "red":
        return JsonResponse({'updated': 0, 'error': 'player_red_card'})
    
    if season_player.has_scheduled_game_in_round(round_):
        return JsonResponse({'updated': 0, 'error': 'scheduled_game'})

    PlayerAvailability.objects.update_or_create(round=round_, player=player,
                                                defaults={'is_available': is_available})

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

    moderator_names = [lm.player.lichess_username for lm in
                       LeagueModerator.objects.filter(league__tag=league_tag, is_active=True)]

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
def link_slack(request):
    try:
        user_id = request.GET.get('user_id', None)
        display_name = request.GET.get('display_name', None)
    except ValueError:
        return HttpResponse('Bad request', status=400)

    if not user_id:
        return HttpResponse('Bad request', status=400)

    token = LoginToken.objects.create(slack_user_id=user_id, username_hint=display_name,
                                      expires=timezone.now() + timedelta(days=30))
    league = League.objects.filter(is_default=True).first()
    sp = SeasonPlayer.objects.filter(player__lichess_username__iexact=display_name).order_by(
        '-season__start_date').first()
    if sp:
        league = sp.season.league
    url = reverse('by_league:login_with_token', args=[league.tag, token.secret_token])
    url = request.build_absolute_uri(url)

    already_linked = [p.lichess_username for p in Player.objects.filter(slack_user_id=user_id)]

    return JsonResponse({'url': url, 'already_linked': already_linked, 'expires': token.expires})


@require_GET
@require_api_token
def get_slack_user_map(request):
    users = {p.lichess_username: p.slack_user_id for p in Player.objects.exclude(slack_user_id='')}
    return JsonResponse({'users': users})


@csrf_exempt
@require_POST
@require_api_token
def player_contact(request):
    try:
        sender = request.POST.get('sender', None)
        recip = request.POST.get('recip', None)
    except ValueError:
        return HttpResponse('Bad request', status=400)

    if not sender or not recip:
        return HttpResponse('Bad request', status=400)

    rounds = _get_active_rounds(None, None)
    updated = 0
    time = timezone.now()
    for r in rounds:
        pairings = r.pairings.filter(white__lichess_username__iexact=sender,
                                     black__lichess_username__iexact=recip) | \
                   r.pairings.filter(white__lichess_username__iexact=recip,
                                     black__lichess_username__iexact=sender)
        for p in pairings:
            presence = p.get_player_presence(Player.objects.get(lichess_username__iexact=sender))
            if not presence.first_msg_time:
                presence.first_msg_time = time
            presence.last_msg_time = time
            presence.save()
            updated += 1

    return JsonResponse({'updated': updated})


@csrf_exempt
@require_POST
@require_api_token
def game_warning(request):
    try:
        league_tag = request.POST.get('league', None)
        season_tag = request.POST.get('season', None)
        white = request.POST.get('white', None)
        black = request.POST.get('black', None)
        reason = request.POST.get('reason', None)
    except ValueError:
        return HttpResponse('Bad request', status=400)

    rounds = _get_active_rounds(league_tag, season_tag)
    if len(rounds) == 0:
        return JsonResponse({'updated': 0, 'error': 'no_matching_rounds'})

    pairings = []
    for r in rounds:
        pairings += _get_pairings(r, None, white, black)

    if len(pairings) == 0:
        # Try alternate colors
        for r in rounds:
            pairings += list(_get_pairings(r, None, black, white))

    if len(pairings) == 0:
        return JsonResponse({'updated': 0, 'error': 'not_found'})
    if len(pairings) > 1:
        return JsonResponse({'updated': 0, 'error': 'ambiguous'})

    signals.game_warning.send(sender=game_warning, pairing=pairings[0], warning=reason)

    return JsonResponse({'updated': 1})


@require_GET
def get_season_games(request):
    # No API token required - this one is public
    league_tag = request.GET.get('league', None)
    season_tag = request.GET.get('season', None)
    include_unplayed = request.GET.get('include_unplayed', False)

    if not league_tag:
        return HttpResponse('Bad request: league required', status=400)
    if not season_tag:
        return HttpResponse('Bad request: season required', status=400)

    games = []

    seasons = Season.objects.order_by('-start_date', '-id')
    if league_tag is not None:
        seasons = seasons.filter(league__tag=league_tag)
    if season_tag is not None:
        seasons = seasons.filter(tag=season_tag)
    else:
        seasons = seasons.filter(is_active=True)

    for s in seasons:
        for p in s.pairings.select_related('white', 'black',
                                           'teamplayerpairing__team_pairing__round',
                                           'teamplayerpairing__team_pairing__white_team',
                                           'teamplayerpairing__team_pairing__black_team'):
            game_id = get_gameid_from_gamelink(p.game_link)
            if game_id or include_unplayed:
                r = p.get_round()
                g = {
                    'league': s.league.name,
                    'season': s.name,
                    'round': r.number if r else None,
                    'game_id': game_id,
                    'white': p.white.lichess_username if p.white else None,
                    'black': p.black.lichess_username if p.black else None,
                    'result': p.result
                }
                if hasattr(p, 'teamplayerpairing'):
                    g.update({
                        'white_team': p.teamplayerpairing.white_team().name,
                        'black_team': p.teamplayerpairing.black_team().name
                    })
                games.append(g)

    return JsonResponse({'games': games})


@require_GET
def celery_up(request):
    # no API token required – public for now
    status = 'up'
    if uptime.celery.is_down:
        status = 'down'
    return JsonResponse({'celery_status': status})
