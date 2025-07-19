from __future__ import annotations
# ^ for annotating unions with | syntax, can be removed once we upgrade to python 3.10+
import json
import re
import sys
import textwrap
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, List
from more_itertools import divide, first

import reversion
from django.core.cache import cache
from django.db.models import Q, QuerySet
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver
from django.urls import reverse
from django.utils import timezone
from django_stubs_ext import ValuesQuerySet

from heltour import settings
from heltour.celery import app
from heltour.tournament import (
    alternates_manager,
    lichessapi,
    pairinggen,
    signals,
    slackapi,
    uptime,
)
from heltour.tournament.models import (
    Alternate,
    Broadcast,
    BroadcastRound,
    LeagueChannel,
    LonePlayerPairing,
    Player,
    PlayerBye,
    PlayerPairing,
    Registration,
    Round,
    ScheduledEvent,
    ScheduledNotification,
    Season,
    SeasonPlayer,
    Team,
    TeamMember,
    TeamPlayerPairing,
    abs_url,
    get_gameid_from_gamelink,
    get_gamelink_from_gameid,
    logger,
    lone_player_pairing_rank_dict,
)
from heltour.tournament.workflows import RoundTransitionWorkflow

# see https://lichess.org/api#tag/Broadcasts/operation/broadcastRoundUpdate for game ids
MAX_GAMES_LICHESS_BROADCAST: int = 12

UsernamesQuerySet = ValuesQuerySet[Player, Dict[str, str]]

def to_usernames(users: UsernamesQuerySet) -> List[str]:
    return list(users.values_list("lichess_username", flat=True))

def just_username(qs: QuerySet[Player]) -> UsernamesQuerySet:
    return qs \
        .order_by('lichess_username') \
        .values('lichess_username') \
        .distinct()

def active_player_usernames() -> List[str]:
    players_qs = Player.objects.all()
    active_qs = players_qs.filter(seasonplayer__season__is_completed=False)
    return to_usernames(just_username(active_qs))

def registrations_needing_updates(without_usernames: List[str]) -> List[str]:
    _24_hours = timezone.now() - timedelta(hours=24)
    active_regs = (
        Registration.objects.filter(
            status__exact="pending",
            season__registration_open=True,
            player__date_modified__lte=_24_hours,
        )
        .exclude(player__lichess_username__in=without_usernames)
        .values_list("player", flat=True)
    )
    reg_players = Player.objects.filter(pk__in=active_regs)
    return to_usernames(just_username(reg_players))

@app.task()
def update_player_ratings(usernames: list[str] = []) -> None:
    if len(usernames) == 0:
        active_players = active_player_usernames()
        registered_players = registrations_needing_updates(
            without_usernames=active_players
        )
        first24th = list(first(divide(24, registered_players)))
        usernames = active_players + first24th
    logger.info(f"[START] Updating {len(usernames)} player ratings")
    updated = 0
    try:
        for user_meta in lichessapi.enumerate_user_metas(usernames, priority=1):
            p = Player.objects.get(lichess_username__iexact=user_meta['id'])
            p.update_profile(user_meta)
            updated += 1
        logger.info(f'[FINISHED] Updated {updated}/{len(usernames)} player ratings')
    except Exception as e:
        logger.warning(f'[ERROR] Error getting ratings: {e}')
        logger.warning(f'[ERROR] Only updated {updated}/{len(usernames)} player ratings')

def pairings_that_need_ratings() -> QuerySet[PlayerPairing]:
    return PlayerPairing.objects.exclude(
            game_link='',
            result=''
        ).exclude(
            white=None,
            black=None
        ).filter(
            Q(white_rating=None) | Q(black_rating=None)
        ).nocache()

