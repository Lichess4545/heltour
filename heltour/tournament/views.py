from django.shortcuts import get_object_or_404, render, redirect
from django.http.response import Http404
from django.utils import timezone
from datetime import timedelta
from .models import *
from .forms import *
from heltour.tournament.templatetags.tournament_extras import leagueurl
import itertools
from django.db.models.query import Prefetch
from django.contrib.admin.views.decorators import staff_member_required
from collections import defaultdict
from decorators import cached_as, cached_view_as
import re

common_team_models = [League, Season, Round, Team]
common_lone_models = [League, Season, Round, LonePlayerScore, LonePlayerPairing, PlayerPairing, PlayerBye, SeasonPlayer,
                      Player, SeasonPrize, SeasonPrizeWinner]

def home(request):
    leagues = League.objects.filter(is_active=True).order_by('display_order')

    context = {
        'leagues': leagues,
    }
    return render(request, 'tournament/home.html', context)

def league_home(request, league_tag=None, season_tag=None):
    league = _get_league(league_tag)
    if league.competitor_type == 'team':
        return team_league_home(request, league_tag, season_tag)
    else:
        return lone_league_home(request, league_tag, season_tag)

def team_league_home(request, league_tag=None, season_tag=None):
    league = _get_league(league_tag)
    other_leagues = League.objects.filter(is_active=True).exclude(pk=league.pk).order_by('display_order')

    rules_doc = LeagueDocument.objects.filter(league=league, type='rules').first()
    rules_doc_tag = rules_doc.tag if rules_doc is not None else None
    intro_doc = LeagueDocument.objects.filter(league=league, type='intro').first()

    current_season = _get_default_season(league_tag, allow_none=True)
    if current_season is None:
        context = {
            'league_tag': league_tag,
            'league': league,
            'season_tag': season_tag,
            'rules_doc_tag': rules_doc_tag,
            'intro_doc': intro_doc,
            'can_edit_document': request.user.has_perm('tournament.change_document'),
            'other_leagues': other_leagues,
        }
        return render(request, 'tournament/team_league_home.html', context)

    season_list = Season.objects.filter(league=_get_league(league_tag)).order_by('-start_date', '-id').exclude(pk=current_season.pk)
    registration_season = Season.objects.filter(league=league, registration_open=True).order_by('-start_date').first()

    team_scores = list(enumerate(sorted(TeamScore.objects.filter(team__season=current_season), reverse=True)[:5], 1))

    # TODO: Use the lichess api to check the game status and remove games even if a game link hasn't been posted yet
    # TODO: Convert game times to the user's local time (maybe in JS?)
    current_game_time_min = timezone.now() - timedelta(hours=3)
    current_game_time_max = timezone.now() + timedelta(minutes=5)
    current_games = PlayerPairing.objects.filter(result='', scheduled_time__gt=current_game_time_min, scheduled_time__lt=current_game_time_max) \
                                         .exclude(game_link='').order_by('scheduled_time')
    upcoming_game_time_min = timezone.now() - timedelta(minutes=5)
    upcoming_game_time_max = timezone.now() + timedelta(hours=12)
    upcoming_games = PlayerPairing.objects.filter(game_link='', result='', scheduled_time__gt=upcoming_game_time_min, scheduled_time__lt=upcoming_game_time_max) \
                                          .order_by('scheduled_time')

    context = {
        'league_tag': league_tag,
        'league': league,
        'season_tag': season_tag,
        'season': current_season,
        'team_scores': team_scores,
        'season_list': season_list,
        'rules_doc_tag': rules_doc_tag,
        'intro_doc': intro_doc,
        'can_edit_document': request.user.has_perm('tournament.change_document'),
        'registration_season': registration_season,
        'current_games': current_games,
        'upcoming_games': upcoming_games,
        'other_leagues': other_leagues,
    }
    return render(request, 'tournament/team_league_home.html', context)

