"""When a team is withdrawn (is_active=False) after playing prior rounds,
generating pairings for the next round must keep that team in JavaFo's
input — with include=False — so the active teams' historical pairings
serialize to real opponent numbers in the TRF.

If the withdrawn team is dropped, generate_trf_content falls back to
opponent "0000" while keeping the original color/score, producing lines
like `0000 b 1` that JavaFo rejects with:

    B.A.B.E: Unexpected format of player line: ...
"""

from unittest.mock import patch

from django.test import TestCase

from heltour.tournament import pairinggen
from heltour.tournament.builder import TournamentBuilder
from heltour.tournament.models import Round, Team
from heltour.tournament.pairinggen import generate_trf_content


class TeamWithdrawalPairingTest(TestCase):
    def test_withdrawn_team_passed_to_javafo_with_include_false(self):
        # 4 teams, 2 boards, round 1 played and completed.
        builder = (
            TournamentBuilder()
            .league(
                "Withdraw League",
                "WL",
                "team",
                rating_type="classical",
                pairing_type="swiss-dutch",
                theme="blue",
            )
            .season("WL", "Test Season", rounds=2, boards=2, is_active=True)
            .team("Team A", ("A1", 2000), ("A2", 1950))
            .team("Team B", ("B1", 1900), ("B2", 1850))
            .team("Team C", ("C1", 1800), ("C2", 1750))
            .team("Team D", ("D1", 1700), ("D2", 1650))
            .round(1)
            .match("Team A", "Team B", "1-0", "1-0")
            .match("Team C", "Team D", "1-0", "0-1")
            .complete()
            .build()
        )
        season = builder._db_objects["season"]
        round_1 = Round.objects.get(season=season, number=1)
        round_1.is_completed = True
        round_1.publish_pairings = True
        round_1.save()
        season.calculate_scores()

        # Withdraw Team B.
        team_b = Team.objects.get(season=season, name="Team B")
        team_b.is_active = False
        team_b.save()

        # Round 2: trigger pairing generation, capturing what gets passed
        # to JavaFo without actually invoking the JavaFo binary.
        round_2, _ = Round.objects.get_or_create(
            season=season, number=2, defaults={"is_completed": False}
        )
        captured = {}

        def fake_run(self):
            captured["players"] = self.players
            captured["total_rounds"] = self.total_round_count
            return []

        with patch.object(pairinggen.JavafoInstance, "run", fake_run):
            pairinggen.generate_pairings(round_2)

        players = captured.get("players")
        self.assertIsNotNone(
            players, "expected JavafoInstance.run to be invoked during pairing"
        )

        by_name = {p.player.name: p for p in players}
        self.assertEqual(
            set(by_name),
            {"Team A", "Team B", "Team C", "Team D"},
            "all teams (active + withdrawn) should appear in JavaFo input",
        )
        self.assertFalse(
            by_name["Team B"].include,
            "withdrawn team must be marked include=False",
        )
        for name in ("Team A", "Team C", "Team D"):
            self.assertTrue(
                by_name[name].include,
                f"{name} should remain include=True",
            )

        # Team A's round-1 history must reference the actual Team B object
        # so generate_trf_content emits a real opponent number, not 0000.
        team_a_history = by_name["Team A"].pairings
        self.assertEqual(len(team_a_history), 1)
        self.assertEqual(team_a_history[0].opponent, team_b)

        # End-to-end: TRF generated from the captured players must not
        # contain any malformed `0000 <color> <numeric>` lines, and the
        # withdrawn team's line must end with the not-paired marker.
        trf = generate_trf_content(captured["total_rounds"], players)
        player_lines = [ln for ln in trf.splitlines() if ln.startswith("001")]
        self.assertEqual(len(player_lines), len(players))
        line_by_name = {
            p.player.name: line for p, line in zip(players, player_lines)
        }

        team_a_line = line_by_name["Team A"]
        for malformed in (
            "0000 w 1", "0000 b 1",
            "0000 w 0", "0000 b 0",
            "0000 w =", "0000 b =",
        ):
            self.assertNotIn(
                malformed,
                team_a_line,
                f"Team A's TRF line should not contain malformed `{malformed}`: {team_a_line!r}",
            )

        self.assertTrue(
            line_by_name["Team B"].rstrip().endswith("  0000 - -"),
            f"withdrawn team's TRF line must end with `0000 - -`, got: {line_by_name['Team B']!r}",
        )
