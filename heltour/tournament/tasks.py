from heltour.tournament.models import *
from heltour.tournament import lichessapi, slackapi, pairinggen, \
    alternates_manager, signals, uptime
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
from django.db.models.signals import post_save
from django.contrib.sites.models import Site
import time

logger = get_task_logger(__name__)

@app.task(bind=True)
def update_player_ratings(self):
    usernames = [p.lichess_username for p in Player.objects.all()]
    try:
        updated = 0
        for user_meta in lichessapi.enumerate_user_metas(usernames, priority=1):
            p = Player.objects.get(lichess_username__iexact=user_meta['id'])
            p.update_profile(user_meta)
            updated += 1
        logger.info('Updated ratings for %d/%d players' % (updated, len(usernames)))
    except Exception as e:
        logger.warning('Error getting ratings: %s' % e)

@app.task(bind=True)
def populate_historical_ratings(self):
    pairings_that_should_have_ratings = PlayerPairing.objects.exclude(game_link='', result='').exclude(white=None, black=None).nocache()
    pairings_that_need_ratings = pairings_that_should_have_ratings.filter(white_rating=None) | pairings_that_should_have_ratings.filter(black_rating=None)

    api_poll_count = 0

    for p in pairings_that_need_ratings.exclude(game_link=''):
        # Poll ratings for the game from the lichess API
        if p.game_id() is None:
            continue
        p.refresh_from_db()
        game_meta = lichessapi.get_game_meta(p.game_id(), priority=0, timeout=300)
        p.white_rating = game_meta['players']['white']['rating']
        p.black_rating = game_meta['players']['black']['rating']
        p.save(update_fields=['white_rating', 'black_rating'])
        api_poll_count += 1
        if api_poll_count >= 100:
            # Limit the processing per task execution
            return

    for p in pairings_that_need_ratings.filter(game_link=''):
        round_ = p.get_round()
        if round_ is None:
            continue
        season = round_.season
        league = season.league
        p.refresh_from_db()
        if not round_.is_completed:
            p.white_rating = p.white.rating_for(league)
            p.black_rating = p.black.rating_for(league)
        else:
            # Look for ratings from a close time period
            p.white_rating = _find_closest_rating(p.white, round_.end_date, season)
            p.black_rating = _find_closest_rating(p.black, round_.end_date, season)
        p.save(update_fields=['white_rating', 'black_rating'])

    for b in PlayerBye.objects.filter(player_rating=None, round__publish_pairings=True).nocache():
        b.refresh_from_db()
        if not b.round.is_completed:
            b.player_rating = b.player.rating_for(b.round.season.league)
        else:
            b.player_rating = _find_closest_rating(b.player, b.round.end_date, b.round.season)
        b.save(update_fields=['player_rating'])

    for tm in TeamMember.objects.filter(player_rating=None, team__season__is_completed=True).nocache():
        tm.refresh_from_db()
        tm.player_rating = _find_closest_rating(tm.player, tm.team.season.end_date(), tm.team.season)
        tm.save(update_fields=['player_rating'])

    for alt in Alternate.objects.filter(player_rating=None, season_player__season__is_completed=True).nocache():
        alt.refresh_from_db()
        alt.player_rating = _find_closest_rating(alt.season_player.player, alt.season_player.season.end_date(), alt.season_player.season)
        alt.save(update_fields=['player_rating'])

    for sp in SeasonPlayer.objects.filter(final_rating=None, season__is_completed=True).nocache():
        sp.refresh_from_db()
        sp.final_rating = _find_closest_rating(sp.player, sp.season.end_date(), sp.season)
        sp.save(update_fields=['final_rating'])

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
        return player.rating_for(season.league)
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

    for game in games_starting:
        try:
            league = game.get_round().season.league
            for meta in lichessapi.get_latest_game_metas(game.white.lichess_username, 5, priority=1, timeout=300):
                try:
                    if meta['players']['white']['user']['id'].lower() == game.white.lichess_username.lower() and \
                            meta['players']['black']['user']['id'].lower() == game.black.lichess_username.lower() and \
                            meta['clock']['initial'] == league.time_control_initial() and \
                            meta['clock']['increment'] == league.time_control_increment() and \
                            meta['rated'] == True:
                        game.game_link = get_gamelink_from_gameid(meta['id'])
                        game.save()
                except KeyError:
                    pass
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
                elif 'winner' in meta and meta['status'] != 'timeout': # timeout = claim victory (which isn't allowed)
                    if meta['winner'] == 'white':
                        game.result = '1-0'
                    elif meta['winner'] == 'black':
                        game.result = '0-1'
                game.save()
            except Exception as e:
                logger.warning('Error updating tv state for %s: %s' % (game.game_link, e))

