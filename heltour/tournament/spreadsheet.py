from .models import *
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from heltour import settings
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
import re
from gspread.exceptions import WorksheetNotFound

def _open_doc(url):
    scope = ['https://spreadsheets.google.com/feeds']
    credentials = ServiceAccountCredentials.from_json_keyfile_name(settings.GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH, scope)
    gc = gspread.authorize(credentials)
    try:
        return gc.open_by_url(url)
    except gspread.SpreadsheetNotFound:
        raise SpreadsheetNotFound

def import_team_season(league, url, name, tag, rosters_only=False, exclude_live_pairings=False):
    doc = _open_doc(url)

    with transaction.atomic():

        # Open the sheets
        sheet_rosters = _trim_cells(doc.worksheet('Rosters').get_all_values())
        sheet_standings = _trim_cells(doc.worksheet('Standings').get_all_values())
        sheet_past_rounds = _trim_cells(doc.worksheet('Past Rounds').get_all_values())

        # Read the round count
        round_ = 1
        round_cols = []
        while True:
            try:
                round_cols.append(sheet_standings[0].index('Round %d' % round_))
            except ValueError:
                # No more rounds
                break
            round_ += 1
        round_count = round_ - 1

        # Read the board count
        board = 1
        while True:
            try:
                sheet_rosters[0].index('Board %d' % board)
            except ValueError:
                # No more boards
                break
            board += 1
        board_count = board - 1

        # Create the season
        season = Season.objects.create(league=league, name=name, tag=tag, rounds=round_count, boards=board_count)

        # Read the teams
        team_name_col = sheet_rosters[0].index('Teams')
        team_name_row = 1
        teams = []
        while True:
            team_name = sheet_rosters[team_name_row][team_name_col]
            if len(team_name) == 0:
                break
            team = Team.objects.create(season=season, number=len(teams) + 1, name=team_name)
            TeamScore.objects.create(team=team)
            teams.append(team)
            team_name_row += 1

        # Read the team members and alternates
        alternates_start_row = [row[0] == 'Alternates' for row in sheet_rosters].index(True)
        for i in range(season.boards):
            board = i + 1
            player_name_col = sheet_rosters[0].index('Board %d' % board)
            player_rating_col = sheet_rosters[0].index('Rating %d' % board)
            # Team members
            for i in range(len(teams)):
                player_row = i + 1
                player_name, is_captain = _parse_player_name(sheet_rosters[player_row][player_name_col])
                player_rating = sheet_rosters[player_row][player_rating_col]
                player, _ = Player.objects.update_or_create(lichess_username__iexact=player_name,
                                                            defaults={'lichess_username': player_name, 'rating': int(player_rating)})
                SeasonPlayer.objects.get_or_create(season=season, player=player)
                TeamMember.objects.get_or_create(team=teams[i], board_number=board, defaults={'player': player, 'is_captain':is_captain})
            # Alternates
            alternates_row = alternates_start_row
            while True:
                player_name = sheet_rosters[alternates_row][player_name_col]
                player_rating = sheet_rosters[alternates_row][player_rating_col]
                if len(player_name) == 0 or len(player_rating) == 0:
                    break
                player, _ = Player.objects.update_or_create(lichess_username__iexact=player_name,
                                                            defaults={'lichess_username': player_name, 'rating': int(player_rating)})
                season_player, _ = SeasonPlayer.objects.get_or_create(season=season, player=player)
                Alternate.objects.get_or_create(season_player=season_player, defaults={'board_number': board})
                alternates_row += 1

        if not rosters_only:

            # Read the pairings
            rounds = Round.objects.filter(season=season).order_by('number')
            last_round_number = 0
            pairings = []
            pairing_rows = []
            for round_ in rounds:
                round_number = round_.number
                try:
                    round_start_row = [row[0] == 'Round %d' % round_number for row in sheet_past_rounds].index(True)
                except ValueError:
                    # No more rounds in this sheet
                    last_round_number = round_number - 1
                    break
                header_row = round_start_row + 1
                result_col = _read_team_pairings(sheet_past_rounds, header_row, season, teams, round_, pairings, pairing_rows)
                round_.publish_pairings = True
                round_.is_completed = True
                round_.save()

            # Load game links from the input formatting on the result column range
            _update_pairing_game_links(doc.worksheet('Past Rounds'), pairings, pairing_rows, result_col)

            # Update the season date based on the round dates
            if len(rounds) > 0:
                season.start_date = rounds[0].start_date.date()
            else:
                season.start_date = timezone.now().date()

            if not exclude_live_pairings:

                # Read the live round data
                round_ = rounds[last_round_number]
                current_round_name = 'Round %d' % round_.number
                sheet_current_round = _trim_cells(doc.worksheet(current_round_name).get_all_values())
                header_row = 0
                pairings = []
                pairing_rows = []
                result_col = _read_team_pairings(sheet_current_round, header_row, season, teams, round_, pairings, pairing_rows)
                _update_pairing_game_links(doc.worksheet(current_round_name), pairings, pairing_rows, result_col)
                round_.publish_pairings = True
                round_.save()

