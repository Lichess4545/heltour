import json
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.utils import timezone

from heltour.tournament.api import (
    _filter_pairings,
    _get_active_rounds,
    _get_next_round,
    _get_pairings,
    find_pairing,
)
from heltour.tournament.models import (
    ApiKey,
    LonePlayerPairing,
    Player,
    Round,
    Season,
)
from heltour.tournament.tests.testutils import (
    createCommonLeagueData,
    get_round,
    get_season,
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
        Round.objects.filter(pk=cls.r1.pk).update(publish_pairings=True)
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

    @patch("heltour.tournament.api._get_active_rounds")
    @patch("heltour.tournament.api._get_pairings")
    def test_find_pairing(self, get_pairings, rounds):
        rounds.return_value = Round.objects.filter(pk=self.r1.pk)
        get_pairings.return_value = list(self.lp)
        req = self.rf.get(
            path="/api/find_pairing/",
            data={
                "league": "loneleague",
            },
            headers={"AUTHORIZATION": f"Token {self.api_key.secret_token}"},
        )
        pairings_json = find_pairing(req)
        self.assertTrue(get_pairings.called)
        self.assertEqual(get_pairings.call_args.kwargs["round_"], self.r1)
        self.assertEqual(get_pairings.call_args.kwargs["scheduled"], None)
        self.assertEqual(pairings_json.status_code, 200)
        try:
            pairings = json.loads(pairings_json.content)
            pairing1white = pairings["pairings"][0]["white"]
            pairing1black = pairings["pairings"][0]["black"]
            pairing2white = pairings["pairings"][1]["white"]
            pairing2black = pairings["pairings"][1]["black"]
            self.assertEqual(pairing1white, "Player1")
            self.assertEqual(pairing1black, "Player2")
            self.assertEqual(pairing2white, "Player3")
            self.assertEqual(pairing2black, "Player4")
        except json.JSONDecodeError as e:
            raise AssertionError(f"JSON not decoded - {e}")
        except KeyError as e:
            raise AssertionError(f"Expected key not in JSON - {e}")
        except IndexError as e:
            raise AssertionError(f"Not enough pairings found - {e}")

    @patch("heltour.tournament.api._get_active_rounds")
    @patch("heltour.tournament.api._get_pairings")
    def test_find_pairing_scheduled(self, get_pairings, rounds):
        rounds.return_value = Round.objects.filter(pk=self.r1.pk)
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
        self.assertTrue(get_pairings.called)
        self.assertEqual(get_pairings.call_args.kwargs["round_"], self.r1)
        self.assertEqual(get_pairings.call_args.kwargs["scheduled"], True)
        self.assertEqual(pairings_json.status_code, 200)
        try:
            pairings = json.loads(pairings_json.content)
            pairing1white = pairings["pairings"][0]["white"]
            pairing1black = pairings["pairings"][0]["black"]
            self.assertEqual(pairing1white, "Player3")
            self.assertEqual(pairing1black, "Player4")
        except json.JSONDecodeError as e:
            raise AssertionError(f"JSON not decoded - {e}")
        except KeyError as e:
            raise AssertionError(f"Expected key not in JSON - {e}")
        except IndexError as e:
            raise AssertionError(f"Not enough pairings found - {e}")

    @patch("heltour.tournament.api._get_active_rounds")
    @patch("heltour.tournament.api._get_pairings")
    def test_find_pairing_unscheduled(self, get_pairings, rounds):
        rounds.return_value = Round.objects.filter(pk=self.r1.pk)
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
        self.assertTrue(get_pairings.called)
        self.assertEqual(get_pairings.call_args.kwargs["round_"], self.r1)
        self.assertEqual(get_pairings.call_args.kwargs["scheduled"], False)
        self.assertEqual(pairings_json.status_code, 200)
        try:
            pairings = json.loads(pairings_json.content)
            pairing1white = pairings["pairings"][0]["white"]
            pairing1black = pairings["pairings"][0]["black"]
            self.assertEqual(pairing1white, "Player1")
            self.assertEqual(pairing1black, "Player2")
        except json.JSONDecodeError as e:
            raise AssertionError(f"JSON not decoded - {e}")
        except KeyError as e:
            raise AssertionError(f"Expected key not in JSON - {e}")
        except IndexError as e:
            raise AssertionError(f"Not enough pairings found - {e}")

    @patch("heltour.tournament.api._get_active_rounds")
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
        self.assertTrue(rounds.called)
        self.assertEqual(rounds.call_args.kwargs["league_tag"], "loneleague")
        self.assertEqual(pairings_json.status_code, 200)
        try:
            pairings = json.loads(pairings_json.content)
            self.assertEqual(
                pairings, {"pairings": None, "error": "no_matching_rounds"}
            )

        except json.JSONDecodeError as e:
            raise AssertionError(f"JSON not decoded - {e}")

    @patch("heltour.tournament.api._get_active_rounds")
    @patch("heltour.tournament.api._get_pairings")
    def test_find_pairing_reverse(self, get_pairings, rounds):
        rounds.return_value = Round.objects.filter(pk=self.r1.pk)
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
        self.assertTrue(get_pairings.called)
        # first call should look for players as requested
        self.assertEqual(get_pairings.call_args_list[0].kwargs["white"], "Player4")
        self.assertEqual(get_pairings.call_args_list[0].kwargs["black"], "Player3")
        # second call should look for reversed players
        self.assertEqual(get_pairings.call_args_list[1].kwargs["white"], "Player3")
        self.assertEqual(get_pairings.call_args_list[1].kwargs["black"], "Player4")
        self.assertEqual(pairings_json.status_code, 200)
        try:
            pairings = json.loads(pairings_json.content)
            pairing1white = pairings["pairings"][0]["white"]
            pairing1black = pairings["pairings"][0]["black"]
            self.assertEqual(pairing1white, "Player3")
            self.assertEqual(pairing1black, "Player4")
        except json.JSONDecodeError as e:
            raise AssertionError(f"JSON not decoded - {e}")
        except KeyError as e:
            raise AssertionError(f"Expected key not in JSON - {e}")
        except IndexError as e:
            raise AssertionError(f"Not enough pairings found - {e}")
