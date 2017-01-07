from .models import *
from heltour import settings
from django.db import transaction
import tempfile
import subprocess
import os
import reversion
import math

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
                with reversion.create_revision():
                    reversion.set_comment('Set seed rating.')
                    team.save()
        teams = sorted(teams, key=lambda team: team.get_teamscore().pairing_sort_key(), reverse=True)

        previous_pairings = TeamPairing.objects.filter(round__season=round_.season, round__number__lt=round_.number).order_by('round__number')

        # Run the pairing algorithm
        pairing_system = DutchTeamPairingSystem()
        team_pairings = pairing_system.create_team_pairings(round_, teams, previous_pairings)

        # Save the team pairings and create the individual pairings based on the team pairings
        board_count = round_.season.boards
        for team_pairing in team_pairings:
            with reversion.create_revision():
                reversion.set_comment('Generated pairings.')
                team_pairing.save()

            white_player_list = _get_player_list(team_pairing.white_team, round_, board_count)
            black_player_list = _get_player_list(team_pairing.black_team, round_, board_count)
            for board_number in range(1, board_count + 1):
                white_player = white_player_list[board_number - 1]
                black_player = black_player_list[board_number - 1]
                if board_number % 2 == 0:
                    white_player, black_player = black_player, white_player
                with reversion.create_revision():
                    reversion.set_comment('Generated pairings.')
                    TeamPlayerPairing.objects.create(team_pairing=team_pairing, board_number=board_number, white=white_player, black=black_player)


# Create a list of players playing for the team this round
#
# The players and board numbers defined in AlternateAssignment are our invariants.
# Other players could end up in slightly different boards than expected if the board
# order changed since an alternate was assigned.
def _get_player_list(team, round_, board_count):
    team_members = [TeamMember.objects.filter(team=team, board_number=b).first() for b in range(1, board_count + 1)]
    alternates = list(AlternateAssignment.objects.filter(round=round_, team=team).order_by('board_number'))

    player_list = [tm.player if tm is not None else None for tm in team_members]

    # Remove players that are being replaced by alternates
    for alt in reversed(alternates):
        if alt.replaced_player is not None:
            try:
                player_list.remove(alt.replaced_player)
            except ValueError:
                del player_list[alt.board_number - 1]
        else:
            del player_list[alt.board_number - 1]

    # Add assigned alternates at the appropriate board
    for alt in alternates:
        player_list.insert(alt.board_number - 1, alt.player)

    return player_list

