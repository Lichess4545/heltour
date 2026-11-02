from unittest.mock import patch

from django.test import SimpleTestCase

from heltour.tournament.models import (
    League,
    LonePlayerPairing,
    LonePlayerScore,
    Player,
    PlayerBye,
    Round,
    Season,
    SeasonPlayer,
)
from heltour.tournament.pairinggen import DutchLonePairingSystem, JavafoInstance


class DutchLonePairingSystemByeTestCase(SimpleTestCase):
    def setUp(self):
        league = League(name='Lone League', tag='loneleague', competitor_type='lone',
                        pairing_type='swiss-dutch')
        season = Season(league=league, name='Test Season', tag='loneseason', rounds=3)
        self.rounds = [Round(id=n, season=season, number=n) for n in range(1, 4)]
        self.season_players = []
        for n in range(1, 9):
            player = Player(id=n, lichess_username='Player%d' % n)
            sp = SeasonPlayer(id=n, season=season, player=player)
            LonePlayerScore(season_player=sp)
            self.season_players.append(sp)
        self.pairings = []
        self.byes = []

    def player(self, n):
        return self.season_players[n - 1].player

    def add_pairing(self, round_number, white, black, result):
        self.pairings.append(
            LonePlayerPairing(round=self.rounds[round_number - 1], white=self.player(white),
                              black=self.player(black), result=result,
                              pairing_order=len(self.pairings) + 1))

    def add_bye(self, round_number, player, type):
        self.byes.append(
            PlayerBye(round=self.rounds[round_number - 1], player=self.player(player), type=type))

    def create_round_3_pairings(self):
        return DutchLonePairingSystem().create_lone_pairings(
            self.rounds[2], self.season_players, self.season_players, self.pairings, self.byes)

    def create_round_3_trf_results(self):
        trf_lines = []

        def capture_input(javafo, input_file_name, output_file_name, args):
            with open(input_file_name) as input_file:
                trf_lines.extend(input_file.read().splitlines())
            with open(output_file_name, 'w') as output_file:
                output_file.write('0\n')

        with patch.object(JavafoInstance, '_call_proc', capture_input):
            self.create_round_3_pairings()
        return {int(line[4:8]): line[89:] for line in trf_lines if line.startswith('001')}

    def set_up_two_full_point_byes_in_round_2(self):
        self.add_pairing(1, 1, 2, '1-0')
        self.add_pairing(1, 3, 4, '1-0')
        self.add_pairing(1, 5, 6, '1-0')
        self.add_pairing(1, 7, 8, '1-0')
        self.add_bye(2, 1, 'full-point-bye')
        self.add_pairing(2, 3, 5, '1-0')
        self.add_pairing(2, 2, 4, '1-0')
        self.add_pairing(2, 6, 7, '1-0')
        self.add_bye(2, 8, 'full-point-pairing-bye')

    def test_full_point_bye_is_written_as_unallocated_bye(self):
        self.set_up_two_full_point_byes_in_round_2()

        trf_results = self.create_round_3_trf_results()

        self.assertEqual('     2 w 1  0000 - F', trf_results[1])
        self.assertEqual('     7 b 0  0000 - +', trf_results[8])

    def test_late_join_full_point_is_written_as_unallocated_bye(self):
        self.season_players[0].loneplayerscore.late_join_points = 1
        self.add_pairing(1, 2, 3, '1-0')
        self.add_pairing(2, 1, 2, '1-0')

        trf_results = self.create_round_3_trf_results()

        self.assertEqual('  0000 - F     2 w 1', trf_results[1])

    def test_pairs_round_after_full_point_bye_and_pairing_bye(self):
        self.set_up_two_full_point_byes_in_round_2()

        lone_pairings, byes = self.create_round_3_pairings()

        self.assertEqual(4, len(lone_pairings))
        self.assertEqual([], byes)
        paired_players = {p.white for p in lone_pairings} | {p.black for p in lone_pairings}
        self.assertEqual({sp.player for sp in self.season_players}, paired_players)
