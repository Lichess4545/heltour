import requests
from heltour import settings
from collections import namedtuple
import slackapi
from django.core.urlresolvers import reverse
from django.contrib.sites.models import Site
from heltour.tournament.models import *
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver
import logging
from heltour.tournament import lichessapi
import time

logger = logging.getLogger(__name__)

def _send_notification(notification_type, league, text):
    if league.enable_notifications:
        for ln in league.leaguechannel_set.filter(type=notification_type, send_messages=True):
            slackapi.send_message(ln.slack_channel, text)

def _message_user(league, username, text):
    if league.enable_notifications:
        slackapi.send_message('@%s' % username, text)

def _message_multiple_users(league, usernames, text):
    if league.enable_notifications:
        slackapi.send_message('+'.join(('@%s' % u for u in usernames)), text)

def _lichess_message(league, username, subject, text):
    if league.enable_notifications:
        lichessapi.send_mail(username, subject, text)

def _abs_url(url):
    site = Site.objects.get_current().domain
    return 'https://%s%s' % (site, url)

@receiver(post_save, sender=Registration, dispatch_uid='heltour.tournament.notify')
def registration_saved(instance, created, **kwargs):
    if not created:
        return
    league = instance.season.league
    reg_url = _abs_url(reverse('admin:review_registration', args=[instance.pk]) + '?_changelist_filters=status__exact%3Dpending%26season__id__exact%3D' + str(instance.season.pk))
    list_url = _abs_url(reverse('admin:tournament_registration_changelist') + '?status__exact=pending&season__id__exact=' + str(instance.season.pk))
    pending_count = instance.season.registration_set.filter(status='pending', season=instance.season).count()
    message = '@%s (%s) has <%s|registered> for %s. <%s|%d pending>' % (instance.lichess_username, instance.classical_rating, reg_url, league.name, list_url, pending_count)
    _send_notification('mod', league, message)

@receiver(post_save, sender=PlayerLateRegistration, dispatch_uid='heltour.tournament.notify')
def latereg_saved(instance, created, **kwargs):
    if not created:
        return
    league = instance.round.season.league
    manage_url = _abs_url(reverse('admin:manage_players', args=[instance.round.season.pk]))
    message = '@%s <%s|added> for round %d' % (instance.player, manage_url, instance.round.number)
    _send_notification('mod', league, message)

@receiver(post_save, sender=PlayerWithdrawal, dispatch_uid='heltour.tournament.notify')
def withdrawal_saved(instance, created, **kwargs):
    if not created:
        return
    league = instance.round.season.league
    manage_url = _abs_url(reverse('admin:manage_players', args=[instance.round.season.pk]))
    message = '@%s <%s|withdrawn> for round %d' % (instance.player, manage_url, instance.round.number)
    _send_notification('mod', league, message)

@receiver(signals.pairing_forfeit_changed, dispatch_uid='heltour.tournament.notify')
def pairing_forfeit_changed(instance, **kwargs):
    round_ = instance.get_round()
    if round_ is None:
        return
    league = round_.season.league
    white = instance.white.lichess_username.lower() if instance.white is not None else '?'
    black = instance.black.lichess_username.lower() if instance.black is not None else '?'
    message = '@%s vs @%s %s' % (white, black, instance.result or '*')
    _send_notification('mod', league, message)

