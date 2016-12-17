from heltour.tournament.models import *
from heltour.tournament import lichessapi, slackapi, pairinggen, \
    alternates_manager, signals
from heltour.celery import app
from celery.utils.log import get_task_logger
from datetime import datetime
from django.core.cache import cache
from heltour import settings
import reversion
from django.contrib import messages
from math import ceil
from django.core.urlresolvers import reverse
from heltour.tournament.workflows import RoundTransitionWorkflow
from django.dispatch.dispatcher import receiver

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
    for username, p in sorted(player_dict.items()):
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
            b.player_rating = _find_closest_rating(b.player, b.round.end_date, b.round.season)
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
    games_starting = games_starting.filter(loneplayerpairing__round__end_date__gt=timezone.now()) | \
                     games_starting.filter(teamplayerpairing__team_pairing__round__end_date__gt=timezone.now())
    games_in_progress = PlayerPairing.objects.filter(result='', tv_state='default').exclude(game_link='').nocache()

#     for game in games_starting:
#         try:
#             league = game.get_round().season.league
#             for meta in lichessapi.get_latest_game_metas(game.white.lichess_username, 5, priority=1, timeout=300):
#                 if meta['players']['white']['userId'].lower() == game.white.lichess_username.lower() and \
#                         meta['players']['black']['userId'].lower() == game.black.lichess_username.lower() and \
#                         meta['clock']['initial'] == league.time_control_initial() and \
#                         meta['clock']['increment'] == league.time_control_increment() and \
#                         meta['rated'] == True:
#                     game.game_link = get_gamelink_from_gameid(meta['id'])
#                     game.save()
#         except Exception as e:
#             logger.warning('Error updating tv state for %s: %s' % (game, e))

    for game in games_in_progress:
        gameid = get_gameid_from_gamelink(game.game_link)
        if gameid is not None:
            try:
                meta = lichessapi.get_game_meta(gameid, priority=1, timeout=300)
                if 'status' not in meta or meta['status'] != 'started':
                    game.tv_state = 'hide'
#                 if 'status' in meta and meta['status'] == 'draw':
#                     game.result = '1/2-1/2'
#                 elif 'winner' in meta:
#                     if meta['winner'] == 'white':
#                         game.result = '1-0'
#                     elif meta['winner'] == 'black':
#                         game.result = '0-1'
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

# How late an event is allowed to run before it's discarded instead
_max_lateness = timedelta(hours=1)

@app.task(bind=True)
def run_scheduled_events(self):
    logger.warning('RSE: start')
    with cache.lock('run_scheduled_events'):
        logger.warning('RSE: passed lock')
        for event in ScheduledEvent.objects.all():
            # Determine a range of times to search
            # If the comparison point (e.g. round start) is in the range, we run the event
            upper_bound = timezone.now() - event.offset
            lower_bound = max(event.last_run or event.date_created, timezone.now() - _max_lateness) - event.offset

            # Determine an upper bound for events that should be run before the next task execution
            # The idea is that we want events to be run as close to their scheduled time as possible,
            # not just at whatever interval this task happens to be run
            future_bound = upper_bound + settings.CELERYBEAT_SCHEDULE['run_scheduled_events']['schedule']
            future_event_time = None

            def matching_rounds(**kwargs):
                result = Round.objects.filter(**kwargs).filter(season__is_active=True)
                if event.league is not None:
                    result = result.filter(season__league=event.league)
                if event.season is not None:
                    result = result.filter(season=event.season)
                return result

            if event.relative_to == 'round_start':
                for obj in matching_rounds(start_date__gt=lower_bound, start_date__lte=upper_bound):
                    logger.warning('RSE: running event %s' % event.type)
                    run_event(event, obj)
                for obj in matching_rounds(start_date__gt=upper_bound, start_date__lte=future_bound):
                    future_event_time = obj.start_date + event.offset if future_event_time is None else min(future_event_time, obj.start_date + event.offset)
            elif event.relative_to == 'round_end':
                for obj in matching_rounds(end_date__gt=lower_bound, end_date__lte=upper_bound):
                    run_event(event, obj)
                    logger.warning('RSE: running event %s' % event.type)
                for obj in matching_rounds(end_date__gt=upper_bound, end_date__lte=future_bound):
                    future_event_time = obj.end_date + event.offset if future_event_time is None else min(future_event_time, obj.end_date + event.offset)

            # Schedule this task to be run again at the next event's scheduled time
            # Note: This could potentially lead to multiple tasks running at the same time. That's why we have a lock
            if future_event_time is not None:
                logger.warning('RSE: next event at %s' % future_event_time)
                run_scheduled_events.apply_async(args=[], eta=future_event_time)
    logger.warning('RSE: done')

def run_event(event, obj):
    event.last_run = timezone.now()
    event.save()

    if event.type == 'notify_mods_unscheduled' and isinstance(obj, Round):
        signals.notify_mods_unscheduled.send(sender=event.__class__, round_=obj)
    elif event.type == 'notify_mods_no_result' and isinstance(obj, Round):
        signals.notify_mods_no_result.send(sender=event.__class__, round_=obj)
    elif event.type == 'start_round_transition' and isinstance(obj, Round):
        workflow = RoundTransitionWorkflow(obj.season)
        warnings = workflow.warnings
        if len(warnings) > 0:
            signals.no_round_transition.send(sender=event.__class__, season=obj.season, warnings=warnings)
        else:
            msg_list = workflow.run(complete_round=True, complete_season=True, update_board_order=True, generate_pairings=True, background=True)
            signals.starting_round_transition.send(sender=event.__class__, season=obj.season, msg_list=msg_list)

@app.task(bind=True)
def generate_pairings(self, round_id, overwrite=False):
    round_ = Round.objects.get(pk=round_id)
    pairinggen.generate_pairings(round_, overwrite)
    round_.publish_pairings = False
    with reversion.create_revision():
        reversion.set_comment('Generated pairings.')
        round_.save()
    signals.pairings_generated.send(sender=generate_pairings, round_=round_)

@receiver(signals.generate_pairings, dispatch_uid='heltour.tournament.tasks')
def start_generate_pairings(sender, round_id, overwrite=False, **kwargs):
    generate_pairings.apply_async(args=[round_id, overwrite])

@app.task(bind=True)
def alternates_manager_tick(self):
    for season in Season.objects.filter(enable_alternates_manager=True):
        for board_number in season.board_number_list():
            alternates_manager.do_alternate_search(season, board_number)