def lone_league_home(request, league_tag=None, season_tag=None):
    league = _get_league(league_tag)
    other_leagues = League.objects.filter(is_active=True).exclude(pk=league.pk).order_by('display_order')

    rules_doc = LeagueDocument.objects.filter(league=league, type='rules').first()
    rules_doc_tag = rules_doc.tag if rules_doc is not None else None
    intro_doc = LeagueDocument.objects.filter(league=league, type='intro').first()

    current_season = _get_default_season(league_tag, allow_none=True)
    if current_season is None:
        context = {
            'league_tag': league_tag,
            'league': league,
            'season_tag': season_tag,
            'rules_doc_tag': rules_doc_tag,
            'intro_doc': intro_doc,
            'can_edit_document': request.user.has_perm('tournament.change_document'),
            'other_leagues': other_leagues,
        }
        return render(request, 'tournament/lone_league_home.html', context)

    season_list = Season.objects.filter(league=_get_league(league_tag)).order_by('-start_date', '-id').exclude(pk=current_season.pk)
    registration_season = Season.objects.filter(league=league, registration_open=True).order_by('-start_date').first()

    player_scores = _lone_player_scores(current_season, final=True)[:5]

    if current_season.is_completed:
        prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season=current_season)
        player_highlights = _get_player_highlights(prize_winners)
    else:
        player_highlights = []

    # TODO: Use the lichess api to check the game status and remove games even if a game link hasn't been posted yet
    # TODO: Convert game times to the user's local time (maybe in JS?)
    current_game_time_min = timezone.now() - timedelta(hours=3)
    current_game_time_max = timezone.now() + timedelta(minutes=5)
    current_games = PlayerPairing.objects.filter(result='', scheduled_time__gt=current_game_time_min, scheduled_time__lt=current_game_time_max) \
                                         .exclude(game_link='').order_by('scheduled_time')
    upcoming_game_time_min = timezone.now() - timedelta(minutes=5)
    upcoming_game_time_max = timezone.now() + timedelta(hours=12)
    upcoming_games = PlayerPairing.objects.filter(game_link='', result='', scheduled_time__gt=upcoming_game_time_min, scheduled_time__lt=upcoming_game_time_max) \
                                          .order_by('scheduled_time')

    context = {
        'league_tag': league_tag,
        'league': league,
        'season_tag': season_tag,
        'season': current_season,
        'player_scores': player_scores,
        'season_list': season_list,
        'rules_doc_tag': rules_doc_tag,
        'intro_doc': intro_doc,
        'can_edit_document': request.user.has_perm('tournament.change_document'),
        'registration_season': registration_season,
        'current_games': current_games,
        'upcoming_games': upcoming_games,
        'other_leagues': other_leagues,
        'player_highlights': player_highlights,
    }
    return render(request, 'tournament/lone_league_home.html', context)

def season_landing(request, league_tag=None, season_tag=None):
    league = _get_league(league_tag)
    if league.competitor_type == 'team':
        return team_season_landing(request, league_tag, season_tag)
    else:
        return lone_season_landing(request, league_tag, season_tag)

@cached_view_as(SeasonDocument, Document, TeamScore, TeamPairing, *common_team_models, vary_request=lambda r: r.user.is_staff)
def team_season_landing(request, league_tag=None, season_tag=None):
    season = _get_season(league_tag, season_tag)
    if season.is_completed:
        return team_completed_season_landing(request, league_tag, season_tag)

    default_season = _get_default_season(league_tag)
    season_list = Season.objects.filter(league=_get_league(league_tag)).order_by('-start_date', '-id').exclude(pk=default_season.pk)

    active_round = Round.objects.filter(season=season, publish_pairings=True, is_completed=False, start_date__lt=timezone.now(), end_date__gt=timezone.now()) \
                                .order_by('-number') \
                                .first()
    last_round = Round.objects.filter(season=season, is_completed=True).order_by('-number').first()
    last_round_pairings = last_round.teampairing_set.all() if last_round is not None else None
    team_scores = list(enumerate(sorted(TeamScore.objects.filter(team__season=season), reverse=True)[:5], 1))

    links_doc = SeasonDocument.objects.filter(season=season, type='links').first()

    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': season,
        'default_season': default_season,
        'season_list': season_list,
        'active_round': active_round,
        'last_round': last_round,
        'last_round_pairings': last_round_pairings,
        'team_scores': team_scores,
        'links_doc': links_doc,
        'can_edit_document': request.user.has_perm('tournament.change_document'),
    }
    return render(request, 'tournament/team_season_landing.html', context)

@cached_view_as(SeasonDocument, Document, *common_lone_models, vary_request=lambda r: r.user.is_staff)
def lone_season_landing(request, league_tag=None, season_tag=None):
    season = _get_season(league_tag, season_tag)
    if season.is_completed:
        return lone_completed_season_landing(request, league_tag, season_tag)

    default_season = _get_default_season(league_tag)
    season_list = Season.objects.filter(league=_get_league(league_tag)).order_by('-start_date', '-id').exclude(pk=default_season.pk)

    active_round = Round.objects.filter(season=season, publish_pairings=True, is_completed=False, start_date__lt=timezone.now(), end_date__gt=timezone.now()) \
                                .order_by('-number') \
                                .first()
    last_round = Round.objects.filter(season=season, is_completed=True).order_by('-number').first()
    last_round_pairings = last_round.loneplayerpairing_set.exclude(result='').order_by('pairing_order')[:10].nocache() if last_round is not None else None
    player_scores = _lone_player_scores(season, final=True)[:5]

    links_doc = SeasonDocument.objects.filter(season=season, type='links').first()

    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': season,
        'default_season': default_season,
        'season_list': season_list,
        'active_round': active_round,
        'last_round': last_round,
        'last_round_pairings': last_round_pairings,
        'player_scores': player_scores,
        'links_doc': links_doc,
        'can_edit_document': request.user.has_perm('tournament.change_document'),
    }
    return render(request, 'tournament/lone_season_landing.html', context)

