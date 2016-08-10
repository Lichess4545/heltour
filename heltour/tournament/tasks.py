from heltour.tournament.models import *
from heltour.tournament import lichessapi
from heltour.celery import app

@app.task(bind=True)
def update_player_ratings(self):
    players = Player.objects.all()
    for p in players:
        p.rating, p.games_played = lichessapi.get_user_classical_rating_and_games_played(p.lichess_username)
        p.save()
    return len(players)