@receiver(signals.player_account_status_changed, dispatch_uid='heltour.tournament.notify')
def player_account_status_changed(instance, old_value, new_value, **kwargs):
    season_players = instance.seasonplayer_set.select_related('season__league').nocache()
    pending_regs = Registration.objects.filter(lichess_username__iexact=instance.lichess_username, status='pending') \
                                       .select_related('season__league').nocache()
    league_set = {sp.season.league for sp in season_players} | {reg.season.league for reg in pending_regs}
    for league in league_set:
        latest_season = league.season_set.filter(is_active=True).order_by('-start_date', '-id').first()
        lichess_profile_url = 'https://en.lichess.org/@/%s' % instance.lichess_username
        if latest_season is not None:
            player_profile_url = _abs_url(reverse('by_league:by_season:player_profile', args=[league.tag, latest_season.tag, instance.lichess_username]))
        else:
            player_profile_url = _abs_url(reverse('by_league:player_profile', args=[league.tag, instance.lichess_username]))
        if old_value == 'normal':
            message = '@%s marked as %s on <%s|lichess>. <%s|Player profile>' % (_slack_user(instance), new_value, lichess_profile_url, player_profile_url)
        else:
            message = '@%s <%s|lichess> account status changed from %s to %s. <%s|Player profile>' % (_slack_user(instance), lichess_profile_url, old_value, new_value, player_profile_url)
        _send_notification('mod', league, message)

@receiver(signals.notify_mods_unscheduled, dispatch_uid='heltour.tournament.notify')
def notify_mods_unscheduled(round_, **kwargs):
    unscheduled_pairings = round_.pairings.filter(result='', scheduled_time=None).exclude(white=None).exclude(black=None).nocache()
    if len(unscheduled_pairings) == 0:
        message = 'All games in round %d are scheduled.' % round_.number
    else:
        pairing_strs = ('@%s vs @%s' % (p.white.lichess_username.lower(), p.black.lichess_username.lower()) for p in unscheduled_pairings)
        message = 'The following games are unscheduled: %s' % (', '.join(pairing_strs))
    _send_notification('mod', round_.season.league, message)

@receiver(signals.notify_mods_no_result, dispatch_uid='heltour.tournament.notify')
def notify_mods_no_result(round_, **kwargs):
    no_result_pairings = round_.pairings.filter(result='').exclude(white=None).exclude(black=None).nocache()
    if len(no_result_pairings) == 0:
        message = 'All games in round %d have results.' % round_.number
    else:
        pairing_strs = ('@%s vs @%s' % (p.white.lichess_username.lower(), p.black.lichess_username.lower()) for p in no_result_pairings)
        message = 'The following games are missing results: %s' % (', '.join(pairing_strs))
    _send_notification('mod', round_.season.league, message)

@receiver(signals.pairings_generated, dispatch_uid='heltour.tournament.notify')
def pairings_generated(round_, **kwargs):
    league = round_.season.league
    review_url = _abs_url(reverse('admin:review_pairings', args=[round_.pk]))
    message = 'Pairings generated for round %d. <%s|Review>' % (round_.number, review_url)
    _send_notification('mod', league, message)

@receiver(signals.no_round_transition, dispatch_uid='heltour.tournament.notify')
def no_round_transition(season, warnings, **kwargs):
    league = season.league
    message = 'Can\'t start the round transition.' + ''.join(['\n' + text for text, _ in warnings])
    _send_notification('no_transition', league, message)

@receiver(signals.starting_round_transition, dispatch_uid='heltour.tournament.notify')
def starting_round_transition(season, msg_list, **kwargs):
    league = season.league
    message = 'Starting automatic round transition...' + ''.join(['\n' + text for text, _ in msg_list])
    _send_notification('mod', league, message)