class SpreadsheetNotFound(Exception):
    pass

def _trim_cells(sheet_array):
    for x in range(len(sheet_array)):
        for y in range(len(sheet_array[x])):
            sheet_array[x][y] = sheet_array[x][y].strip()
    return sheet_array

def _parse_player_name(player_name):
    if player_name[-1:] == '*':
        is_captain = True
        player_name = player_name[:-1]
    else:
        is_captain = False
    return player_name, is_captain

def _parse_player_name_and_rating(cell):
    match = re.match(r'([^\s]*)\s*\((\d+)\)', cell)
    if match is None:
        if len(cell) > 0 and cell != 'BYE' and cell != 'FULL BYE' and cell != 'WITHDRAW':
            return cell, None
        return None, None
    return match.group(1), match.group(2)

def _read_team_pairings(sheet, header_row, season, teams, round_, pairings, pairing_rows):
    white_col = sheet[header_row].index('WHITE')
    white_team_col = white_col - 1
    black_col = sheet[header_row].index('BLACK')
    black_team_col = black_col + 1
    result_col = sheet[header_row].index('RESULT')
    date_col = sheet[header_row].index('DATE')
    time_col = sheet[header_row].index('TIME')
    pairing_row = header_row + 1
    # Team pairings
    for j in range(len(teams) / 2):
        white_team_name = sheet[pairing_row][white_team_col]
        white_team = Team.objects.get(season=season, name__iexact=white_team_name)
        black_team_name = sheet[pairing_row][black_team_col]
        black_team = Team.objects.get(season=season, name__iexact=black_team_name)
        team_pairing = TeamPairing.objects.create(round=round_, white_team=white_team, black_team=black_team, pairing_order=j + 1)
        # Individual pairings
        for k in range(season.boards):
            white_player_name, _ = _parse_player_name(sheet[pairing_row][white_col])
            white_player, _ = Player.objects.get_or_create(lichess_username__iexact=white_player_name, defaults={'lichess_username': white_player_name})
            black_player_name, _ = _parse_player_name(sheet[pairing_row][black_col])
            black_player, _ = Player.objects.get_or_create(lichess_username__iexact=black_player_name, defaults={'lichess_username': black_player_name})
            result = sheet[pairing_row][result_col]
            if result == u'\u2694':
                result = ''
            date = sheet[pairing_row][date_col]
            time = sheet[pairing_row][time_col]
            scheduled_time = None
            if '/' in date:
                scheduled_time = datetime.strptime('%s %s' % (date, time), '%m/%d/%Y %H:%M')
                scheduled_time = scheduled_time.replace(tzinfo=timezone.UTC())
                if round_.start_date is None or scheduled_time < round_.start_date:
                    round_.start_date = scheduled_time
                    round_.save()
                game_end_estimate = scheduled_time + timedelta(hours=3)
                if round_.end_date is None or game_end_estimate > round_.end_date:
                    round_.end_date = game_end_estimate
                    round_.save()
            pairing = TeamPlayerPairing.objects.create(team_pairing=team_pairing, board_number=k + 1, white=white_player, black=black_player, result=result, scheduled_time=scheduled_time)
            pairings.append(pairing)
            pairing_rows.append(pairing_row)
            pairing_row += 1
    return result_col

