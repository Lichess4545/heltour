"""Tests for the FastAPI v1 routes (heltour.api.routes.v1).

Tests exercise the sync handler functions directly rather than going through
the HTTP layer — the HTTP layer is a thin `in_thread` wrapper around these,
so testing them directly keeps the suite fast and avoids ASGI/threading
concerns under Django's test transaction.

Query-count assertions guard against N+1 regressions: as more matches are
added to a round, the query count must stay constant.
"""

from fastapi import HTTPException

from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection

from heltour.api.auth import Viewer
from heltour.api.routes.v1 import (
    _current_round_sync,
    _round_matches_by_id_sync,
    _round_matches_by_slug_sync,
)

_ANON = Viewer.anonymous()
from heltour.tournament.models import (
    League,
    LonePlayerPairing,
    Player,
    Round,
    Season,
    Team,
    TeamMember,
    TeamPairing,
    TeamPlayerPairing,
)


def _make_team_round(
    *,
    league_tag: str,
    season_tag: str,
    boards: int,
    team_count: int,
    publish: bool = True,
    show_fide_names: bool = False,
):
    """Build a single team Round with `team_count // 2` team matches and
    `boards` boards each. Returns the created Round.
    """
    league = League.objects.create(
        name=f"League {league_tag}",
        tag=league_tag,
        competitor_type="team",
        rating_type="classical",
        show_fide_names=show_fide_names,
    )
    season = Season.objects.create(
        league=league,
        name=f"Season {season_tag}",
        tag=season_tag,
        rounds=1,
        boards=boards,
    )
    rnd = Round.objects.get(season=season, number=1)
    rnd.publish_pairings = publish
    rnd.save()

    teams = []
    player_n = 0
    for t in range(1, team_count + 1):
        team = Team.objects.create(season=season, number=t, name=f"{league_tag}-T{t}")
        for b in range(1, boards + 1):
            player_n += 1
            p = Player.objects.create(
                lichess_username=f"{league_tag}_p{player_n}",
                profile={"perfs": {"classical": {"rating": 1500 + player_n}}},
            )
            TeamMember.objects.create(team=team, player=p, board_number=b)
        teams.append(team)

    # Pair teams (1 vs 2, 3 vs 4, ...).
    pairing_order = 0
    for i in range(0, team_count, 2):
        pairing_order += 1
        white_team = teams[i]
        black_team = teams[i + 1]
        tp = TeamPairing.objects.create(
            white_team=white_team,
            black_team=black_team,
            round=rnd,
            pairing_order=pairing_order,
        )
        wm = list(white_team.teammember_set.order_by("board_number"))
        bm = list(black_team.teammember_set.order_by("board_number"))
        for b in range(boards):
            TeamPlayerPairing.objects.create(
                team_pairing=tp,
                board_number=b + 1,
                white=wm[b].player,
                black=bm[b].player,
                result="1-0" if b % 2 == 0 else "0-1",
                game_link="",
            )
    return rnd


def _make_lone_round(
    *,
    league_tag: str,
    season_tag: str,
    pairing_count: int,
    publish: bool = True,
):
    league = League.objects.create(
        name=f"Lone {league_tag}",
        tag=league_tag,
        competitor_type="individual",
        rating_type="classical",
    )
    season = Season.objects.create(
        league=league, name=f"Season {season_tag}", tag=season_tag, rounds=1,
    )
    rnd = Round.objects.get(season=season, number=1)
    rnd.publish_pairings = publish
    rnd.save()

    for i in range(1, pairing_count + 1):
        white = Player.objects.create(
            lichess_username=f"{league_tag}_w{i}",
            profile={"perfs": {"classical": {"rating": 1700 + i}}},
        )
        black = Player.objects.create(
            lichess_username=f"{league_tag}_b{i}",
            profile={"perfs": {"classical": {"rating": 1600 + i}}},
        )
        LonePlayerPairing.objects.create(
            round=rnd,
            white=white,
            black=black,
            pairing_order=i,
            result="1-0",
            game_link="",
        )
    return rnd