@receiver(signals.alternate_search_started, dispatch_uid='heltour.tournament.notify')
def alternate_search_started(season, team, board_number, round_, **kwargs):
    league = season.league

    team_pairing = team.get_teampairing(round_)
    if team_pairing is not None:
        pairing = team_pairing.teamplayerpairing_set.filter(board_number=board_number).exclude(white=None).exclude(black=None).nocache().first()
    else:
        pairing = None

    team_member = team.teammember_set.filter(board_number=board_number).first()
    if pairing is not None:
        player = pairing.white if pairing.white_team() == team else pairing.black
    elif team_member is not None:
        player = team_member.player
    else:
        player = None

    # Send a DM to the player being replaced
    if player is not None:
        message_to_replaced_player = '@%s: I am searching for an alternate to replace you for round %d, since you have been marked as unavailable. If this is a mistake, please contact a mod as soon as possible.' \
                                     % (_slack_user(player), round_.number)
        _message_user(league, _slack_user(player), message_to_replaced_player)

    # Send a DM to the opponent
    if pairing is not None:
        opponent = pairing.black if pairing.white_team() == team else pairing.white
        if opponent.is_available_for(round_):
            message_to_opponent = '@%s: Your opponent, @%s, has been marked as unavailable. I am searching for an alternate for you to play, please be patient.' \
                                  % (_slack_user(opponent), _slack_user(player))
            _message_user(league, _slack_user(opponent), message_to_opponent)

    # Broadcast a message to both team captains
    message = '%sI have started searching for an alternate for <@%s> on board %d of "%s" in round %d.' \
              % (_captains_ping(team, round_), _slack_user(player), board_number, team.name, round_.number)
    _send_notification('captains', league, message)

@receiver(signals.alternate_search_reminder, dispatch_uid='heltour.tournament.notify')
def alternate_search_reminder(season, team, board_number, round_, **kwargs):
    league = season.league

    team_pairing = team.get_teampairing(round_)
    if team_pairing is None:
        return
    pairing = team_pairing.teamplayerpairing_set.filter(board_number=board_number).exclude(white=None).exclude(black=None).nocache().first()
    if pairing is None:
        return
    player = pairing.white if pairing.white_team() == team else pairing.black

    # Broadcast a reminder to both team captains
    message = '%sI am still searching for an alternate for <@%s> on board %d of "%s" in round %d.' \
              % (_captains_ping(team, round_), _slack_user(player), board_number, team.name, round_.number)
    _send_notification('captains', league, message)

@receiver(signals.alternate_search_all_contacted, dispatch_uid='heltour.tournament.notify')
def alternate_search_all_contacted(season, team, board_number, round_, number_contacted, **kwargs):
    league = season.league
    # Broadcast a message to both team captains
    message = '%sI have messaged every eligible alternate for board %d of "%s". Still waiting for responses from %d.' % (_captains_ping(team, round_), board_number, team.name, number_contacted)
    _send_notification('captains', league, message)

@receiver(signals.alternate_search_failed, dispatch_uid='heltour.tournament.notify')
def alternate_search_failed(season, team, board_number, round_, **kwargs):
    league = season.league
    # Broadcast a message to both team captains
    message = '%sSorry, I could not find an alternate for board %d of "%s" in round %d.' \
              % (_captains_ping(team, round_), board_number, team.name, round_.number)
    _send_notification('captains', league, message)

@receiver(signals.alternate_assigned, dispatch_uid='heltour.tournament.notify')
def alternate_assigned(season, alt_assignment, **kwargs):
    league = season.league
    aa = alt_assignment

    opponent = _notify_alternate_and_opponent(league, aa)
    if opponent is not None:
        opponent_notified = ' Their opponent, @%s, has been notified.' % _slack_user(opponent)
    else:
        opponent_notified = ''

    # Send a message to the captains
    if aa.player == aa.replaced_player:
        message = '%sI have reassigned <@%s> to play on board %d of "%s" for round %d.%s' \
                  % (_captains_ping(aa.team, aa.round), _slack_user(aa.player), aa.board_number, aa.team.name, opponent_notified)
    else:
        message = '%sI have assigned <@%s> to play on board %d of "%s" in place of <@%s> for round %d.%s' \
                  % (_captains_ping(aa.team, aa.round), _slack_user(aa.player), aa.board_number, aa.team.name, _slack_user(aa.replaced_player), aa.round.number, opponent_notified)
    _send_notification('captains', league, message)

