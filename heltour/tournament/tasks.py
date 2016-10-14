from heltour.tournament.models import *
from heltour.tournament import lichessapi, slackapi
from heltour.celery import app
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

# Disabled for now because of rate-limiting
lichess_teams = [] # ['lichess4545-league']

@app.task(bind=True)
def update_player_ratings(self):
    players = Player.objects.all()
    player_dict = {p.lichess_username: p for p in players}

    # Query players from the bulk user endpoint based on our lichess teams
    for team_name in lichess_teams:
        for username, rating, games_played in lichessapi.enumerate_user_classical_rating_and_games_played(team_name, priority=0, timeout=300):
            # Remove the player from the dict
            p = player_dict.pop(username, None)
            if p is not None:
                p.rating, p.games_played = rating, games_played
                p.save()

    # Any players not found above will be queried individually
    for username, p in player_dict.items():
        try:
            p.rating, p.games_played = lichessapi.get_user_classical_rating_and_games_played(username, priority=0, timeout=300)
            p.save()
        except Exception as e:
            logger.warning('Error getting rating for %s: %s' % (username, e))

    logger.info('Updated ratings for %d players', len(players))

@app.task(bind=True)
def populate_historical_ratings(self):
    pairings_that_should_have_ratings = PlayerPairing.objects.exclude(game_link='', result='').nocache()
    pairings_that_need_ratings = pairings_that_should_have_ratings.filter(white_rating=None) | pairings_that_should_have_ratings.filter(black_rating=None)

    api_poll_count = 0

    for p in pairings_that_need_ratings.exclude(game_link=''):
        # Poll ratings for the game from the lichess API
        print 'Getting ratings for ' + p.game_id()
        game_meta = lichessapi.get_game_meta(p.game_id(), priority=0, timeout=300)
        p.white_rating = game_meta['players']['white']['rating']
        p.black_rating = game_meta['players']['black']['rating']
        p.save()
        api_poll_count += 1
        if api_poll_count >= 100:
            # Limit the processing per task execution
            pass # return

    for p in pairings_that_need_ratings.filter(game_link=''):
        if not p.get_round().is_completed:
            p.white_rating = p.white.rating
            p.black_rating = p.black.rating
        else:
            # Look for ratings from a close time period
            p.white_rating = _find_closest_rating(p.white, p.get_round().end_date, p.get_round().season)
            p.black_rating = _find_closest_rating(p.black, p.get_round().end_date, p.get_round().season)
        p.save()

    for b in PlayerBye.objects.filter(round__publish_pairings=True):
        if not b.round.is_completed:
            b.player_rating = b.player.rating
        else:
            b.player_rating = _find_closest_rating(b.player, p.get_round().end_date, p.get_round().season)

    for tm in TeamMember.objects.filter(player_rating=None, team__season__is_completed=True):
        tm.player_rating = _find_closest_rating(tm.player, tm.team.season.end_date(), tm.team.season)

    for alt in Alternate.objects.filter(player_rating=None, season_player__season__is_completed=True):
        alt.player_rating = _find_closest_rating(alt.player, alt.season_player.season.end_date(), alt.season_player.season)

    for sp in SeasonPlayer.objects.filter(final_rating=None, season__is_completed=True):
        sp.final_rating = _find_closest_rating(sp.player, sp.season.end_date(), sp.season)

def _find_closest_rating(player, date, season):
    if season.league.competitor_type == 'team':
        season_pairings = TeamPlayerPairing.objects.filter(team_pairing__round__season=season).exclude(white_rating=None, black_rating=None).nocache()
    else:
        season_pairings = LonePlayerPairing.objects.filter(round__season=season).exclude(white_rating=None, black_rating=None).nocache()
    pairings = season_pairings.filter(white=player) | season_pairings.filter(black=player)

    def pairing_date(p):
        if season.league.competitor_type == 'team':
            return p.team_pairing.round.end_date
        else:
            return p.round.end_date

    def rating(p):
        if p.white == player:
            return p.white_rating

    pairings_by_date = sorted([(pairing_date(p), p) for p in pairings])
    if len(pairings_by_date) == 0:
        # Default to current rating
        return player.rating
    pairings_by_date_lt = [p for p in pairings_by_date if p[0] <= date]
    pairings_by_date_gt = [p for p in pairings_by_date if p[0] > date]
    if len(pairings_by_date_lt) > 0:
        return pairings_by_date_lt[-1]
    else:
        return pairings_by_date_gt[0]

@app.task(bind=True)
def update_tv_state(self):
    games_to_update = PlayerPairing.objects.filter(result='', tv_state='default').exclude(game_link='').nocache()

    for game in games_to_update:
        gameid = get_gameid_from_gamelink(game.game_link)
        if gameid is not None:
            try:
                meta = lichessapi.get_game_meta(gameid, priority=1, timeout=300)
                if 'status' not in meta or meta['status'] != 'started':
                    game.tv_state = 'hide'
                    game.save()
            except Exception as e:
                logger.warning('Error updating tv state for %s: %s' % (game.game_link, e))

@app.task(bind=True)
def update_slack_users(self):
    slack_users = slackapi.get_user_list()
    name_set = {u.name.lower() for u in slack_users}
    for p in Player.objects.all():
        in_slack_group = p.lichess_username.lower() in name_set
        if in_slack_group != p.in_slack_group:
            p.in_slack_group = in_slack_group
            p.save()
