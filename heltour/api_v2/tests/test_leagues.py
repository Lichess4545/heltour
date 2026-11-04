from datetime import UTC, datetime

from heltour.api_v2.tests.testutils import ApiV2TestCase
from heltour.tournament.models import League, Round, Season


class LeaguesTestCase(ApiV2TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        League.objects.create(
            name="Team 4545",
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
            competitor_type="individual",
            display_order=2,
        )
        League.objects.create(
            name="Unparseable Time Control League",
            tag="badtc",
            time_control="forty-five+45",
            rating_type="rapid",
            competitor_type="lone",
            display_order=2,
        )
        League.objects.create(
            name="Inactive League",
            tag="inactive",
            time_control="30+30",
            rating_type="classical",
            competitor_type="lone",
            is_active=False,
        )

    def _tags(self, **query: str) -> list[str]:
        leagues = self.get_json("/api/v2/leagues/", **query)["leagues"]
        return [league["tag"] for league in leagues]

    def test_when_listed_leagues_follow_lichess_conventions(self) -> None:
        self.assertEqual(
            self.get_json("/api/v2/leagues/"),
            {
                "leagues": [
                    {
                        "tag": "inactive",
                        "name": "Inactive League",
                        "competitorType": "lone",
                        "timeControl": {"initial": 1800, "increment": 30},
                        "variant": "standard",
                        "rated": True,
                        "active": False,
                    },
                    {
                        "tag": "team4545",
                        "name": "Team 4545",
                        "competitorType": "team",
                        "timeControl": {"initial": 2700, "increment": 45},
                        "variant": "standard",
                        "rated": True,
                        "active": True,
                    },
                    {
                        "tag": "badtc",
                        "name": "Unparseable Time Control League",
                        "competitorType": "lone",
                        "variant": "standard",
                        "rated": True,
                        "active": True,
                    },
                    {
                        "tag": "chess960",
                        "name": "Chess960 League",
                        "competitorType": "lone",
                        "timeControl": {"initial": 1200, "increment": 10},
                        "variant": "chess960",
                        "rated": True,
                        "active": True,
                    },
                ]
            },
        )

    def test_when_active_is_true_only_active_leagues_are_listed(self) -> None:
        self.assertEqual(self._tags(active="true"), ["team4545", "badtc", "chess960"])

    def test_when_active_is_false_only_inactive_leagues_are_listed(self) -> None:
        self.assertEqual(self._tags(active="false"), ["inactive"])

    def test_when_active_is_not_a_boolean_the_request_is_bad(self) -> None:
        self.assertEqual(self.status_of("/api/v2/leagues/", active="maybe"), 400)


class LeagueTestCase(ApiV2TestCase):
    league: League
    older: Season
    newer: Season

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.league = League.objects.create(
            name="Lone League",
            tag="loneleague",
            time_control="15+10",
            rating_type="rapid",
            competitor_type="lone",
        )
        cls.older = Season.objects.create(
            league=cls.league,
            name="Season 1",
            tag="1",
            rounds=2,
            start_date=datetime(2026, 9, 7, tzinfo=UTC),
        )
        cls.newer = Season.objects.create(
            league=cls.league,
            name="Season 2",
            tag="2",
            rounds=2,
            start_date=datetime(2026, 10, 26, tzinfo=UTC),
        )
        Season.objects.filter(pk=cls.newer.pk).update(is_active=True)
        Round.objects.filter(season=cls.newer, number=1).update(publish_pairings=True)
        Round.objects.filter(season=cls.older).update(
            publish_pairings=True, is_completed=True
        )

    def _round(self, season: Season, number: int) -> Round:
        return Round.objects.get(season=season, number=number)

    def test_when_a_league_is_shown_it_has_its_rounds_newest_first(self) -> None:
        self.assertEqual(
            self.get_json("/api/v2/leagues/loneleague/"),
            {
                "tag": "loneleague",
                "name": "Lone League",
                "competitorType": "lone",
                "timeControl": {"initial": 900, "increment": 10},
                "variant": "standard",
                "rated": True,
                "active": True,
                "rounds": [
                    {
                        "id": self._round(self.newer, 2).pk,
                        "season": "2",
                        "number": 2,
                        "startsAt": 1793577600000,
                        "endsAt": 1794182400000,
                        "pairingsPublished": False,
                        "completed": False,
                        "active": False,
                    },
                    {
                        "id": self._round(self.newer, 1).pk,
                        "season": "2",
                        "number": 1,
                        "startsAt": 1792972800000,
                        "endsAt": 1793577600000,
                        "pairingsPublished": True,
                        "completed": False,
                        "active": True,
                    },
                    {
                        "id": self._round(self.older, 2).pk,
                        "season": "1",
                        "number": 2,
                        "startsAt": 1789344000000,
                        "endsAt": 1789948800000,
                        "pairingsPublished": True,
                        "completed": True,
                        "active": False,
                    },
                    {
                        "id": self._round(self.older, 1).pk,
                        "season": "1",
                        "number": 1,
                        "startsAt": 1788739200000,
                        "endsAt": 1789344000000,
                        "pairingsPublished": True,
                        "completed": True,
                        "active": False,
                    },
                ],
            },
        )

    def test_when_a_round_has_no_dates_its_times_are_left_out(self) -> None:
        Round.objects.update(start_date=None, end_date=None)
        rounds = self.get_json("/api/v2/leagues/loneleague/")["rounds"]
        self.assertTrue(all("startsAt" not in round_ for round_ in rounds))
        self.assertTrue(all("endsAt" not in round_ for round_ in rounds))

    def test_when_the_tag_is_unknown_the_league_is_not_found(self) -> None:
        self.assertEqual(self.status_of("/api/v2/leagues/unknown/"), 404)
