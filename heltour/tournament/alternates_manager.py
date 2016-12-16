from heltour.tournament.models import *
from django.core.urlresolvers import reverse

_alternate_contact_interval = timedelta(seconds=30)

def current_round(season):
    if not season.enable_alternates_manager:
        return None
    return season.round_set.filter(publish_pairings=True, is_completed=False).order_by('number').first()

def do_alternate_search(season, board_number):
    round_ = current_round(season)
    if round_ is None:
        return
    print 'Alternate search on bd %d' % board_number
    player_availabilities = PlayerAvailability.objects.filter(round=round_, is_available=False) \
                                                      .select_related('player').nocache()
    round_pairings = TeamPlayerPairing.objects.filter(team_pairing__round=round_) \
                                              .select_related('white', 'black').nocache()
    players_in_round = {p.white for p in round_pairings} | {p.black for p in round_pairings}
    board_pairings = TeamPlayerPairing.objects.filter(team_pairing__round=round_, board_number=board_number, result='', game_link='') \
                                              .select_related('white', 'black').nocache()
    players_on_board = {p.white for p in board_pairings} | {p.black for p in board_pairings}
    teams_by_player = {p.white: p.white_team() for p in board_pairings}
    teams_by_player.update({p.black: p.black_team() for p in board_pairings})

    unavailable_players = {pa.player for pa in player_availabilities}
    players_that_need_replacements = players_on_board & unavailable_players
    number_of_alternates_contacted = len(Alternate.objects.filter(season_player__season=season, board_number=board_number, status='contacted'))
    alternates_not_contacted = sorted(Alternate.objects.filter(season_player__season=season, board_number=board_number, status='waiting') \
                                                       .select_related('season_player__registration', 'season_player__player').nocache(), \
                                      key=lambda a: a.priority_date())

    # TODO: Detect when all searches are complete and:
    # 1. Set alternates contacted->waiting
    # 2. Message those alternates

    for p in players_that_need_replacements:
        search, _ = AlternateSearch.objects.get_or_create(round=round_, team=teams_by_player[p], board_number=board_number)
        if not search.is_active or search.status == 'all_contacted':
            continue

        if search.status == '':
            slacknotify.alternate_search_started(season, teams_by_player[p], board_number, round_)
            search.status = 'started'
            search.save()

        if search.last_alternate_contact_date is None:
            do_contact = True
        else:
            time_since_last_contact = timezone.now() - search.last_alternate_contact_date
            do_contact = time_since_last_contact >= _alternate_contact_interval

        if do_contact:
            try:
                while True:
                    alt_to_contact = alternates_not_contacted.pop(0)
                    if alt_to_contact.season_player.player not in unavailable_players and \
                            alt_to_contact.season_player.player not in players_in_round and \
                            alt_to_contact.season_player.games_missed < 2:
                        break

                alt_username = alt_to_contact.season_player.player.lichess_username
                league_tag = season.league.tag
                season_tag = season.tag
                auth = PrivateUrlAuth.objects.create(authenticated_user=alt_username, expires=round_.end_date)
                accept_url = reverse('by_league:by_season:alternate_accept_with_token', args=[league_tag, season_tag, auth.secret_token])
                decline_url = reverse('by_league:by_season:alternate_decline_with_token', args=[league_tag, season_tag, auth.secret_token])
                slacknotify.alternate_needed(alt_to_contact, accept_url, decline_url)
                alt_to_contact.status = 'contacted'
                alt_to_contact.save()
                search.last_alternate_contact_date = timezone.now()
                search.save()
            except IndexError:
                slacknotify.alternate_search_all_contacted(season, teams_by_player[p], board_number, round_, number_of_alternates_contacted)
                search.status = 'all_contacted'
                search.save()

def alternate_accepted(alternate):
    season = alternate.season_player.season
    round_ = current_round(season)
    if alternate.status != 'contacted':
        return False
    if (TeamPlayerPairing.objects.filter(team_pairing__round=round_, white=alternate.season_player.player) | \
        TeamPlayerPairing.objects.filter(team_pairing__round=round_, black=alternate.season_player.player)).nocache().exists():
        return False
    active_searches = AlternateSearch.objects.filter(round=round_, board_number=alternate.board_number, is_active=True) \
                                             .order_by('date_created').select_related('team').nocache()
    for search in active_searches:
        if search.still_needs_alternate():
            assignment, _ = AlternateAssignment.objects.update_or_create(round=round_, team=search.team, board_number=search.board_number, \
                                                                         defaults={'player': alternate.season_player.player, 'replaced_player': None})
            alternate.status = 'accepted'
            alternate.save()
            slacknotify.alternate_assigned(season, assignment)
            return True
    return False

def alternate_declined(season, alternate):
    if alternate.status == 'waiting' or alternate.status == 'contacted':
        alternate.status = 'declined'
        alternate.save()
