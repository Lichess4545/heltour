import json
import logging
import threading
import time
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase, override_settings
from django.utils import timezone


from heltour.tournament.management.commands.watch_games import (
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
    RATE_LIMIT_BACKOFF_SECONDS,
    WATCHER_MAX_USERNAMES,
    Watcher,
    _chunked,
    _event_matches_league,
    _iter_events,
    _result_for_event,
    apply_event,
    get_active_usernames,
    stream_games,
)
from heltour.tournament.models import (
    LonePlayerPairing,
    PlayerPairing,
)
from heltour.tournament.tests.testutils import (
    Shush,
    createCommonLeagueData,
    get_league,
    get_player,
    get_round,
    get_season,
)


def setUpModule():
    # Silence INFO chatter from the watcher; warnings and errors still surface.
    logging.disable(logging.INFO)


def tearDownModule():
    logging.disable(logging.NOTSET)


def _build_event(
    *,
    game_id="abc123",
    white="Player1",
    black="Player2",
    initial=2700,  # 45 minutes
    increment=45,
    perf="classical",
    rated=True,
    status="started",
    moves="",
    winner=None,
):
    # Matches the real schema from /api/stream/games-by-users:
    #   players.<color>.userId (flat), statusName as the human-readable status.
    event = {
        "id": game_id,
        "rated": rated,
        "perf": perf,
        "statusName": status,
        "moves": moves,
        "clock": {"initial": initial, "increment": increment},
        "players": {
            "white": {"userId": white, "rating": 1500},
            "black": {"userId": black, "rating": 1500},
        },
    }
    if winner is not None:
        event["winner"] = winner
    return event


class _FakeStreamResponse:
    """Mimics a streaming requests.Response for use as a context manager."""

    def __init__(self, lines, status_code=200):
        self._lines = list(lines)
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            err = requests.exceptions.HTTPError(f"HTTP {self.status_code}")
            err.response = self
            raise err

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            yield line


class TestPureHelpers(TestCase):
    def test_result_for_event_draws(self):
        self.assertEqual(_result_for_event("draw", None), "1/2-1/2")
        self.assertEqual(_result_for_event("stalemate", None), "1/2-1/2")
        self.assertEqual(
            _result_for_event("insufficientMaterialClaim", None), "1/2-1/2"
        )

    def test_result_for_event_winners(self):
        self.assertEqual(_result_for_event("mate", "white"), "1-0")
        self.assertEqual(_result_for_event("resign", "black"), "0-1")
        self.assertEqual(_result_for_event("outoftime", "white"), "1-0")

    def test_result_for_event_live_returns_none(self):
        self.assertIsNone(_result_for_event("started", None))
        self.assertIsNone(_result_for_event("created", None))
        self.assertIsNone(_result_for_event("started", "white"))

    def test_result_for_event_timeout_claim_ignored(self):
        self.assertIsNone(_result_for_event("timeout", "white"))
        self.assertIsNone(_result_for_event("timeout", "black"))

    def test_result_for_event_no_winner_no_status(self):
        self.assertIsNone(_result_for_event(None, None))
        self.assertIsNone(_result_for_event("noStart", None))

    def test_chunked(self):
        self.assertEqual(list(_chunked([], 3)), [])
        self.assertEqual(list(_chunked(["a"], 3)), [["a"]])
        self.assertEqual(
            list(_chunked(["a", "b", "c", "d", "e"], 2)),
            [["a", "b"], ["c", "d"], ["e"]],
        )


