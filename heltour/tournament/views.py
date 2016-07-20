from django.shortcuts import render, redirect
from .models import *
from .forms import *

def pairings(request):
    try:
        season = Season.objects.order_by('-start_date')[0]
        round_ = Round.objects.filter(season=season).order_by('-number')[0]
    except IndexError:
        return no_pairings_available(request)
    return pairings_by_season(request, season.id, round_.number)

def pairings_by_round(request, round_number):
    try:
        season = Season.objects.order_by('-start_date')[0]
    except IndexError:
        return no_pairings_available(request)
    return pairings_by_season(request, season.id, round_number)

def pairings_by_season(request, season_id, round_number):
    team_pairings = TeamPairing.objects.filter(round__number=round_number, round__season__id=season_id)
    if len(team_pairings) == 0:
        return no_pairings_available(request)
    pairing_lists = [team_pairing.pairing_set.order_by('board_number') for team_pairing in team_pairings]
    context = {
        'round_number': round_number,
        'pairing_lists': pairing_lists
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
    if request.method == 'POST':
        form = RegistrationForm(request.POST, season=season)
        if form.is_valid() and season.id == form.cleaned_data['season_id']:
            Registration.objects.create(
                season = season,
                status = 'pending',
                lichess_username = form.cleaned_data['lichess_username'],
                slack_username = form.cleaned_data['slack_username'],
                email = form.cleaned_data['email'],
                classical_rating = form.cleaned_data['classical_rating'],
                peak_classical_rating = form.cleaned_data['peak_classical_rating'],
                has_played_20_games = form.cleaned_data['has_played_20_games'],
                already_in_slack_group = form.cleaned_data['already_in_slack_group'],
                previous_season_alternate = form.cleaned_data['previous_season_alternate'],
                can_commit = form.cleaned_data['can_commit'],
                friends = form.cleaned_data['friends'],
                agreed_to_rules = form.cleaned_data['agreed_to_rules'],
                alternate_preference = form.cleaned_data['alternate_preference'],
                weeks_unavailable = ','.join(form.cleaned_data['weeks_unavailable']),
            )
            return redirect('/registration_success/')
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

def review_registration(modeladmin, request, object_id):
    reg = Registration.objects.get(pk=object_id)
    
    context = {
        'has_permission': True,
        'opts': modeladmin.model._meta,
        'site_url': '/',
        'original': reg,
        'title': 'Review registration'
    }

    return render(request, 'tournament/admin/review_registration.html', context)

def home(request):
    return redirect('/pairings/')

def faq(request):
    context = {
    }
    return render(request, 'tournament/faq.html', context)

def rosters(request):
    context = {
    }
    return render(request, 'tournament/rosters.html', context)

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