def team_completed_season_landing(request, league_tag=None, season_tag=None):
    season = _get_season(league_tag, season_tag)
    default_season = _get_default_season(league_tag)
    season_list = Season.objects.filter(league=_get_league(league_tag)).order_by('-start_date', '-id').exclude(pk=default_season.pk)

    round_numbers = list(range(1, season.rounds + 1))
    team_scores = list(enumerate(sorted(TeamScore.objects.filter(team__season=season).select_related('team').nocache(), reverse=True), 1))

    first_team = team_scores[0][1] if len(team_scores) > 0 else None
    second_team = team_scores[1][1] if len(team_scores) > 1 else None
    third_team = team_scores[2][1] if len(team_scores) > 2 else None

    links_doc = SeasonDocument.objects.filter(season=season, type='links').first()

    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': season,
        'default_season': default_season,
        'season_list': season_list,
        'round_numbers': round_numbers,
        'team_scores': team_scores,
        'first_team': first_team,
        'second_team': second_team,
        'third_team': third_team,
        'links_doc': links_doc,
        'can_edit_document': request.user.has_perm('tournament.change_document'),
    }
    return render(request, 'tournament/team_completed_season_landing.html', context)

def lone_completed_season_landing(request, league_tag=None, season_tag=None):
    season = _get_season(league_tag, season_tag)
    default_season = _get_default_season(league_tag)
    season_list = Season.objects.filter(league=_get_league(league_tag)).order_by('-start_date', '-id').exclude(pk=default_season.pk)

    round_numbers = list(range(1, season.rounds + 1))
    player_scores = _lone_player_scores(season)

    first_player = player_scores[0][1] if len(player_scores) > 0 else None
    second_player = player_scores[1][1] if len(player_scores) > 1 else None
    third_player = player_scores[2][1] if len(player_scores) > 2 else None

    u1600_winner = SeasonPrizeWinner.objects.filter(season_prize__season=season, season_prize__max_rating=1600, season_prize__rank=1).first()
    if u1600_winner is not None:
        u1600_player = find([ps[1] for ps in player_scores], season_player__player=u1600_winner.player)
    else:
        u1600_player = None

    prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season=season)
    player_highlights = _get_player_highlights(prize_winners)

    links_doc = SeasonDocument.objects.filter(season=season, type='links').first()

    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': season,
        'default_season': default_season,
        'season_list': season_list,
        'round_numbers': round_numbers,
        'player_scores': player_scores,
        'first_player': first_player,
        'second_player': second_player,
        'third_player': third_player,
        'u1600_player': u1600_player,
        'player_highlights': player_highlights,
        'links_doc': links_doc,
        'can_edit_document': request.user.has_perm('tournament.change_document'),
    }
    return render(request, 'tournament/lone_completed_season_landing.html', context)

def pairings(request, league_tag=None, season_tag=None, round_number=None, team_number=None):
    league = _get_league(league_tag)
    if league.competitor_type == 'team':
        return team_pairings(request, league_tag, season_tag, round_number, team_number)
    else:
        return lone_pairings(request, league_tag, season_tag, round_number, team_number)

@cached_view_as(TeamScore, TeamPairing, TeamMember, SeasonPlayer, AlternateAssignment, Player, PlayerAvailability, TeamPlayerPairing,
                PlayerPairing, *common_team_models, vary_request=lambda r: (r.user.is_staff, r.user.has_perm('tournament.change_pairing')))
def team_pairings(request, league_tag=None, season_tag=None, round_number=None, team_number=None):
    specified_round = round_number is not None
    season = _get_season(league_tag, season_tag)
    round_number_list = [round_.number for round_ in Round.objects.filter(season=season, publish_pairings=True).order_by('-number')]
    if round_number is None:
        try:
            round_number = round_number_list[0]
        except IndexError:
            pass
    team_list = season.team_set.order_by('name')
    team_pairings = TeamPairing.objects.filter(round__number=round_number, round__season=season) \
                                       .order_by('pairing_order') \
                                       .select_related('white_team', 'black_team') \
                                       .nocache()
    if team_number is not None:
        current_team = get_object_or_404(team_list, number=team_number)
        team_pairings = team_pairings.filter(white_team=current_team) | team_pairings.filter(black_team=current_team)
    else:
        current_team = None
    pairing_lists = [list(
                          team_pairing.teamplayerpairing_set.order_by('board_number')
                                      .select_related('white', 'black')
                                      .nocache()
                    ) for team_pairing in team_pairings]
    unavailable_players = {pa.player for pa in PlayerAvailability.objects.filter(round__season=season, round__number=round_number, is_available=False) \
                                                                         .select_related('player')
                                                                         .nocache()}
    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': season,
        'round_number': round_number,
        'round_number_list': round_number_list,
        'current_team': current_team,
        'team_list': team_list,
        'pairing_lists': pairing_lists,
        'unavailable_players': unavailable_players,
        'specified_round': specified_round,
        'specified_team': team_number is not None,
        'can_edit': request.user.has_perm('tournament.change_pairing')
    }
    return render(request, 'tournament/team_pairings.html', context)