class TestEventMatchesLeague(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.league = get_league("lone")
        cls.league.time_control = "45+45"
        cls.league.rating_type = "classical"
        cls.league.save()

    def test_match(self):
        self.assertTrue(_event_matches_league(_build_event(), self.league))

    def test_clock_initial_mismatch(self):
        self.assertFalse(
            _event_matches_league(_build_event(initial=600), self.league)
        )

    def test_clock_increment_mismatch(self):
        self.assertFalse(
            _event_matches_league(_build_event(increment=0), self.league)
        )

    def test_perf_mismatch(self):
        self.assertFalse(
            _event_matches_league(_build_event(perf="rapid"), self.league)
        )

    def test_perf_missing_passes(self):
        # Some events may omit perf; don't reject solely on missing perf.
        evt = _build_event()
        del evt["perf"]
        self.assertTrue(_event_matches_league(evt, self.league))

    def test_unrated_rejected(self):
        self.assertFalse(
            _event_matches_league(_build_event(rated=False), self.league)
        )

    def test_missing_clock_rejected(self):
        evt = _build_event()
        del evt["clock"]
        self.assertFalse(_event_matches_league(evt, self.league))


class TestApplyEvent(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.league = get_league("lone")
        cls.league.time_control = "45+45"
        cls.league.rating_type = "classical"
        cls.league.save()
        cls.season = get_season("lone")
        cls.round_ = get_round("lone", 1)
        cls.round_.publish_pairings = True
        cls.round_.is_completed = False
        cls.round_.end_date = timezone.now() + timezone.timedelta(days=2)
        cls.round_.save()
        cls.p1 = get_player("Player1")
        cls.p2 = get_player("Player2")

    def _new_pairing(self, white=None, black=None, **kwargs):
        white = white or self.p1
        black = black or self.p2
        return LonePlayerPairing.objects.create(
            round=self.round_,
            white=white,
            black=black,
            pairing_order=PlayerPairing.objects.count() + 1,
            **kwargs,
        )

    def test_started_event_sets_game_link(self):
        pairing = self._new_pairing()
        self.assertTrue(apply_event(_build_event(game_id="aaa111")))
        pairing.refresh_from_db()
        self.assertIn("aaa111", pairing.game_link)
        self.assertEqual(pairing.tv_state, "default")
        self.assertEqual(pairing.result, "")

    def test_started_event_with_moves_sets_has_moves(self):
        pairing = self._new_pairing()
        self.assertTrue(apply_event(_build_event(moves="e4 c5 Nf3")))
        pairing.refresh_from_db()
        self.assertEqual(pairing.tv_state, "has_moves")

    def test_winner_white_sets_one_zero(self):
        pairing = self._new_pairing()
        self.assertTrue(
            apply_event(_build_event(status="mate", winner="white", moves="e4 e5"))
        )
        pairing.refresh_from_db()
        self.assertEqual(pairing.result, "1-0")
        self.assertEqual(pairing.tv_state, "hide")

    def test_winner_black_sets_zero_one(self):
        pairing = self._new_pairing()
        self.assertTrue(apply_event(_build_event(status="resign", winner="black")))
        pairing.refresh_from_db()
        self.assertEqual(pairing.result, "0-1")

    def test_outoftime_with_winner_sets_result(self):
        pairing = self._new_pairing()
        self.assertTrue(
            apply_event(_build_event(status="outoftime", winner="black"))
        )
        pairing.refresh_from_db()
        self.assertEqual(pairing.result, "0-1")

    def test_draw_status_sets_half_point(self):
        pairing = self._new_pairing()
        self.assertTrue(apply_event(_build_event(status="stalemate")))
        pairing.refresh_from_db()
        self.assertEqual(pairing.result, "1/2-1/2")

    def test_aborted_clears_matching_link(self):
        pairing = self._new_pairing(game_link="https://lichess.org/abc123")
        self.assertTrue(
            apply_event(_build_event(game_id="abc123", status="aborted"))
        )
        pairing.refresh_from_db()
        self.assertEqual(pairing.game_link, "")
        self.assertEqual(pairing.tv_state, "default")

    def test_aborted_does_not_clear_other_link(self):
        pairing = self._new_pairing(game_link="https://lichess.org/zzz999")
        self.assertFalse(
            apply_event(_build_event(game_id="abc123", status="aborted"))
        )
        pairing.refresh_from_db()
        self.assertEqual(pairing.game_link, "https://lichess.org/zzz999")

    def test_existing_link_for_other_game_is_preserved(self):
        pairing = self._new_pairing(game_link="https://lichess.org/zzz999")
        self.assertFalse(apply_event(_build_event(game_id="abc123")))
        pairing.refresh_from_db()
        self.assertEqual(pairing.game_link, "https://lichess.org/zzz999")

    def test_clock_mismatch_skipped(self):
        self._new_pairing()
        self.assertFalse(apply_event(_build_event(initial=600, increment=0)))

    def test_perf_mismatch_skipped(self):
        self._new_pairing()
        self.assertFalse(apply_event(_build_event(perf="rapid")))

    def test_unrated_skipped(self):
        self._new_pairing()
        self.assertFalse(apply_event(_build_event(rated=False)))

    def test_round_not_published_skipped(self):
        self.round_.publish_pairings = False
        self.round_.save()
        try:
            self._new_pairing()
            self.assertFalse(apply_event(_build_event()))
        finally:
            self.round_.publish_pairings = True
            self.round_.save()

    def test_round_completed_skipped(self):
        self.round_.is_completed = True
        self.round_.save()
        try:
            self._new_pairing()
            self.assertFalse(apply_event(_build_event()))
        finally:
            self.round_.is_completed = False
            self.round_.save()

    def test_no_matching_pairing(self):
        self.assertFalse(
            apply_event(_build_event(white="NoSuchUser1", black="NoSuchUser2"))
        )

    def test_already_resolved_pairing_ignored(self):
        pairing = self._new_pairing(result="1-0")
        self.assertFalse(apply_event(_build_event(status="resign", winner="black")))
        pairing.refresh_from_db()
        self.assertEqual(pairing.result, "1-0")

    def test_malformed_events(self):
        with Shush():
            self.assertFalse(apply_event({"id": "zzz"}))
            self.assertFalse(apply_event({"id": "zzz", "players": None}))
            self.assertFalse(apply_event({"id": "zzz", "players": {"white": {}}}))
            self.assertFalse(apply_event({}))
            # Missing "id" — userIds present but no game id.
            self.assertFalse(
                apply_event(
                    {"players": {"white": {"userId": "a"}, "black": {"userId": "b"}}}
                )
            )
            # Old schema with nested user.id should be rejected as malformed.
            self.assertFalse(
                apply_event(
                    {
                        "id": "zzz",
                        "players": {
                            "white": {"user": {"id": "a"}},
                            "black": {"user": {"id": "b"}},
                        },
                    }
                )
            )

    def test_fide_league_accepts_lichess_rapid_perf(self):
        # League configured for FIDE Rapid (cascade or specific) should accept
        # a Lichess rapid game.
        self.league.rating_type = "fide"
        self.league.time_control = "10+5"  # 600s + 5s
        self.league.save()
        try:
            pairing = self._new_pairing()
            self.assertTrue(
                apply_event(
                    _build_event(
                        initial=600, increment=5, perf="rapid", status="resign", winner="white"
                    )
                )
            )
            pairing.refresh_from_db()
            self.assertEqual(pairing.result, "1-0")
        finally:
            self.league.rating_type = "classical"
            self.league.time_control = "45+45"
            self.league.save()

    def test_already_linked_game_bypasses_league_check(self):
        # If the pairing already references this exact game, accept the event
        # even when the league config wouldn't normally validate it (e.g.,
        # mod-set link with different time control).
        from heltour.tournament.models import get_gamelink_from_gameid as gl
        link = gl("hardcoded")
        pairing = self._new_pairing(game_link=link)
        # Event has a clock that wouldn't match the league.
        self.assertTrue(
            apply_event(
                _build_event(
                    game_id="hardcoded",
                    initial=300,  # league expects 2700
                    increment=0,
                    status="resign",
                    winner="black",
                )
            )
        )
        pairing.refresh_from_db()
        self.assertEqual(pairing.result, "0-1")

    def test_username_case_insensitive(self):
        pairing = self._new_pairing()
        self.assertTrue(apply_event(_build_event(white="player1", black="PLAYER2")))
        pairing.refresh_from_db()
        self.assertNotEqual(pairing.game_link, "")


class TestGetActiveUsernames(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()

    def test_returns_lowercased_active_season_players(self):
        usernames = get_active_usernames()
        self.assertEqual(usernames, [f"player{i}" for i in range(1, 9)])

    def test_skips_inactive_season_players(self):
        from heltour.tournament.models import SeasonPlayer
        sp = SeasonPlayer.objects.get(player__lichess_username="Player1")
        sp.is_active = False
        sp.save()
        usernames = get_active_usernames()
        self.assertNotIn("player1", usernames)
        self.assertIn("player2", usernames)

    def test_skips_completed_season(self):
        season = get_season("lone")
        season.is_completed = True
        season.save()
        usernames = get_active_usernames()
        for i in range(1, 9):
            self.assertNotIn(f"player{i}", usernames)

    def test_includes_multiple_active_seasons(self):
        from heltour.tournament.models import SeasonPlayer
        team_season = get_season("team")
        SeasonPlayer.objects.create(season=team_season, player=get_player("Player1"))
        usernames = get_active_usernames()
        self.assertEqual(usernames.count("player1"), 1)


class TestIterEvents(TestCase):
    def test_skips_blank_lines(self):
        resp = _FakeStreamResponse(["", json.dumps({"id": "a"}), ""])
        self.assertEqual(list(_iter_events(resp)), [{"id": "a"}])

    def test_skips_invalid_json(self):
        with Shush():
            resp = _FakeStreamResponse(
                ["{not json", json.dumps({"id": "a"}), "also bad"]
            )
            self.assertEqual(list(_iter_events(resp)), [{"id": "a"}])


class TestStreamGames(TestCase):
    """Tests for the stream_games connection/reconnection loop."""

    def _stop(self):
        return threading.Event()

    def test_keepalive_lines_ignored(self):
        events_seen = []
        stop = self._stop()

        def session_factory():
            return MagicMock(post=MagicMock(return_value=_FakeStreamResponse(["", "", ""])))

        sess = session_factory()
        # Stop the loop after the first iteration.
        with patch.object(stop, "wait", side_effect=lambda s: stop.set() or True):
            stream_games(
                ["a"],
                stop_event=stop,
                on_event=events_seen.append,
                session=sess,
            )
        self.assertEqual(events_seen, [])

    def test_dispatches_events(self):
        events_seen = []
        stop = self._stop()
        lines = [json.dumps({"id": "a"}), json.dumps({"id": "b"})]
        sess = MagicMock(post=MagicMock(return_value=_FakeStreamResponse(lines)))

        with patch.object(stop, "wait", side_effect=lambda s: stop.set() or True):
            stream_games(
                ["alice"],
                stop_event=stop,
                on_event=events_seen.append,
                session=sess,
            )
        self.assertEqual(events_seen, [{"id": "a"}, {"id": "b"}])

    def test_event_handler_exception_does_not_kill_stream(self):
        events_seen = []
        stop = self._stop()

        def handler(event):
            events_seen.append(event)
            if len(events_seen) == 1:
                raise RuntimeError("boom")

        lines = [json.dumps({"id": "a"}), json.dumps({"id": "b"})]
        sess = MagicMock(post=MagicMock(return_value=_FakeStreamResponse(lines)))

        with Shush(), patch.object(
            stop, "wait", side_effect=lambda s: stop.set() or True
        ):
            stream_games(
                ["alice"],
                stop_event=stop,
                on_event=handler,
                session=sess,
            )
        self.assertEqual(len(events_seen), 2)

    def test_401_stops_loop_immediately(self):
        stop = self._stop()
        sess = MagicMock(
            post=MagicMock(return_value=_FakeStreamResponse([], status_code=401))
        )
        with Shush():
            stream_games(
                ["alice"],
                stop_event=stop,
                on_event=lambda e: None,
                session=sess,
            )
        self.assertTrue(stop.is_set())
        # Only one connection attempt; we don't retry an unrecoverable 401.
        self.assertEqual(sess.post.call_count, 1)

    def test_429_triggers_long_backoff(self):
        stop = self._stop()
        sess = MagicMock(
            post=MagicMock(return_value=_FakeStreamResponse([], status_code=429))
        )
        wait_seconds = []

        def fake_wait(seconds):
            wait_seconds.append(seconds)
            stop.set()
            return True

        with Shush(), patch.object(stop, "wait", side_effect=fake_wait):
            stream_games(
                ["alice"],
                stop_event=stop,
                on_event=lambda e: None,
                session=sess,
            )
        self.assertEqual(len(wait_seconds), 1)
        self.assertGreaterEqual(wait_seconds[0], RATE_LIMIT_BACKOFF_SECONDS)

    def test_500_reconnects_with_backoff(self):
        stop = self._stop()
        # First attempt: 500 (raises), second attempt: stop fired during wait.
        responses = [
            _FakeStreamResponse([], status_code=500),
            _FakeStreamResponse([]),
        ]
        sess = MagicMock(post=MagicMock(side_effect=responses))
        wait_seconds = []

        def fake_wait(seconds):
            wait_seconds.append(seconds)
            stop.set()
            return True

        with Shush(), patch.object(stop, "wait", side_effect=fake_wait):
            stream_games(
                ["alice"],
                stop_event=stop,
                on_event=lambda e: None,
                session=sess,
            )
        # Should have waited the initial backoff before reconnecting.
        self.assertEqual(wait_seconds, [INITIAL_BACKOFF_SECONDS])

    def test_connection_error_is_logged_and_retried(self):
        stop = self._stop()
        sess = MagicMock(
            post=MagicMock(side_effect=requests.exceptions.ConnectionError("boom"))
        )

        wait_calls = {"n": 0}

        def fake_wait(seconds):
            wait_calls["n"] += 1
            if wait_calls["n"] >= 2:
                stop.set()
                return True
            return False

        with Shush(), patch.object(stop, "wait", side_effect=fake_wait):
            stream_games(
                ["alice"],
                stop_event=stop,
                on_event=lambda e: None,
                session=sess,
            )
        # We attempted at least twice before giving up.
        self.assertGreaterEqual(sess.post.call_count, 2)

    def test_backoff_doubles_then_resets(self):
        stop = self._stop()
        responses = [
            requests.exceptions.ConnectionError("boom1"),
            requests.exceptions.ConnectionError("boom2"),
            _FakeStreamResponse([]),  # success — should reset backoff to initial
        ]
        sess = MagicMock(post=MagicMock(side_effect=responses))
        wait_seconds = []

        def fake_wait(seconds):
            wait_seconds.append(seconds)
            if len(wait_seconds) >= 3:
                stop.set()
                return True
            return False

        with Shush(), patch.object(stop, "wait", side_effect=fake_wait):
            stream_games(
                ["alice"],
                stop_event=stop,
                on_event=lambda e: None,
                session=sess,
            )
        # Expected pattern: 1, 2, 1 (success resets).
        self.assertEqual(wait_seconds[0], INITIAL_BACKOFF_SECONDS)
        self.assertEqual(wait_seconds[1], INITIAL_BACKOFF_SECONDS * 2)
        self.assertEqual(wait_seconds[2], INITIAL_BACKOFF_SECONDS)

    def test_backoff_caps_at_max(self):
        stop = self._stop()
        sess = MagicMock(
            post=MagicMock(side_effect=requests.exceptions.ConnectionError("boom"))
        )
        wait_seconds = []

        def fake_wait(seconds):
            wait_seconds.append(seconds)
            if len(wait_seconds) >= 30:
                stop.set()
                return True
            return False

        with Shush(), patch.object(stop, "wait", side_effect=fake_wait):
            stream_games(
                ["alice"],
                stop_event=stop,
                on_event=lambda e: None,
                session=sess,
            )
        self.assertLessEqual(max(wait_seconds), MAX_BACKOFF_SECONDS)

    def test_stop_breaks_loop_immediately(self):
        stop = self._stop()
        stop.set()
        sess = MagicMock()
        stream_games(
            ["alice"],
            stop_event=stop,
            on_event=lambda e: None,
            session=sess,
        )
        sess.post.assert_not_called()

    def test_stop_during_stream_breaks_inner_loop(self):
        stop = self._stop()
        captured = {"n": 0}

        def handler(event):
            captured["n"] += 1
            stop.set()

        # Many events; should only process one before the stop check breaks out.
        lines = [json.dumps({"id": str(i)}) for i in range(10)]
        sess = MagicMock(post=MagicMock(return_value=_FakeStreamResponse(lines)))

        stream_games(
            ["alice"],
            stop_event=stop,
            on_event=handler,
            session=sess,
        )
        self.assertEqual(captured["n"], 1)

    @override_settings(LICHESS_API_TOKEN="my-token")
    def test_authorization_header_when_token_present(self):
        stop = self._stop()
        captured = {}

        def post(url, data=None, headers=None, stream=None, timeout=None):
            captured.update(url=url, headers=headers, data=data)
            return _FakeStreamResponse([])

        sess = MagicMock()
        sess.post.side_effect = post

        with patch.object(stop, "wait", side_effect=lambda s: stop.set() or True):
            stream_games(
                ["alice", "bob"],
                stop_event=stop,
                on_event=lambda e: None,
                session=sess,
            )
        self.assertEqual(captured["headers"].get("Authorization"), "Bearer my-token")
        self.assertEqual(captured["data"], "alice,bob")

    @override_settings(LICHESS_API_TOKEN="")
    def test_no_authorization_header_when_token_missing(self):
        stop = self._stop()
        captured = {}

        def post(url, data=None, headers=None, stream=None, timeout=None):
            captured.update(headers=headers)
            return _FakeStreamResponse([])

        sess = MagicMock()
        sess.post.side_effect = post

        with patch.object(stop, "wait", side_effect=lambda s: stop.set() or True):
            stream_games(
                ["alice"],
                stop_event=stop,
                on_event=lambda e: None,
                session=sess,
            )
        self.assertNotIn("Authorization", captured["headers"])

    def test_user_agent_header_is_set(self):
        stop = self._stop()
        captured = {}

        def post(url, data=None, headers=None, stream=None, timeout=None):
            captured.update(headers=headers)
            return _FakeStreamResponse([])

        sess = MagicMock()
        sess.post.side_effect = post

        with patch.object(stop, "wait", side_effect=lambda s: stop.set() or True):
            stream_games(
                ["alice"],
                stop_event=stop,
                on_event=lambda e: None,
                session=sess,
            )
        ua = captured["headers"].get("User-Agent", "")
        self.assertIn("heltour/", ua)
        self.assertIn("django/", ua)
        self.assertIn("python/", ua)


class TestWatcher(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()

    def test_restart_chunks_usernames(self):
        watcher = Watcher()
        usernames = [f"player{i}" for i in range(WATCHER_MAX_USERNAMES * 2 + 5)]

        with patch(
            "heltour.tournament.management.commands.watch_games.stream_games",
            lambda **kwargs: None,
        ):
            watcher._restart_streams(usernames)
        try:
            self.assertEqual(len(watcher._stream_threads), 3)
            self.assertEqual(len(watcher._stream_stops), 3)
        finally:
            watcher.stop()

    def test_restart_with_empty_list_creates_no_streams(self):
        watcher = Watcher()
        watcher._restart_streams([])
        self.assertEqual(watcher._stream_threads, [])
        self.assertEqual(watcher._stream_stops, [])

    def test_restart_replaces_previous_streams(self):
        watcher = Watcher(refresh_interval=0.01)

        with patch(
            "heltour.tournament.management.commands.watch_games.stream_games",
            lambda **kwargs: kwargs["stop_event"].wait(),
        ):
            watcher._restart_streams(["a", "b"])
            first_stops = list(watcher._stream_stops)
            watcher._restart_streams(["c", "d"])
            try:
                # Old stops were signalled.
                for ev in first_stops:
                    self.assertTrue(ev.is_set())
                self.assertEqual(len(watcher._stream_stops), 1)
            finally:
                watcher.stop()

    def test_run_refreshes_usernames_and_stops(self):
        watcher = Watcher(refresh_interval=0.01)
        get_users = MagicMock(return_value=[])

        with patch(
            "heltour.tournament.management.commands.watch_games.get_active_usernames",
            get_users,
        ), patch(
            "heltour.tournament.management.commands.watch_games.stream_games",
            lambda **kwargs: None,
        ):
            t = threading.Thread(target=watcher.run, daemon=True)
            t.start()
            time.sleep(0.05)
            watcher.stop()
            t.join(timeout=2)
        self.assertGreaterEqual(get_users.call_count, 1)
        self.assertFalse(t.is_alive())

    def test_run_handles_get_usernames_exception(self):
        watcher = Watcher(refresh_interval=0.01)
        get_users = MagicMock(side_effect=RuntimeError("db down"))

        with Shush(), patch(
            "heltour.tournament.management.commands.watch_games.get_active_usernames",
            get_users,
        ):
            t = threading.Thread(target=watcher.run, daemon=True)
            t.start()
            time.sleep(0.05)
            watcher.stop()
            t.join(timeout=2)
        # Multiple ticks should have happened — the loop kept running.
        self.assertGreater(get_users.call_count, 1)
        self.assertFalse(t.is_alive())

    def test_run_only_restarts_streams_when_usernames_change(self):
        watcher = Watcher(refresh_interval=0.01)
        get_users = MagicMock(return_value=["alice", "bob"])
        restarts = MagicMock()

        # Patch _restart_streams so we can count how often it runs.
        original_restart = watcher._restart_streams

        def counting_restart(usernames):
            restarts(usernames)
            original_restart(usernames)

        watcher._restart_streams = counting_restart  # type: ignore[assignment]

        with patch(
            "heltour.tournament.management.commands.watch_games.get_active_usernames",
            get_users,
        ), patch(
            "heltour.tournament.management.commands.watch_games.stream_games",
            lambda **kwargs: kwargs["stop_event"].wait(),
        ):
            t = threading.Thread(target=watcher.run, daemon=True)
            t.start()
            time.sleep(0.05)
            watcher.stop()
            t.join(timeout=2)
        # First tick triggered one restart; subsequent identical lists did not.
        self.assertEqual(restarts.call_count, 1)