@app.task()
def populate_historical_ratings():
    pairings_qs = pairings_that_need_ratings()

    api_poll_count = 0

    for p in pairings_qs.exclude(game_link=''):
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

    for p in pairings_qs.filter(game_link=''):
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

    for b in PlayerBye.objects.filter(
        player_rating=None,
        round__publish_pairings=True,
        player__account_status='normal'
    ).nocache():
        b.refresh_from_db()
        if not b.round.is_completed:
            b.player_rating = b.player.rating_for(b.round.season.league)
        else:
            b.player_rating = _find_closest_rating(b.player, b.round.end_date, b.round.season)
        b.save(update_fields=['player_rating'])

    for tm in TeamMember.objects.filter(
        player_rating=None,
        team__season__is_completed=True,
        player__account_status='normal'
    ).nocache():
        tm.refresh_from_db()
        tm.player_rating = _find_closest_rating(tm.player, tm.team.season.end_date(),
                                                tm.team.season)
        tm.save(update_fields=['player_rating'])

    for alt in Alternate.objects.filter(
        player_rating=None,
        season_player__season__is_completed=True,
        season_player__player__account_status='normal'
    ).nocache():
        alt.refresh_from_db()
        alt.player_rating = _find_closest_rating(alt.season_player.player,
                                                 alt.season_player.season.end_date(),
                                                 alt.season_player.season)
        alt.save(update_fields=['player_rating'])

    for sp in SeasonPlayer.objects.filter(
        final_rating=None,
        season__is_completed=True,
        player__account_status='normal'
    ).nocache():
        sp.refresh_from_db()
        sp.final_rating = _find_closest_rating(sp.player, sp.season.end_date(), sp.season)
        sp.save(update_fields=['final_rating'])


def _find_closest_rating(player, date, season):
    if player is None:
        return None
    if season.league.competitor_type == 'team':
        season_pairings = TeamPlayerPairing.objects.filter(
            team_pairing__round__season=season).exclude(white_rating=None,
                                                        black_rating=None).nocache()
    else:
        season_pairings = LonePlayerPairing.objects.filter(round__season=season).exclude(
            white_rating=None, black_rating=None).nocache()
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

    pairings_by_date = sorted([(pairing_date(p), p) for p in pairings], key=lambda p: p[0])
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
            try:
                game_meta = lichessapi.get_game_meta(p.game_id(), priority=0, timeout=300)
                player_meta = game_meta['players']['white'] if p.white == player else \
                    game_meta['players']['black']
                if 'ratingDiff' in player_meta:
                    return player_meta['rating'] + player_meta['ratingDiff']
            except lichessapi.ApiClientError:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logger.error(f'[ERROR] ApiClient: Error fetching game {p.game_id()}')
                stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
                logger.error(stacktrace)
                return None
            except Exception:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logger.error("[ERROR] General Exception: This should really be an ApiClientError.")
                stacktrace = traceback.format_exception(exc_type, exc_value, exc_traceback)
                logger.error(stacktrace)
                return None
        return rating(p)
    else:
        return rating(pairings_by_date_gt[0][1])


@app.task()
def update_tv_state():
    games_starting = PlayerPairing.objects.filter(result='', game_link='',
                                                  scheduled_time__lt=timezone.now()).nocache()
    games_starting = games_starting.filter(loneplayerpairing__round__end_date__gt=timezone.now()) | \
                     games_starting.filter(
                         teamplayerpairing__team_pairing__round__end_date__gt=timezone.now())
    games_in_progress = PlayerPairing.objects.filter(Q(result='') & (Q(tv_state='default') | Q(tv_state='has_moves'))).exclude(
        game_link='').nocache()

    for game in games_starting:
        try:
            league = game.get_round().season.league
            roundstart = round(game.get_round().start_date.timestamp()*1000) # round start in miliseconds
            for meta in lichessapi.get_latest_game_metas(lichess_username=game.white.lichess_username,
                                                         variant=league.rating_type, since=roundstart,
                                                         number=5, opponent=game.black.lichess_username, priority=1,
                                                         timeout=300):
                try:
                    if (meta['players']['white']['user'][
                        'id'].lower() == game.white.lichess_username.lower() and
                        meta['players']['black']['user'][
                            'id'].lower() == game.black.lichess_username.lower() and
                        meta['clock']['initial'] == league.time_control_initial() and
                        meta['clock']['increment'] == league.time_control_increment() and
                        meta['perf'] == league.rating_type and
                        meta['rated'] is True and
                        meta['status'] != 'aborted'):
                        game.game_link = get_gamelink_from_gameid(meta['id'])
                        if ' ' in meta.get('moves'): # ' ' indicates >= 2 moves
                            game.tv_state = 'has_moves'
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
                if 'moves' in meta and ' ' in meta['moves']: # ' ' indicates >= 2 moves
                    game.tv_state = 'has_moves'
                if 'status' in meta and meta['status'] == 'draw':
                    game.result = '1/2-1/2'
                if meta.get('status') == 'aborted':
                    game.game_link = ''
                elif 'winner' in meta and meta[
                    'status'] != 'timeout':  # timeout = claim victory (which isn't allowed)
                    if meta['winner'] == 'white':
                        game.result = '1-0'
                    elif meta['winner'] == 'black':
                        game.result = '0-1'
                game.save()
            except Exception as e:
                logger.warning('Error updating tv state for %s: %s' % (game.game_link, e))