@app.task(bind=True)
def update_lichess_presence(self):
    games_starting = PlayerPairing.objects.filter(\
                                                  result='', game_link='', \
                                                  scheduled_time__lt=timezone.now() + timedelta(minutes=5), \
                                                  scheduled_time__gt=timezone.now() - timedelta(minutes=22)) \
                                                  .exclude(white=None).exclude(black=None).select_related('white', 'black').nocache()
    games_starting = games_starting.filter(loneplayerpairing__round__end_date__gt=timezone.now()) | \
                     games_starting.filter(teamplayerpairing__team_pairing__round__end_date__gt=timezone.now())

    users = {}
    for game in games_starting:
        users[game.white.lichess_username.lower()] = game.white
        users[game.black.lichess_username.lower()] = game.black
    for status in lichessapi.enumerate_user_statuses(list(users.keys()), priority=1, timeout=60):
        if status.get('online'):
            user = users[status.get('id').lower()]
            for g in games_starting:
                if user in (g.white, g.black):
                    presence = g.get_player_presence(user)
                    presence.online_for_game = True
                    presence.save()

@app.task(bind=True)
def update_slack_users(self):
    slack_users = {u.id: u for u in slackapi.get_user_list()}
    for p in Player.objects.all():
        u = slack_users.get(p.slack_user_id)
        if u != None and u.tz_offset != (p.timezone_offset and p.timezone_offset.total_seconds()):
            p.timezone_offset = None if u.tz_offset is None else timedelta(seconds=u.tz_offset)
            p.save()

# How late an event is allowed to run before it's discarded instead
_max_lateness = timedelta(hours=1)