class RoundMatchesByIdTeamTests(TestCase):
    def test_returns_team_matches_and_player_matches(self):
        rnd = _make_team_round(
            league_tag="tl1", season_tag="s1", boards=2, team_count=2,
        )
        dto = _round_matches_by_id_sync(rnd.pk, _ANON, None)

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
        # round 1: published+complete; round 2: published; round 3: unpublished.
        rounds = list(Round.objects.filter(season=season).order_by("number"))
        rounds[0].publish_pairings = True
        rounds[0].is_completed = True
        rounds[0].save()
        rounds[1].publish_pairings = True
        rounds[1].save()
        # rounds[2] left as default (unpublished, not completed).

        dto = _round_matches_by_id_sync(rounds[1].pk, _ANON, None)
        self.assertEqual(len(dto.rounds), 3)
        self.assertEqual([r.round_number for r in dto.rounds], [1, 2, 3])
        self.assertEqual(
            [r.is_published for r in dto.rounds], [True, True, False],
        )
        self.assertEqual(
            [r.is_completed for r in dto.rounds], [True, False, False],
        )

    def test_use_fide_information_reflects_league_flag(self):
        rnd = _make_team_round(
            league_tag="fideleague", season_tag="s1", boards=2, team_count=2,
            show_fide_names=True,
        )
        dto = _round_matches_by_id_sync(rnd.pk, _ANON, None)
        self.assertTrue(dto.settings.use_fide_information)

    def test_404_when_round_missing(self):
        with self.assertRaises(HTTPException) as ctx:
            _round_matches_by_id_sync(999_999, _ANON, None)
        self.assertEqual(ctx.exception.status_code, 404)


class RoundMatchesByIdLoneTests(TestCase):
    def test_returns_individual_matches(self):
        rnd = _make_lone_round(
            league_tag="ll1", season_tag="ls1", pairing_count=3,
        )
        dto = _round_matches_by_id_sync(rnd.pk, _ANON, None)
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
        rnd = _make_lone_round(
            league_tag="ll2", season_tag="ls2", pairing_count=1,
        )
        # Add a bye-style pairing with no black player.
        solo = Player.objects.create(lichess_username="ll2_solo")
        LonePlayerPairing.objects.create(
            round=rnd, white=solo, black=None, pairing_order=2, result="",
            game_link="",
        )
        dto = _round_matches_by_id_sync(rnd.pk, _ANON, None)
        self.assertEqual(len(dto.matches), 2)
        bye = dto.matches[1]
        self.assertEqual(bye.white_username, "ll2_solo")
        self.assertIsNone(bye.black_username)
        self.assertIsNone(bye.black_rating)


class RoundMatchesBySlugTests(TestCase):
    def test_resolves_round_by_slug(self):
        rnd = _make_team_round(
            league_tag="slug-l", season_tag="slug-s", boards=2, team_count=2,
        )
        dto = _round_matches_by_slug_sync("slug-l", "slug-s", 1, _ANON, None)
        self.assertEqual(dto.round_id, rnd.pk)

    def test_404_on_missing_slug(self):
        with self.assertRaises(HTTPException) as ctx:
            _round_matches_by_slug_sync("nope", "nope", 1, _ANON, None)
        self.assertEqual(ctx.exception.status_code, 404)