@app.task()
def update_lichess_presence():
    games_starting = PlayerPairing.objects.filter(
        result='', tv_state='default',
        scheduled_time__lt=timezone.now() + timedelta(minutes=5),
        scheduled_time__gt=timezone.now() - timedelta(minutes=22)
        ).exclude(white=None).exclude(black=None).select_related('white', 'black').nocache()
    games_starting = (games_starting.filter(loneplayerpairing__round__end_date__gt=timezone.now()) |
                      games_starting.filter(
                         teamplayerpairing__team_pairing__round__end_date__gt=timezone.now()))

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


@app.task()
def update_slack_users():
    slack_users = {u.id: u for u in slackapi.get_user_list()}
    for p in Player.objects.all():
        u = slack_users.get(p.slack_user_id)
        if u is not None and u.tz_offset != (p.timezone_offset and p.timezone_offset.total_seconds()):
            p.timezone_offset = None if u.tz_offset is None else timedelta(seconds=u.tz_offset)
            p.save()


def _expire_bad_tokens(*, league_games, bad_token):
    # set expiration of rejected token to yesterday, so we know to not use it anymore.
    for game in league_games:
        for token in [game.get_white_oauth_token(), game.get_black_oauth_token()]:
            if token.access_token==bad_token:
                token.expire()
                return None # only one oauth_token can be the bad token, so we do not need to proceed the function


def _start_league_games(*, tokens, clock, increment, do_clockstart, clockstart, clockstart_in, variant, leaguename, league_games):
    result = None
    try:
        result = lichessapi.bulk_start_games(tokens=tokens, clock=clock, increment=increment, do_clockstart=do_clockstart, clockstart=clockstart, clockstart_in=clockstart_in, variant=variant, leaguename=leaguename)
    except lichessapi.ApiClientError as err:
        logger.info(f"Received error from lichess api: {err}")
        logger.info("Attempting to recover by removing rejected tokens.")
        # try to handle errors due to rjected tokens
        e = str(err).replace('API failure: CLIENT-ERROR: [400] ', '') # get json part from error
        try:
            result = json.loads(e)
            new_tokens = None
            for bad_token in result["tokens"]:
                _expire_bad_tokens(league_games=league_games, bad_token=bad_token)
                # remove bad token from our token string + the good token paired with it, remove potential superfluous comma
                # the token string is structured as such: white_token_game1:black_token_game1,white_token_game2:black_token_game2 and so on.
                optional_white_token = "([A-z0-9_]*:)?"
                optional_black_token = "(:[A-z0-9_]*)?"
                # either the pairing with the bad token is the first in the string, or there is a comma in front of it
                start_or_comma = "(^|,)"
                removed_token = re.sub(
                    f"{start_or_comma}{optional_white_token}{bad_token}{optional_black_token}",
                    "",
                    tokens,
                )
                # if it was the last token, then we end up with a useless comma in the end, remove that
                new_tokens = re.sub("^,", "", removed_token)
            if new_tokens:
                try:
                    # if there are still tokens to be paired, retry, and give up afterwards.
                    result = lichessapi.bulk_start_games(
                        tokens=new_tokens,
                        clock=clock,
                        increment=increment,
                        do_clockstart=do_clockstart,
                        clockstart=clockstart,
                        clockstart_in=clockstart_in,
                        variant=variant,
                        leaguename=leaguename,
                    )
                except lichessapi.ApiClientError as err:
                    # give up.
                    logger.exception(
                        f"[ERROR] Failed to bulk start games for league {leaguename} after removing rejected tokens."
                    )
        except KeyError:
            logger.exception(f'[ERROR] could not parse error as json for {leaguename}:\n{e}')
    if result is None: # starting games failed, or all tokens rejected
        return
    gamechannel = LeagueChannel.objects.filter(league__name=leaguename, type='games').first()
    # use lichess reply to set game ids
    for game in league_games:
        try:
            for gameids in result['games']:
                if (
                    gameids["white"] == game.white.lichess_username.lower()
                    and gameids["black"] == game.black.lichess_username.lower()
                ):
                    game.game_link = get_gamelink_from_gameid(gameids["id"])
                    game.save()
                    signals.notify_players_game_started.send(
                        sender=_start_league_games,
                        pairing=game,
                        do_clockstart=do_clockstart,
                        clockstart_in=clockstart_in,
                        gameid=gameids["id"],
                    )
                    if gamechannel is not None:
                        slackapi.send_message(
                            channel=gamechannel.slack_channel,
                            text=(
                                f"<@{game.white.lichess_username}> vs "
                                f"<@{game.black.lichess_username}>: "
                                f"{game.game_link}"
                            ),
                        )
                    if game.get_league().is_team_league():
                        message = (
                            f"Board {game.teamplayerpairing.board_number} game "
                            f"<@{game.white.lichess_username}> vs "
                            f"<@{game.black.lichess_username}> has started: "
                            f"{game.game_link}"
                        )
                        if game.teamplayerpairing.white_team().slack_channel:
                            slackapi.send_message(
                                channel=game.teamplayerpairing.white_team().slack_channel,
                                text=message,
                            )
                            time.sleep(settings.SLEEP_UNIT)
                        if game.teamplayerpairing.black_team().slack_channel:
                            slackapi.send_message(
                                channel=game.teamplayerpairing.black_team().slack_channel,
                                text=message,
                            )
                            time.sleep(settings.SLEEP_UNIT)
        except slackapi.SlackError:
            logger.info(f'[ERROR] sending slack game message to {gamechannel.slack_channel}.')
        except KeyError as e:
            logger.info(f'[ERROR] For league {leaguename}, unexpected bulk pairing json response with error {e}')
        except TypeError: # if all tokens are rejected by lichess, result['games'] is None, resulting in a TypeError.
            pass


