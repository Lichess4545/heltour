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

    # Figure out which players need to be replaced and which alternates have/haven't been contacted
    player_availabilities = PlayerAvailability.objects.filter(round=round_, is_available=False) \
                                                      .select_related('player').nocache()
    availability_modified_dates = {pa.player: pa.date_modified for pa in player_availabilities}
    round_pairings = TeamPlayerPairing.objects.filter(team_pairing__round=round_) \
                                              .select_related('white', 'black').nocache()
    players_in_round = {p.white for p in round_pairings} | {p.black for p in round_pairings}
    board_pairings = TeamPlayerPairing.objects.filter(team_pairing__round=round_, board_number=board_number, result='', game_link='') \
                                              .select_related('white', 'black').nocache()
    players_on_board = {p.white for p in board_pairings} | {p.black for p in board_pairings}
    teams_by_player = {p.white: p.white_team() for p in board_pairings}
    teams_by_player.update({p.black: p.black_team() for p in board_pairings})

    unavailable_players = {pa.player for pa in player_availabilities}
    players_that_need_replacements = sorted(players_on_board & unavailable_players, key=lambda p: availability_modified_dates[p])
    number_of_alternates_contacted = len(Alternate.objects.filter(season_player__season=season, board_number=board_number, status='contacted'))
    alternates_not_contacted = sorted(Alternate.objects.filter(season_player__season=season, board_number=board_number, status='waiting') \
                                                       .select_related('season_player__registration', 'season_player__player').nocache(), \
                                      key=lambda a: a.priority_date())

    # TODO: Detect when all searches are complete and:
    # 1. Set alternates contacted->waiting
    # 2. Message those alternates
    # TODO: Set the unresponsive status as appropriate

    # Continue the search for an alternate to fill each open spot
    for p in players_that_need_replacements:
        search, created = AlternateSearch.objects.get_or_create(round=round_, team=teams_by_player[p], board_number=board_number)
        if not search.is_active or search.status == 'all_contacted':
            # Search is over (or was manually disabled), move on to the next open spot
            continue

        if created:
            # Search has just started
            signals.alternate_search_started.send(sender=do_alternate_search, season=season, team=teams_by_player[p], \
                                                  board_number=board_number, round_=round_)
            search.status = 'started'
            search.save()

        # Figure out if it's time to contact the next alternate on the list
        # If not, we don't need to do anything for this open spot until the next tick
        if search.last_alternate_contact_date is None:
            do_contact = True
        else:
            time_since_last_contact = timezone.now() - search.last_alternate_contact_date
            do_contact = time_since_last_contact >= _alternate_contact_interval

        if do_contact:
            try:
                # Figure out which alternate to contact
                while True:
                    # This will throw an IndexError if no alternates are left on the list
                    alt_to_contact = alternates_not_contacted.pop(0)
                    # If the alternate is unavailable, or already playing a game this round, or has a red card,
                    # continue the loop and try the next one
                    if alt_to_contact.season_player.player not in unavailable_players and \
                            alt_to_contact.season_player.player not in players_in_round and \
                            alt_to_contact.season_player.games_missed < 2:
                        break

                # Contact the alternate, providing them with a pair of private links to respond
                alt_username = alt_to_contact.season_player.player.lichess_username
                league_tag = season.league.tag
                season_tag = season.tag
                auth = PrivateUrlAuth.objects.create(authenticated_user=alt_username, expires=round_.end_date)
                accept_url = reverse('by_league:by_season:alternate_accept_with_token', args=[league_tag, season_tag, auth.secret_token])
                decline_url = reverse('by_league:by_season:alternate_decline_with_token', args=[league_tag, season_tag, auth.secret_token])
                signals.alternate_needed.send(sender=do_alternate_search, alternate=alt_to_contact, accept_url=accept_url, decline_url=decline_url)
                alt_to_contact.status = 'contacted'
                alt_to_contact.save()
                search.last_alternate_contact_date = timezone.now()
                search.save()
            except IndexError:
                # No alternates left, so the search is over
                # The spot can still be filled if previously-contacted alternates end up responding
                signals.alternate_search_all_contacted.send(sender=do_alternate_search, season=season, team=teams_by_player[p], \
                                            board_number=board_number, round_=round_, number_contacted=number_of_alternates_contacted)
                search.status = 'all_contacted'
                search.save()

def alternate_accepted(alternate):
    # This is called by the alternate_accept endpoint
    # The alternate gets there via a private link sent to their slack
    season = alternate.season_player.season
    round_ = current_round(season)
    # Validate that the alternate is in the correct state
    if alternate.status != 'contacted':
        return False
    # Validate that the alternate doesn't already have a game in the round
    # Players can sometimes play multiple games (e.g. playing up a board), but that isn't done through the alternates manager
    if (TeamPlayerPairing.objects.filter(team_pairing__round=round_, white=alternate.season_player.player) | \
        TeamPlayerPairing.objects.filter(team_pairing__round=round_, black=alternate.season_player.player)).nocache().exists():
        return False
    # Find an open spot to fill, prioritized by the time the search started
    active_searches = AlternateSearch.objects.filter(round=round_, board_number=alternate.board_number, is_active=True) \
                                             .order_by('date_created').select_related('team').nocache()
    for search in active_searches:
        if search.still_needs_alternate():
            assignment, _ = AlternateAssignment.objects.update_or_create(round=round_, team=search.team, board_number=search.board_number, \
                                                                         defaults={'player': alternate.season_player.player, 'replaced_player': None})
            alternate.status = 'accepted'
            alternate.save()
            signals.alternate_assigned.send(sender=alternate_accepted, season=season, alt_assignment=assignment)
            return True
    return False

def alternate_declined(season, alternate):
    # This is called by the alternate_decline endpoint
    # The alternate gets there via a private link sent to their slack
    if alternate.status == 'waiting' or alternate.status == 'contacted':
        alternate.status = 'declined'
        alternate.save()
