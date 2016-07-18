from django.shortcuts import render

# Create your views here.

def pairings(request, season_id, round_number):
    context = {
        'round_number': round_number
    }
    return render(request, 'tournament/pairings.html', context)