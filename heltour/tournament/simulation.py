import math
import random

from heltour.tournament import pairinggen
from heltour.tournament.models import (
    LonePlayerPairing,
    LonePlayerScore,
    PlayerLateRegistration,
    TeamPlayerPairing,
    TeamScore,
)

sysrand = random.SystemRandom()


def simulate_round(round_):
    forfeit_chance = 0.10
    forfeit_results = ['1X-0F', '1/2Z-1/2Z', '0F-1X', '0F-0F']

    def result_chances(rating_delta):
        rating_delta_index = int(min(math.floor(abs(rating_delta) / 100.0), 5))
        chances_by_rating_delta = [
            (0.40, 0.15, 0.45),
            (0.25, 0.10, 0.65),
            (0.20, 0.10, 0.70),
            (0.15, 0.10, 0.75),
            (0.10, 0.10, 0.80),
            (0.05, 0.00, 0.95),
        ]
        chances = chances_by_rating_delta[rating_delta_index]
        if rating_delta < 0:
            chances = tuple(reversed(chances))
        return chances

    for p in round_.pairings.select_related('white', 'black'):
        if sysrand.random() < forfeit_chance:
            p.result = sysrand.choice(forfeit_results)
        else:
            chances = result_chances(p.white_rating_display() - p.black_rating_display())
            r = sysrand.random()
            if r < chances[0]:
                p.result = '0-1'
            elif r < chances[0] + chances[1]:
                p.result = '1/2-1/2'
            else:
                p.result = '1-0'
        p.save()


def simulate_season(season):
    # Reset all season data
    print('Clearing season data')
    for r in season.round_set.order_by('-number'):
        r.publish_pairings = False
        r.is_completed = False
        r.save()
    LonePlayerPairing.objects.filter(round__season=season).delete()
    TeamPlayerPairing.objects.filter(team_pairing__round__season=season).delete()
    LonePlayerScore.objects.filter(season_player__season=season).delete()
    TeamScore.objects.filter(team__season=season).delete()
    latereg_players = {latereg.player_id for latereg in
                       PlayerLateRegistration.objects.filter(round__season=season)}
    for sp in season.seasonplayer_set.all():
        if sp.player_id in latereg_players:
            sp.delete()
        else:
            sp.is_active = True
            sp.save()

    # Run each round
    for r in season.round_set.order_by('number'):
        print('Running round %d' % r.number)
        pairinggen.generate_pairings(r)
        r.publish_pairings = True
        r.save()
        simulate_round(r)
        r.is_completed = True
        r.save()