def lone_pairings(request, league_tag=None, season_tag=None, round_number=None, team_number=None):
    specified_round = round_number is not None
    season = _get_season(league_tag, season_tag)
    round_number_list = [round_.number for round_ in Round.objects.filter(season=season, publish_pairings=True).order_by('-number')]
    if round_number is None:
        try:
            round_number = round_number_list[0]
        except IndexError:
            pass
    round_ = Round.objects.filter(number=round_number, season=season).first()
    pairings = LonePlayerPairing.objects.filter(round=round_).order_by('pairing_order').select_related('white', 'black').nocache()
    byes = PlayerBye.objects.filter(round=round_).order_by('type', 'player_rank', 'player__lichess_username').select_related('player').nocache()

    next_pairing_order = 0
    for p in pairings:
        next_pairing_order = max(next_pairing_order, p.pairing_order + 1)

    # Find duplicate players
    player_refcounts = {}
    for p in pairings:
        player_refcounts[p.white] = player_refcounts.get(p.white, 0) + 1
        player_refcounts[p.black] = player_refcounts.get(p.black, 0) + 1
    for b in byes:
        player_refcounts[b.player] = player_refcounts.get(b.player, 0) + 1
    duplicate_players = {k for k, v in player_refcounts.items() if v > 1}

    active_players = {sp.player for sp in SeasonPlayer.objects.filter(season=season, is_active=True)}

    def pairing_error(pairing):
        if not request.user.is_staff:
            return None
        if pairing.white == None or pairing.black == None:
            return 'Missing player'
        if pairing.white in duplicate_players:
            return 'Duplicate player: %s' % pairing.white.lichess_username
        if pairing.black in duplicate_players:
            return 'Duplicate player: %s' % pairing.black.lichess_username
        if not round_.is_completed and pairing.white not in active_players:
            return 'Inactive player: %s' % pairing.white.lichess_username
        if not round_.is_completed and pairing.black not in active_players:
            return 'Inactive player: %s' % pairing.black.lichess_username
        return None

    def bye_error(bye):
        if not request.user.is_staff:
            return None
        if bye.player in duplicate_players:
            return 'Duplicate player: %s' % bye.player.lichess_username
        if not round_.is_completed and bye.player not in active_players:
            return 'Inactive player: %s' % bye.player.lichess_username
        return None

    # Add errors
    pairings = [(p, pairing_error(p)) for p in pairings]
    byes = [(b, bye_error(b)) for b in byes]

    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': season,
        'round_': round_,
        'round_number_list': round_number_list,
        'pairings': pairings,
        'byes': byes,
        'specified_round': specified_round,
        'next_pairing_order': next_pairing_order,
        'duplicate_players': duplicate_players,
        'can_edit': request.user.has_perm('tournament.change_pairing')
    }
    return render(request, 'tournament/lone_pairings.html', context)

def register(request, league_tag=None, season_tag=None):
    try:
        if season_tag is None:
            season = Season.objects.filter(league=_get_league(league_tag), registration_open=True).order_by('-start_date')[0]
        else:
            season = Season.objects.filter(league=_get_league(league_tag), registration_open=True, tag=season_tag)[0]
    except IndexError:
        return registration_closed(request, league_tag, season_tag)
    if request.method == 'POST':
        form = RegistrationForm(request.POST, season=season)
        if form.is_valid():
            registration = form.save()
            return redirect(leagueurl('registration_success', league_tag=league_tag, season_tag=season_tag))
    else:
        form = RegistrationForm(season=season)

    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': _get_season(league_tag, season_tag),
        'form': form,
        'registration_season': season
    }
    return render(request, 'tournament/register.html', context)

def registration_success(request, league_tag=None, season_tag=None):
    try:
        if season_tag is None:
            season = Season.objects.filter(league=_get_league(league_tag), registration_open=True).order_by('-start_date')[0]
        else:
            season = Season.objects.filter(league=_get_league(league_tag), registration_open=True, tag=season_tag)[0]
    except IndexError:
        return registration_closed(request, league_tag, season_tag)
    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': _get_season(league_tag, season_tag),
        'registration_season': season
    }
    return render(request, 'tournament/registration_success.html', context)

def registration_closed(request, league_tag=None, season_tag=None):
    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': _get_season(league_tag, season_tag)
    }
    return render(request, 'tournament/registration_closed.html', context)

def faq(request, league_tag=None, season_tag=None):
    league = _get_league(league_tag)
    league_document = LeagueDocument.objects.filter(league=league, type='faq').first()
    # If the FAQ document doesn't exist, create a placeholder
    if league_document is None:
        league_document = LeagueDocument.objects.filter(league=league, tag='faq').first()
    if league_document is None:
        document = Document.objects.create(name='FAQ', content='Coming soon.')
        league_document = LeagueDocument.objects.create(league=league, document=document, tag='faq', type='faq')
    context = {
        'league_tag': league_tag,
        'league': league,
        'season_tag': season_tag,
        'season': _get_season(league_tag, season_tag),
        'document': league_document.document,
        'is_faq': True,
        'can_edit': request.user.has_perm('tournament.change_document'),
    }
    return render(request, 'tournament/document.html', context)

