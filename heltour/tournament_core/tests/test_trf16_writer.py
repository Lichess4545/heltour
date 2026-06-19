"""
Tests for TRF16 writer/serializer.

Verifies that write_trf16 produces output that round-trips through TRF16Parser.
"""

import unittest
from datetime import datetime

from heltour.tournament_core.trf16 import (
    TRF16Header,
    TRF16Parser,
    TRF16Player,
    TRF16Team,
)
from heltour.tournament_core.trf16_writer import write_trf16


def _make_header(**overrides):
    defaults = {
        "tournament_name": "Test Tournament",
        "city": "Internet",
        "federation": "INT",
        "start_date": datetime(2024, 1, 1),
        "end_date": datetime(2024, 1, 31),
        "num_players": 4,
        "num_rated_players": 4,
        "num_teams": 0,
        "tournament_type": "Swiss",
        "chief_arbiter": "Admin",
        "deputy_arbiters": ["Deputy One"],
        "time_control": "15+10",
        "num_rounds": 3,
        "round_dates": [],
    }
    defaults.update(overrides)
    return TRF16Header(**defaults)


def _make_player(start_number, name, rating=1500, results=None, **overrides):
    defaults = {
        "team_number": start_number,
        "board_number": 0,
        "title": "m",
        "name": name,
        "rating": rating,
        "federation": "INT",
        "fide_id": "0",
        "birth_year": 0,
        "points": 0.0,
        "rank": 0,
        "start_number": start_number,
        "results": results or [],
    }
    defaults.update(overrides)
    return TRF16Player(**defaults)


class TestTRF16WriterRoundTrip(unittest.TestCase):
    """Round-trip: write → parse → verify fields match."""

    def _round_trip(self, header, players, teams=None):
        output = write_trf16(header, players, teams)
        parser = TRF16Parser(output)
        return parser.parse_all()

    def test_round_trip_header(self):
        header = _make_header(
            tournament_name="Round Trip Test",
            city="Testville",
            federation="TST",
            num_players=2,
            num_rated_players=2,
            num_rounds=1,
            chief_arbiter="Chief",
            deputy_arbiters=["Dep A", "Dep B"],
            time_control="90+30",
        )
        players = {
            1: _make_player(1, "Alice", 2000, [(2, "w", "1")], points=1.0, rank=1),
            2: _make_player(2, "Bob", 1800, [(1, "b", "0")], points=0.0, rank=2),
        }

        parsed_h, _, _ = self._round_trip(header, players)

        self.assertEqual(parsed_h.tournament_name, "Round Trip Test")
        self.assertEqual(parsed_h.city, "Testville")
        self.assertEqual(parsed_h.federation, "TST")
        self.assertEqual(parsed_h.num_players, 2)
        self.assertEqual(parsed_h.num_rated_players, 2)
        self.assertEqual(parsed_h.num_rounds, 1)
        self.assertEqual(parsed_h.chief_arbiter, "Chief")
        self.assertEqual(parsed_h.deputy_arbiters, ["Dep A", "Dep B"])
        self.assertEqual(parsed_h.time_control, "90+30")

    def test_round_trip_players(self):
        header = _make_header(num_players=2, num_rated_players=2, num_rounds=1)
        players = {
            1: _make_player(
                1, "Alice", 2000, [(2, "w", "1")], points=1.0, rank=1, federation="USA"
            ),
            2: _make_player(
                2, "Bob", 1800, [(1, "b", "0")], points=0.0, rank=2, federation="GBR"
            ),
        }

        _, parsed_players, _ = self._round_trip(header, players)

        self.assertEqual(len(parsed_players), 2)

        p1 = parsed_players[1]
        self.assertEqual(p1.name, "Alice")
        self.assertEqual(p1.rating, 2000)
        self.assertEqual(p1.federation, "USA")
        self.assertEqual(p1.points, 1.0)
        self.assertEqual(p1.rank, 1)
        self.assertEqual(len(p1.results), 1)
        self.assertEqual(p1.results[0], (2, "w", "1"))

        p2 = parsed_players[2]
        self.assertEqual(p2.name, "Bob")
        self.assertEqual(p2.rating, 1800)
        self.assertEqual(p2.results[0], (1, "b", "0"))

    def test_round_trip_teams(self):
        header = _make_header(num_players=4, num_rated_players=4, num_teams=2, num_rounds=1)
        players = {
            1: _make_player(1, "Alice", 2000, [(3, "w", "1")], points=1.0, rank=1),
            2: _make_player(2, "Bob", 1900, [(4, "b", "0")], points=0.0, rank=4),
            3: _make_player(3, "Charlie", 1950, [(1, "b", "0")], points=0.0, rank=3),
            4: _make_player(4, "Dave", 1850, [(2, "w", "1")], points=1.0, rank=2),
        }
        teams = {
            "Dragons": TRF16Team(name="Dragons", player_ids=[1, 2]),
            "Knights": TRF16Team(name="Knights", player_ids=[3, 4]),
        }

        _, _, parsed_teams = self._round_trip(header, players, teams)

        self.assertEqual(len(parsed_teams), 2)
        self.assertIn("Dragons", parsed_teams)
        self.assertIn("Knights", parsed_teams)
        self.assertEqual(parsed_teams["Dragons"].player_ids, [1, 2])
        self.assertEqual(parsed_teams["Knights"].player_ids, [3, 4])

    def test_round_trip_draw(self):
        header = _make_header(num_players=2, num_rated_players=2, num_rounds=1)
        players = {
            1: _make_player(1, "Alice", 2000, [(2, "w", "=")], points=0.5, rank=1),
            2: _make_player(2, "Bob", 1800, [(1, "b", "=")], points=0.5, rank=2),
        }

        _, parsed_players, _ = self._round_trip(header, players)

        self.assertEqual(parsed_players[1].results[0], (2, "w", "="))
        self.assertEqual(parsed_players[2].results[0], (1, "b", "="))


