"""
Test TRF16 parser with real tournament data.
"""

import unittest
from heltour.tournament_core.trf16 import TRF16Parser
from heltour.tournament_core.trf16_converter import TRF16Converter


class TestTRF16RealData(unittest.TestCase):
    """Test TRF16 parser with actual tournament data."""

    def setUp(self):
        """Set up with the real TRF16 data provided."""
        # Using first few teams and rounds from the actual data
        self.real_trf16 = """012 ΔΙΑΣΥΛΛΟΓΙΚΟ ΚΥΠΕΛΛΟ ΚΡΗΤΙΚΗΣ ΦΙΛΙΑΣ 2024 
022 Heraklion
032 GRE
042 2024/11/23
052 2024/11/24
062 129 (88)
072 84
082 15
092 Team Swiss System
102 FA Stefanatos Charalampos
112 Michailidi Afroditi, Gkizis Konstantinos, Magoulianos Nikolaos
122 15 minutes plus 10 sec per move
142 7
132                                                                                        24/11/23  24/11/23  24/11/23  24/11/24  24/11/24  24/11/24  24/11/24

001    1 m    Psarianos,Emmanouil               1442 GRE    42143683 2014/00/00  3.5   34  0000 - -     7 w 1    99 b 1    19 w 1    59 b 0    29 w 0    13 b =  
001    2 m    Psarakis,Kyriakos                 0000 GRE    42172284 2017/00/00  3.5   38  0000 - -     8 b 1   100 w 1    20 b 1    60 w 0    30 b 0    14 w =  
001    3 m    Bouchlis,Nikolaos                 1424 GRE    42183219 2014/00/00  3.5   37  0000 - -     9 w 1   101 b 1    21 w 1    61 b 0    31 w 0    15 b =  
001    4 m    Lampousakis,Dimitrios Christos    0000 GRE    42189209 2015/00/00  2.0   76  0000 - -    10 b =   102 w 0    55 b =    62 w 1    32 b 0    16 w 0  
001    5 m    Lampousakis,Michail               0000 GRE    42189217 2015/00/00  2.0   77  0000 - -    11 w 0   103 b 0    56 w 0    63 b 1    33 w 1    17 b 0  
001    6 m    Stylianakis,Iosif                 0000 GRE    42185890 2011/00/00  2.5   68  0000 - -    12 b 0   104 w =    57 b 0    64 w 1    34 b 1    18 w 0  
001    7 m    Naoum,Spyridon                    2250 GRE     4227506 1997/00/00  4.0   30    22 w 1     1 b 0   107 w 1    44 b 1    13 w 1  0000 - -    84 b 0  
001    8 m    Bairamian,Artur                   1826 GRE     4295064 2004/00/00  2.5   66    23 b 0     2 w 0   108 b =    45 w 1    14 b 1  0000 - -    85 w 0  

013 ΣΑΧ                                1    2    3    4    5    6  128
013 Α.Π.Ο. ΜΙΚΗΣ ΘΕΟΔΩΡΑΚΗΣ            7    8    9   10   11   12   83  120"""

    def test_parse_real_header(self):
        """Test parsing header from real TRF16 data."""
        parser = TRF16Parser(self.real_trf16)
        header = parser.parse_header()

        self.assertEqual(
            header.tournament_name, "ΔΙΑΣΥΛΛΟΓΙΚΟ ΚΥΠΕΛΛΟ ΚΡΗΤΙΚΗΣ ΦΙΛΙΑΣ 2024"
        )
        self.assertEqual(header.city, "Heraklion")
        self.assertEqual(header.federation, "GRE")
        self.assertEqual(header.num_players, 129)
        self.assertEqual(header.num_rated_players, 84)  # From line 072
        self.assertEqual(header.num_teams, 15)
        self.assertEqual(header.tournament_type, "Team Swiss System")
        self.assertEqual(header.num_rounds, 7)
        self.assertEqual(len(header.deputy_arbiters), 3)

    def test_parse_real_players(self):
        """Test parsing players from real data."""
        parser = TRF16Parser(self.real_trf16)
        players = parser.parse_players()

        # Should have parsed 8 players from the sample
        self.assertEqual(len(players), 8)

        # Check first player details
        player1 = None
        for player in players.values():
            if player.name == "Psarianos,Emmanouil":
                player1 = player
                break

        self.assertIsNotNone(player1)
        self.assertEqual(player1.rating, 1442)
        self.assertEqual(player1.federation, "GRE")
        self.assertEqual(player1.fide_id, "42143683")
        self.assertEqual(player1.points, 3.5)
        self.assertEqual(player1.rank, 34)

        # Check round results
        self.assertEqual(len(player1.results), 7)
        # Round 1: bye
        self.assertEqual(player1.results[0], (None, "-", "-"))
        # Round 2: played board 7 as white and won
        self.assertEqual(player1.results[1], (7, "w", "1"))
        # Round 3: played board 99 as black and won
        self.assertEqual(player1.results[2], (99, "b", "1"))

    def test_parse_real_teams(self):
        """Test parsing teams from real data."""
        parser = TRF16Parser(self.real_trf16)
        teams = parser.parse_teams()

        # Should have 2 teams in our sample
        self.assertEqual(len(teams), 2)

        # Check team names and composition
        self.assertIn("ΣΑΧ", teams)
        self.assertIn("Α.Π.Ο. ΜΙΚΗΣ ΘΕΟΔΩΡΑΚΗΣ", teams)

        # Check ΣΑΧ team
        sax_team = teams["ΣΑΧ"]
        self.assertEqual(sax_team.player_ids, [1, 2, 3, 4, 5, 6, 128])

        # Check ΜΙΚΗΣ ΘΕΟΔΩΡΑΚΗΣ team
        mikis_team = teams["Α.Π.Ο. ΜΙΚΗΣ ΘΕΟΔΩΡΑΚΗΣ"]
        self.assertEqual(mikis_team.player_ids, [7, 8, 9, 10, 11, 12, 83, 120])

    def test_board_assignment(self):
        """Test that board numbers are assigned correctly."""
        parser = TRF16Parser(self.real_trf16)
        parser.parse_players()
        parser.parse_teams()
        parser.update_board_numbers()

        # Check board assignments for ΣΑΧ team
        for player_id in [1, 2, 3, 4, 5, 6]:
            if player_id in parser.players:
                player = parser.players[player_id]
                expected_board = [1, 2, 3, 4, 5, 6, 128].index(player_id) + 1
                self.assertEqual(player.board_number, expected_board)

    def test_extract_round_2_pairings(self):
        """Test extracting pairings from round 2."""
        parser = TRF16Parser(self.real_trf16)
        parser.parse_all()
        parser.update_board_numbers()

        # Get round 2 pairings
        round2_pairings = parser.parse_round_pairings(2)

        # In round 2, we should see:
        # Board 1 (Psarianos) vs Board 7 (Naoum) - Psarianos won as white
        # Board 2 (Psarakis) vs Board 8 (Bairamian) - Psarakis won as black

        # Find the pairing where Psarianos plays
        found_pairing = False
        for pairing in round2_pairings:
            if pairing.white_player_id:
                white = parser.players.get(pairing.white_player_id)
                black = parser.players.get(pairing.black_player_id)
                if white and black:
                    if (
                        white.name == "Psarianos,Emmanouil"
                        and black.name == "Naoum,Spyridon"
                    ):
                        found_pairing = True
                        self.assertEqual(pairing.result, "1-0")
                        break

        self.assertTrue(found_pairing, "Expected Psarianos vs Naoum pairing not found")

    def test_converter_with_real_data(self):
        """Test the converter with real tournament data."""
        converter = TRF16Converter(self.real_trf16)
        converter.parse()

        # Create tournament builder
        builder = converter.create_tournament_builder()

        # Should have correct league setup
        self.assertEqual(
            builder.metadata.league_name, "ΔΙΑΣΥΛΛΟΓΙΚΟ ΚΥΠΕΛΛΟ ΚΡΗΤΙΚΗΣ ΦΙΛΙΑΣ 2024"
        )
        self.assertEqual(builder.metadata.competitor_type, "team")
        self.assertEqual(builder.metadata.season_settings["rounds"], 7)

        # Teams should be added
        self.assertIn("ΣΑΧ", builder.metadata.teams)
        self.assertIn("Α.Π.Ο. ΜΙΚΗΣ ΘΕΟΔΩΡΑΚΗΣ", builder.metadata.teams)


if __name__ == "__main__":
    unittest.main()