def _generate_lone_pairings(round_, overwrite=False):
    with transaction.atomic():
        existing_pairings = LonePlayerPairing.objects.filter(round=round_)
        if existing_pairings.count() > 0:
            if overwrite:
                delete_pairings(round_)
            else:
                raise PairingsExistException()
        else:
            # Always overwrite pairing byes
            PlayerBye.objects.filter(round=round_, type='full-point-pairing-bye').delete()

        # Perform any registrations and withdrawals
        for reg in round_.playerlateregistration_set.all():
            reg.perform_registration()
        for wd in round_.playerwithdrawal_set.all():
            wd.perform_withdrawal()

        # Sort by seed rating/score
        season_players = SeasonPlayer.objects.filter(season=round_.season).select_related('player', 'loneplayerscore').nocache()
        for sp in season_players:
            if sp.seed_rating is None:
                sp.seed_rating = sp.player.rating
                with reversion.create_revision():
                    reversion.set_comment('Set seed rating.')
                    sp.save()
        season_players = sorted(season_players, key=lambda sp: sp.get_loneplayerscore().pairing_sort_key(), reverse=True)

        # Create byes for unavailable players
        current_byes = {bye.player for bye in PlayerBye.objects.filter(round=round_)}
        unavailable_players = {avail.player for avail in PlayerAvailability.objects.filter(round=round_, is_available=False)}
        for p in unavailable_players - current_byes:
            with reversion.create_revision():
                reversion.set_comment('Generated pairings.')
                PlayerBye.objects.create(round=round_, player=p, type='half-point-bye')

        # Don't generate pairings for players that have been withdrawn or have byes
        include_players = {sp for sp in season_players if sp.is_active and sp.player not in current_byes and sp.player not in unavailable_players}

        previous_pairings = LonePlayerPairing.objects.filter(round__season=round_.season, round__number__lt=round_.number).order_by('round__number')
        previous_byes = PlayerBye.objects.filter(round__season=round_.season, round__number__lt=round_.number).order_by('round__number')

        # Run the pairing algorithm
        if round_.season.league.pairing_type == 'swiss-dutch-baku-accel':
            pairing_system = DutchLonePairingSystem(accel='baku')
        else:
            pairing_system = DutchLonePairingSystem()
        lone_pairings, byes = pairing_system.create_lone_pairings(round_, season_players, include_players, previous_pairings, previous_byes)

        # Save the lone pairings
        rank_dict = lone_player_pairing_rank_dict(round_.season)
        for lone_pairing in lone_pairings:
            lone_pairing.refresh_ranks(rank_dict)
            with reversion.create_revision():
                reversion.set_comment('Generated pairings.')
                lone_pairing.save()

        # Save pairing byes and update player ranks for all byes
        for bye in byes + list(PlayerBye.objects.filter(round=round_)):
            bye.refresh_rank(rank_dict)
            with reversion.create_revision():
                reversion.set_comment('Generated pairings.')
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
            if white_team is not None and black_team is not None:
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
    def __init__(self, accel=None):
        self.accel = accel

    def create_lone_pairings(self, round_, season_players, include_players, previous_pairings, previous_byes):
        # Note: Assumes season_players is sorted by seed and previous_pairings/previous_byes are sorted by round

        if self.accel == 'baku':
            # Ensure each player is in the correct acceleration group
            if round_.number == 1:
                # Calculate all groups from scratch
                group_1_size = int(2 * math.ceil(len(season_players) / 4.0))
                sorted_players = sorted(season_players, key=lambda sp: sp.seed_rating, reverse=True)
                for sp in sorted_players[:group_1_size]:
                    sp.loneplayerscore.acceleration_group = 1
                    sp.loneplayerscore.save()
                for sp in sorted_players[group_1_size:]:
                    sp.loneplayerscore.acceleration_group = 2
                    sp.loneplayerscore.save()
            else:
                # Update groups only for players that don't already have one
                min_rating_for_group_1 = min((sp.seed_rating for sp in season_players if sp.loneplayerscore.acceleration_group == 1))
                for sp in season_players:
                    if sp.loneplayerscore.acceleration_group == 0:
                        if sp.seed_rating >= min_rating_for_group_1:
                            sp.loneplayerscore.acceleration_group = 1
                        else:
                            sp.loneplayerscore.acceleration_group = 2
                        sp.loneplayerscore.save()

        def acceleration_scores(sp):
            if self.accel == 'baku' and sp.loneplayerscore.acceleration_group == 1:
                return [1, 1, 1, 0.5, 0.5]
            return None

        players = [
            JavafoPlayer(
                         sp.player, sp.get_loneplayerscore().pairing_points(),
                         list(self._process_pairings(sp, previous_pairings, previous_byes, round_.number, sp.loneplayerscore.late_join_points)),
                         sp in include_players, acceleration_scores=acceleration_scores(sp)
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
    def __init__(self, player, score, pairings, include=True, acceleration_scores=None):
        self.player = player
        self.score = score
        self.pairings = pairings
        self.include = include
        self.acceleration_scores = acceleration_scores

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
                if not player.include:
                    line += '{0: >6} {1} {2}'.format('0000', '-', '-')
                line += '\n'
                input_file.write(line)
            for n, player in enumerate(self.players, 1):
                if player.acceleration_scores:
                    line = 'XXA {0: >4} {1}\n'.format(n, ' '.join('{0: >4.1f}'.format(s) for s in player.acceleration_scores))
                    print line.strip()
                    input_file.write(line)
                    pass
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