def _notify_alternate_and_opponent(league, aa):
    captain = aa.team.captain()
    if captain is not None:
        captain_text = ' The team captain is <@%s>.' % _slack_user(captain)
    else:
        captain_text = ''

    team_pairing = aa.team.get_teampairing(aa.round)
    if team_pairing is None:
        # Round hasn't started yet
        message_to_alternate = '@%s: You will be playing on board %d of "%s" for round %d.%s' \
                               % (_slack_user(aa.player), aa.board_number, aa.team.name, aa.round.number, captain_text)
        _message_user(league, _slack_user(aa.player), message_to_alternate)
        return None

    pairing = team_pairing.teamplayerpairing_set.filter(board_number=aa.board_number).exclude(white=None).exclude(black=None).nocache().first()
    if pairing is None:
        # No pairing yet for some reason
        message_to_alternate = '@%s: You will be playing on board %d of "%s" for round %d.%s' \
                               % (_slack_user(aa.player), aa.board_number, aa.team.name, aa.round.number, captain_text)
        _message_user(league, _slack_user(aa.player), message_to_alternate)
        return None

    opponent = pairing.black if pairing.white_team() == aa.team else pairing.white
    if not opponent.is_available_for(aa.round):
        # Still looking for an alternate for the opponent
        message_to_alternate = ('@%s: You are playing on board %d of "%s".%s\n' \
                               + 'I am still searching for another alternate for you to play, please be patient.') \
                               % (_slack_user(aa.player), aa.board_number, aa.team.name, captain_text)
        _message_user(league, _slack_user(aa.player), message_to_alternate)
        return None

    # Normal assignment
    message_to_alternate = ('@%s: You are playing on board %d of "%s".%s\n' \
                           + 'Please contact your opponent, <@%s>, as soon as possible.') \
                           % (_slack_user(aa.player), aa.board_number, aa.team.name, captain_text, _slack_user(opponent))
    _message_user(league, _slack_user(aa.player), message_to_alternate)

    # Send a DM to the opponent
    if aa.player == aa.replaced_player:
        message_to_opponent = '@%s: Your opponent, <@%s>, no longer requires an alternate. Please contact <@%s> as soon as possible.' \
                              % (_slack_user(opponent), _slack_user(aa.replaced_player), _slack_user(aa.player))
    elif aa.replaced_player is not None:
        message_to_opponent = '@%s: Your opponent, @%s, has been replaced by an alternate. Please contact your new opponent, <@%s>, as soon as possible.' \
                              % (_slack_user(opponent), _slack_user(aa.replaced_player), _slack_user(aa.player))
    else:
        message_to_opponent = '@%s: Your opponent has been replaced by an alternate. Please contact your new opponent, <@%s>, as soon as possible.' \
                              % (_slack_user(opponent), _slack_user(aa.player))
    _message_user(league, _slack_user(opponent), message_to_opponent)

    # Send configured notifications
    im_msg = 'You have been paired for Round {round} in {season}.\n' \
           + '<@{white}> (_white pieces_) vs <@{black}> (_black pieces_)\n' \
           + 'Send a direct message to your opponent, <@{opponent}>, as soon as possible.\n' \
           + 'When you have agreed on a time, post it in {scheduling_channel_link}.'

    mp_msg = 'You have been paired for Round {round} in {season}.\n' \
           + '<@{white}> (_white pieces_) vs <@{black}> (_black pieces_)\n' \
           + 'Message your opponent here as soon as possible.\n' \
           + 'When you have agreed on a time, post it in {scheduling_channel_link}.'

    li_subject = 'Round {round} - {league}'
    li_msg = 'You have been paired for Round {round} in {season}.\n' \
           + '@{white} (white pieces) vs @{black} (black pieces)\n' \
           + 'Message your opponent on Slack as soon as possible.\n' \
           + '{slack_url}\n' \
           + 'When you have agreed on a time, post it in {scheduling_channel}.'

    send_pairing_notification('round_started', pairing, im_msg, mp_msg, li_subject, li_msg)

    return opponent

