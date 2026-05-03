"""Tests for the sync service functions backing the round-matches routes.

We exercise the sync handlers directly rather than going through the
HTTP layer — the HTTP layer is a thin ``in_thread`` wrapper around
these, so testing them directly keeps the suite fast. The HTTP layer
itself is covered separately in ``test_http.py``.

Query-count assertions guard against N+1 regressions: as more matches
are added to a round, the query count must stay constant.
"""

from fastapi import HTTPException

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from heltour.api.round_management.service import (
    round_matches_by_id_sync,
    round_matches_by_slug_sync,
)
from heltour.api.round_management.tests.builders import make_lone_round, make_team_round
from heltour.api.shared.auth import Viewer
from heltour.tournament.models import League, LonePlayerPairing, Player, Round, Season

_ANON = Viewer.anonymous()


class RoundMatchesByIdTeamTests(TestCase):
    def test_returns_team_matches_and_player_matches(self):
        rnd = make_team_round(
            league_tag="tl1", season_tag="s1", boards=2, team_count=2,
        )
        dto = round_matches_by_id_sync(rnd.pk, _ANON, None)

        self.assertEqual(dto.round_id, rnd.pk)
        self.assertEqual(dto.round_number, 1)
        self.assertEqual(dto.event_tag, "s1")
        self.assertEqual(dto.league_tag, "tl1")
        self.assertTrue(dto.is_team)
        self.assertFalse(dto.is_completed)
        self.assertFalse(dto.settings.use_fide_information)

        self.assertEqual(len(dto.team_matches), 1)
        tm = dto.team_matches[0]
        self.assertEqual(tm.pairing_order, 1)
        self.assertEqual(tm.white_team_name, "tl1-T1")
        self.assertEqual(tm.black_team_name, "tl1-T2")
        self.assertFalse(tm.is_bye)

        self.assertEqual(len(dto.matches), 2)
        m1, m2 = dto.matches
        self.assertEqual(m1.board_number, 1)
        self.assertEqual(m2.board_number, 2)
        self.assertEqual(m1.team_match_id, tm.id)
        self.assertEqual(m1.white_username, "tl1_p1")
        self.assertEqual(m1.black_username, "tl1_p3")
        self.assertEqual(m1.white_rating, 1501)
        self.assertEqual(m1.black_rating, 1503)
        self.assertEqual(m1.result, "1-0")
        self.assertIsNone(m1.white_fide_name)
        self.assertIsNone(m1.white_gender)

    def test_event_rounds_lists_all_rounds_in_order(self):
        league = League.objects.create(
            name="L", tag="l1", competitor_type="team", rating_type="classical",
        )
        season = Season.objects.create(
            league=league, name="S", tag="s1", rounds=3, boards=2,
        )
        rounds = list(Round.objects.filter(season=season).order_by("number"))
        rounds[0].publish_pairings = True
        rounds[0].is_completed = True
        rounds[0].save()
        rounds[1].publish_pairings = True
        rounds[1].save()

        dto = round_matches_by_id_sync(rounds[1].pk, _ANON, None)
        self.assertEqual(len(dto.rounds), 3)
        self.assertEqual([r.round_number for r in dto.rounds], [1, 2, 3])
        self.assertEqual(
            [r.is_published for r in dto.rounds], [True, True, False],
        )
        self.assertEqual(
            [r.is_completed for r in dto.rounds], [True, False, False],
        )

    def test_use_fide_information_reflects_league_flag(self):
        rnd = make_team_round(
            league_tag="fideleague", season_tag="s1", boards=2, team_count=2,
            show_fide_names=True,
        )
        dto = round_matches_by_id_sync(rnd.pk, _ANON, None)
        self.assertTrue(dto.settings.use_fide_information)

    def test_404_when_round_missing(self):
        with self.assertRaises(HTTPException) as ctx:
            round_matches_by_id_sync(999_999, _ANON, None)
        self.assertEqual(ctx.exception.status_code, 404)


