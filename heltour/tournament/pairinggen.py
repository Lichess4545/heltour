from .models import *
from heltour import settings
from django.db import transaction
import tempfile
import subprocess
import os

def generate_pairings(round_, overwrite=False):
    if round_.season.league.competitor_type == 'team':
        _generate_team_pairings(round_, overwrite)
    else:
        _generate_lone_pairings(round_, overwrite)

def _generate_team_pairings(round_, overwrite=False):
    with transaction.atomic():
        existing_pairings = TeamPairing.objects.filter(round=round_)
        if existing_pairings.count() > 0:
            if overwrite:
                delete_pairings(round_)
            else:
                raise PairingsExistException()

        # Sort by seed rating/score
        teams = Team.objects.filter(season=round_.season, is_active=True).select_related('teamscore').nocache()
        for team in teams:
            if team.seed_rating is None:
                team.seed_rating = team.average_rating()
                team.save()
        teams = sorted(teams, key=lambda team: team.get_teamscore().pairing_sort_key(), reverse=True)

        previous_pairings = TeamPairing.objects.filter(round__season=round_.season, round__number__lt=round_.number).order_by('round__number')

        # Run the pairing algorithm
        pairing_system = DutchTeamPairingSystem()
        team_pairings = pairing_system.create_team_pairings(round_, teams, previous_pairings)

        # Save the team pairings and create the individual pairings based on the team pairings
        board_count = round_.season.boards
        for team_pairing in team_pairings:
            team_pairing.save()
            for board_number in range(1, board_count + 1):
                white = TeamMember.objects.filter(team=team_pairing.white_team, board_number=board_number).first()
                white_player = white.player if white is not None else None
                black = TeamMember.objects.filter(team=team_pairing.black_team, board_number=board_number).first()
                black_player = black.player if black is not None else None

                white_alt = AlternateAssignment.objects.filter(round=round_, team=team_pairing.white_team, board_number=board_number).first()
                if white_alt is not None:
                    white_player = white_alt.player
                black_alt = AlternateAssignment.objects.filter(round=round_, team=team_pairing.black_team, board_number=board_number).first()
                if black_alt is not None:
                    black_player = black_alt.player

                if board_number % 2 == 0:
                    white, black = black, white
                TeamPlayerPairing.objects.create(team_pairing=team_pairing, board_number=board_number, white=white_player, black=black_player)

def _generate_lone_pairings(round_, overwrite=False):
    with transaction.atomic():
        existing_pairings = LonePlayerPairing.objects.filter(round=round_)
        if existing_pairings.count() > 0:
            if overwrite:
                delete_pairings(round_)
            else:
                raise PairingsExistException()

        # Perform any registrations and withdrawls
        for reg in round_.playerlateregistration_set.all():
            reg.perform_registration()
        for wd in round_.playerwithdrawl_set.all():
            wd.perform_withdrawl()

        # Sort by seed rating/score
        season_players = SeasonPlayer.objects.filter(season=round_.season, is_active=True).select_related('player', 'loneplayerscore').nocache()
        for sp in season_players:
            if sp.seed_rating is None:
                sp.seed_rating = sp.player.rating
                sp.save()
        season_players = sorted(season_players, key=lambda sp: sp.get_loneplayerscore().pairing_sort_key(), reverse=True)

        # Exclude players with byes
        current_byes = {bye.player for bye in PlayerBye.objects.filter(round=round_)}
        season_players = [sp for sp in season_players if sp.player not in current_byes]

        previous_pairings = LonePlayerPairing.objects.filter(round__season=round_.season, round__number__lt=round_.number).order_by('round__number')
        previous_byes = PlayerBye.objects.filter(round__season=round_.season, round__number__lt=round_.number).order_by('round__number')

        # Run the pairing algorithm
        pairing_system = DutchLonePairingSystem()
        lone_pairings, byes = pairing_system.create_lone_pairings(round_, season_players, previous_pairings, previous_byes)

        # Save the lone pairings
        rank_dict = lone_player_pairing_rank_dict(round_.season)
        for lone_pairing in lone_pairings:
            lone_pairing.white_rank = rank_dict.get(lone_pairing.white_id, None)
            lone_pairing.black_rank = rank_dict.get(lone_pairing.black_id, None)
            lone_pairing.save()

        # Save pairing byes and update player ranks for all byes
        for bye in byes + list(PlayerBye.objects.filter(round=round_)):
            bye.player_rank = rank_dict.get(bye.player_id, None)
            bye.save()