@app.task(bind=True)
def run_scheduled_events(self):
    now = timezone.now()
    with cache.lock('run_scheduled_events'):
        future_event_time = None
        for event in ScheduledEvent.objects.all():
            # Determine a range of times to search
            # If the comparison point (e.g. round start) is in the range, we run the event
            upper_bound = now - event.offset
            lower_bound = max(event.last_run or event.date_created, now - _max_lateness) - event.offset

            # Determine an upper bound for events that should be run before the next task execution
            # The idea is that we want events to be run as close to their scheduled time as possible,
            # not just at whatever interval this task happens to be run
            future_bound = upper_bound + settings.CELERYBEAT_SCHEDULE['run_scheduled_events']['schedule']

            def matching_rounds(**kwargs):
                result = Round.objects.filter(**kwargs).filter(season__is_active=True)
                if event.league is not None:
                    result = result.filter(season__league=event.league)
                if event.season is not None:
                    result = result.filter(season=event.season)
                return result

            def matching_pairings(**kwargs):
                team_result = PlayerPairing.objects.filter(**kwargs).filter(teamplayerpairing__team_pairing__round__season__is_active=True)
                lone_result = PlayerPairing.objects.filter(**kwargs).filter(loneplayerpairing__round__season__is_active=True)
                if event.league is not None:
                    team_result = team_result.filter(teamplayerpairing__team_pairing__round__season__league=event.league)
                    lone_result = lone_result.filter(loneplayerpairing__round__season__league=event.league)
                if event.season is not None:
                    team_result = team_result.filter(teamplayerpairing__team_pairing__round__season=event.season)
                    lone_result = lone_result.filter(loneplayerpairing__round__season=event.season)
                return team_result | lone_result

            if event.relative_to == 'round_start':
                for obj in matching_rounds(start_date__gt=lower_bound, start_date__lte=upper_bound):
                    event.run(obj)
                for obj in matching_rounds(start_date__gt=upper_bound, start_date__lte=future_bound):
                    future_event_time = obj.start_date + event.offset if future_event_time is None else min(future_event_time, obj.start_date + event.offset)
            elif event.relative_to == 'round_end':
                for obj in matching_rounds(end_date__gt=lower_bound, end_date__lte=upper_bound):
                    event.run(obj)
                for obj in matching_rounds(end_date__gt=upper_bound, end_date__lte=future_bound):
                    future_event_time = obj.end_date + event.offset if future_event_time is None else min(future_event_time, obj.end_date + event.offset)
            elif event.relative_to == 'game_scheduled_time':
                for obj in matching_pairings(scheduled_time__gt=lower_bound, scheduled_time__lte=upper_bound):
                    event.run(obj)
                for obj in matching_pairings(scheduled_time__gt=upper_bound, scheduled_time__lte=future_bound):
                    future_event_time = obj.scheduled_time + event.offset if future_event_time is None else min(future_event_time, obj.scheduled_time + event.offset)

        # Run ScheduledNotifications now
        upper_bound = now
        lower_bound = now - _max_lateness

        future_bound = upper_bound + settings.CELERYBEAT_SCHEDULE['run_scheduled_events']['schedule']

        for n in ScheduledNotification.objects.filter(notification_time__gt=lower_bound, notification_time__lte=upper_bound):
            n.run()
        for n in ScheduledNotification.objects.filter(notification_time__gt=upper_bound, notification_time__lte=future_bound):
            future_event_time = n.notification_time if future_event_time is None else min(future_event_time, n.notification_time)

        # Schedule this task to be run again at the next event's scheduled time
        # Note: This could potentially lead to multiple tasks running at the same time. That's why we have a lock
        if future_event_time is not None:
            run_scheduled_events.apply_async(args=[], eta=future_event_time)

@app.task(bind=True)
def round_transition(self, round_id):
    season = Round.objects.get(pk=round_id).season
    workflow = RoundTransitionWorkflow(season)
    warnings = workflow.warnings
    if len(warnings) > 0:
        signals.no_round_transition.send(sender=round_transition, season=season, warnings=warnings)
    else:
        msg_list = workflow.run(complete_round=True, complete_season=True, update_board_order=True, generate_pairings=True, background=True)
        signals.starting_round_transition.send(sender=round_transition, season=season, msg_list=msg_list)

@receiver(signals.do_round_transition, dispatch_uid='heltour.tournament.tasks')
def do_round_transition(sender, round_id, **kwargs):
    round_transition.apply_async(args=[round_id])

@app.task(bind=True)
def generate_pairings(self, round_id, overwrite=False):
    round_ = Round.objects.get(pk=round_id)
    pairinggen.generate_pairings(round_, overwrite)
    round_.publish_pairings = False
    with reversion.create_revision():
        reversion.set_comment('Generated pairings.')
        round_.save()
    signals.pairings_generated.send(sender=generate_pairings, round_=round_)

@receiver(signals.do_generate_pairings, dispatch_uid='heltour.tournament.tasks')
def do_generate_pairings(sender, round_id, overwrite=False, **kwargs):
    generate_pairings.apply_async(args=[round_id, overwrite], countdown=1)

