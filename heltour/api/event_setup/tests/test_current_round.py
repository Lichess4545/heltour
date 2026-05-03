"""Tests for the current-round resolver in the event-setup domain."""

from fastapi import HTTPException

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from heltour.api.event_setup.service import current_round_sync
from heltour.tournament.models import League, Round, Season


class CurrentRoundTests(TestCase):
    def test_picks_latest_published_in_progress_round(self):
        league = League.objects.create(
            name="CR", tag="cr", competitor_type="team", rating_type="classical",
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

        dto = current_round_sync("cr")
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

        dto = current_round_sync("cr2")
        self.assertEqual(dto.round_number, 2)

    def test_404_when_league_missing(self):
        with self.assertRaises(HTTPException) as ctx:
            current_round_sync("doesnotexist")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "league not found")

    def test_404_when_no_published_round(self):
        League.objects.create(
            name="empty", tag="empty", competitor_type="team",
            rating_type="classical",
        )
        with self.assertRaises(HTTPException) as ctx:
            current_round_sync("empty")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "no published round")

    def test_uses_constant_queries(self):
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
        current_round_sync("crq")
        with CaptureQueriesContext(connection) as ctx:
            current_round_sync("crq")
        # Expected upper bound: League.get + Round.first(select_related season) = 2.
        # Cacheops may further reduce this; we only care it's not unbounded.
        self.assertLessEqual(len(ctx.captured_queries), 4)