class RoundMatchesByIdLoneTests(TestCase):
    def test_returns_individual_matches(self):
        rnd = make_lone_round(
            league_tag="ll1", season_tag="ls1", pairing_count=3,
        )
        dto = round_matches_by_id_sync(rnd.pk, _ANON, None)
        self.assertFalse(dto.is_team)
        self.assertEqual(dto.team_matches, [])
        self.assertEqual(len(dto.matches), 3)
        self.assertEqual(
            [m.white_username for m in dto.matches],
            ["ll1_w1", "ll1_w2", "ll1_w3"],
        )
        for m in dto.matches:
            self.assertIsNone(m.board_number)
            self.assertIsNone(m.team_match_id)

    def test_handles_lone_pairing_with_missing_player(self):
        rnd = make_lone_round(
            league_tag="ll2", season_tag="ls2", pairing_count=1,
        )
        solo = Player.objects.create(lichess_username="ll2_solo")
        LonePlayerPairing.objects.create(
            round=rnd, white=solo, black=None, pairing_order=2, result="",
            game_link="",
        )
        dto = round_matches_by_id_sync(rnd.pk, _ANON, None)
        self.assertEqual(len(dto.matches), 2)
        bye = dto.matches[1]
        self.assertEqual(bye.white_username, "ll2_solo")
        self.assertIsNone(bye.black_username)
        self.assertIsNone(bye.black_rating)


class RoundMatchesBySlugTests(TestCase):
    def test_resolves_round_by_slug(self):
        rnd = make_team_round(
            league_tag="slug-l", season_tag="slug-s", boards=2, team_count=2,
        )
        dto = round_matches_by_slug_sync("slug-l", "slug-s", 1, _ANON, None)
        self.assertEqual(dto.round_id, rnd.pk)

    def test_404_on_missing_slug(self):
        with self.assertRaises(HTTPException) as ctx:
            round_matches_by_slug_sync("nope", "nope", 1, _ANON, None)
        self.assertEqual(ctx.exception.status_code, 404)


class NoNPlusOneTests(TestCase):
    """Lock down the query counts for the round-matches handler so future
    edits can't accidentally reintroduce N+1.

    Pattern: build a small round and a larger round, then assert the query
    count for the larger round is the same as for the small one. Each round
    uses a distinct league/season tag so cacheops can't skip the second call.
    """

    def _count_queries(self, callable_):
        with CaptureQueriesContext(connection) as ctx:
            callable_()
        return len(ctx.captured_queries)

    def test_team_round_query_count_is_constant_in_dataset_size(self):
        small = make_team_round(
            league_tag="nplus_team_s", season_tag="s", boards=2, team_count=2,
        )
        large = make_team_round(
            league_tag="nplus_team_l", season_tag="l", boards=4, team_count=6,
        )

        small_count = self._count_queries(
            lambda: round_matches_by_id_sync(small.pk, _ANON, None)
        )
        large_count = self._count_queries(
            lambda: round_matches_by_id_sync(large.pk, _ANON, None)
        )

        small_dto = round_matches_by_id_sync(small.pk, _ANON, None)
        large_dto = round_matches_by_id_sync(large.pk, _ANON, None)
        self.assertEqual(len(small_dto.matches), 2)
        self.assertEqual(len(large_dto.matches), 12)
        self.assertEqual(len(small_dto.team_matches), 1)
        self.assertEqual(len(large_dto.team_matches), 3)

        self.assertEqual(
            small_count, large_count,
            f"team-round query count grew with data: {small_count} -> {large_count}",
        )
        self.assertLessEqual(small_count, 6)

    def test_lone_round_query_count_is_constant_in_dataset_size(self):
        small = make_lone_round(
            league_tag="nplus_lone_s", season_tag="s", pairing_count=2,
        )
        large = make_lone_round(
            league_tag="nplus_lone_l", season_tag="l", pairing_count=20,
        )

        small_count = self._count_queries(
            lambda: round_matches_by_id_sync(small.pk, _ANON, None)
        )
        large_count = self._count_queries(
            lambda: round_matches_by_id_sync(large.pk, _ANON, None)
        )

        large_dto = round_matches_by_id_sync(large.pk, _ANON, None)
        self.assertEqual(len(large_dto.matches), 20)

        self.assertEqual(
            small_count, large_count,
            f"lone-round query count grew with data: {small_count} -> {large_count}",
        )
        self.assertLessEqual(small_count, 5)