@app.task(bind=True)
def validate_registration(self, reg_id):
    reg = Registration.objects.get(pk=reg_id)

    fail_reason = None
    warnings = []

    try:
        user_meta = lichessapi.get_user_meta(reg.lichess_username, 1)
        player, _ = Player.get_or_create(reg.lichess_username)
        player.update_profile(user_meta)
        reg.classical_rating = player.rating_for(reg.season.league)
        reg.peak_classical_rating = lichessapi.get_peak_rating(reg.lichess_username, reg.season.league.rating_type)
        reg.has_played_20_games = not player.provisional_for(reg.season.league)
        if player.account_status != 'normal':
            fail_reason = 'The lichess user "%s" has the "%s" mark.' % (reg.lichess_username, player.account_status)
        if reg.already_in_slack_group and not player.slack_user_id:
            reg.already_in_slack_group = False
    except lichessapi.ApiWorkerError:
        fail_reason = 'The lichess user "%s" could not be found.' % reg.lichess_username

    if not reg.has_played_20_games:
        warnings.append('Has a provisional rating.')
    if not reg.can_commit and (reg.season.league.competitor_type != 'team' or reg.alternate_preference != 'alternate'):
        warnings.append('Can\'t commit to a game per week.')
    if not reg.agreed_to_rules:
        warnings.append('Didn\'t agree to rules.')

    if fail_reason:
        reg.validation_ok = False
        reg.validation_warning = False
        comment_text = 'Validation error: %s' % fail_reason
    elif warnings:
        reg.validation_ok = True
        reg.validation_warning = True
        comment_text = 'Validation warning: %s' % ' '.join(warnings)
    else:
        reg.validation_ok = True
        reg.validation_warning = False
        comment_text = 'Validated.'
    add_system_comment(reg, comment_text)

    with reversion.create_revision():
        reversion.set_comment('Validated registration.')
        reg.save()

@receiver(post_save, sender=Registration, dispatch_uid='heltour.tournament.tasks')
def registration_saved(instance, created, **kwargs):
    if not created:
        return
    validate_registration.apply_async(args=[instance.pk], countdown=1)

@receiver(signals.do_validate_registration, dispatch_uid='heltour.tournament.tasks')
def do_validate_registration(reg_id, **kwargs):
    validate_registration.apply_async(args=[reg_id], countdown=1)

@app.task(bind=True)
def pairings_published(self, round_id, overwrite=False):
    round_ = Round.objects.get(pk=round_id)
    season = round_.season
    league = season.league

    if round_.number == season.rounds and season.registration_open and league.get_leaguesetting().close_registration_at_last_round:
        with reversion.create_revision():
            reversion.set_comment('Close registration')
            season.registration_open = False
            season.save()

    slackapi.send_control_message('refresh pairings %s' % league.tag)
    alternates_manager.round_pairings_published(round_)
    signals.notify_mods_pairings_published.send(sender=pairings_published, round_=round_)
    signals.notify_players_round_start.send(sender=pairings_published, round_=round_)
    signals.notify_mods_round_start_done.send(sender=pairings_published, round_=round_)

@receiver(signals.do_pairings_published, dispatch_uid='heltour.tournament.tasks')
def do_pairings_published(sender, round_id, **kwargs):
    pairings_published.apply_async(args=[round_id], countdown=1)

@app.task(bind=True)
def schedule_publish(self, round_id):
    with cache.lock('schedule_publish'):
        round_ = Round.objects.get(pk=round_id)
        if round_.publish_pairings:
            # Already published
            return
        round_.publish_pairings = True
        round_.save()
    # Update ranks in case of manual edits
    rank_dict = lone_player_pairing_rank_dict(round_.season)
    for lpp in round_.loneplayerpairing_set.all().nocache():
        lpp.refresh_ranks(rank_dict)
        with reversion.create_revision():
            reversion.set_comment('Published pairings.')
            lpp.save()
    for bye in round_.playerbye_set.all():
        bye.refresh_rank(rank_dict)
        with reversion.create_revision():
            reversion.set_comment('Published pairings.')
            bye.save()

