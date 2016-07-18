from django.shortcuts import render
from .models import *

def pairings(request):
    season = Season.objects.order_by('-start_date')[0]
    round_ = Round.objects.filter(season=season).order_by('-number')[0]
    return pairings_by_season(request, season.id, round_.number)

def pairings_by_round(request, round_number):
    season = Season.objects.order_by('-start_date')[0]
    return pairings_by_season(request, season.id, round_number)

def pairings_by_season(request, season_id, round_number):
    team_pairings = TeamPairing.objects.filter(round__number=round_number, round__season__id=season_id)
    pairing_lists = [team_pairing.pairing_set.order_by('board_number') for team_pairing in team_pairings]
    context = {
        'round_number': round_number,
        'pairing_lists': pairing_lists
    }
    return render(request, 'tournament/pairings.html', context)