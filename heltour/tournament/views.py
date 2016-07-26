from django.shortcuts import render, redirect
from .models import *
from .forms import *

# TODO: Make behavior consistent when a league has no seasons

def season_landing(request, league_tag=None, season_id=None):
    default_season = _get_default_season(league_tag)
    season_list = list(Season.objects.filter(league=_get_league(league_tag)).order_by('-start_date', '-id'))
    season_list.remove(default_season)
    context = {
        'league_tag': league_tag,
        'season_id': season_id,
        'season': _get_season(league_tag, season_id),
        'default_season': default_season,
        'season_list': season_list 
    }
    return render(request, 'tournament/season_landing.html', context)

def pairings(request, league_tag=None, season_id=None, round_number=None):
    season = _get_season(league_tag, season_id)
    if season is None:
        return no_pairings_available(request)
    if round_number is None:
        try:
            round_number = Round.objects.filter(season=season).order_by('-number')[0].number
        except IndexError:
            return no_pairings_available(request, league_tag, season_id)
    team_pairings = TeamPairing.objects.filter(round__number=round_number, round__season=season)
    if len(team_pairings) == 0:
        return no_pairings_available(request, league_tag, season_id, round_number)
    pairing_lists = [team_pairing.pairing_set.order_by('board_number') for team_pairing in team_pairings]
    round_number_list = [round_.number for round_ in Round.objects.filter(season=season).order_by('-number')]
    context = {
        'league_tag': league_tag,
        'season_id': season_id,
        'season': season,
        'round_number': round_number,
        'round_number_list': round_number_list,
        'pairing_lists': pairing_lists,
        'can_edit': request.user.has_perm('tournament.change_pairing')
    }
    return render(request, 'tournament/pairings.html', context)

def no_pairings_available(request, league_tag=None, season_id=None, round_number=None):
    season = _get_season(league_tag, season_id)
    if season_id is not None:
        round_number_list = [round_.number for round_ in Round.objects.filter(season=season).order_by('-number')]
    else:
        round_number_list = []
    context = {
        'league_tag': league_tag,
        'season_id': season_id,
        'season': season,
        'round_number_list': round_number_list,
        'round_number': round_number
    }
    return render(request, 'tournament/no_pairings.html', context)

def register(request, league_tag=None, season_id=None):
    try:
        if season_id is None:
            season = Season.objects.filter(league=_get_league(league_tag), registration_open=True).order_by('-start_date')[0]
        else:
            season = Season.objects.filter(league=_get_league(league_tag), registration_open=True, pk=season_id)[0]
    except IndexError:
        return registration_closed(request, league_tag, season_id)
    if request.method == 'POST':
        form = RegistrationForm(request.POST, season=season)
        if form.is_valid():
            registration = form.save()
            return redirect('registration_success')
    else:
        form = RegistrationForm(season=season)
    
    context = {
        'league_tag': league_tag,
        'season_id': season_id,
        'season': _get_season(league_tag, season_id),
        'form': form,
        'registration_season': season
    }
    return render(request, 'tournament/register.html', context)

def registration_success(request, league_tag=None, season_id=None):
    context = {
        'league_tag': league_tag,
        'season_id': season_id,
        'season': _get_season(league_tag, season_id)
    }
    return render(request, 'tournament/registration_success.html', context)

def registration_closed(request, league_tag=None, season_id=None):
    context = {
        'league_tag': league_tag,
        'season_id': season_id,
        'season': _get_season(league_tag, season_id)
    }
    return render(request, 'tournament/registration_closed.html', context)

def league_home(request, league_tag=None):
    if league_tag is not None and league_tag != '':
        return redirect('by_league:pairings', league_tag)
    else:
        return redirect('pairings')

def faq(request, league_tag=None, season_id=None):
    context = {
        'league_tag': league_tag,
        'season_id': season_id,
        'season': _get_season(league_tag, season_id)
    }
    return render(request, 'tournament/faq.html', context)

def rosters(request, league_tag=None, season_id=None):
    season = _get_season(league_tag, season_id)
    if season is None:
        return no_rosters_available(request, league_tag, season_id)
    teams = Team.objects.filter(season=season).order_by('number')
    board_numbers = list(range(1, season.boards + 1))
    context = {
        'league_tag': league_tag,
        'season_id': season_id,
        'season': season,
        'teams': teams,
        'board_numbers': board_numbers
    }
    return render(request, 'tournament/rosters.html', context)

def no_rosters_available(request, league_tag=None, season_id=None):
    context = {
        'league_tag': league_tag,
        'season_id': season_id,
        'season': _get_season(league_tag, season_id)
    }
    return render(request, 'tournament/no_rosters.html', context)

def standings(request, league_tag=None, season_id=None):
    season = _get_season(league_tag, season_id)
    round_numbers = list(range(1, season.rounds + 1))
    team_scores = sorted(TeamScore.objects.filter(team__season=season), reverse=True)
    tie_score = season.boards / 2.0
    context = {
        'league_tag': league_tag,
        'season_id': season_id,
        'season': season,
        'round_numbers': round_numbers,
        'team_scores': team_scores,
        'tie_score': tie_score
    }
    return render(request, 'tournament/standings.html', context)

def crosstable(request, league_tag=None, season_id=None):
    context = {
        'league_tag': league_tag,
        'season_id': season_id,
        'season': _get_season(league_tag, season_id)
    }
    return render(request, 'tournament/crosstable.html', context)

def stats(request, league_tag=None, season_id=None):
    context = {
        'league_tag': league_tag,
        'season_id': season_id,
        'season': _get_season(league_tag, season_id)
    }
    return render(request, 'tournament/stats.html', context)

def _get_league(league_tag):
    if league_tag is None:
        return _get_default_league()
    else:
        return League.objects.get(tag=league_tag)

def _get_default_league():
    try:
        return League.objects.filter(is_default=True).order_by('id')[0]
    except IndexError:
        return League.objects.order_by('id')[0]
    
def _get_season(league_tag, season_id):
    if season_id is None:
        return _get_default_season(league_tag)
    else:
        return Season.objects.get(league=_get_league(league_tag), pk=season_id)

def _get_default_season(league_tag):
    try:
        return Season.objects.filter(league=_get_league(league_tag), is_active=True).order_by('-start_date', '-id')[0]
    except IndexError:
        raise ValueError('League has no seasons')