def delete_pairings(round_):
    if round_.season.league.competitor_type == 'team':
        if TeamPlayerPairing.objects.filter(team_pairing__round=round_).exclude(result='').count():
            raise PairingHasResultException()
        TeamPairing.objects.filter(round=round_).delete()
    else:
        if LonePlayerPairing.objects.filter(round=round_).exclude(result='').count():
            raise PairingHasResultException()
        LonePlayerPairing.objects.filter(round=round_).delete()
        PlayerBye.objects.filter(round=round_, type='full-point-pairing-bye').delete()

class PairingsExistException(Exception):
    pass

class PairingHasResultException(Exception):
    pass

class PlaceholderTeamPairingSystem:
    def create_team_pairings(self, round_, teams, previous_pairings):
        # Pair teams in some arbitrary order for testing purposes
        team_pairings = []
        for i in range(int(len(teams) / 2)):
            white_team = teams[i * 2]
            black_team = teams[i * 2 + 1]
            team_pairings.append(TeamPairing(white_team=white_team, black_team=black_team, round=round_, pairing_order=i + 1))
        return team_pairings

class DutchTeamPairingSystem:
    def create_team_pairings(self, round_, teams, previous_pairings):
        # Note: Assumes teams is sorted by seed and previous_pairings is sorted by round

        players = [
            JavafoPlayer(team, team.teamscore.match_points, list(self._process_pairings(team, previous_pairings))) for team in teams
        ]
        javafo = JavafoInstance(round_.season.rounds, players)
        pairs = javafo.run()

        team_pairings = []
        for i in range(len(pairs)):
            white_team = pairs[i][0]
            black_team = pairs[i][1]
            team_pairings.append(TeamPairing(white_team=white_team, black_team=black_team, round=round_, pairing_order=i + 1))
        return team_pairings

    def _process_pairings(self, team, pairings):
        team_pairings = [p for p in pairings if p.white_team == team or p.black_team == team]
        for p in team_pairings:
            if p.white_team == team:
                yield JavafoPairing(p.black_team, 'white', 1.0 if p.white_points > p.black_points else 0.5 if p.white_points == p.black_points else 0)
            if p.black_team == team:
                yield JavafoPairing(p.white_team, 'black', 1.0 if p.black_points > p.white_points else 0.5 if p.white_points == p.black_points else 0)

class DutchLonePairingSystem:
    def create_lone_pairings(self, round_, season_players, previous_pairings, previous_byes):
        # Note: Assumes season_players is sorted by seed and previous_pairings/previous_byes are sorted by round

        players = [
            JavafoPlayer(
                         sp.player, sp.get_loneplayerscore().pairing_points(),
                         list(self._process_pairings(sp, previous_pairings, previous_byes, round_.number, sp.loneplayerscore.late_join_points / 2.0))
            ) for sp in season_players
        ]
        javafo = JavafoInstance(round_.season.rounds, players)
        pairs = javafo.run()
        lone_pairings = []
        byes = []
        for i in range(len(pairs)):
            white = pairs[i][0]
            black = pairs[i][1]
            if black is None:
                byes.append(PlayerBye(player=white, round=round_, type='full-point-pairing-bye'))
            else:
                lone_pairings.append(LonePlayerPairing(white=white, black=black, round=round_, pairing_order=i + 1))
        return lone_pairings, byes

    def _process_pairings(self, sp, pairings, byes, current_round_number, bonus_score):
        player_pairings = [p for p in pairings if p.white == sp.player or p.black == sp.player]
        player_byes = [b for b in byes if b.player == sp.player]
        for n in range(1, current_round_number):
            p = find(player_pairings, round__number=n)
            b = find(player_byes, round__number=n)
            if p is not None:
                if p.white == sp.player:
                    yield JavafoPairing(p.black, 'white', p.white_score(), forfeit=not p.game_played())
                else:
                    yield JavafoPairing(p.white, 'black', p.black_score(), forfeit=not p.game_played())
            elif b is not None:
                yield JavafoPairing(None, None, b.score(), forfeit=True)
            elif bonus_score >= 1:
                yield JavafoPairing(None, None, 1, forfeit=True)
                bonus_score -= 1
            elif bonus_score == 0.5:
                yield JavafoPairing(None, None, 0.5, forfeit=True)
                bonus_score = 0
            else:
                yield JavafoPairing(None, None, None, forfeit=True)