@receiver(signals.do_schedule_publish, dispatch_uid='heltour.tournament.tasks')
def do_schedule_publish(sender, round_id, eta, **kwargs):
    schedule_publish.apply_async(args=[round_id], eta=eta)
    if eta > timezone.now():
        signals.publish_scheduled.send(sender=do_schedule_publish, round_id=round_id, eta=eta)

@app.task(bind=True)
def notify_slack_link(self, player):
    email = slackapi.get_user(player.slack_user_id).email
    msg = 'Your lichess account has been successfully linked with the Slack account "%s".' % email
    lichessapi.send_mail(lichess_username, 'Slack Account Linked', msg)

@receiver(signals.slack_account_linked, dispatch_uid='heltour.tournament.tasks')
def do_notify_slack_link(player, **kwargs):
    notify_slack_link.apply_async(args=[player], countdown=1)

@app.task(bind=True)
def create_team_channel(self, team_ids):
    intro_message = 'Welcome! This is your private team channel. Feel free to chat, study, discuss strategy, or whatever you like!\n' \
                      + 'You need to pick a team captain and a team name by {season_start}.\n' \
                      + 'Once you\'ve chosen (or if you need help with anything), contact one of the moderators:\n' \
                      + '{mods}'

    for team in Team.objects.filter(id__in=team_ids).select_related('season__league').nocache():
        pairings_url = abs_url(reverse('by_league:by_season:pairings_by_team', args=[team.season.league.tag, team.season.tag, team.number]))
        mods = team.season.league.leaguemoderator_set.filter(is_active=True)
        mods_str = ' '.join(('<@%s>' % lm.player.lichess_username.lower() for lm in mods))
        season_start = '?' if team.season.start_date is None else team.season.start_date.strftime('%b %-d')
        intro_message_formatted = intro_message.format(mods=mods_str, season_start=season_start)
        team_members = team.teammember_set.select_related('player').nocache()
        user_ids = [tm.player.slack_user_id for tm in team_members]
        channel_name = 'team-%d-s%s' % (team.number, team.season.tag)

        try:
            group = slackapi.create_group(channel_name)
            time.sleep(1)
        except slackapi.NameTaken:
            logger.error('Could not create slack team, name taken: %s' % channel_name)
            continue
        channel_ref = '#%s' % group.name
        for user_id in user_ids:
            if user_id:
                try:
                    slackapi.invite_to_group(group.id, user_id)
                except slackapi.SlackError:
                    logger.exception('Could not invite %s to slack' % user_id)
                time.sleep(1)
        slackapi.invite_to_group(group.id, settings.CHESSTER_USER_ID)
        time.sleep(1)
        with reversion.create_revision():
            reversion.set_comment('Creating slack channel')
            team.slack_channel = group.id
            team.save()

        slackapi.set_group_topic(group.id, pairings_url)
        time.sleep(1)
        slackapi.leave_group(group.id)
        time.sleep(1)
        slackapi.send_message(channel_ref, intro_message_formatted)
        time.sleep(1)

@receiver(signals.do_create_team_channel, dispatch_uid='heltour.tournament.tasks')
def do_create_team_channel(sender, team_ids, **kwargs):
    create_team_channel.apply_async(args=[team_ids], countdown=1)

@app.task(bind=True)
def alternates_manager_tick(self):
    for season in Season.objects.filter(is_active=True, is_completed=False):
        if season.alternates_manager_enabled():
            alternates_manager.tick(season)

@app.task(bind=True)
def celery_is_up(self):
    uptime.celery.is_up = True

@receiver(post_save, sender=PlayerPairing, dispatch_uid='heltour.tournament.tasks')
def pairing_changed(instance, created, **kwargs):
    if instance.game_link != '' and instance.result == '':
        game_id = get_gameid_from_gamelink(instance.game_link)
        if game_id:
            lichessapi.add_watch(game_id)
