from datetime import UTC, datetime
from typing import Any

from heltour.api_v2.tests.testutils import ApiV2TestCase
from heltour.tournament.models import (
    LonePlayerPairing,
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


class RoundsTestCase(ApiV2TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        createCommonLeagueData()
        Season.objects.filter(pk=get_season("team").pk).update(is_active=True)
        Round.objects.filter(pk=get_round("team", 1).pk).update(publish_pairings=True)

    def _numbers(self, **query: str) -> list[int]:
        rounds = self.get_json("/api/v2/leagues/teamleague/rounds/", **query)
        return [round_["number"] for round_ in rounds["rounds"]]

    def test_when_rounds_are_listed_they_are_the_league_rounds(self) -> None:
        self.assertEqual(
            self.get_json("/api/v2/leagues/teamleague/rounds/"),
            {
                "rounds": [
                    {
                        "id": get_round("team", number).pk,
                        "season": "teamseason",
                        "number": number,
                        "pairingsPublished": number == 1,
                        "completed": False,
                        "active": number == 1,
                    }
                    for number in (3, 2, 1)
                ]
            },
        )

    def test_when_active_is_true_only_active_rounds_are_listed(self) -> None:
        self.assertEqual(self._numbers(active="true"), [1])

    def test_when_active_is_false_only_inactive_rounds_are_listed(self) -> None:
        self.assertEqual(self._numbers(active="false"), [3, 2])

    def test_when_the_tag_is_unknown_the_rounds_are_not_found(self) -> None:
        self.assertEqual(self.status_of("/api/v2/leagues/unknown/rounds/"), 404)


class RoundTestCase(ApiV2TestCase):
    match: TeamPairing

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        createCommonLeagueData()
        cls.match = TeamPairing.objects.create(
            round=get_round("team", 1),
            white_team=get_team("Team 1"),
            black_team=get_team("Team 2"),
            pairing_order=1,
        )

    def _round_path(self, league_type: str, tag: str | None = None) -> str:
        round_id = get_round(league_type, 1).pk
        return f"/api/v2/leagues/{tag or f'{league_type}league'}/rounds/{round_id}/"

    def _pairings(self, league_type: str) -> list[Any]:
        pairings: list[Any] = self.get_json(self._round_path(league_type))["pairings"]
        return pairings

    def _lone_pairing(
        self, white: str = "Player1", black: str = "Player2", **fields: Any
    ) -> LonePlayerPairing:
        pairing = LonePlayerPairing.objects.create(
            round=get_round("lone", 1),
            white=get_player(white),
            black=get_player(black),
            pairing_order=1,
        )
        PlayerPairing.objects.filter(pk=pairing.pk).update(**fields)
        return pairing

    def _board(
        self,
        board_number: int,
        white: str | None = "Player1",
        black: str | None = "Player3",
    ) -> TeamPlayerPairing:
        return TeamPlayerPairing.objects.create(
            team_pairing=self.match,
            board_number=board_number,
            white=get_player(white) if white else None,
            black=get_player(black) if black else None,
        )

    def test_when_a_round_is_shown_it_has_its_lone_pairings(self) -> None:
        pairing = self._lone_pairing(
            white_rating=1650,
            black_rating=1720,
            result="1-0",
            game_link="https://lichess.org/game/abcd1234",
            scheduled_time=datetime(2026, 11, 2, 18, 30, tzinfo=UTC),
        )
        self.assertEqual(
            self.get_json(self._round_path("lone")),
            {
                "id": get_round("lone", 1).pk,
                "season": "loneseason",
                "number": 1,
                "pairingsPublished": False,
                "completed": False,
                "active": False,
                "pairings": [
                    {
                        "id": pairing.pk,
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
            },
        )

    def test_when_a_board_is_paired_it_has_its_number_teams_and_team_match(
        self,
    ) -> None:
        TeamPairing.objects.update(white_points=1.5, black_points=0.5)
        board = self._board(1)
        self.assertEqual(
            self._pairings("team"),
            [
                {
                    "id": board.pk,
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

    def test_when_the_board_is_even_white_plays_for_the_match_black_team(self) -> None:
        self._board(2)
        [pairing] = self._pairings("team")
        self.assertEqual(pairing["players"]["white"]["team"], 2)
        self.assertEqual(pairing["players"]["black"]["team"], 1)

    def test_when_a_board_has_no_black_player_black_has_only_its_team(self) -> None:
        self._board(1, black=None)
        [pairing] = self._pairings("team")
        self.assertEqual(pairing["players"]["black"], {"team": 2})

    def test_when_white_forfeits_black_wins_and_the_pairing_is_a_forfeit(self) -> None:
        self._lone_pairing(result="0F-1X")
        [pairing] = self._pairings("lone")
        self.assertEqual(pairing["players"]["white"]["points"], 0)
        self.assertEqual(pairing["players"]["black"]["points"], 1)
        self.assertIs(pairing["forfeit"], True)

    def test_when_a_pairing_is_unplayed_it_has_no_points_game_or_forfeit(self) -> None:
        self._lone_pairing()
        [pairing] = self._pairings("lone")
        self.assertNotIn("points", pairing["players"]["white"])
        self.assertNotIn("points", pairing["players"]["black"])
        self.assertNotIn("game", pairing)
        self.assertNotIn("forfeit", pairing)
        self.assertNotIn("scheduledAt", pairing)

    def test_when_pairings_are_unpublished_they_are_still_listed(self) -> None:
        self._lone_pairing()
        self.assertFalse(get_round("lone", 1).publish_pairings)
        self.assertEqual(len(self._pairings("lone")), 1)

    def test_when_the_round_is_in_another_league_it_is_not_found(self) -> None:
        path = self._round_path("lone", tag="teamleague")
        self.assertEqual(self.status_of(path), 404)

    def test_when_the_round_is_unknown_it_is_not_found(self) -> None:
        path = "/api/v2/leagues/teamleague/rounds/999999/"
        self.assertEqual(self.status_of(path), 404)

    def test_when_boards_are_added_the_query_count_stays_the_same(self) -> None:
        path = self._round_path("team")
        self._board(1)
        with self.assertNumQueries(4):
            self.assertEqual(len(self.get_json(path)["pairings"]), 1)
        self._board(2, "Player4", "Player2")
        with self.assertNumQueries(4):
            self.assertEqual(len(self.get_json(path)["pairings"]), 2)

    def test_when_lone_pairings_are_added_the_query_count_stays_the_same(self) -> None:
        path = self._round_path("lone")
        self._lone_pairing()
        with self.assertNumQueries(4):
            self.assertEqual(len(self.get_json(path)["pairings"]), 1)
        self._lone_pairing("Player3", "Player4")
        self._lone_pairing("Player5", "Player6")
        with self.assertNumQueries(4):
            self.assertEqual(len(self.get_json(path)["pairings"]), 3)
