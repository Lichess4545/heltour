import json
from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import ANY, call, patch

from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from heltour.tournament.api import (
    _filter_pairings,
    _get_active_rounds,
    _get_next_round,
    _get_pairings,
    find_pairing,
    get_leagues,
    update_pairing,
    v2_pairings,
)
from heltour.tournament.models import (
    ApiKey,
    League,
    LonePlayerPairing,
    Player,
    PlayerPairing,
    Round,
    Season,
    TeamPairing,
    TeamPlayerPairing,
)
from heltour.tournament.tests.testutils import (
    createCommonLeagueData,
    get_player,
    get_round,
    get_season,
    get_team,
)


class ApiTokenTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rf = RequestFactory()
        cls.api_key = ApiKey.objects.create(name="test_key")

    def test_noauthorization(self):
        req = self.rf.get(
            path="/api/find_pairing/",
            data={
                "league": "loneleague",
            },
        )
        response = find_pairing(req)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.content, b"Unauthorized")

    def test_wrongkey(self):
        req = self.rf.get(
            path="/api/find_pairing/",
            data={
                "league": "loneleague",
            },
            headers={"AUTHORIZATION": "Token someincorrectkey"},
        )
        response = find_pairing(req)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.content, b"Unauthorized")


class ApiPairingsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        s = get_season("lone")
        Season.objects.filter(pk=s.pk).update(is_active=True)
        cls.r1 = get_round(league_type="lone", round_number=1)
        cls.r1_query = Round.objects.filter(pk=cls.r1.pk)
        cls.r1_query.update(publish_pairings=True)
        p1 = Player.objects.get(lichess_username="Player1")
        p2 = Player.objects.get(lichess_username="Player2")
        p3 = Player.objects.get(lichess_username="Player3")
        p4 = Player.objects.get(lichess_username="Player4")
        cls.lp1 = LonePlayerPairing.objects.create(
            round=cls.r1, white=p1, black=p2, pairing_order=1
        )
        cls.lp2 = LonePlayerPairing.objects.create(
            round=cls.r1,
            white=p3,
            black=p4,
            pairing_order=2,
            scheduled_time=timezone.now(),
        )
        cls.api_key = ApiKey.objects.create(name="test_key")
        cls.lp = LonePlayerPairing.objects.all()
        cls.lp1_list = list(cls.lp.filter(pk=cls.lp1.pk))
        cls.lp2_list = list(cls.lp.filter(pk=cls.lp2.pk))
        cls.rf = RequestFactory()

    def test_filter_pairings(self):
        f_none = _filter_pairings(pairings=self.lp)
        self.assertEqual(f_none, list(self.lp))
        f_player_player1 = _filter_pairings(pairings=self.lp, player="Player1")
        self.assertEqual(f_player_player1, self.lp1_list)
        f_white_player3 = _filter_pairings(pairings=self.lp, white="Player3")
        self.assertEqual(f_white_player3, self.lp2_list)
        f_black_player2 = _filter_pairings(pairings=self.lp, black="Player2")
        self.assertEqual(f_black_player2, self.lp1_list)
        f_scheduled_true = _filter_pairings(pairings=self.lp, scheduled=True)
        self.assertEqual(f_scheduled_true, self.lp2_list)
        f_scheduled_false = _filter_pairings(pairings=self.lp, scheduled=False)
        self.assertEqual(f_scheduled_false, self.lp1_list)

    def test_get_pairings(self):
        f_none = _get_pairings(round_=self.r1)
        self.assertEqual(f_none, list(self.lp))
        f_player_player4 = _get_pairings(round_=self.r1, player="Player4")
        self.assertEqual(f_player_player4, self.lp2_list)
        f_white_player1 = _get_pairings(round_=self.r1, white="Player1")
        self.assertEqual(f_white_player1, self.lp1_list)
        f_black_player2 = _get_pairings(round_=self.r1, black="Player2")
        self.assertEqual(f_black_player2, self.lp1_list)
        f_scheduled_true = _get_pairings(round_=self.r1, scheduled=True)
        self.assertEqual(f_scheduled_true, self.lp2_list)
        f_scheduled_false = _get_pairings(round_=self.r1, scheduled=False)
        self.assertEqual(f_scheduled_false, self.lp1_list)

    def test_get_next_round(self):
        next_r = _get_next_round(
            league_tag="loneleague", season_tag="loneseason", round_num=1
        )
        self.assertEqual(next_r, self.r1)
        next_r_round_num_none = _get_next_round(
            league_tag="loneleague", season_tag="loneseason", round_num=None
        )
        self.assertEqual(next_r_round_num_none, self.r1)
        next_r_league_none = _get_next_round(
            league_tag=None, season_tag="loneseason", round_num=1
        )
        self.assertEqual(next_r_league_none, self.r1)
        next_r_season_none = _get_next_round(
            league_tag="loneleague", season_tag=None, round_num=1
        )
        self.assertEqual(next_r_season_none, self.r1)

    def test_get_active_rounds(self):
        act_r = _get_active_rounds(league_tag=None, season_tag=None)
        self.assertEqual(act_r.first(), self.r1)
        act_r_league = _get_active_rounds(league_tag="loneleague", season_tag=None)
        self.assertEqual(act_r_league.first(), self.r1)
        act_r_season = _get_active_rounds(season_tag="loneseason", league_tag=None)
        self.assertEqual(act_r_season.first(), self.r1)

    @patch("heltour.tournament.api._get_active_rounds", autospec=True)
    @patch("heltour.tournament.api._get_pairings", autospec=True)
    def test_find_pairing(self, get_pairings, rounds):
        rounds.return_value = self.r1_query
        get_pairings.return_value = list(self.lp)
        req = self.rf.get(
            path="/api/find_pairing/",
            data={
                "league": "loneleague",
            },
            headers={"AUTHORIZATION": f"Token {self.api_key.secret_token}"},
        )
        pairings_json = find_pairing(req)
        get_pairings.assert_called_once_with(
            round_=self.r1,
            player=None,
            white=None,
            black=None,
            scheduled=None,
        )
        self.assertEqual(pairings_json.status_code, 200)
        self.assertEqual(
            json.loads(pairings_json.content),
            {
                "pairings": [
                    {
                        "league": "loneleague",
                        "season": "loneseason",
                        "white": "Player1",
                        "black": "Player2",
                        "round": 1,
                        "white_rating": 0,
                        "black_rating": 0,
                        "datetime": None,
                        "game_link": "",
                        "result": "",
                    },
                    {
                        "league": "loneleague",
                        "season": "loneseason",
                        "white": "Player3",
                        "black": "Player4",
                        "round": 1,
                        "white_rating": 0,
                        "black_rating": 0,
                        "datetime": ANY,
                        "game_link": "",
                        "result": "",
                    },
                ]
            },
        )

    @patch("heltour.tournament.api._get_active_rounds", autspec=True)
    @patch("heltour.tournament.api._get_pairings", autospec=True)
    def test_find_pairing_scheduled(self, get_pairings, rounds):
        rounds.return_value = self.r1_query
        get_pairings.return_value = self.lp2_list
        req = self.rf.get(
            path="/api/find_pairing/",
            data={
                "league": "loneleague",
                "scheduled": "true",
            },
            headers={"AUTHORIZATION": f"Token {self.api_key.secret_token}"},
        )
        pairings_json = find_pairing(req)
        get_pairings.assert_called_once_with(
            round_=self.r1, scheduled=True, white=None, black=None, player=None
        )
        self.assertEqual(pairings_json.status_code, 200)
        pairings = json.loads(pairings_json.content)
        self.assertEqual(
            pairings,
            {
                "pairings": [
                    {
                        "league": "loneleague",
                        "season": "loneseason",
                        "white": "Player3",
                        "black": "Player4",
                        "round": 1,
                        "white_rating": 0,
                        "black_rating": 0,
                        "datetime": ANY,
                        "game_link": "",
                        "result": "",
                    },
                ]
            },
        )
        self.assertTrue(pairings["pairings"][0]["datetime"] is not None)

    @patch("heltour.tournament.api._get_active_rounds", autospec=True)
    @patch("heltour.tournament.api._get_pairings", autospec=True)
    def test_find_pairing_unscheduled(self, get_pairings, rounds):
        rounds.return_value = self.r1_query
        get_pairings.return_value = self.lp1_list
        req = self.rf.get(
            path="/api/find_pairing/",
            data={
                "league": "loneleague",
                "scheduled": "false",
            },
            headers={"AUTHORIZATION": f"Token {self.api_key.secret_token}"},
        )
        pairings_json = find_pairing(req)
        get_pairings.assert_called_once_with(
            round_=self.r1, scheduled=False, white=None, black=None, player=None
        )
        self.assertEqual(pairings_json.status_code, 200)
        self.assertEqual(
            json.loads(pairings_json.content),
            {
                "pairings": [
                    {
                        "league": "loneleague",
                        "season": "loneseason",
                        "white": "Player1",
                        "black": "Player2",
                        "round": 1,
                        "white_rating": 0,
                        "black_rating": 0,
                        "datetime": None,
                        "game_link": "",
                        "result": "",
                    },
                ]
            },
        )

    @patch("heltour.tournament.api._get_active_rounds", autospec=True)
    def test_find_pairing_no_rounds(self, rounds):
        rounds.return_value = []
        req = self.rf.get(
            path="/api/find_pairing/",
            data={
                "league": "loneleague",
            },
            headers={"AUTHORIZATION": f"Token {self.api_key.secret_token}"},
        )
        pairings_json = find_pairing(req)
        rounds.assert_called_once_with(league_tag="loneleague", season_tag=None)
        self.assertEqual(pairings_json.status_code, 200)
        self.assertEqual(
            json.loads(pairings_json.content),
            {"pairings": None, "error": "no_matching_rounds"},
        )

    @patch("heltour.tournament.api._get_active_rounds", autospec=True)
    @patch("heltour.tournament.api._get_pairings", autospec=True)
    def test_find_pairing_reverse(self, get_pairings, rounds):
        rounds.return_value = self.r1_query
        get_pairings.side_effect = [[], self.lp2_list]
        req = self.rf.get(
            path="/api/find_pairing/",
            data={
                "league": "loneleague",
                "white": "Player4",
                "black": "Player3",
            },
            headers={"AUTHORIZATION": f"Token {self.api_key.secret_token}"},
        )
        pairings_json = find_pairing(req)
        get_pairings.assert_has_calls(
            [
                # first call should look for players as requested
                call(
                    round_=self.r1,
                    player=None,
                    white="Player4",
                    black="Player3",
                    scheduled=None,
                ),
                # second call should look for reversed players
                call(
                    round_=self.r1,
                    player=None,
                    white="Player3",
                    black="Player4",
                    scheduled=None,
                ),
            ],
            any_order=False,
        )
        self.assertEqual(pairings_json.status_code, 200)
        self.assertEqual(
            json.loads(pairings_json.content),
            {
                "pairings": [
                    {
                        "league": "loneleague",
                        "season": "loneseason",
                        "white": "Player3",
                        "black": "Player4",
                        "round": 1,
                        "white_rating": 0,
                        "black_rating": 0,
                        "datetime": ANY,
                        "game_link": "",
                        "result": "",
                    },
                ]
            },
        )

    @patch("heltour.tournament.api._get_active_rounds", autospec=True)
    def test_update_pairing_no_round(self, rounds):
        rounds.return_value = []
        req = self.rf.post(
            path="/api/update_pairing/",
            data={
                "league": "loneleague",
            },
            headers={"AUTHORIZATION": f"Token {self.api_key.secret_token}"},
        )
        update_json = update_pairing(req)
        rounds.assert_called_once_with(league_tag="loneleague", season_tag=None)
        self.assertEqual(update_json.status_code, 200)
        self.assertEqual(
            json.loads(update_json.content),
            {"updated": 0, "error": "no_matching_rounds"},
        )

    @patch("heltour.tournament.api._get_active_rounds", autospec=True)
    @patch("heltour.tournament.api._get_pairings", autospec=True)
    def test_update_pairing_no_pairing(self, get_pairings, rounds):
        rounds.return_value = self.r1_query
        get_pairings.return_value = []
        req = self.rf.post(
            path="/api/update_pairing/",
            data={
                "league": "loneleague",
            },
            headers={"AUTHORIZATION": f"Token {self.api_key.secret_token}"},
        )
        update_json = update_pairing(req)
        rounds.assert_called_once_with(league_tag="loneleague", season_tag=None)
        self.assertEqual(update_json.status_code, 200)
        self.assertEqual(
            json.loads(update_json.content),
            {"updated": 0, "error": "not_found"},
        )

    @patch("heltour.tournament.api._get_active_rounds", autospec=True)
    @patch("heltour.tournament.api._get_pairings", autospec=True)
    def test_update_pairing_two_pairings(self, get_pairings, rounds):
        rounds.return_value = self.r1_query
        get_pairings.return_value = list(self.lp)
        req = self.rf.post(
            path="/api/update_pairing/",
            data={
                "league": "loneleague",
            },
            headers={"AUTHORIZATION": f"Token {self.api_key.secret_token}"},
        )
        update_json = update_pairing(req)
        rounds.assert_called_once_with(league_tag="loneleague", season_tag=None)
        get_pairings.assert_called_once_with(
            round_=self.r1, player=None, white=None, black=None
        )
        self.assertEqual(update_json.status_code, 200)
        self.assertEqual(
            json.loads(update_json.content),
            {"updated": 0, "error": "ambiguous"},
        )

    @patch("heltour.tournament.api.LonePlayerPairing.save", autospec=True)
    @patch("heltour.tournament.api._get_active_rounds", autospec=True)
    @patch("heltour.tournament.api._get_pairings", autospec=True)
    def test_update_pairing(self, get_pairings, rounds, psave):
        rounds.return_value = self.r1_query
        get_pairings.return_value = self.lp1_list
        req = self.rf.post(
            path="/api/update_pairing/",
            data={
                "league": "loneleague",
                "season": "loneseason",
                "white": "Player1",
                "black": "Player2",
                "game_link": "https://lichess.org/somelink",
                "result": "1-0",
                "datetime": timezone.now(),
                "white_confirmed": True,
                "black_confirmed": False,
            },
            headers={"AUTHORIZATION": f"Token {self.api_key.secret_token}"},
        )
        update_json = update_pairing(req)
        rounds.assert_called_once_with(league_tag="loneleague", season_tag="loneseason")
        get_pairings.assert_called_once_with(
            round_=self.r1, player=None, white="Player1", black="Player2"
        )
        psave.assert_called()
        self.assertEqual(update_json.status_code, 200)
        self.assertEqual(
            json.loads(update_json.content),
            {
                "updated": 1,
                "reversed": False,
                "white": "Player1",
                "black": "Player2",
                "game_link_changed": True,
                "result_changed": True,
            },
        )

    def _post_update_pairing(self, **data):
        req = self.rf.post(
            path="/api/update_pairing/",
            data={"league": "loneleague", "season": "loneseason", **data},
            headers={"AUTHORIZATION": f"Token {self.api_key.secret_token}"},
        )
        return json.loads(update_pairing(req).content)

    def _set_lp1(self, **fields):
        LonePlayerPairing.objects.filter(pk=self.lp1.pk).update(**fields)

    def _lp1(self):
        return LonePlayerPairing.objects.get(pk=self.lp1.pk)

    def test_update_pairing_strict_does_not_match_reversed_colors(self):
        response = self._post_update_pairing(
            white="Player2",
            black="Player1",
            game_link="https://lichess.org/strictgame",
            strict="true",
        )
        self.assertEqual(response, {"updated": 0, "error": "not_found"})
        self.assertEqual(self._lp1().game_link, "")

    def test_update_pairing_strict_refuses_a_different_game_link(self):
        self._set_lp1(game_link="https://lichess.org/firstgame")
        response = self._post_update_pairing(
            white="Player1",
            black="Player2",
            game_link="https://lichess.org/secondgame",
            result="1-0",
            strict="true",
        )
        self.assertEqual(response, {"updated": 0, "error": "game_link_conflict"})
        lp1 = self._lp1()
        self.assertEqual(lp1.game_link, "https://lichess.org/firstgame")
        self.assertEqual(lp1.result, "")

    def test_update_pairing_strict_refuses_to_replace_a_result(self):
        self._set_lp1(game_link="https://lichess.org/firstgame", result="1/2-1/2")
        response = self._post_update_pairing(
            white="Player1",
            black="Player2",
            game_link="https://lichess.org/firstgame",
            result="1-0",
            strict="true",
        )
        self.assertEqual(response, {"updated": 0, "error": "result_already_set"})
        self.assertEqual(self._lp1().result, "1/2-1/2")

    def test_update_pairing_strict_accepts_the_stored_game_link(self):
        self._set_lp1(game_link="https://lichess.org/firstgame")
        response = self._post_update_pairing(
            white="Player1",
            black="Player2",
            game_link="https://lichess.org/firstgame",
            result="1-0",
            strict="true",
        )
        self.assertEqual(
            response,
            {
                "updated": 1,
                "reversed": False,
                "white": "Player1",
                "black": "Player2",
                "game_link_changed": False,
                "result_changed": True,
            },
        )
        lp1 = self._lp1()
        self.assertEqual(lp1.game_link, "https://lichess.org/firstgame")
        self.assertEqual(lp1.result, "1-0")

    def test_update_pairing_without_strict_overwrites(self):
        self._set_lp1(game_link="https://lichess.org/firstgame", result="1/2-1/2")
        response = self._post_update_pairing(
            white="Player2",
            black="Player1",
            game_link="https://lichess.org/secondgame",
            result="0-1",
        )
        self.assertEqual(
            response,
            {
                "updated": 1,
                "reversed": True,
                "white": "Player1",
                "black": "Player2",
                "game_link_changed": True,
                "result_changed": True,
            },
        )
        lp1 = self._lp1()
        self.assertEqual(lp1.game_link, "https://lichess.org/secondgame")
        self.assertEqual(lp1.result, "0-1")


class ApiGetLeaguesTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rf = RequestFactory()
        cls.api_key = ApiKey.objects.create(name="test_key")
        League.objects.create(
            name="Lichess4545 League",
            tag="team4545",
            time_control="45+45",
            rating_type="classical",
            competitor_type="team",
            display_order=1,
        )
        League.objects.create(
            name="Chess960 League",
            tag="chess960",
            time_control="20+10",
            rating_type="chess960",
            competitor_type="lone",
            display_order=2,
        )
        League.objects.create(
            name="Blank Time Control League",
            tag="blanktc",
            time_control="",
            rating_type="blitz",
            competitor_type="lone",
            display_order=3,
        )
        League.objects.create(
            name="Unparseable Time Control League",
            tag="badtc",
            time_control="forty-five+45",
            rating_type="rapid",
            competitor_type="lone",
            display_order=4,
        )
        League.objects.create(
            name="Inactive League",
            tag="inactive",
            time_control="30+30",
            rating_type="classical",
            competitor_type="lone",
            is_active=False,
        )

    def test_get_leagues_requires_api_token(self):
        response = get_leagues(self.rf.get(path="/api/get_leagues/"))
        self.assertEqual(response.status_code, 401)

    def test_get_leagues(self):
        req = self.rf.get(
            path="/api/get_leagues/",
            headers={"AUTHORIZATION": f"Token {self.api_key.secret_token}"},
        )
        response = get_leagues(req)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.content),
            {
                "leagues": [
                    {
                        "tag": "team4545",
                        "name": "Lichess4545 League",
                        "time_control": {"initial": 2700, "increment": 45},
                        "variant": "standard",
                        "rated": True,
                    },
                    {
                        "tag": "chess960",
                        "name": "Chess960 League",
                        "time_control": {"initial": 1200, "increment": 10},
                        "variant": "chess960",
                        "rated": True,
                    },
                    {
                        "tag": "blanktc",
                        "name": "Blank Time Control League",
                        "time_control": None,
                        "variant": "standard",
                        "rated": True,
                    },
                    {
                        "tag": "badtc",
                        "name": "Unparseable Time Control League",
                        "time_control": None,
                        "variant": "standard",
                        "rated": True,
                    },
                ]
            },
        )