@receiver(signals.alternate_needed, dispatch_uid='heltour.tournament.notify')
def alternate_needed(alternate, round_, response_time, accept_url, decline_url, **kwargs):
    league = round_.season.league
    player = alternate.season_player.player
    setting = PlayerNotificationSetting.get_or_default(player=player, type='alternate_needed', league=league, offset=None)

    # Send a DM to the alternate, regardless of settings
    round_str = 'this round' if round_.publish_pairings else 'round %d' % round_.number
    message = '@%s: A team needs an alternate for %s. Would you like to play? Please respond within %s.\n<%s|Yes, I want to play>\n<%s|No, maybe next week>' \
              % (_slack_user(alternate.season_player), round_str, _offset_str(response_time), _abs_url(accept_url), _abs_url(decline_url))
    _message_user(league, _slack_user(player), message)

    if setting.enable_lichess_mail:
        # Send a lichess message
        li_subject = 'Round %d - %s' % (round_.number, league.name)
        li_msg = 'A team needs an alternate for %s. Please check Slack for more information.\n' % round_str \
               + 'https://lichess4545.slack.com/messages/@chesster/'
        _lichess_message(league, _slack_user(player), li_subject, li_msg)

@receiver(signals.alternate_spots_filled, dispatch_uid='heltour.tournament.notify')
def alternate_spots_filled(alternate, response_time, **kwargs):
    league = alternate.season_player.season.league
    # Send a DM to the alternate
    if alternate.status == 'unresponsive':
        message = 'All available alternate spots have now been filled. You\'ve been moved to the bottom of the list since you didn\'t respond within %s.' % _offset_str(response_time)
    else:
        message = 'All available alternate spots have now been filled. You\'ll be notified again if another spot opens.'
    _message_user(league, _slack_user(alternate.season_player), message)

# TODO: Special notification for cancelling a search/reassigning the original player?

def _offset_str(offset):
    if offset is None:
        return '?'
    s = offset.total_seconds()
    if s == 3600:
        return '1 hour'
    elif s % 3600 == 0:
        return '%d hours' % (s / 3600)
    else:
        return '%d minutes' % (s / 60)

def send_pairing_notification(type_, pairing, im_msg, mp_msg, li_subject, li_msg, offset=None, player=None):
    if pairing.white is None or pairing.black is None:
        return
    round_ = pairing.get_round()
    season = round_.season
    league = season.league
    scheduling = LeagueChannel.objects.filter(league=league, type='scheduling').first()
    white = pairing.white.lichess_username.lower()
    black = pairing.black.lichess_username.lower()
    white_setting = PlayerNotificationSetting.get_or_default(player=pairing.white, type=type_, league=league, offset=offset)
    black_setting = PlayerNotificationSetting.get_or_default(player=pairing.black, type=type_, league=league, offset=offset)
    use_mpim = white_setting.enable_slack_mpim and black_setting.enable_slack_mpim and mp_msg
    send_to_white = player is None or player == pairing.white
    send_to_black = player is None or player == pairing.black

    common_params = {
        'white': white,
        'black': black,
        'round': round_.number,
        'season': season.name,
        'league': league.name,
        'time_control': league.time_control,
        'offset': _offset_str(offset),
        'scheduling_channel': scheduling.slack_channel if scheduling is not None else '#scheduling',
        'scheduling_channel_link': scheduling.channel_link() if scheduling is not None else '#scheduling'
    }
    white_params = {
        'self': white,
        'opponent': black,
        'color': 'white',
        'slack_url': 'https://lichess4545.slack.com/messages/%s%s/' % ('@chesster,' if use_mpim else '@', black)
    }
    white_params.update(common_params)
    black_params = {
        'self': black,
        'opponent': white,
        'color': 'black',
        'slack_url': 'https://lichess4545.slack.com/messages/%s%s/' % ('@chesster,' if use_mpim else '@', white)
    }
    black_params.update(common_params)

    # Send lichess mails
    if send_to_white and white_setting.enable_lichess_mail and li_subject and li_msg:
        _lichess_message(league, white, li_subject.format(**white_params), li_msg.format(**white_params))
    if send_to_black and black_setting.enable_lichess_mail and li_subject and li_msg:
        _lichess_message(league, black, li_subject.format(**black_params), li_msg.format(**black_params))
    # Send slack ims
    if send_to_white and (white_setting.enable_slack_im or white_setting.enable_slack_mpim) and not use_mpim and im_msg:
        _message_user(league, white, im_msg.format(**white_params))
    if send_to_black and (black_setting.enable_slack_im or black_setting.enable_slack_mpim) and not use_mpim and im_msg:
        _message_user(league, black, im_msg.format(**black_params))
    # Send slack mpim
    if send_to_white and use_mpim:
        _message_multiple_users(league, [white, black], mp_msg.format(**common_params))