@cached_view_as(TeamMember, SeasonPlayer, Alternate, AlternateAssignment, AlternateBucket, Player, PlayerAvailability, *common_team_models,
                vary_request=lambda r: (r.user.is_staff, r.user.has_perm('tournament.manage_players')))
def rosters(request, league_tag=None, season_tag=None):
    league = _get_league(league_tag)
    if league.competitor_type != 'team':
        raise Http404
    season = _get_season(league_tag, season_tag)
    if season is None:
        context = {
            'league_tag': league_tag,
            'league': league,
            'season_tag': season_tag,
            'season': season,
            'can_edit': request.user.has_perm('tournament.manage_players'),
        }
        return render(request, 'tournament/team_rosters.html', context)

    teams = Team.objects.filter(season=season).order_by('number').prefetch_related(
        Prefetch('teammember_set', queryset=TeamMember.objects.select_related('player'))
    ).nocache()
    board_numbers = list(range(1, season.boards + 1))

    alternates = Alternate.objects.filter(season_player__season=season)
    alternates_by_board = [sorted(
                                  alternates.filter(board_number=n)
                                            .select_related('season_player__registration', 'season_player__player')
                                            .nocache(),
                                  key=lambda alt: alt.priority_date()
                           ) for n in board_numbers]
    alternate_rows = list(enumerate(itertools.izip_longest(*alternates_by_board), 1))
    if len(alternate_rows) == 0:
        alternate_rows.append((1, [None for _ in board_numbers]))

    current_round = Round.objects.filter(season=season, publish_pairings=True).order_by('-number').first()
    scheduled_alternates = {assign.player for assign in AlternateAssignment.objects.filter(round=current_round)
                                                                                   .select_related('player')
                                                                                   .nocache()}
    unresponsive_players = {sp.player for sp in SeasonPlayer.objects.filter(season=season, unresponsive=True)
                                                                    .select_related('player')
                                                                    .nocache()}
    games_missed_by_player = {sp.player: sp.games_missed for sp in SeasonPlayer.objects.filter(season=season)
                                                                                       .select_related('player')
                                                                                       .nocache()}
    yellow_card_players = {player for player, games_missed in games_missed_by_player.items() if games_missed == 1}
    red_card_players = {player for player, games_missed in games_missed_by_player.items() if games_missed >= 2}

    context = {
        'league_tag': league_tag,
        'league': league,
        'season_tag': season_tag,
        'season': season,
        'teams': teams,
        'board_numbers': board_numbers,
        'alternate_rows': alternate_rows,
        'scheduled_alternates': scheduled_alternates,
        'unresponsive_players': unresponsive_players,
        'yellow_card_players': yellow_card_players,
        'red_card_players': red_card_players,
        'can_edit': request.user.has_perm('tournament.manage_players'),
    }
    return render(request, 'tournament/team_rosters.html', context)

def standings(request, league_tag=None, season_tag=None, section=None):
    league = _get_league(league_tag)
    if league.competitor_type == 'team':
        return team_standings(request, league_tag, season_tag)
    else:
        return lone_standings(request, league_tag, season_tag, section)

@cached_view_as(TeamScore, TeamPairing, *common_team_models, vary_request=lambda r: r.user.is_staff)
def team_standings(request, league_tag=None, season_tag=None):
    season = _get_season(league_tag, season_tag)
    round_numbers = list(range(1, season.rounds + 1))
    team_scores = list(enumerate(sorted(TeamScore.objects.filter(team__season=season).select_related('team').nocache(), reverse=True), 1))
    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': season,
        'round_numbers': round_numbers,
        'team_scores': team_scores,
    }
    return render(request, 'tournament/team_standings.html', context)

@cached_view_as(*common_lone_models, vary_request=lambda r: r.user.is_staff)
def lone_standings(request, league_tag=None, season_tag=None, section=None):
    season = _get_season(league_tag, season_tag)
    round_numbers = list(range(1, season.rounds + 1))
    player_scores = _lone_player_scores(season)

    if section is not None:
        match = re.match(r'u(\d+)', section)
        if match is not None:
            max_rating = int(match.group(1))
            player_scores = [ps for ps in player_scores if ps[1].season_player.seed_rating < max_rating]

    player_sections = [('u%d' % sp.max_rating, 'U%d' % sp.max_rating) for sp in SeasonPrize.objects.filter(season=season).exclude(max_rating=None).order_by('max_rating')]
    section_dict = {k: (k, v) for k, v in player_sections}
    current_section = section_dict.get(section, None)

    if season.is_completed:
        prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season=season)
    else:
        prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season__league=season.league)
    player_highlights = _get_player_highlights(prize_winners)

    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': season,
        'round_numbers': round_numbers,
        'player_scores': player_scores,
        'player_sections': player_sections,
        'current_section': current_section,
        'player_highlights': player_highlights,
    }
    return render(request, 'tournament/lone_standings.html', context)

