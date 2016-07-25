from django.shortcuts import render, redirect
from .models import *
from .forms import *

def pairings(request):
    try:
        most_recent_round = Round.objects.order_by('-season__start_date', '-season__id', '-number')[0]
    except IndexError:
        return no_pairings_available(request)
    return pairings_by_season(request, most_recent_round.season.id, most_recent_round.number)

def pairings_by_round(request, round_number):
    try:
        most_recent_round = Round.objects.order_by('-season__start_date', '-season__id', '-number')[0]
    except IndexError:
        return no_pairings_available(request)
    return pairings_by_season(request, most_recent_round.season.id, round_number)

def pairings_by_season(request, season_id, round_number):
    team_pairings = TeamPairing.objects.filter(round__number=round_number, round__season__id=season_id)
    if len(team_pairings) == 0:
        return no_pairings_available(request)
    pairing_lists = [team_pairing.pairing_set.order_by('board_number') for team_pairing in team_pairings]
    context = {
        'round_number': round_number,
        'pairing_lists': pairing_lists,
        'can_edit': request.user.has_perm('tournament.change_pairing')
    }
    return render(request, 'tournament/pairings.html', context)

def no_pairings_available(request):
    context = {
    }
    return render(request, 'tournament/no_pairings.html', context)

def register(request):
    try:
        season = Season.objects.filter(registration_open=True).order_by('-start_date')[0]
    except IndexError:
        return registration_closed(request)
    return redirect('register_by_season', season_id=season.id)

def register_by_season(request, season_id):
    try:
        season = Season.objects.filter(registration_open=True, pk=season_id)[0]
    except IndexError:
        return registration_closed(request)
    if request.method == 'POST':
        form = RegistrationForm(request.POST, season=season)
        if form.is_valid():
            registration = form.save()
            return redirect('registration_success')
    else:
        form = RegistrationForm(season=season)
    return render(request, 'tournament/register.html', {'form': form, 'season': season})

def registration_success(request):
    context = {
    }
    return render(request, 'tournament/registration_success.html', context)

def registration_closed(request):
    context = {
    }
    return render(request, 'tournament/registration_closed.html', context)

def home(request):
    return redirect('/pairings/')

def faq(request):
    context = {
    }
    return render(request, 'tournament/faq.html', context)

def rosters(request):
    try:
        most_recent_round = Round.objects.order_by('-season__start_date', '-season__id', '-number')[0]
    except IndexError:
        return no_rosters_available(request)
    return rosters_by_season(request, most_recent_round.season.id)

def rosters_by_season(request, season_id):
    try:
        season = Season.objects.filter(pk=season_id)[0]
    except IndexError:
        return no_rosters_available(request)
    teams = Team.objects.filter(season=season).order_by('number')
    board_numbers = list(range(1, season.boards + 1))
    context = {
        'teams': teams,
        'board_numbers': board_numbers
    }
    return render(request, 'tournament/rosters.html', context)

def no_rosters_available(request):
    context = {
    }
    return render(request, 'tournament/no_rosters.html', context)

def standings(request):
    context = {
    }
    return render(request, 'tournament/standings.html', context)

def crosstable(request):
    context = {
    }
    return render(request, 'tournament/crosstable.html', context)

def stats(request):
    context = {
    }
    return render(request, 'tournament/stats.html', context)