class CurrentRoundTests(TestCase):
    def test_picks_latest_published_in_progress_round(self):
        league = League.objects.create(
            name="CR", tag="cr", competitor_type="team", rating_type="classical",
        )
        season = Season.objects.create(
            league=league, name="S", tag="s1", rounds=3, boards=2,
        )
        rounds = list(Round.objects.filter(season=season).order_by("number"))
        # Round 1 published+complete, Round 2 published+in-progress, Round 3 unpublished.
        rounds[0].publish_pairings = True
        rounds[0].is_completed = True
        rounds[0].save()
        rounds[1].publish_pairings = True
        rounds[1].save()

        dto = _current_round_sync("cr")
        # in-progress (is_completed=False) sorts first by `is_completed, -number`.
        self.assertEqual(dto.round_number, 2)
        self.assertEqual(dto.round_id, rounds[1].pk)
        self.assertEqual(dto.event_tag, "s1")
        self.assertEqual(dto.league_tag, "cr")

    def test_falls_back_to_latest_completed_when_nothing_in_progress(self):
        league = League.objects.create(
            name="CR2", tag="cr2", competitor_type="team", rating_type="classical",
        )
        season = Season.objects.create(
            league=league, name="S", tag="s1", rounds=2, boards=2,
        )
        rounds = list(Round.objects.filter(season=season).order_by("number"))
        for r in rounds:
            r.publish_pairings = True
            r.is_completed = True
            r.save()

        dto = _current_round_sync("cr2")
        # Both completed → ordered by `-number`, so round 2 wins.
        self.assertEqual(dto.round_number, 2)

    def test_404_when_league_missing(self):
        with self.assertRaises(HTTPException) as ctx:
            _current_round_sync("doesnotexist")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "league not found")

    def test_404_when_no_published_round(self):
        League.objects.create(
            name="empty", tag="empty", competitor_type="team",
            rating_type="classical",
        )
        with self.assertRaises(HTTPException) as ctx:
            _current_round_sync("empty")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "no published round")


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
        small = _make_team_round(
            league_tag="nplus_team_s", season_tag="s", boards=2, team_count=2,
        )
        large = _make_team_round(
            league_tag="nplus_team_l", season_tag="l", boards=4, team_count=6,
        )

        small_count = self._count_queries(
            lambda: _round_matches_by_id_sync(small.pk, _ANON, None)
        )
        large_count = self._count_queries(
            lambda: _round_matches_by_id_sync(large.pk, _ANON, None)
        )

        # Sanity: returned matches really do scale, so any per-row query
        # would show up.
        small_dto = _round_matches_by_id_sync(small.pk, _ANON, None)
        large_dto = _round_matches_by_id_sync(large.pk, _ANON, None)
        self.assertEqual(len(small_dto.matches), 2)
        self.assertEqual(len(large_dto.matches), 12)
        self.assertEqual(len(small_dto.team_matches), 1)
        self.assertEqual(len(large_dto.team_matches), 3)

        self.assertEqual(
            small_count, large_count,
            f"team-round query count grew with data: {small_count} -> {large_count}",
        )
        # Expected: Round.get + event_rounds + TeamPairing + TeamPlayerPairing = 4.
        self.assertLessEqual(small_count, 6)

    def test_lone_round_query_count_is_constant_in_dataset_size(self):
        small = _make_lone_round(
            league_tag="nplus_lone_s", season_tag="s", pairing_count=2,
        )
        large = _make_lone_round(
            league_tag="nplus_lone_l", season_tag="l", pairing_count=20,
        )

        small_count = self._count_queries(
            lambda: _round_matches_by_id_sync(small.pk, _ANON, None)
        )
        large_count = self._count_queries(
            lambda: _round_matches_by_id_sync(large.pk, _ANON, None)
        )

        large_dto = _round_matches_by_id_sync(large.pk, _ANON, None)
        self.assertEqual(len(large_dto.matches), 20)

        self.assertEqual(
            small_count, large_count,
            f"lone-round query count grew with data: {small_count} -> {large_count}",
        )
        # Expected: Round.get + event_rounds + LonePlayerPairing = 3.
        self.assertLessEqual(small_count, 5)

    def test_current_round_uses_constant_queries(self):
        league = League.objects.create(
            name="cr-q", tag="crq", competitor_type="team", rating_type="classical",
        )
        season = Season.objects.create(
            league=league, name="S", tag="s1", rounds=2, boards=2,
        )
        rounds = list(Round.objects.filter(season=season).order_by("number"))
        for r in rounds:
            r.publish_pairings = True
            r.save()

        # First call warms cacheops; second call is what we measure to keep
        # the assertion stable regardless of cache state.
        _current_round_sync("crq")
        n = self._count_queries(lambda: _current_round_sync("crq"))
        # Expected upper bound: League.get + Round.first(select_related season) = 2.
        # Cacheops may further reduce this; we only care it's not unbounded.
        self.assertLessEqual(n, 4)