@receiver(signals.notify_players_round_start, dispatch_uid='heltour.tournament.notify')
def notify_players_round_start(round_, **kwargs):
    im_msg = 'You have been paired for Round {round} in {season}.\n' \
           + '<@{white}> (_white pieces_) vs <@{black}> (_black pieces_)\n' \
           + 'Send a direct message to your opponent, <@{opponent}>, within 48 hours.\n' \
           + 'When you have agreed on a time, post it in {scheduling_channel_link}.'

    mp_msg = 'You have been paired for Round {round} in {season}.\n' \
           + '<@{white}> (_white pieces_) vs <@{black}> (_black pieces_)\n' \
           + 'Message your opponent here within 48 hours.\n' \
           + 'When you have agreed on a time, post it in {scheduling_channel_link}.'

    li_subject = 'Round {round} - {league}'
    li_msg = 'You have been paired for Round {round} in {season}.\n' \
           + '@{white} (white pieces) vs @{black} (black pieces)\n' \
           + 'Message your opponent on Slack within 48 hours.\n' \
           + '{slack_url}\n' \
           + 'When you have agreed on a time, post it in {scheduling_channel}.'

    season = round_.season
    league = season.league
    if not league.enable_notifications:
        return
    if not round_.publish_pairings or round_.is_completed:
        logger.error('Could not send round start notifications due to incorrect round state: %s' % round_)
        return
    unavailable_players = {pa.player for pa in PlayerAvailability.objects.filter(round=round_, is_available=False) \
                                                      .select_related('player').nocache()}
    for pairing in round_.pairings.select_related('white', 'black'):
        if season.alternates_manager_enabled() and (pairing.white in unavailable_players or pairing.black in unavailable_players):
            # Don't send a notification, since the alternates manager will handle it
            continue
        send_pairing_notification('round_started', pairing, im_msg, mp_msg, li_subject, li_msg)
        time.sleep(1)

@receiver(signals.notify_players_game_time, dispatch_uid='heltour.tournament.notify')
def notify_players_game_time(pairing, **kwargs):
    im_msg = 'Your game is about to start.\n' \
           + '<@{white}> (_white pieces_) vs <@{black}> (_black pieces_)\n' \
           + 'Send a <https://en.lichess.org/?user={opponent}#friend|lichess challenge> for a rated {time_control} game as {color}.'

    mp_msg = 'Your game is about to start.\n' \
           + '<@{white}> (_white pieces_) vs <@{black}> (_black pieces_)\n' \
           + 'Send a lichess challenge for a rated {time_control} game.'

    li_subject = 'Round {round} - {league}'
    li_msg = 'Your game is about to start.\n' \
           + '@{white} (white pieces) vs @{black} (black pieces)\n' \
           + 'Send a challenge for a rated {time_control} game as {color}.\n' \
           + 'https://en.lichess.org/?user={opponent}#friend' \

    if pairing.game_link == '' and pairing.result == '':
        send_pairing_notification('game_time', pairing, im_msg, mp_msg, li_subject, li_msg)

