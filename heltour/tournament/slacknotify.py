import requests
from heltour import settings
from collections import namedtuple
import slackapi
from django.core.urlresolvers import reverse
from django.contrib.sites.models import Site
from heltour.tournament.models import *
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver

_heltour_identity = {'username': 'heltour'}
_alternates_manager_identity = {'username': 'alternates-manager', 'icon': ':busts_in_silhouette:'}

def _send_notification(notification_type, league, text, identity=_heltour_identity):
    for ln in league.leaguenotification_set.filter(type=notification_type):
        slackapi.send_message(ln.slack_channel, text, **identity)

def _message_user(username, text, identity=_heltour_identity):
    slackapi.send_message('@%s' % username, text, **identity)

def _abs_url(url):
    site = Site.objects.get_current().domain
    return 'https://%s%s' % (site, url)

@receiver(post_save, sender=Registration, dispatch_uid='heltour.tournament.slacknotify')
def registration_saved(instance, created, **kwargs):
    if not created:
        return
    league = instance.season.league
    reg_url = _abs_url(reverse('admin:review_registration', args=[instance.pk]) + '?_changelist_filters=status__exact%3Dpending%26season__id__exact%3D' + str(instance.season.pk))
    list_url = _abs_url(reverse('admin:tournament_registration_changelist') + '?status__exact=pending&season__id__exact=' + str(instance.season.pk))
    pending_count = instance.season.registration_set.filter(status='pending', season=instance.season).count()
    message = '@%s (%s) has <%s|registered> for %s. <%s|%d pending>' % (instance.lichess_username, instance.classical_rating, reg_url, league.name, list_url, pending_count)
    _send_notification('mod', league, message)

@receiver(post_save, sender=PlayerLateRegistration, dispatch_uid='heltour.tournament.slacknotify')
def latereg_saved(instance, created, **kwargs):
    if not created:
        return
    league = instance.round.season.league
    manage_url = _abs_url(reverse('admin:manage_players', args=[instance.round.season.pk]))
    message = '@%s <%s|added> for round %d' % (instance.player, manage_url, instance.round.number)
    _send_notification('mod', league, message)

@receiver(post_save, sender=PlayerWithdrawl, dispatch_uid='heltour.tournament.slacknotify')
def withdrawl_saved(instance, created, **kwargs):
    if not created:
        return
    league = instance.round.season.league
    manage_url = _abs_url(reverse('admin:manage_players', args=[instance.round.season.pk]))
    message = '@%s <%s|withdrawn> for round %d' % (instance.player, manage_url, instance.round.number)
    _send_notification('mod', league, message)

@receiver(signals.pairing_forfeit_changed, dispatch_uid='heltour.tournament.slacknotify')
def pairing_forfeit_changed(instance, **kwargs):
    round_ = instance.get_round()
    if round_ is None:
        return
    league = round_.season.league
    white = instance.white.lichess_username.lower() if instance.white is not None else '?'
    black = instance.black.lichess_username.lower() if instance.black is not None else '?'
    message = '@%s vs @%s %s' % (white, black, instance.result or '*')
    _send_notification('mod', league, message)

def unscheduled_games(round_, pairings):
    if len(pairings) == 0:
        message = 'All games in round %d are scheduled.' % round_.number
    else:
        pairing_strs = ('@%s vs @%s' % (p.white.lichess_username.lower(), p.black.lichess_username.lower()) for p in pairings)
        message = 'The following games are unscheduled: %s' % (', '.join(pairing_strs))
    _send_notification('mod', round_.season.league, message)

def no_result_games(round_, pairings):
    if len(pairings) == 0:
        message = 'All games in round %d have results.' % round_.number
    else:
        pairing_strs = ('@%s vs @%s' % (p.white.lichess_username.lower(), p.black.lichess_username.lower()) for p in pairings)
        message = 'The following games are missing results: %s' % (', '.join(pairing_strs))
    _send_notification('mod', round_.season.league, message)

def pairings_generated(round_):
    league = round_.season.league
    review_url = _abs_url(reverse('admin:review_pairings', args=[round_.pk]))
    message = 'Pairings generated for round %d. <%s|Review>' % (round_.number, review_url)
    _send_notification('mod', league, message)

def no_transition(season, warnings):
    league = season.league
    message = 'Can\'t start the round transition.' + ''.join(['\n' + text for text, _ in warnings])
    _send_notification('no_transition', league, message)

def starting_transition(season, msg_list):
    league = season.league
    message = 'Starting automatic round transition...' + ''.join(['\n' + text for text, _ in msg_list])
    _send_notification('mod', league, message)