@app.task()
def start_games():
    logger.info('[START] Checking for games to start.')
    games_to_start = PlayerPairing.objects.filter(
            result='', game_link='',
            scheduled_time__lt=timezone.now() + timedelta(minutes=5, seconds=30),
            scheduled_time__gt=timezone.now() + timedelta(seconds=30),
            white_confirmed=True, black_confirmed=True
            ).exclude(white=None).exclude(black=None).select_related('white', 'black').nocache()
    leagues = {}
    token_dict = {}
    for game in games_to_start:
        gameleague = game.get_league()
        if gameleague is not None and gameleague.get_leaguesetting().start_games:
            white_token = game.get_white_access_token()
            black_token = game.get_black_access_token()
            if game.tokens_valid():
                if gameleague.name not in token_dict:
                    token_dict[gameleague.name] = []
                if gameleague.name not in leagues:
                    leagues[gameleague.name] = gameleague
                token_dict[gameleague.name].append(f'{white_token}:{black_token}')
    for leaguename, league in leagues.items():
        clock = league.time_control_initial()
        increment = league.time_control_increment()
        variant = league.rating_type
        if variant in ['classical', 'rapid', 'blitz', 'bullet']:
            variant = 'standard'
        # filter games_to_start to the current league
        league_games = games_to_start.filter(loneplayerpairing__round__season__league=league) | games_to_start.filter(teamplayerpairing__team_pairing__round__season__league=league)
        # get tokens per game
        tokens = ','.join(token_dict[leaguename])
        do_clockstart = league.get_leaguesetting().start_clocks
        clockstart_in = league.get_leaguesetting().start_clock_time
        clockstart = round((datetime.utcnow().timestamp()+clockstart_in*60)*1000) # now + 6 minutes in milliseconds
        _start_league_games(tokens=tokens, clock=clock, increment=increment, do_clockstart=do_clockstart, clockstart=clockstart, clockstart_in=clockstart_in, variant=variant, leaguename=leaguename, league_games=league_games)
        round_ = Round.objects.filter(season__league=league, is_completed=False, publish_pairings=True).first()
        signals.do_update_broadcast_round.send(sender="start_games", round_=round_)
    logger.info('[FINISHED] Done trying to start games.')


def _create_team_string(season: Season) -> str:
    if not season.league.is_team_league():
        return ""
    teams = Team.objects.filter(season=season)
    lines = []
    for team in teams:
        for teamplayer in TeamMember.objects.filter(team=team).order_by(
            "team__number", "board_number"
        ):
            # %3B = ';'
            # %20 = ' '
            lines.append(f"{team.name}%3B%20{teamplayer.player.lichess_username}")
        # %0A = '\n'
    return "%0A".join(lines)

def _create_broadcast_grouping(broadcasts: QuerySet[Broadcast], title: str) -> str:
    for broadcast in broadcasts:
        if broadcast.first_board != 1:
            title = f"{title}{broadcast.first_board - 1}"
        title = f"{title}\n{broadcast.lichess_id} | Boards {broadcast.first_board} - "
    return title