def _update_pairing_game_links(worksheet, pairings, pairing_rows, game_link_col):
    if len(pairings) > 0:
        game_link_col_letter = chr(ord('A') + game_link_col)
        range_game_links = worksheet.range('%s%d:%s%d' % (game_link_col_letter, 1, game_link_col_letter, pairing_rows[-1] + 1))
        for i in range(len(pairings)):
            input_value = range_game_links[pairing_rows[i]].input_value
            match = re.match('=HYPERLINK\("(.*)","(.*)"\)', input_value)
            if match is not None:
                pairings[i].game_link = match.group(1)
                pairings[i].save()

def import_lonewolf_season(league, url, name, tag, rosters_only=False, exclude_live_pairings=False):
    doc = _open_doc(url)

    with transaction.atomic():

        # Open the sheets
        try:
            sheet_standings = _trim_cells(doc.worksheet('STANDINGS').get_all_values())
            season_complete = False
        except WorksheetNotFound:
            sheet_standings = _trim_cells(doc.worksheet('STANDINGS FINAL').get_all_values())
            season_complete = True
        try:
            sheet_changes = _trim_cells(doc.worksheet('PLAYER CHANGES').get_all_values())
        except WorksheetNotFound:
            sheet_changes = None
        sheet_readme = _trim_cells(doc.worksheet('README').get_all_values())

        # Read the round count
        round_count = None
        for row in sheet_readme:
            for cell in row:
                match = re.search('(\d+) round', cell)
                if match is not None:
                    round_count = int(match.group(1))

        # Create the season
        season = Season.objects.create(league=league, name=name, tag=tag, rounds=round_count)

        # Read the players and their scores
        name_col = sheet_standings[0].index('Name')
        rating_col = sheet_standings[0].index('Rtng')
        points_col = sheet_standings[0].index('Tot')
        try:
            ljp_col = sheet_standings[0].index('LjP')
        except ValueError:
            ljp_col = None
        tb1_col = sheet_standings[0].index('TBrk[M]')
        tb2_col = sheet_standings[0].index('TBrk[S]')
        tb3_col = sheet_standings[0].index('TBrk[C]')
        tb4_col = sheet_standings[0].index('TBrk[O]')
        row = 1
        while row < len(sheet_standings):
            name = sheet_standings[row][name_col]
            if len(name) == 0:
                break
            rating = int(sheet_standings[row][rating_col])
            player, _ = Player.objects.update_or_create(lichess_username__iexact=name,
                                                            defaults={'lichess_username': name, 'rating': rating})
            season_player, _ = SeasonPlayer.objects.get_or_create(season=season, player=player, defaults={'seed_rating': rating})
            points = int(float(sheet_standings[row][points_col]) * 2)
            ljp = int(float(sheet_standings[row][ljp_col]) * 2) if ljp_col is not None else 0
            tb1 = int(float(sheet_standings[row][tb1_col]) * 2)
            tb2 = int(float(sheet_standings[row][tb2_col]) * 2)
            tb3 = int(float(sheet_standings[row][tb3_col]) * 2)
            tb4 = int(float(sheet_standings[row][tb4_col]) * 2)

            LonePlayerScore.objects.create(season_player=season_player, points=points, late_join_points=ljp, tiebreak1=tb1, tiebreak2=tb2, tiebreak3=tb3, tiebreak4=tb4)
            row += 1

        if sheet_changes is not None:
            # Read the round changes
            round_col = sheet_changes[0].index('round')
            name_col = sheet_changes[0].index('username')
            action_col = sheet_changes[0].index('action')
            rating_col = sheet_changes[0].index('rating')
            for row in range(1, len(sheet_changes)):
                name = sheet_changes[row][name_col]
                if len(name) == 0:
                    break
                round_number = int(sheet_changes[row][round_col])
                action = sheet_changes[row][action_col]
                rating = int(sheet_changes[row][rating_col]) if len(sheet_changes[row][rating_col]) > 0 else None
                player, _ = Player.objects.get_or_create(lichess_username__iexact=name,
                                                                defaults={'lichess_username': name, 'rating': rating})
                SeasonPlayer.objects.get_or_create(season=season, player=player, defaults={'seed_rating': player.rating})
                if action == 'register':
                    PlayerLateRegistration.objects.create(round=season.round_set.get(number=round_number), player=player)
                elif action == 'withdraw':
                    PlayerWithdrawl.objects.create(round=season.round_set.get(number=round_number), player=player)
                elif action == 'half-point-bye':
                    PlayerBye.objects.create(round=season.round_set.get(number=round_number), player=player, type='half-point-bye')

        # TODO: Infer missing round changes from the standings page
        round_cols = [(n, sheet_standings[0].index('Rd %d' % n)) for n in range(1, round_count + 1) if ('Rd %d' % n) in sheet_standings[0]]

        # TODO: Fill missing pairings from the standings page

        # Read the pairings
        for round_ in season.round_set.all():
            try:
                worksheet = doc.worksheet('ROUND %d PAIRINGS' % round_.number)
            except WorksheetNotFound:
                continue
            sheet = _trim_cells(worksheet.get_all_values())
            pairings = []
            pairing_rows = []

            time_col = sheet[0].index('Game Scheduled (in GMT)')
            white_col = sheet[0].index('White')
            white_rank_col = white_col - 1
            black_col = sheet[0].index('Black')
            black_rank_col = black_col - 1
            result_col = sheet[0].index('Result')
            for row in range(1, len(sheet)):
                white_player_name, white_player_rating = _parse_player_name_and_rating(sheet[row][white_col])
                if white_player_name is None:
                    continue
                white_player, _ = Player.objects.get_or_create(lichess_username__iexact=white_player_name, defaults={'lichess_username': white_player_name, 'rating': white_player_rating})
                SeasonPlayer.objects.get_or_create(season=season, player=white_player, defaults={'seed_rating': white_player.rating})
                try:
                    white_rank = int(sheet[row][white_rank_col])
                except ValueError:
                    white_rank = None

                if sheet[row][black_col] == 'BYE':
                    PlayerBye.objects.update_or_create(round=round_, player=white_player, type='half-point-bye', defaults={'player_rank': white_rank})
                    continue

                black_player_name, black_player_rating = _parse_player_name_and_rating(sheet[row][black_col])
                if black_player_name is None:
                    continue
                black_player, _ = Player.objects.get_or_create(lichess_username__iexact=black_player_name, defaults={'lichess_username': black_player_name, 'rating': black_player_rating})
                SeasonPlayer.objects.get_or_create(season=season, player=black_player, defaults={'seed_rating': black_player.rating})
                try:
                    black_rank = int(sheet[row][black_rank_col])
                except ValueError:
                    black_rank = None

                result = sheet[row][result_col]
                if result == u'\u2694':
                    result = ''
                time_str = sheet[row][time_col]
                scheduled_time = None
                if '/' in time_str:
                    scheduled_time = datetime.strptime(time_str, '%m/%d %H:%M')
                    scheduled_time = scheduled_time.replace(tzinfo=timezone.UTC())
                    if round_.start_date is None or scheduled_time < round_.start_date:
                        round_.start_date = scheduled_time
                        round_.save()
                    game_end_estimate = scheduled_time + timedelta(hours=3)
                    if round_.end_date is None or game_end_estimate > round_.end_date:
                        round_.end_date = game_end_estimate
                        round_.save()
                pairing = LonePlayerPairing.objects.create(round=round_, pairing_order=row, white=white_player, white_rank=white_rank,
                                                           black=black_player, black_rank=black_rank, result=result, scheduled_time=scheduled_time)
                pairings.append(pairing)
                pairing_rows.append(row)
            _update_pairing_game_links(worksheet, pairings, pairing_rows, result_col)

        # Set round states
        last_round = None
        for round_ in season.round_set.order_by('number'):
            if round_.loneplayerpairing_set.count() > 0:
                round_.publish_pairings = True
                round_.is_completed = season_complete
                round_.save()
                if last_round is not None:
                    last_round.is_completed = True
                    last_round.save()
                last_round = round_

        if season_complete:
            season.is_completed = True
            season.save()
