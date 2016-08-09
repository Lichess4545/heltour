from .models import *
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from heltour import settings
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
import re

def import_season(league, url, name, rosters_only=False, exclude_live_pairings=False):
    scope = ['https://spreadsheets.google.com/feeds']
    credentials = ServiceAccountCredentials.from_json_keyfile_name(settings.GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH, scope)
    gc = gspread.authorize(credentials)
    try:
        doc = gc.open_by_url(url)
    except gspread.SpreadsheetNotFound:
        raise SpreadsheetNotFound
    
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
        season = Season.objects.create(league=league, name=name, rounds=round_count, boards=board_count)
        
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
                player_rating  = sheet_rosters[player_row][player_rating_col]
                player, _ = Player.objects.update_or_create(lichess_username__iexact=player_name, defaults={'lichess_username': player_name, 'rating': int(player_rating)})
                SeasonPlayer.objects.get_or_create(season=season, player=player)
                TeamMember.objects.get_or_create(team=teams[i], board_number=board, defaults={'player': player, 'is_captain':is_captain})
            # Alternates
            alternates_row = alternates_start_row
            while True:
                player_name = sheet_rosters[alternates_row][player_name_col]
                player_rating  = sheet_rosters[alternates_row][player_rating_col]
                if len(player_name) == 0 or len(player_rating) == 0:
                    break
                player, _ = Player.objects.update_or_create(lichess_username__iexact=player_name, defaults={'lichess_username': player_name, 'rating': int(player_rating)})
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
            pairing = PlayerPairing.objects.create(white=white_player, black=black_player, result=result, scheduled_time=scheduled_time)
            TeamPlayerPairing.objects.create(player_pairing=pairing, team_pairing=team_pairing, board_number=k + 1)
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