class TestTRF16WriterEdgeCases(unittest.TestCase):
    """Edge cases: byes, forfeits, zero-rated, missing data."""

    def _round_trip_players(self, header, players, teams=None):
        output = write_trf16(header, players, teams)
        parser = TRF16Parser(output)
        parser.parse_header()
        return parser.parse_players()

    def test_bye(self):
        header = _make_header(num_players=2, num_rated_players=2, num_rounds=2)
        players = {
            1: _make_player(
                1, "Alice", 2000, [(None, "-", "-"), (2, "w", "1")], points=1.0, rank=1
            ),
            2: _make_player(
                2, "Bob", 1800, [(None, "-", "-"), (1, "b", "0")], points=0.0, rank=2
            ),
        }

        parsed = self._round_trip_players(header, players)

        self.assertEqual(parsed[1].results[0], (None, "-", "-"))
        self.assertEqual(parsed[1].results[1], (2, "w", "1"))

    def test_forfeit_win(self):
        header = _make_header(num_players=2, num_rated_players=2, num_rounds=1)
        players = {
            1: _make_player(1, "Alice", 2000, [(0, "-", "+")], points=1.0, rank=1),
            2: _make_player(2, "Bob", 1800, [(0, "-", "-")], points=0.0, rank=2),
        }

        parsed = self._round_trip_players(header, players)

        # Forfeit win round-trips exactly
        self.assertEqual(parsed[1].results[0], (0, "-", "+"))
        # Forfeit loss becomes indistinguishable from bye in TRF16 format
        self.assertEqual(parsed[2].results[0], (None, "-", "-"))

    def test_zero_rated_player(self):
        header = _make_header(num_players=2, num_rated_players=1, num_rounds=1)
        players = {
            1: _make_player(1, "Alice", 0, [(2, "w", "1")], points=1.0, rank=1),
            2: _make_player(2, "Bob", 1800, [(1, "b", "0")], points=0.0, rank=2),
        }

        parsed = self._round_trip_players(header, players)

        self.assertEqual(parsed[1].rating, 0)
        self.assertEqual(parsed[1].name, "Alice")

    def test_missing_birth_date(self):
        header = _make_header(num_players=1, num_rated_players=1, num_rounds=1)
        players = {
            1: _make_player(
                1, "Alice", 2000, [(None, "-", "-")], points=0.0, rank=1, birth_year=0
            ),
        }

        parsed = self._round_trip_players(header, players)

        self.assertEqual(parsed[1].birth_year, 0)
        self.assertEqual(parsed[1].name, "Alice")

    def test_with_birth_date(self):
        header = _make_header(num_players=1, num_rated_players=1, num_rounds=1)
        players = {
            1: _make_player(
                1, "Alice", 2000, [(None, "-", "-")], points=0.0, rank=1, birth_year=1990
            ),
        }

        parsed = self._round_trip_players(header, players)

        self.assertEqual(parsed[1].birth_year, 1990)

    def test_no_title(self):
        header = _make_header(num_players=1, num_rated_players=1, num_rounds=1)
        players = {
            1: _make_player(
                1, "Alice", 2000, [(None, "-", "-")], points=0.0, rank=1, title=""
            ),
        }

        parsed = self._round_trip_players(header, players)

        # Empty title gets written as "-", which round-trips as "-"
        self.assertEqual(parsed[1].title, "-")
        self.assertEqual(parsed[1].name, "Alice")

    def test_no_federation(self):
        header = _make_header(num_players=1, num_rated_players=1, num_rounds=1)
        players = {
            1: _make_player(
                1, "Alice", 2000, [(None, "-", "-")], points=0.0, rank=1, federation=""
            ),
        }

        parsed = self._round_trip_players(header, players)

        self.assertEqual(parsed[1].federation, "---")
        self.assertEqual(parsed[1].name, "Alice")

    def test_lone_tournament_no_teams(self):
        header = _make_header(num_players=2, num_rated_players=2, num_teams=0, num_rounds=1)
        players = {
            1: _make_player(1, "Alice", 2000, [(2, "w", "1")], points=1.0, rank=1),
            2: _make_player(2, "Bob", 1800, [(1, "b", "0")], points=0.0, rank=2),
        }

        output = write_trf16(header, players)

        self.assertNotIn("013", output)
        parser = TRF16Parser(output)
        _, _, teams = parser.parse_all()
        self.assertEqual(len(teams), 0)

    def test_multiple_rounds(self):
        header = _make_header(num_players=3, num_rated_players=3, num_rounds=3)
        players = {
            1: _make_player(
                1,
                "Alice",
                2000,
                [(2, "w", "1"), (3, "b", "="), (None, "-", "-")],
                points=1.5,
                rank=1,
            ),
            2: _make_player(
                2,
                "Bob",
                1900,
                [(1, "b", "0"), (None, "-", "-"), (3, "w", "1")],
                points=1.0,
                rank=2,
            ),
            3: _make_player(
                3,
                "Charlie",
                1800,
                [(None, "-", "-"), (1, "w", "="), (2, "b", "0")],
                points=0.5,
                rank=3,
            ),
        }

        parsed = self._round_trip_players(header, players)

        self.assertEqual(len(parsed[1].results), 3)
        self.assertEqual(parsed[1].results[0], (2, "w", "1"))
        self.assertEqual(parsed[1].results[1], (3, "b", "="))
        self.assertEqual(parsed[1].results[2], (None, "-", "-"))