class JavafoPlayer:
    def __init__(self, player, score, pairings):
        self.player = player
        self.score = score
        self.pairings = pairings

class JavafoPairing:
    def __init__(self, opponent, color, score, forfeit=False):
        self.opponent = opponent
        self.color = color
        self.score = score
        self.forfeit = forfeit

class JavafoPairingResult:
    def __init__(self, white, black):
        self.white = white
        self.black = black

# TODO: Verify for score >= 10
class JavafoInstance:
    '''Interfaces with javafo.jar

    Arguments:
    total_round_count -- number of rounds in the tournament
    players -- a list of JavafoPlayer objects ordered by seed

    Each player's list of pairings should be ordered by round number.
    '''
    def __init__(self, total_round_count, players):
        self.total_round_count = total_round_count
        self.players = players

    '''Runs the Javafo process

    Returns a list of JavafoPairingResult objects in the order they should be displayed.
    '''
    def run(self):
        input_file = tempfile.NamedTemporaryFile(suffix='.trfx')
        output_file_name = input_file.name + ".out.txt"
        try:
            # Write to input file
            input_file.write('XXR %d\n' % self.total_round_count)
            for n, player in enumerate(self.players, 1):
                line = '001  {0: >3}  {1:74.1f}     '.format(n, player.score)
                for pairing in player.pairings:
                    opponent_num = next((num for num, player in enumerate(self.players, 1) if player.player == pairing.opponent), '0000')
                    color = 'w' if pairing.color == 'white' else 'b' if pairing.color == 'black' else '-'
                    if pairing.forfeit:
                        score = '+' if pairing.score == 1 else '-' if pairing.score == 0 else '=' if pairing.score == 0.5 else ' '
                    else:
                        score = '1' if pairing.score == 1 else '0' if pairing.score == 0 else '=' if pairing.score == 0.5 else ' '
                    if score == ' ':
                        color = '-'
                    line += '{0: >6} {1} {2}'.format(opponent_num, color, score)
                line += '\n'
                print line
                input_file.write(line)
            input_file.flush()

            self._call_proc(input_file.name, output_file_name, '-q 10000')

            pairs = self._read_output(output_file_name)
            if len(pairs) == 0 and len(self.players) > 1:
                # Took too long before terminating, use the slower but more deterministic algorithm
                self._call_proc(input_file.name, output_file_name, '-w')
                pairs = self._read_output(output_file_name)

            return pairs
        finally:
            input_file.close()
            try:
                os.remove(output_file_name)
            except OSError:
                pass

    def _call_proc(self, input_file_name, output_file_name, args):
        proc = subprocess.Popen('%s %s -p %s %s' % (settings.JAVAFO_COMMAND, input_file_name, output_file_name, args), shell=True, stdout=subprocess.PIPE)
        stdout = proc.communicate()[0]
        if proc.returncode != 0:
            raise RuntimeError('Javafo return code: %s. Output: %s' % (proc.returncode, stdout))

    def _read_output(self, output_file_name):
        with open(output_file_name) as output_file:
            pair_count = int(output_file.readline())
            pairs = []
            for _ in range(pair_count):
                w, b = output_file.readline().split(' ')
                if int(b) == 0:
                    pairs.append([self.players[int(w) - 1].player, None])
                else:
                    pairs.append([self.players[int(w) - 1].player, self.players[int(b) - 1].player])
            return pairs
