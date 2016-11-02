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
    pairings_that_should_have_ratings = PlayerPairing.objects.exclude(game_link='', result='').exclude(white=None, black=None).nocache()
    pairings_that_need_ratings = pairings_that_should_have_ratings.filter(white_rating=None) | pairings_that_should_have_ratings.filter(black_rating=None)

    api_poll_count = 0

    for p in pairings_that_need_ratings.exclude(game_link=''):
        # Poll ratings for the game from the lichess API
        if p.game_id() is None:
            continue
        game_meta = lichessapi.get_game_meta(p.game_id(), priority=0, timeout=300)
        p.white_rating = game_meta['players']['white']['rating']
        p.black_rating = game_meta['players']['black']['rating']
        p.save()
        api_poll_count += 1
        if api_poll_count >= 100:
            # Limit the processing per task execution
            return

    for p in pairings_that_need_ratings.filter(game_link=''):
        if p.get_round() is None:
            continue
        if not p.get_round().is_completed:
            p.white_rating = p.white.rating
            p.black_rating = p.black.rating
        else:
            # Look for ratings from a close time period
            p.white_rating = _find_closest_rating(p.white, p.get_round().end_date, p.get_round().season)
            p.black_rating = _find_closest_rating(p.black, p.get_round().end_date, p.get_round().season)
        p.save()

    for b in PlayerBye.objects.filter(player_rating=None, round__publish_pairings=True).nocache():
        if not b.round.is_completed:
            b.player_rating = b.player.rating
        else:
            b.player_rating = _find_closest_rating(b.player, p.get_round().end_date, p.get_round().season)
        b.save()

    for tm in TeamMember.objects.filter(player_rating=None, team__season__is_completed=True).nocache():
        tm.player_rating = _find_closest_rating(tm.player, tm.team.season.end_date(), tm.team.season)
        tm.save()

    for alt in Alternate.objects.filter(player_rating=None, season_player__season__is_completed=True).nocache():
        alt.player_rating = _find_closest_rating(alt.season_player.player, alt.season_player.season.end_date(), alt.season_player.season)
        alt.save()

    for sp in SeasonPlayer.objects.filter(final_rating=None, season__is_completed=True).nocache():
        sp.final_rating = _find_closest_rating(sp.player, sp.season.end_date(), sp.season)
        sp.save()

def _find_closest_rating(player, date, season):
    if player is None:
        return None
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
        else:
            return p.black_rating

    pairings_by_date = sorted([(pairing_date(p), p) for p in pairings])
    if len(pairings_by_date) == 0:
        # Try to find the seed rating
        sp = SeasonPlayer.objects.filter(season=season, player=player).first()
        if sp is not None and sp.seed_rating is not None:
            return sp.seed_rating
        # Default to current rating
        return player.rating
    pairings_by_date_lt = [p for p in pairings_by_date if p[0] <= date]
    pairings_by_date_gt = [p for p in pairings_by_date if p[0] > date]
    if len(pairings_by_date_lt) > 0:
        # Get the rating AFTER the game
        p = pairings_by_date_lt[-1][1]
        if p.game_id() is not None:
            game_meta = lichessapi.get_game_meta(p.game_id(), priority=0, timeout=300)
            player_meta = game_meta['players']['white'] if p.white == player else game_meta['players']['black']
            if 'ratingDiff' in player_meta:
                return player_meta['rating'] + player_meta['ratingDiff']
        return rating(p)
    else:
        return rating(pairings_by_date_gt[0][1])

@app.task(bind=True)
def update_tv_state(self):
    games_starting = PlayerPairing.objects.filter(result='', game_link='', scheduled_time__lt=timezone.now()).nocache()
    games_in_progress = PlayerPairing.objects.filter(result='', tv_state='default').exclude(game_link='').nocache()

    for game in games_starting:
        try:
            league = game.get_round().season.league
            for meta in lichessapi.get_latest_game_metas(game.white.lichess_username, 5, priority=1, timeout=300):
                if meta['players']['white']['userId'].lower() == game.white.lichess_username.lower() and \
                        meta['players']['black']['userId'].lower() == game.black.lichess_username.lower() and \
                        meta['clock']['initial'] == league.time_control_initial() and \
                        meta['clock']['increment'] == league.time_control_increment() and \
                        meta['rated'] == True:
                    game.game_link = get_gamelink_from_gameid(meta['id'])
                    game.save()
        except Exception as e:
            logger.warning('Error updating tv state for %s: %s' % (game, e))

    for game in games_in_progress:
        gameid = get_gameid_from_gamelink(game.game_link)
        if gameid is not None:
            try:
                meta = lichessapi.get_game_meta(gameid, priority=1, timeout=300)
                if 'status' not in meta or meta['status'] != 'started':
                    game.tv_state = 'hide'
                if 'status' in meta and meta['status'] == 'draw':
                    game.result = '1/2-1/2'
                elif 'winner' in meta:
                    if meta['winner'] == 'white':
                        game.result = '1-0'
                    elif meta['winner'] == 'black':
                        game.result = '0-1'
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
