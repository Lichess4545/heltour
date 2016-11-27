import requests
from heltour import settings
from collections import namedtuple
import slackapi
from django.core.urlresolvers import reverse
from django.contrib.sites.models import Site

_events = {'mod': ['user_registered', 'latereg_created', 'withdrawl_created', 'pairing_forfeit_changed', 'unscheduled_games', 'no_result_games',
                   'pairings_generated', 'no_transition', 'starting_transition'],
           'captains': ['alternate_search_started', 'alternate_search_failed', 'alternate_assigned']}

_heltour_identity = {'username': 'heltour'}
_alternates_manager_identity = {'username': 'alternates-manager', 'icon': ':busts_in_silhouette:'}

def _send_notification(event_type, league, text, identity=_heltour_identity):
    for ln in league.leaguenotification_set.all():
        if event_type in _events[ln.type]:
            slackapi.send_message(ln.slack_channel, text, **identity)

def _message_user(username, text, identity=_heltour_identity):
    slackapi.send_message('@%s' % username, text, **identity)

def _abs_url(url):
    site = Site.objects.get_current().domain
    return 'https://%s%s' % (site, url)

def user_registered(reg):
    league = reg.season.league
    reg_url = _abs_url(reverse('admin:review_registration', args=[reg.pk]) + '?_changelist_filters=status__exact%3Dpending%26season__id__exact%3D' + str(reg.season.pk))
    list_url = _abs_url(reverse('admin:tournament_registration_changelist') + '?status__exact=pending&season__id__exact=' + str(reg.season.pk))
    pending_count = reg.season.registration_set.filter(status='pending', season=reg.season).count()
    message = '@%s (%s) has <%s|registered> for %s. <%s|%d pending>' % (reg.lichess_username, reg.classical_rating, reg_url, league.name, list_url, pending_count)
    _send_notification('user_registered', league, message)

def latereg_created(latereg):
    league = latereg.round.season.league
    manage_url = _abs_url(reverse('admin:manage_players', args=[latereg.round.season.pk]))
    message = '@%s <%s|added> for round %d' % (latereg.player, manage_url, latereg.round.number)
    _send_notification('latereg_created', league, message)

def withdrawl_created(withdrawl):
    league = withdrawl.round.season.league
    manage_url = _abs_url(reverse('admin:manage_players', args=[withdrawl.round.season.pk]))
    message = '@%s <%s|withdrawn> for round %d' % (withdrawl.player, manage_url, withdrawl.round.number)
    _send_notification('withdrawl_created', league, message)

def pairing_forfeit_changed(pairing):
    round_ = pairing.get_round()
    if round_ is None:
        return
    league = round_.season.league
    white = pairing.white.lichess_username.lower() if pairing.white is not None else '?'
    black = pairing.black.lichess_username.lower() if pairing.black is not None else '?'
    message = '@%s vs @%s %s' % (white, black, pairing.result or '*')
    _send_notification('pairing_forfeit_changed', league, message)

def unscheduled_games(round_, pairings):
    if len(pairings) == 0:
        message = 'All games in round %d are scheduled.' % round_.number
    else:
        pairing_strs = ('@%s vs @%s' % (p.white.lichess_username.lower(), p.black.lichess_username.lower()) for p in pairings)
        message = 'The following games are unscheduled: %s' % (', '.join(pairing_strs))
    _send_notification('unscheduled_games', round_.season.league, message)

def no_result_games(round_, pairings):
    if len(pairings) == 0:
        message = 'All games in round %d have results.' % round_.number
    else:
        pairing_strs = ('@%s vs @%s' % (p.white.lichess_username.lower(), p.black.lichess_username.lower()) for p in pairings)
        message = 'The following games are missing results: %s' % (', '.join(pairing_strs))
    _send_notification('no_result_games', round_.season.league, message)

def pairings_generated(round_):
    league = round_.season.league
    review_url = _abs_url(reverse('admin:review_pairings', args=[round_.pk]))
    message = 'Pairings generated for round %d. <%s|Review>' % (round_.number, review_url)
    _send_notification('pairings_generated', league, message)