def _get_player_highlights(prize_winners):
    return [
        ('gold', {pw.player for pw in prize_winners.filter(season_prize__rank=1, season_prize__max_rating=None)}),
        ('silver', {pw.player for pw in prize_winners.filter(season_prize__rank=2, season_prize__max_rating=None)}),
        ('bronze', {pw.player for pw in prize_winners.filter(season_prize__rank=3, season_prize__max_rating=None)}),
        ('blue', {pw.player for pw in prize_winners.filter(season_prize__rank=1).exclude(season_prize__max_rating=None)})
    ]

@cached_as(LonePlayerScore, LonePlayerPairing, PlayerPairing, PlayerBye, SeasonPlayer, Player)
def _lone_player_scores(season, final=False, sort_by_seed=False, include_current=False):
    # For efficiency, rather than having LonePlayerScore.round_scores() do independent
    # calculations, we populate a few common data structures and use those as parameters.

    if sort_by_seed:
        sort_key = lambda s: s.season_player.seed_rating
    elif season.is_completed or final:
        sort_key = lambda s: s.final_standings_sort_key()
    else:
        sort_key = lambda s: s.pairing_sort_key()
    player_scores = list(enumerate(sorted(LonePlayerScore.objects.filter(season_player__season=season).select_related('season_player__player').nocache(), key=sort_key, reverse=True), 1))
    player_number_dict = {p.season_player.player: n for n, p in player_scores}

    pairings = LonePlayerPairing.objects.filter(round__season=season).select_related('white', 'black').nocache()
    white_pairings_dict = defaultdict(list)
    black_pairings_dict = defaultdict(list)
    for p in pairings:
        if p.white is not None:
            white_pairings_dict[p.white].append(p)
        if p.black is not None:
            black_pairings_dict[p.black].append(p)

    byes = PlayerBye.objects.filter(round__season=season).select_related('round', 'player').nocache()
    byes_dict = defaultdict(list)
    for bye in byes:
        byes_dict[bye.player].append(bye)

    rounds = Round.objects.filter(season=season).order_by('number')
    # rounds = [round_ for round_ in Round.objects.filter(season=season).order_by('number') if round_.is_completed or (include_current and round_.publish_pairings)]

    def round_scores(player_score):
        return list(player_score.round_scores(rounds, player_number_dict, white_pairings_dict, black_pairings_dict, byes_dict, include_current))

    return [(n, ps, round_scores(ps)) for n, ps in player_scores]

@cached_view_as(TeamScore, TeamPairing, *common_team_models, vary_request=lambda r: r.user.is_staff)
def crosstable(request, league_tag=None, season_tag=None):
    league = _get_league(league_tag)
    if league.competitor_type != 'team':
        raise Http404
    season = _get_season(league_tag, season_tag)
    team_scores = TeamScore.objects.filter(team__season=season).order_by('team__number').select_related('team').nocache()
    context = {
        'league_tag': league_tag,
        'league': league,
        'season_tag': season_tag,
        'season': season,
        'team_scores': team_scores,
    }
    return render(request, 'tournament/team_crosstable.html', context)

@cached_view_as(*common_lone_models, vary_request=lambda r: r.user.is_staff)
def wallchart(request, league_tag=None, season_tag=None):
    league = _get_league(league_tag)
    if league.competitor_type == 'team':
        raise Http404
    season = _get_season(league_tag, season_tag)
    round_numbers = list(range(1, season.rounds + 1))
    player_scores = _lone_player_scores(season, sort_by_seed=True, include_current=True)

    if season.is_completed:
        prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season=season)
    else:
        prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season__league=season.league)
    player_highlights = _get_player_highlights(prize_winners)

    context = {
        'league_tag': league_tag,
        'league': league,
        'season_tag': season_tag,
        'season': season,
        'round_numbers': round_numbers,
        'player_scores': player_scores,
        'player_highlights': player_highlights,
    }
    return render(request, 'tournament/lone_wallchart.html', context)

def result(request, pairing_id, league_tag=None, season_tag=None):
    season = _get_season(league_tag, season_tag)
    team_pairing = get_object_or_404(TeamPairing, round__season=season, pk=pairing_id)
    pairings = team_pairing.teamplayerpairing_set.order_by('board_number').nocache()
    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': season,
        'team_pairing': team_pairing,
        'pairings': pairings,
        'round_number': team_pairing.round.number,
    }
    return render(request, 'tournament/team_match_result.html', context)