def _create_or_update_broadcast(
    *,
    season: Season,
    broadcast_id: str = "",
    grouping: str = "",
    first_board: int = 1,
) -> str:
    result = ""
    if season.league.is_team_league():
        format_ = "Team Swiss"
        teamTable = True
        teams = _create_team_string(season=season)
    else:
        format_ = "Swiss"
        teamTable = False
        teams = ""
    if season.broadcast_title_override:
        title = season.broadcast_title_override
    else:
        title = f"{season.league.name} S{season.tag}"
    # TODO maybe mention the actual highest boad instead of the highest board in theory
    name = (
        f"{title} Boards {first_board} to "
        f"{first_board + MAX_GAMES_LICHESS_BROADCAST - 1}"
    )
    tc = season.league.time_control.replace("+", "%2b")
    players = ""
    markdown = (
        f"This is the broadcast for season {season.tag} of the {season.league.name} "
        f"league, a {season.league.rating_type} tournament with a {tc} time control "
        "played exclusively on lichess. For more information or to sign up, visit "
        "[our website](https://lichess4545.com)."
    )
    infoplayers = " ".join(
        SeasonPlayer.objects.filter(season=season)
        .order_by("-player__rating")
        .values_list("player__lichess_username", flat=True)[:4]
    )
    try:
        response = lichessapi.update_or_create_broadcast(
            broadcast_id=broadcast_id,
            name=name,
            nrounds=season.rounds,
            format_=format_,
            tc=tc,
            teamTable=teamTable,
            grouping=grouping,
            teams=teams,
            players=players,
            infoplayers=infoplayers,
            markdown=markdown,
        )
        dictresult = response.get("tour")
        if dictresult is not None:
            result = dictresult.get("id")
    except lichessapi.ApiWorkerError:
        logger.error(f"[ERROR] Failed to create or update broadcast for {season}.")
    return result


def _create_or_update_broadcast_round(round_: Round, first_board: int = 1) -> str:
    result = ""
    startsAt = round(datetime.timestamp(round_.start_date)) * 1000
    if round_.is_team_league():
        games_query = TeamPlayerPairing.objects.filter(
            team_pairing__round=round_
        ).order_by("team_pairing__pairing_order", "board_number")[
            (first_board - 1) : (first_board + MAX_GAMES_LICHESS_BROADCAST - 1)
        ]
    else:
        games_query = LonePlayerPairing.objects.filter(round=round_).order_by(
            "pairing_order"
        )[(first_board - 1) : (first_board + MAX_GAMES_LICHESS_BROADCAST - 1)]
    game_links = []
    broadcast_updates = []
    for game in games_query:
        if game.game_link:
            game_links.append(game.game_id())
            if not game.broadcasted:
                game.broadcasted = True
                broadcast_updates.append(game)
    if round_.is_team_league():
        updated_games = TeamPlayerPairing.objects.bulk_update(broadcast_updates, ["broadcasted"])
    else:
        updated_games = LonePlayerPairing.objects.bulk_update(broadcast_updates, ["broadcasted"])
    broadcast_round_id = round_.get_broadcast_round_id(first_board=first_board)
    if broadcast_round_id:
        broadcast_id = ""
    else:
        broadcast_id = round_.get_broadcast_id(first_board=first_board)
        if not broadcast_id:
            raise ValueError(
                f"[ERROR] trying to create {round_} for non-existent season broadcast."
            )
    if updated_games > 0:
        # setting the startdate to +- now makes lichess check for updates in the games
        startsAt = round(datetime.timestamp(timezone.now())) * 1000
    try:
        if not broadcast_round_id or updated_games > 0:
            response = lichessapi.update_or_create_broadcast_round(
                broadcast_id=broadcast_id,
                broadcast_round_id=broadcast_round_id,
                round_number=round_.number,
                game_links=game_links,
                startsAt=startsAt,
            )
            dictresult = response.get("round")
            if dictresult is not None:
                result = dictresult.get("id")
    except lichessapi.ApiWorkerError:
        logger.error(f"[ERROR] Failed to create or update broadcast for {round_}")
    return result


