from .models import *
from heltour import settings
import tempfile
import subprocess
import os

def generate_pairings(round_, overwrite=True):
    existing_pairings = TeamPairing.objects.filter(round=round_)
    if existing_pairings.count() > 0:
        if overwrite:
            existing_pairings.delete()
        else:
            raise ValueError("The specified round already has pairings.")
    teams = Team.objects.filter(season=round_.season, is_active=True).order_by('number') # TODO: Order by/generate a seed
    previous_pairings = TeamPairing.objects.filter(round__season=round_.season, round__number__lt=round_.number).order_by('round__number')
    
    # Run the pairing algorithm
    # TODO: Implement a proper algorithm
    pairing_system = DutchTeamPairingSystem()
    team_pairings = pairing_system.create_team_pairings(round_, teams, previous_pairings)
    
    # Save the team pairings and create the individual pairings based on the team pairings
    board_count = round_.season.boards
    for team_pairing in team_pairings:
        team_pairing.save()
        for board_number in range(1, board_count + 1):
            white = TeamMember.objects.filter(team=team_pairing.white_team, board_number=board_number).first()
            black = TeamMember.objects.filter(team=team_pairing.black_team, board_number=board_number).first()
            if board_number % 2 == 0:
                white, black = black, white
            if white is not None and black is not None:
                player_pairing = PlayerPairing.objects.create(white=white.player, black=black.player)
                TeamPlayerPairing.objects.create(player_pairing=player_pairing, team_pairing=team_pairing, board_number=board_number)
            else:
                # TODO: Consider how to handle missing players
                # Maybe allow null players in pairings? Or just raise an error
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

class JavafoPlayer:
    def __init__(self, player, score, pairings):
        self.player = player
        self.score = score
        self.pairings = pairings

class JavafoPairing:
    def __init__(self, opponent, color, score):
        self.opponent = opponent
        self.color = color
        self.score = score

class JavafoPairingResult:
    def __init__(self, white, black):
        self.white = white
        self.black = black

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
        try:
            # Write to input file
            # TODO: Consider adding a seed rating field to teams/lone players for consistent pairings
            input_file.write('XXR %d\n' % self.total_round_count)
            for n, player in enumerate(self.players, 1):
                line = '001  {0: >3}  {1:74.1f}     '.format(n, player.score)
                for pairing in player.pairings:
                    opponent_num = next((num for num, player in enumerate(self.players, 1) if player.player == pairing.opponent))
                    color = 'w' if pairing.color == 'white' else 'b' if pairing.color == 'black' else '-'
                    score = '1' if pairing.score == 1 else '0' if pairing.score == 0 else '=' if pairing.score == 0.5 else '-'
                    line += '{0: >6} {1} {2}'.format(opponent_num, color, score)
                line += '\n'
                input_file.write(line)
            input_file.flush()
            
            output_file_name = input_file.name + ".out.txt"
            self._call_proc(input_file.name, output_file_name, '-q 10000')
            
            pairs = self._read_output(output_file_name)
            if len(pairs) == 0 and len(self.players) > 1:
                # Took too long before terminating, use the slower but more deterministic algorithm 
                self._call_proc(input_file.name, output_file_name, '-w')
                pairs = self._read_output(output_file_name)
            
            return pairs
        finally:
            input_file.close()
            os.remove(output_file_name)
    
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
                pairs.append([self.players[int(n) - 1].player for n in output_file.readline().split(' ')])
            return pairs