@cached_view_as(League, Season, Round, TeamPlayerPairing, PlayerPairing, vary_request=lambda r: r.user.is_staff)
def stats(request, league_tag=None, season_tag=None):
    league = _get_league(league_tag)
    if league.competitor_type != 'team':
        raise Http404
    season = _get_season(league_tag, season_tag)

    all_pairings = PlayerPairing.objects.filter(teamplayerpairing__team_pairing__round__season=season) \
                                        .select_related('teamplayerpairing', 'white', 'black') \
                                        .nocache()

    def count_results(board_num=None):
        total = 0.0
        counts = [0, 0, 0, 0]
        rating_delta = 0
        for p in all_pairings:
            if board_num is not None and p.teamplayerpairing.board_number != board_num:
                continue
            if p.game_link == '' or p.result == '':
                # Don't count forfeits etc
                continue
            total += 1
            if p.white.rating is not None and p.black.rating is not None:
                rating_delta += p.white.rating - p.black.rating
            if p.result == '1-0':
                counts[0] += 1
                counts[3] += 1
            elif p.result == '0-1':
                counts[2] += 1
                counts[3] -= 1
            elif p.result == '1/2-1/2':
                counts[1] += 1
        if total == 0:
            return board_num, tuple(counts), (0, 0, 0, 0), 0.0
        percents = (counts[0] / total, counts[1] / total, counts[2] / total, counts[3] / total)
        return board_num, tuple(counts), percents, rating_delta / total

    _, total_counts, total_percents, total_rating_delta = count_results()
    boards = [count_results(board_num=n) for n in season.board_number_list()]

    context = {
        'league_tag': league_tag,
        'league': league,
        'season_tag': season_tag,
        'season': season,
        'has_win_rate_stats': total_counts != (0, 0, 0, 0),
        'total_rating_delta': total_rating_delta,
        'total_counts': total_counts,
        'total_percents': total_percents,
        'boards': boards,
    }
    return render(request, 'tournament/team_stats.html', context)

@staff_member_required
def league_dashboard(request, league_tag=None, season_tag=None):
    league = _get_league(league_tag)
    if league.competitor_type == 'team':
        return team_league_dashboard(request, league_tag, season_tag)
    else:
        return lone_league_dashboard(request, league_tag, season_tag)

@staff_member_required
def team_league_dashboard(request, league_tag=None, season_tag=None):
    league = _get_league(league_tag, season_tag)
    season = _get_season(league_tag, season_tag, allow_none=True)

    default_season = _get_default_season(league_tag, allow_none=True)
    season_list = list(Season.objects.filter(league=league).order_by('-start_date', '-id'))
    if default_season is not None:
        season_list.remove(default_season)

    pending_reg_count = len(Registration.objects.filter(season=season, status='pending'))

    team_members = TeamMember.objects.filter(team__season=season).select_related('player').nocache()
    alternates = Alternate.objects.filter(season_player__season=season).select_related('season_player__player').nocache()
    season_players = set(sp.player for sp in SeasonPlayer.objects.filter(season=season, is_active=True).select_related('player').nocache())
    team_players = set(tm.player for tm in team_members)
    alternate_players = set(alt.season_player.player for alt in alternates)
    unassigned_player_count = len(season_players - team_players - alternate_players)

    last_round = Round.objects.filter(season=season, publish_pairings=True, is_completed=False).order_by('number').first()
    next_round = Round.objects.filter(season=season, publish_pairings=False, is_completed=False).order_by('number').first()

    context = {
        'league_tag': league_tag,
        'league': league,
        'season_tag': season_tag,
        'season': season,
        'default_season': default_season,
        'season_list': season_list,
        'pending_reg_count': pending_reg_count,
        'unassigned_player_count': unassigned_player_count,
        'last_round': last_round,
        'next_round': next_round
    }
    return render(request, 'tournament/team_league_dashboard.html', context)

@staff_member_required
def lone_league_dashboard(request, league_tag=None, season_tag=None):
    league = _get_league(league_tag, season_tag)
    season = _get_season(league_tag, season_tag, allow_none=True)

    default_season = _get_default_season(league_tag, allow_none=True)
    season_list = list(Season.objects.filter(league=league).order_by('-start_date', '-id'))
    if default_season is not None:
        season_list.remove(default_season)

    pending_reg_count = len(Registration.objects.filter(season=season, status='pending'))

    team_members = TeamMember.objects.filter(team__season=season).select_related('player').nocache()
    alternates = Alternate.objects.filter(season_player__season=season).select_related('season_player__player').nocache()
    season_players = set(sp.player for sp in SeasonPlayer.objects.filter(season=season, is_active=True).select_related('player').nocache())
    team_players = set(tm.player for tm in team_members)
    alternate_players = set(alt.season_player.player for alt in alternates)
    unassigned_player_count = len(season_players - team_players - alternate_players)

    last_round = Round.objects.filter(season=season, publish_pairings=True, is_completed=False).order_by('number').first()
    next_round = Round.objects.filter(season=season, publish_pairings=False, is_completed=False).order_by('number').first()

    context = {
        'league_tag': league_tag,
        'league': league,
        'season_tag': season_tag,
        'season': season,
        'default_season': default_season,
        'season_list': season_list,
        'pending_reg_count': pending_reg_count,
        'unassigned_player_count': unassigned_player_count,
        'last_round': last_round,
        'next_round': next_round
    }
    return render(request, 'tournament/lone_league_dashboard.html', context)