def no_transition(season, warnings):
    league = season.league
    message = 'Can\'t start the round transition.' + ''.join(['\n' + text for text, _ in warnings])
    _send_notification('no_transition', league, message)

def starting_transition(season, msg_list):
    league = season.league
    message = 'Starting automatic round transition...' + ''.join(['\n' + text for text, _ in msg_list])
    _send_notification('starting_transition', league, message)

def alternate_search_started(season, team, board_number, round_):
    league = season.league
    team_member = team.teammember_set.filter(board_number=board_number).first()

    # Send a DM to the player being replaced
    if team_member is not None:
        message_to_replaced_player = '@%s: I am searching for an alternate to replace you for this round, since you have been marked as unavailable. If this is a mistake, please contact a mod as soon as possible.' \
                                     % team_member.player.lichess_username
        _message_user(team_member.player.lichess_username, message_to_replaced_player, _alternates_manager_identity)

    # Send a DM to the opponent
    opposing_team = team.get_opponent(round_)
    if opposing_team is not None:
        opponent = opposing_team.teammember_set.filter(board_number=board_number).first()
        if opponent is not None and team_member is not None:
            message_to_opponent = '@%s: Your opponent, @%s, has been marked as unavailable. I am searching for an alternate for you to play, please be patient.' \
                                  % (opponent.player.lichess_username, team_member.player.lichess_username)
            _message_user(team_member.player.lichess_username, message_to_opponent, _alternates_manager_identity)

    # Broadcast a message to both team captains
    message = '%sI have started searching for an alternate for @%s on board %d of "%s".' % (_captains_ping(team, round_), team_member, board_number, team.name)
    _send_notification('alternate_search_started', league, message)

def alternate_search_failed(season, team, board_number, round_):
    league = season.league
    # Broadcast a message to both team captains
    message = '%sI have messaged every eligible alternate for board %d of "%s". No responses yet.' % (_captains_ping(team, round_), board_number, team.name)
    _send_notification('alternate_search_failed', league, message)

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
                captain_text = ' The team captain is @%s.' % captain.player.lichess_username
            else:
                captain_text = ''
            message_to_alternate = ('@%s: You are playing on board %d of "%s".%s\n' \
                                   + 'Please contact your opponent, @%s, as soon as possible.') \
                                   % (aa.player.lichess_username, aa.board_number, aa.team.name, captain_text, opponent.player.lichess_username)
            _message_user(aa.player.lichess_username, message_to_alternate, _alternates_manager_identity)

            # Send a DM to the opponent
            if aa.replaced_player is not None:
                message_to_opponent = '@%s: Your opponent, @%s, has been replaced by an alternate. Please contact your new opponent, @%s, as soon as possible.' \
                                      % (opponent.player.lichess_username, aa.replaced_player.lichess_username, aa.player.lichess_username)
            else:
                message_to_opponent = '@%s: Your opponent has been replaced by an alternate. Please contact your new opponent, @%s, as soon as possible.' \
                                      % (opponent.player.lichess_username, aa.player.lichess_username)
            _message_user(opponent.player.lichess_username, message_to_opponent, _alternates_manager_identity)
            opponent_notified = 'Their opponent, @%s, has been notified.' % opponent
        else:
            opponent_notified = ''

    # Broadcast a message
    message = '%sI have assigned @%s to play on board %d of "%s" in place of %s.%s' % (_captains_ping(aa.team, aa.round_), aa.player, aa.board_number, aa.team.name, aa.replaced_player, opponent_notified)
    _send_notification('alternate_assigned', league, message)

# TODO: Special notification for cancelling a search/reassigning the original player?

def _captains_ping(team, round_):
    captains = []
    captain = team.captain()
    if captain is not None:
        captains.append(captain.player.lichess_username)
    opp = team.get_opponent(round_)
    if opp is not None:
        opp_captain = opp.captain()
        if opp_captain is not None:
            captains.append(opp_captain.player.lichess_username)
    return '' if len(captains) == 0 else '@%s: ' % captains[0] if len(captains) == 1 else '@%s, @%s: ' % (captains[0], captains[1])