@receiver(signals.before_game_time, dispatch_uid='heltour.tournament.notify')
def before_game_time(player, pairing, offset, **kwargs):
    im_msg = 'Reminder: Your game will start in {offset}.\n' \
           + '<@{white}> (_white pieces_) vs <@{black}> (_black pieces_)'

    mp_msg = 'Reminder: Your game will start in {offset}.'

    li_subject = 'Round {round} - {league}'
    li_msg = 'Reminder: Your game will start in {offset}.\n' \
           + '@{white} (white pieces) vs @{black} (black pieces)'

    if pairing.game_link == '' and pairing.result == '':
        send_pairing_notification('before_game_time', pairing, im_msg, mp_msg, li_subject, li_msg, offset, player)

@receiver(signals.notify_players_unscheduled, dispatch_uid='heltour.tournament.notify')
def notify_players_unscheduled(round_, **kwargs):
    im_msg = 'Reminder: Your game is currently unscheduled.\n' \
           + '<@{white}> (_white pieces_) vs <@{black}> (_black pieces_)\n' \
           + 'When you have agreed on a time, post it in {scheduling_channel_link}.\n' \
           + 'If you have any issues, please contact a mod.'

    mp_msg = 'Reminder: Your game is currently unscheduled.\n' \
           + 'When you have agreed on a time, post it in {scheduling_channel_link}.\n' \
           + 'If you have any issues, please contact a mod.'

    li_subject = 'Round {round} - {league}'
    li_msg = 'Reminder: Your game is currently unscheduled.\n' \
           + '@{white} (white pieces) vs @{black} (black pieces)\n' \
           + 'When you have agreed on a time, post it in {scheduling_channel}.\n' \
           + 'If you have any issues, please contact a mod.'

    season = round_.season
    league = season.league
    if not league.enable_notifications:
        return
    if not round_.publish_pairings or round_.is_completed:
        logger.error('Could not send unscheduled notifications due to incorrect round state: %s' % round_)
        return
    unavailable_players = {pa.player for pa in PlayerAvailability.objects.filter(round=round_, is_available=False) \
                                                      .select_related('player').nocache()}
    for pairing in round_.pairings.filter(result='', game_link='', scheduled_time=None).select_related('white', 'black'):
        if season.alternates_manager_enabled() and (pairing.white in unavailable_players or pairing.black in unavailable_players):
            # Don't send a notification, since the alternates manager is searching for an alternate
            continue
        send_pairing_notification('unscheduled_game', pairing, im_msg, mp_msg, li_subject, li_msg)
        time.sleep(1)

@receiver(signals.game_warning, dispatch_uid='heltour.tournament.notify')
def game_warning(pairing, warning, **kwargs):
    im_msg = 'Important: Your game is not valid because *%s*\n' % warning \
           + 'If this was a mistake, please correct it and try again.\n' \
           + 'If this is not a league game, you may ignore this message.'

    mp_msg = 'Important: Your game is not valid because *%s*\n' % warning \
           + 'If this was a mistake, please correct it and try again.\n' \
           + 'If this is not a league game, you may ignore this message.'

    li_subject = 'Round {round} - {league}'
    li_msg = 'Important: Your game is not valid because %s\n' % warning \
           + 'If this was a mistake, please correct it and try again.\n' \
           + 'If this is not a league game, you may ignore this message.'

    send_pairing_notification('game_warning', pairing, im_msg, mp_msg, li_subject, li_msg)

def _slack_user(obj):
    if obj is None:
        return '?'
    if hasattr(obj, 'player'):
        return obj.player.lichess_username.lower()
    if hasattr(obj, 'lichess_username'):
        return obj.lichess_username.lower()
    return str(obj).lower()

def _captains_ping(team, round_):
    captains = []
    captain = team.captain()
    if captain is not None:
        captains.append(captain)
    opp = team.get_opponent(round_)
    if opp is not None:
        opp_captain = opp.captain()
        if opp_captain is not None:
            captains.append(opp_captain)
    return '' if len(captains) == 0 else '<@%s>: ' % _slack_user(captains[0]) if len(captains) == 1 else '<@%s>, <@%s>: ' % (_slack_user(captains[0]), _slack_user(captains[1]))