def document(request, document_tag, league_tag=None, season_tag=None):
    league_document = LeagueDocument.objects.filter(league=_get_league(league_tag), tag=document_tag).first()
    if league_document is None:
        season_document = SeasonDocument.objects.filter(season=_get_season(league_tag, season_tag), tag=document_tag).first()
        if season_document is None:
            raise Http404
        document = season_document.document
    else:
        document = league_document.document

    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': _get_season(league_tag, season_tag, allow_none=True),
        'document': document,
        'is_faq': False,
        'can_edit': request.user.has_perm('tournament.change_document'),
    }
    return render(request, 'tournament/document.html', context)

def player_profile(request, username, league_tag=None, season_tag=None):
    season = _get_season(league_tag, season_tag, allow_none=True)
    player = get_object_or_404(Player, lichess_username__iexact=username)

    def game_count(season):
        if season.league.competitor_type == 'team':
            return (TeamPlayerPairing.objects.filter(white=player) | TeamPlayerPairing.objects.filter(black=player)).filter(team_pairing__round__season=season).count()
        else:
            return (LonePlayerPairing.objects.filter(white=player) | LonePlayerPairing.objects.filter(black=player)).filter(round__season=season).count()

    def team_name(season):
        if season.league.competitor_type == 'team':
            team_member = player.teammember_set.filter(team__season=season).first()
            if team_member is not None:
                return team_member.team.name
        return None

    other_season_leagues = [(l, [(sp.season, game_count(sp.season), team_name(sp.season)) for sp in player.seasonplayer_set.filter(season__league=l).exclude(season=season)]) \
                     for l in League.objects.order_by('display_order')]
    other_season_leagues = [l for l in other_season_leagues if len(l[1]) > 0]

    season_player = SeasonPlayer.objects.filter(season=season, player=player).first()

    if season is None:
        games = None
    elif season.league.competitor_type == 'team':
        pairings = TeamPlayerPairing.objects.filter(white=player) | TeamPlayerPairing.objects.filter(black=player)
        games = [(p.team_pairing.round, p, p.white_team() if p.white == player else p.black_team()) for p in pairings.filter(team_pairing__round__season=season).exclude(result='').order_by('team_pairing__round__number').nocache()]
    else:
        pairings = LonePlayerPairing.objects.filter(white=player) | LonePlayerPairing.objects.filter(black=player)
        games = [(p.round, p, None) for p in pairings.filter(round__season=season).exclude(result='').order_by('round__number').nocache()]

    team_member = TeamMember.objects.filter(team__season=season, player=player).first()
    alternate = Alternate.objects.filter(season_player=season_player).first()

    schedule = []
    for round_ in season.round_set.filter(is_completed=False).order_by('number'):
        if season.league.competitor_type == 'team':
            pairing = pairings.filter(team_pairing__round=round_).first()
        else:
            pairing = pairings.filter(round=round_).first()
        if pairing is not None:
            if pairing.result != '':
                continue
            schedule.append((round_, pairing, None, None))
            continue
        if season.league.competitor_type == 'team':
            assignment = AlternateAssignment.objects.filter(round=round_, player=player).first()
            if assignment is not None and (team_member is None or team_member.team != assignment.team):
                schedule.append((round_, None, 'Scheduled', assignment.team))
                continue
            if season_player is None or not season_player.is_active:
                continue
            availability = PlayerAvailability.objects.filter(round=round_, player=player).first()
            if availability is not None and not availability.is_available:
                schedule.append((round_, None, 'Unavailable', None))
                continue
            if team_member is not None:
                schedule.append((round_, None, 'Scheduled', None))
                continue
            schedule.append((round_, None, 'Available', None))
        else:
            bye = PlayerBye.objects.filter(round=round_, player=player).first()
            if bye is not None:
                schedule.append((round_, None, bye.get_type_display(), None))
                continue
            if season_player is None or not season_player.is_active:
                continue
            schedule.append((round_, None, 'Scheduled', None))

    context = {
        'league_tag': league_tag,
        'league': _get_league(league_tag),
        'season_tag': season_tag,
        'season': season,
        'player': player,
        'other_season_leagues': other_season_leagues,
        'season_player': season_player,
        'games': games,
        'team_member': team_member,
        'alternate': alternate,
        'schedule': schedule,
    }
    return render(request, 'tournament/player_profile.html', context)

def _get_league(league_tag, allow_none=False):
    if league_tag is None:
        return _get_default_league(allow_none)
    else:
        return get_object_or_404(League, tag=league_tag)

def _get_default_league(allow_none=False):
    try:
        return League.objects.filter(is_default=True).order_by('id')[0]
    except IndexError:
        league = League.objects.order_by('id').first()
        if not allow_none and league is None:
            raise Http404
        return league

def _get_season(league_tag, season_tag, allow_none=False):
    if season_tag is None:
        return _get_default_season(league_tag, allow_none)
    else:
        return get_object_or_404(Season, league=_get_league(league_tag), tag=season_tag)

def _get_default_season(league_tag, allow_none=False):
    season = Season.objects.filter(league=_get_league(league_tag), is_active=True).order_by('-start_date', '-id').first()
    if not allow_none and season is None:
        raise Http404
    return season