class ApiV2PairingsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.api_key = ApiKey.objects.create(name="test_key")
        Season.objects.update(is_active=True)
        Round.objects.filter(number=1).update(publish_pairings=True)
        cls.match = TeamPairing.objects.create(
            round=get_round("team", 1),
            white_team=get_team("Team 1"),
            black_team=get_team("Team 2"),
            pairing_order=1,
        )

    def _pairings(self, **filters):
        request = RequestFactory().get(
            "/api/v2/pairings/",
            filters,
            headers={"AUTHORIZATION": f"Token {self.api_key.secret_token}"},
        )
        return json.loads(v2_pairings(request).content)["pairings"]

    def _lone_pairing(self, white="Player1", black="Player2", **fields):
        pairing = LonePlayerPairing.objects.create(
            round=get_round("lone", 1),
            white=get_player(white),
            black=get_player(black),
            pairing_order=1,
        )
        PlayerPairing.objects.filter(pk=pairing.pk).update(**fields)

    def _board(self, board_number, white="Player1", black="Player3"):
        TeamPlayerPairing.objects.create(
            team_pairing=self.match,
            board_number=board_number,
            white=white and get_player(white),
            black=black and get_player(black),
        )

    def test_when_no_api_token_is_given_the_request_is_unauthorized(self):
        response = v2_pairings(RequestFactory().get("/api/v2/pairings/"))
        self.assertEqual(response.status_code, 401)

    def test_when_a_lone_game_is_played_it_has_ratings_points_game_and_schedule(self):
        self._lone_pairing(
            white_rating=1650,
            black_rating=1720,
            result="1-0",
            game_link="https://lichess.org/game/abcd1234",
            scheduled_time=datetime(2026, 11, 2, 18, 30, tzinfo=dt_timezone.utc),
        )
        self.assertEqual(
            self._pairings(),
            [
                {
                    "league": "loneleague",
                    "season": "loneseason",
                    "round": 1,
                    "players": {
                        "white": {
                            "user": {"name": "Player1", "id": "player1"},
                            "rating": 1650,
                            "points": 1,
                        },
                        "black": {
                            "user": {"name": "Player2", "id": "player2"},
                            "rating": 1720,
                            "points": 0,
                        },
                    },
                    "game": {
                        "id": "abcd1234",
                        "url": "https://lichess.org/game/abcd1234",
                    },
                    "scheduledAt": 1793644200000,
                }
            ],
        )

    def test_when_a_board_is_paired_it_has_its_number_teams_and_team_match(self):
        TeamPairing.objects.update(white_points=1.5, black_points=0.5)
        self._board(1)
        self.assertEqual(
            self._pairings(),
            [
                {
                    "league": "teamleague",
                    "season": "teamseason",
                    "round": 1,
                    "board": 1,
                    "players": {
                        "white": {
                            "user": {"name": "Player1", "id": "player1"},
                            "rating": 0,
                            "team": 1,
                        },
                        "black": {
                            "user": {"name": "Player3", "id": "player3"},
                            "rating": 0,
                            "team": 2,
                        },
                    },
                    "teamMatch": {
                        "teams": [
                            {"number": 1, "name": "Team 1", "points": 1.5},
                            {"number": 2, "name": "Team 2", "points": 0.5},
                        ],
                        "boards": 2,
                    },
                }
            ],
        )

    def test_when_the_board_is_even_white_plays_for_the_match_black_team(self):
        self._board(2)
        [pairing] = self._pairings()
        self.assertEqual(pairing["players"]["white"]["team"], 2)
        self.assertEqual(pairing["players"]["black"]["team"], 1)

    def test_when_white_forfeits_black_wins_and_the_pairing_is_a_forfeit(self):
        self._lone_pairing(result="0F-1X")
        [pairing] = self._pairings()
        self.assertEqual(pairing["players"]["white"]["points"], 0)
        self.assertEqual(pairing["players"]["black"]["points"], 1)
        self.assertIs(pairing["forfeit"], True)

    def test_when_a_board_has_no_black_player_black_has_only_its_team(self):
        self._board(1, black=None)
        [pairing] = self._pairings()
        self.assertEqual(pairing["players"]["black"], {"team": 2})

    def test_when_filtered_by_league_other_leagues_are_left_out(self):
        self._board(1)
        self._lone_pairing()
        [pairing] = self._pairings(league="teamleague")
        self.assertEqual(pairing["league"], "teamleague")

    def test_when_filtered_by_season_other_seasons_are_left_out(self):
        self._board(1)
        self._lone_pairing()
        [pairing] = self._pairings(season="loneseason")
        self.assertEqual(pairing["season"], "loneseason")

    def test_when_pairings_are_added_the_query_count_stays_the_same(self):
        self._board(1)
        self._lone_pairing()
        with CaptureQueriesContext(connection) as queries:
            self._pairings()
        self._board(2, "Player4", "Player2")
        self._lone_pairing("Player3", "Player4")
        self._lone_pairing("Player5", "Player6")
        with self.assertNumQueries(len(queries)):
            self.assertEqual(len(self._pairings()), 5)