class TestTRF16WriterFromExistingSample(unittest.TestCase):
    """Parse existing TRF16 sample → extract data → write → re-parse → verify."""

    SAMPLE = """012 Test Team Tournament
022 Test City
032 GRE
042 2024/11/23
052 2024/11/24
062 12 (10)
072 10
082 3
092 Team Swiss System
102 Test Arbiter
112 Assistant One, Assistant Two
122 15 minutes plus 10 sec per move
142 3
132                                                                                        24/11/23  24/11/23  24/11/24

001    1 m    Player One                        1500 GRE    12345678 2000/01/01  2.5   4  0000 - -     7 w 1     9 b 0
001    2 m    Player Two                        1450 GRE    12345679 2001/01/01  1.5   6  0000 - -     8 b 0    10 w 1
001    3 m    Player Three                      1400 GRE    12345680 2002/01/01  2.0   5  0000 - -     9 w 1    11 b 0
001    4 m    Player Four                       1350 GRE    12345681 2003/01/01  1.0   8  0000 - -    10 b 0    12 w 0
001    5 m    Player Five                       1600 GRE    12345682 1999/01/01  2.5   3     1 w 1     9 b 1  0000 - -
001    6 m    Player Six                        1550 GRE    12345683 1998/01/01  1.5   7     2 b 1    10 w 0  0000 - -
001    7 m    Player Seven                      1700 GRE    12345684 1997/01/01  2.0   2     1 b 0    11 w 1  0000 - -
001    8 m    Player Eight                      1650 GRE    12345685 1996/01/01  3.0   1     2 w 1    12 b 1  0000 - -
001    9 m    Player Nine                       1300 GRE    12345686 2004/01/01  0.5  11     3 b 0     1 w 1     5 w 0
001   10 m    Player Ten                        1250 GRE    12345687 2005/01/01  1.5   9     4 w 1     2 b 0     6 b 1
001   11 m    Player Eleven                     1200 GRE    12345688 2006/01/01  1.0  10  0000 - -     3 w 1     7 b 0
001   12 m    Player Twelve                     1150 GRE    12345689 2007/01/01  0.0  12  0000 - -     4 b 1     8 w 0

013 Team Alpha                           1    2    3    4
013 Team Beta                            5    6    7    8
013 Team Gamma                           9   10   11   12"""

    def test_full_round_trip(self):
        # Parse original
        original_parser = TRF16Parser(self.SAMPLE)
        orig_header, orig_players, orig_teams = original_parser.parse_all()

        # Write
        output = write_trf16(orig_header, orig_players, orig_teams)

        # Re-parse
        reparser = TRF16Parser(output)
        new_header, new_players, new_teams = reparser.parse_all()

        # Verify header
        self.assertEqual(new_header.tournament_name, orig_header.tournament_name)
        self.assertEqual(new_header.city, orig_header.city)
        self.assertEqual(new_header.federation, orig_header.federation)
        self.assertEqual(new_header.num_players, orig_header.num_players)
        self.assertEqual(new_header.num_rated_players, orig_header.num_rated_players)
        self.assertEqual(new_header.num_teams, orig_header.num_teams)
        self.assertEqual(new_header.num_rounds, orig_header.num_rounds)

        # Verify all players
        self.assertEqual(len(new_players), len(orig_players))
        for start_num in orig_players:
            orig = orig_players[start_num]
            new = new_players[start_num]
            self.assertEqual(new.name, orig.name, f"Player {start_num} name mismatch")
            self.assertEqual(new.rating, orig.rating, f"Player {start_num} rating mismatch")
            self.assertEqual(
                new.federation, orig.federation, f"Player {start_num} federation mismatch"
            )
            self.assertEqual(new.points, orig.points, f"Player {start_num} points mismatch")
            self.assertEqual(new.rank, orig.rank, f"Player {start_num} rank mismatch")
            self.assertEqual(
                len(new.results),
                len(orig.results),
                f"Player {start_num} result count mismatch",
            )
            for r_idx, (orig_r, new_r) in enumerate(zip(orig.results, new.results)):
                self.assertEqual(
                    new_r,
                    orig_r,
                    f"Player {start_num} round {r_idx + 1} result mismatch",
                )

        # Verify teams
        self.assertEqual(len(new_teams), len(orig_teams))
        for team_name in orig_teams:
            self.assertIn(team_name, new_teams)
            self.assertEqual(
                new_teams[team_name].player_ids, orig_teams[team_name].player_ids
            )


if __name__ == "__main__":
    unittest.main()