def alternate_search_started(season, team, board_number, round_):
    league = season.league
    team_member = team.teammember_set.filter(board_number=board_number).first()

    # Send a DM to the player being replaced
    if team_member is not None:
        message_to_replaced_player = '@%s: I am searching for an alternate to replace you for this round, since you have been marked as unavailable. If this is a mistake, please contact a mod as soon as possible.' \
                                     % _slack_user(team_member)
        _message_user(_slack_user(team_member), message_to_replaced_player, _alternates_manager_identity)

    # Send a DM to the opponent
    opposing_team = team.get_opponent(round_)
    if opposing_team is not None:
        opponent = opposing_team.teammember_set.filter(board_number=board_number).first()
        if opponent is not None and team_member is not None:
            message_to_opponent = '@%s: Your opponent, @%s, has been marked as unavailable. I am searching for an alternate for you to play, please be patient.' \
                                  % (_slack_user(opponent), _slack_user(team_member))
            _message_user(_slack_user(opponent), message_to_opponent, _alternates_manager_identity)

    # Broadcast a message to both team captains
    message = '%sI have started searching for an alternate for @%s on board %d of "%s".' % (_captains_ping(team, round_), _slack_user(team_member), board_number, team.name)
    _send_notification('captains', league, message, _alternates_manager_identity)

def alternate_search_all_contacted(season, team, board_number, round_, number_contacted):
    league = season.league
    # Broadcast a message to both team captains
    message = '%sI have messaged every eligible alternate for board %d of "%s". Still waiting for responses from %d.' % (_captains_ping(team, round_), board_number, team.name, number_contacted)
    _send_notification('captains', league, message, _alternates_manager_identity)

def alternate_assigned(season, alt_assignment):
    league = season.league
    aa = alt_assignment

    opposing_team = aa.team.get_opponent(aa.round)
    if opposing_team is not None:
        opponent = opposing_team.teammember_set.filter(board_number=aa.board_number).first()
        if opponent is not None:
            # Send a DM to the alternate
            captain = aa.team.captain()
            if captain is not None:
                captain_text = ' The team captain is @%s.' % _slack_user(captain)
            else:
                captain_text = ''
            message_to_alternate = ('@%s: You are playing on board %d of "%s".%s\n' \
                                   + 'Please contact your opponent, @%s, as soon as possible.') \
                                   % (_slack_user(aa.player), aa.board_number, aa.team.name, captain_text, _slack_user(opponent))
            _message_user(_slack_user(aa.player), message_to_alternate, _alternates_manager_identity)

            # Send a DM to the opponent
            if aa.player == aa.replaced_player:
                message_to_opponent = '@%s: Your opponent, @%s, no longer requires an alternate. Please contact @%s as soon as possible.' \
                                      % (_slack_user(opponent), _slack_user(aa.replaced_player), _slack_user(aa.player))
            elif aa.replaced_player is not None:
                message_to_opponent = '@%s: Your opponent, @%s, has been replaced by an alternate. Please contact your new opponent, @%s, as soon as possible.' \
                                      % (_slack_user(opponent), _slack_user(aa.replaced_player), _slack_user(aa.player))
            else:
                message_to_opponent = '@%s: Your opponent has been replaced by an alternate. Please contact your new opponent, @%s, as soon as possible.' \
                                      % (_slack_user(opponent), _slack_user(aa.player))
            _message_user(_slack_user(opponent), message_to_opponent, _alternates_manager_identity)
            opponent_notified = ' Their opponent, @%s, has been notified.' % _slack_user(opponent)
        else:
            opponent_notified = ''

    # Broadcast a message
    if aa.player == aa.replaced_player:
        message = '%sI have reassigned @%s to play on board %d of "%s".%s' % (_captains_ping(aa.team, aa.round), _slack_user(aa.player), aa.board_number, aa.team.name, opponent_notified)
    else:
        message = '%sI have assigned @%s to play on board %d of "%s" in place of @%s.%s' % (_captains_ping(aa.team, aa.round), _slack_user(aa.player), aa.board_number, aa.team.name, _slack_user(aa.replaced_player), opponent_notified)
    _send_notification('captains', league, message, _alternates_manager_identity)

def alternate_needed(alt, accept_url, decline_url):
    # Send a DM to the alternate
    message = '@%s: A team needs an alternate this round. Would you like to play? Please respond within 48 hours.\n<%s|Yes, I want to play>\n<%s|No, maybe next week>' % (_slack_user(alt.season_player), _abs_url(accept_url), _abs_url(decline_url))
    _message_user(_slack_user(alt.season_player), message, _alternates_manager_identity)

# TODO: Special notification for cancelling a search/reassigning the original player?

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
    return '' if len(captains) == 0 else '@%s: ' % _slack_user(captains[0]) if len(captains) == 1 else '@%s, @%s: ' % (_slack_user(captains[0]), _slack_user(captains[1]))