@app.task()
def do_update_broadcast_round(round_: Round) -> None:
    if not round_.season.create_broadcast:
        return
    if round_.is_team_league():
        new_games = (
            TeamPlayerPairing.objects.exclude(game_link="")
            .filter(team_pairing__round=round_)
            .exclude(broadcasted=True)
        )
    else:
        new_games = (
            LonePlayerPairing.objects.exclude(game_link="")
            .filter(round=round_)
            .exclude(broadcasted=True)
        )
    if new_games.exists():
        broadcastrounds = BroadcastRound.objects.filter(round_id=round_)
        for broadcastround in broadcastrounds:
            _create_or_update_broadcast_round(
                round_=round_, first_board=broadcastround.first_board
            )


@app.task()
def do_create_broadcast_round(round_: Round) -> None:
    if not round_.season.create_broadcast:
        return
    broadcasts = Broadcast.objects.filter(season=round_.season)
    broadcasts_count = broadcasts.count()
    broadcasts_count_initial = broadcasts_count
    teamsize = 1
    max_games = MAX_GAMES_LICHESS_BROADCAST
    if round_.is_team_league():
        pairingcount = TeamPlayerPairing.objects.filter(
            team_pairing__round=round_
        ).count()
        teamsize = round_.season.boards
        # calculate how many team pairings we can get into the max games lichess allows:
        max_games = (MAX_GAMES_LICHESS_BROADCAST // teamsize) * teamsize
    else:
        pairingcount = LonePlayerPairing.objects.filter(round=round_).count()
    while pairingcount > broadcasts_count * max_games:
        broadcast = _create_or_update_broadcast(
            season=round_.season, first_board=broadcasts_count * max_games + 1
        )
        Broadcast.objects.create(
            season=round_.season,
            lichess_id=broadcast,
            first_board=broadcasts_count * max_games + 1,
        )
        broadcasts = Broadcast.objects.filter(season=round_.season)
        broadcasts_count = broadcasts.count()
    if round_.season.broadcast_title_override:
        title = round_.season.broadcast_title_override
    else:
        title = f"{round_.season.league.name} S{round_.season.tag}"
    grouping = _create_broadcast_grouping(broadcasts=broadcasts, title=title)
    for bc in broadcasts:
        if broadcasts_count_initial != broadcasts_count:
            # only now after creating all broadcasts we have all the ids of the grouped
            # broadcasts, so update them
            _create_or_update_broadcast(
                season=round_.season,
                broadcast_id=bc.lichess_id,
                grouping=grouping,
                first_board=bc.first_board,
            )
        if not BroadcastRound.objects.filter(round_id=round_, broadcast=bc).exists():
            broadcastround = _create_or_update_broadcast_round(
                round_=round_, first_board=bc.first_board
            )
            BroadcastRound.objects.create(
                lichess_id=broadcastround, round_id=round_, broadcast=bc
            )


@app.task()
def do_create_broadcast(season: Season, first_board: int = 1) -> None:
    if not season.create_broadcast:
        return
    bc = Broadcast.objects.create(season=season, first_board=first_board)
    bc.lichess_id = _create_or_update_broadcast(season=season, first_board=first_board)
    bc.save()


@app.task()
def do_update_broadcast(season: Season, first_board: int = 1) -> None:
    bcid = season.get_broadcast_id(first_board=first_board)
    if not season.create_broadcast or not bcid:
        return
    _create_or_update_broadcast(
        season=season, broadcast_id=bcid, first_board=first_board
    )


# How late an event is allowed to run before it's discarded instead
_max_lateness = timedelta(hours=1)


@app.task()
def run_scheduled_events():
    now = timezone.now()
    with cache.lock('run_scheduled_events'):
        future_event_time = None
        for event in ScheduledEvent.objects.all():
            # Determine a range of times to search
            # If the comparison point (e.g. round start) is in the range, we run the event
            upper_bound = now - event.offset
            lower_bound = max(event.last_run or event.date_created,
                              now - _max_lateness) - event.offset

            # Determine an upper bound for events that should be run before the next task execution
            # The idea is that we want events to be run as close to their scheduled time as possible,
            # not just at whatever interval this task happens to be run
            future_bound = upper_bound + settings.CELERYBEAT_SCHEDULE['run_scheduled_events'][
                'schedule']

            def matching_rounds(**kwargs):
                result = Round.objects.filter(**kwargs).filter(season__is_active=True)
                if event.league is not None:
                    result = result.filter(season__league=event.league)
                if event.season is not None:
                    result = result.filter(season=event.season)
                return result

            def matching_pairings(**kwargs):
                team_result = PlayerPairing.objects.filter(**kwargs).filter(
                    teamplayerpairing__team_pairing__round__season__is_active=True)
                lone_result = PlayerPairing.objects.filter(**kwargs).filter(
                    loneplayerpairing__round__season__is_active=True)
                if event.league is not None:
                    team_result = team_result.filter(
                        teamplayerpairing__team_pairing__round__season__league=event.league)
                    lone_result = lone_result.filter(
                        loneplayerpairing__round__season__league=event.league)
                if event.season is not None:
                    team_result = team_result.filter(
                        teamplayerpairing__team_pairing__round__season=event.season)
                    lone_result = lone_result.filter(loneplayerpairing__round__season=event.season)
                return team_result | lone_result

            if event.relative_to == 'round_start':
                for obj in matching_rounds(start_date__gt=lower_bound, start_date__lte=upper_bound):
                    event.run(obj)
                for obj in matching_rounds(start_date__gt=upper_bound,
                                           start_date__lte=future_bound):
                    future_event_time = obj.start_date + event.offset if future_event_time is None else min(
                        future_event_time, obj.start_date + event.offset)
            elif event.relative_to == 'round_end':
                for obj in matching_rounds(end_date__gt=lower_bound, end_date__lte=upper_bound):
                    event.run(obj)
                for obj in matching_rounds(end_date__gt=upper_bound, end_date__lte=future_bound):
                    future_event_time = obj.end_date + event.offset if future_event_time is None else min(
                        future_event_time, obj.end_date + event.offset)
            elif event.relative_to == 'game_scheduled_time':
                for obj in matching_pairings(scheduled_time__gt=lower_bound,
                                             scheduled_time__lte=upper_bound):
                    event.run(obj)
                for obj in matching_pairings(scheduled_time__gt=upper_bound,
                                             scheduled_time__lte=future_bound):
                    future_event_time = obj.scheduled_time + event.offset if future_event_time is None else min(
                        future_event_time, obj.scheduled_time + event.offset)

        # Run ScheduledNotifications now
        upper_bound = now
        lower_bound = now - _max_lateness

        future_bound = upper_bound + settings.CELERYBEAT_SCHEDULE['run_scheduled_events'][
            'schedule']

        for n in ScheduledNotification.objects.filter(notification_time__gt=lower_bound,
                                                      notification_time__lte=upper_bound):
            n.run()
        for n in ScheduledNotification.objects.filter(notification_time__gt=upper_bound,
                                                      notification_time__lte=future_bound):
            future_event_time = n.notification_time if future_event_time is None else min(
                future_event_time, n.notification_time)

        # Schedule this task to be run again at the next event's scheduled time
        # Note: This could potentially lead to multiple tasks running at the same time. That's why we have a lock
        if future_event_time is not None:
            run_scheduled_events.apply_async(args=[], eta=future_event_time)


@app.task()
def round_transition(round_id):
    season = Round.objects.get(pk=round_id).season
    workflow = RoundTransitionWorkflow(season)
    warnings = workflow.warnings
    if len(warnings) > 0:
        signals.no_round_transition.send(sender=round_transition, season=season, warnings=warnings)
    else:
        msg_list = workflow.run(complete_round=True, complete_season=True, update_board_order=True,
                                generate_pairings=True, background=True)
        signals.starting_round_transition.send(sender=round_transition, season=season,
                                               msg_list=msg_list)


@receiver(signals.do_round_transition, dispatch_uid='heltour.tournament.tasks')
def do_round_transition(sender, round_id, **kwargs):
    round_transition.apply_async(args=[round_id])


@app.task()
def generate_pairings(round_id, overwrite=False):
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


@receiver(signals.do_validate_registration, dispatch_uid="heltour.tournament.tasks")
def do_validate_registration(regs: QuerySet[Registration], **kwargs) -> None:
    update_player_ratings(
        usernames=list(regs.values_list("player__lichess_username", flat=True))
    )


@app.task()
def pairings_published(round_id, overwrite=False):
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
    if season.create_broadcast:
        signals.do_create_broadcast_round.send(sender=pairings_published, round_=round_)


@receiver(signals.do_pairings_published, dispatch_uid='heltour.tournament.tasks')
def do_pairings_published(sender, round_id, **kwargs):
    pairings_published.apply_async(args=[round_id], countdown=1)


@app.task()
def schedule_publish(round_id):
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


@app.task()
def notify_slack_link(lichess_username):
    player = Player.get_or_create(lichess_username)
    email = slackapi.get_user(player.slack_user_id).email
    msg = 'Your lichess account has been successfully linked with the Slack account "%s".' % email
    lichessapi.send_mail(lichess_username, 'Slack Account Linked', msg)


@receiver(signals.slack_account_linked, dispatch_uid='heltour.tournament.tasks')
def do_notify_slack_link(lichess_username, **kwargs):
    notify_slack_link.apply_async(args=[lichess_username], countdown=1)


@app.task()
def create_team_channel(team_ids):
    intro_message = textwrap.dedent("""
            Welcome! This is your private team channel. Feel free to chat, study, discuss strategy, or whatever you like!
            You need to pick a team captain and a team name by {season_start}.
            Once you've chosen (or if you need help with anything), contact one of the moderators using the command `@chesster summon mods` in #general (do not contact them directly.)

            Here are some useful links for your team:
            - <{pairings_url}|View your team pairings>
            - <{calendar_url}|Import your team pairings to your calendar>""")

    for team in Team.objects.filter(id__in=team_ids).select_related('season__league').nocache():
        pairings_url = abs_url(reverse('by_league:by_season:pairings_by_team',
                                       args=[team.season.league.tag, team.season.tag, team.number]))
        calendar_url = abs_url(reverse('by_league:by_season:pairings_by_team_icalendar',
                                       args=[team.season.league.tag, team.season.tag,
                                             team.number])).replace('https:', 'webcal:')
        mods = team.season.league.leaguemoderator_set.filter(is_active=True)
        mods_str = ' '.join(('<@%s>' % lm.player.lichess_username.lower() for lm in mods))
        season_start = '?' if team.season.start_date is None else team.season.start_date.strftime(
            '%b %-d')
        intro_message_formatted = intro_message.format(mods=mods_str, season_start=season_start,
                                                       pairings_url=pairings_url,
                                                       calendar_url=calendar_url)
        team_members = team.teammember_set.select_related('player').nocache()
        user_ids = [tm.player.slack_user_id for tm in team_members]
        channel_name = 'team-%d-s%s' % (team.number, team.season.tag)
        topic = "Team Pairings: %s | Team Calendar: %s" % (pairings_url, calendar_url)

        try:
            group = slackapi.create_group(channel_name)
            time.sleep(settings.SLEEP_UNIT)
        except slackapi.NameTaken:
            logger.error('Could not create slack team, name taken: %s' % channel_name)
            continue
        channel_ref = '#%s' % group.name
        try:
            slackapi.invite_to_group(group.id, user_ids)
        except slackapi.SlackError:
            logger.exception('Could not invite %s to channel' % ",".join(user_ids))
            time.sleep(settings.SLEEP_UNIT)
        try:
            slackapi.invite_to_group(group.id, [settings.CHESSTER_USER_ID])
        except slackapi.SlackError:
             logger.exception('Could not invite chesster to channel')
             time.sleep(settings.SLEEP_UNIT)
        time.sleep(settings.SLEEP_UNIT)
        with reversion.create_revision():
            reversion.set_comment('Creating slack channel')
            team.slack_channel = group.id
            team.save()

        try:
            slackapi.set_group_topic(group.id, topic)
        except slackapi.SlackError:
            logger.exception('Could not set channel topic for channel %s' % channel_ref)
        time.sleep(settings.SLEEP_UNIT)
        try:
            slackapi.leave_group(group.id)
        except slackapi.SlackError:
            logger.exception('Could not leave channel %s' % channel_ref)
        time.sleep(settings.SLEEP_UNIT)
        slackapi.send_message(channel_ref, intro_message_formatted)
        time.sleep(settings.SLEEP_UNIT)


@receiver(signals.do_create_team_channel, dispatch_uid='heltour.tournament.tasks')
def do_create_team_channel(sender, team_ids, **kwargs):
    create_team_channel.apply_async(args=[team_ids], countdown=1)


@app.task()
def alternates_manager_tick():
    with cache.lock('alternates_tick'):
        for season in Season.objects.filter(is_active=True, is_completed=False):
            if season.alternates_manager_enabled():
                alternates_manager.tick(season)


@app.task()
def celery_is_up():
    uptime.celery.is_up = True


@receiver(post_save, sender=PlayerPairing, dispatch_uid='heltour.tournament.tasks')
def pairing_changed(instance, created, **kwargs):
    if instance.game_link != '' and instance.result == '':
        game_id = get_gameid_from_gamelink(instance.game_link)
        if game_id:
            lichessapi.add_watch(game_id)
