from unittest.mock import patch

from django.test import TestCase

from heltour.tournament.models import (
    League,
    Player,
    Registration,
    Season,
    SeasonPlayer,
)
from heltour.tournament.tests.testutils import Shush


def _make_fide_league(rating_type="fide_standard"):
    return League.objects.create(
        name=f"FIDE League {rating_type}",
        tag=f"fide-{rating_type}",
        competitor_type="lone",
        rating_type=rating_type,
    )


def _make_player(username, fide_id="", fide_profile=None, profile=None):
    return Player.objects.create(
        lichess_username=username,
        fide_id=fide_id,
        fide_profile=fide_profile,
        profile=profile,
    )


SAMPLE_FIDE_PROFILE = {
    "id": 2016192,
    "name": "Carlsen, Magnus",
    "federation": "NOR",
    "standard": 2830,
    "rapid": 2823,
    "blitz": 2886,
    "title": "GM",
    "year": 1990,
    "inactive": 0,
}


class PlayerFideRatingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fide_std = _make_fide_league("fide_standard")
        cls.fide_rapid = _make_fide_league("fide_rapid")
        cls.fide_blitz = _make_fide_league("fide_blitz")
        cls.classical = League.objects.create(
            name="Classical League",
            tag="classical-league",
            competitor_type="lone",
            rating_type="classical",
        )

    def test_rating_for_fide_standard(self):
        player = _make_player("fide_player1", fide_profile=SAMPLE_FIDE_PROFILE)
        self.assertEqual(player.rating_for(self.fide_std), 2830)

    def test_rating_for_fide_rapid(self):
        player = _make_player("fide_player2", fide_profile=SAMPLE_FIDE_PROFILE)
        self.assertEqual(player.rating_for(self.fide_rapid), 2823)

    def test_rating_for_fide_blitz(self):
        player = _make_player("fide_player3", fide_profile=SAMPLE_FIDE_PROFILE)
        self.assertEqual(player.rating_for(self.fide_blitz), 2886)

    def test_rating_for_fide_defaults_1400_when_no_profile(self):
        player = _make_player("fide_player4")
        self.assertEqual(player.rating_for(self.fide_std), 1400)

    def test_rating_for_fide_defaults_1400_when_key_missing(self):
        player = _make_player("fide_player5", fide_profile={"id": 1, "rapid": 2000})
        self.assertEqual(player.rating_for(self.fide_std), 1400)

    def test_rating_for_fide_does_not_affect_classical(self):
        player = _make_player(
            "fide_player6",
            fide_profile=SAMPLE_FIDE_PROFILE,
            profile={"perfs": {"classical": {"rating": 2100}}},
        )
        self.assertEqual(player.rating_for(self.classical), 2100)

    def test_rating_for_classical_returns_0_when_no_profile(self):
        player = _make_player("fide_player7")
        self.assertEqual(player.rating_for(self.classical), 0)

    def test_rating_for_none_league_returns_player_rating(self):
        player = _make_player("fide_player8")
        player.rating = 1500
        player.save()
        self.assertEqual(player.rating_for(None), 1500)


class PlayerFideFallbackRatingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fide = _make_fide_league("fide")

    def test_rating_for_fide_uses_standard_when_present(self):
        player = _make_player("fb1", fide_profile=SAMPLE_FIDE_PROFILE)
        self.assertEqual(player.rating_for(self.fide), 2830)

    def test_rating_for_fide_falls_back_to_rapid(self):
        player = _make_player(
            "fb2", fide_profile={"id": 1, "rapid": 2200, "blitz": 2100}
        )
        self.assertEqual(player.rating_for(self.fide), 2200)

    def test_rating_for_fide_falls_back_to_blitz(self):
        player = _make_player("fb3", fide_profile={"id": 1, "blitz": 2050})
        self.assertEqual(player.rating_for(self.fide), 2050)

    def test_rating_for_fide_defaults_1400_when_no_keys(self):
        player = _make_player("fb4", fide_profile={"id": 1, "name": "X"})
        self.assertEqual(player.rating_for(self.fide), 1400)

    def test_rating_for_fide_defaults_1400_when_no_profile(self):
        player = _make_player("fb5")
        self.assertEqual(player.rating_for(self.fide), 1400)

    def test_rating_for_fide_skips_null_standard(self):
        player = _make_player(
            "fb6", fide_profile={"id": 1, "standard": None, "rapid": 2100}
        )
        self.assertEqual(player.rating_for(self.fide), 2100)

    def test_games_played_fide_always_zero(self):
        player = _make_player("fb7", fide_profile=SAMPLE_FIDE_PROFILE)
        self.assertEqual(player.games_played_for(self.fide), 0)

    def test_provisional_fide_always_false(self):
        player = _make_player("fb8")
        self.assertFalse(player.provisional_for(self.fide))


class PlayerFideGamesPlayedTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fide_std = _make_fide_league("fide_standard")
        cls.classical = League.objects.create(
            name="Classical League GP",
            tag="classical-gp",
            competitor_type="lone",
            rating_type="classical",
        )

    def test_games_played_fide_always_zero(self):
        player = _make_player("gp_fide1", fide_profile=SAMPLE_FIDE_PROFILE)
        self.assertEqual(player.games_played_for(self.fide_std), 0)

    def test_games_played_fide_zero_even_without_profile(self):
        player = _make_player("gp_fide2")
        self.assertEqual(player.games_played_for(self.fide_std), 0)

    def test_games_played_classical_reads_from_profile(self):
        player = _make_player(
            "gp_classical",
            profile={"perfs": {"classical": {"rating": 1800, "games": 42}}},
        )
        self.assertEqual(player.games_played_for(self.classical), 42)


class PlayerFideProvisionalTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fide_std = _make_fide_league("fide_standard")
        cls.classical = League.objects.create(
            name="Classical League Prov",
            tag="classical-prov",
            competitor_type="lone",
            rating_type="classical",
        )

    def test_provisional_fide_always_false(self):
        player = _make_player("prov_fide1", fide_profile=SAMPLE_FIDE_PROFILE)
        self.assertFalse(player.provisional_for(self.fide_std))

    def test_provisional_fide_false_even_without_profile(self):
        player = _make_player("prov_fide2")
        self.assertFalse(player.provisional_for(self.fide_std))

    def test_provisional_classical_true_when_no_profile(self):
        player = _make_player("prov_classical1")
        self.assertTrue(player.provisional_for(self.classical))

    def test_provisional_classical_true_when_prov_set(self):
        player = _make_player(
            "prov_classical2",
            profile={"perfs": {"classical": {"rating": 1500, "prov": True}}},
        )
        self.assertTrue(player.provisional_for(self.classical))


class PlayerUpdateFideProfileTestCase(TestCase):
    def test_update_fide_profile_stores_data(self):
        player = _make_player("update_fide1")
        self.assertIsNone(player.fide_profile)

        player.update_fide_profile(SAMPLE_FIDE_PROFILE)
        player.refresh_from_db()

        self.assertEqual(player.fide_profile["standard"], 2830)
        self.assertEqual(player.fide_profile["rapid"], 2823)
        self.assertEqual(player.fide_profile["blitz"], 2886)

    def test_update_fide_profile_overwrites_old_data(self):
        player = _make_player("update_fide2", fide_profile={"standard": 1400})
        player.update_fide_profile(SAMPLE_FIDE_PROFILE)
        player.refresh_from_db()
        self.assertEqual(player.fide_profile["standard"], 2830)


class RegistrationFideRatingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fide_league = _make_fide_league("fide_standard")
        cls.season = Season.objects.create(
            league=cls.fide_league,
            name="FIDE Season",
            tag="fide-season",
            rounds=3,
        )

    def test_registration_rating_uses_fide(self):
        player = _make_player("reg_fide1", fide_profile=SAMPLE_FIDE_PROFILE)
        reg = Registration.objects.create(
            season=self.season,
            status="pending",
            player=player,
            email="a@test.com",
            has_played_20_games=True,
            can_commit=True,
            agreed_to_rules=True,
            agreed_to_tos=True,
            alternate_preference="full_time",
        )
        self.assertEqual(reg.rating, 2830)

    def test_registration_rating_defaults_1400(self):
        player = _make_player("reg_fide2")
        reg = Registration.objects.create(
            season=self.season,
            status="pending",
            player=player,
            email="a@test.com",
            has_played_20_games=True,
            can_commit=True,
            agreed_to_rules=True,
            agreed_to_tos=True,
            alternate_preference="full_time",
        )
        self.assertEqual(reg.rating, 1400)


class FideTasksTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fide_league = _make_fide_league("fide_standard")
        cls.season = Season.objects.create(
            league=cls.fide_league,
            name="Active FIDE Season",
            tag="active-fide",
            rounds=5,
            is_completed=False,
        )
        cls.player_with_fide = _make_player("task_fide1", fide_id="2016192")
        SeasonPlayer.objects.create(season=cls.season, player=cls.player_with_fide)
        cls.player_no_fide = _make_player("task_nofide")
        SeasonPlayer.objects.create(season=cls.season, player=cls.player_no_fide)

    @patch("heltour.tournament.lichessapi.get_fide_player")
    def test_update_fide_ratings_fetches_for_players_with_fide_id(self, mock_get):
        from heltour.tournament.tasks import update_fide_ratings

        mock_get.return_value = SAMPLE_FIDE_PROFILE
        with Shush():
            update_fide_ratings()

        mock_get.assert_called_once_with("2016192", priority=1)
        self.player_with_fide.refresh_from_db()
        self.assertEqual(self.player_with_fide.fide_profile["standard"], 2830)

    @patch("heltour.tournament.lichessapi.get_fide_player")
    def test_update_fide_ratings_skips_players_without_fide_id(self, mock_get):
        from heltour.tournament.tasks import update_fide_ratings

        mock_get.return_value = SAMPLE_FIDE_PROFILE
        with Shush():
            update_fide_ratings()

        called_ids = [c.args[0] for c in mock_get.call_args_list]
        self.assertNotIn("", called_ids)

    @patch("heltour.tournament.lichessapi.get_fide_player")
    def test_update_fide_ratings_handles_api_error(self, mock_get):
        from heltour.tournament.lichessapi import ApiWorkerError
        from heltour.tournament.tasks import update_fide_ratings

        mock_get.side_effect = ApiWorkerError("timeout")
        with Shush():
            update_fide_ratings()

        self.player_with_fide.refresh_from_db()
        self.assertIsNone(self.player_with_fide.fide_profile)

    @patch("heltour.tournament.lichessapi.get_fide_player")
    def test_force_update_all_ignores_staleness(self, mock_get):
        from heltour.tournament.tasks import force_update_all_fide_ratings

        self.player_with_fide.fide_profile = SAMPLE_FIDE_PROFILE
        self.player_with_fide.save()

        updated_profile = {**SAMPLE_FIDE_PROFILE, "standard": 2835}
        mock_get.return_value = updated_profile
        with Shush():
            force_update_all_fide_ratings()

        mock_get.assert_called_once_with("2016192", priority=1)
        self.player_with_fide.refresh_from_db()
        self.assertEqual(self.player_with_fide.fide_profile["standard"], 2835)


class FideLichessApiTestCase(TestCase):
    @patch("heltour.tournament.lichessapi._apicall_with_error_parsing")
    def test_get_fide_player_calls_correct_url(self, mock_apicall):
        import json
        from django.conf import settings
        from heltour.tournament.lichessapi import get_fide_player

        mock_apicall.return_value = json.dumps(SAMPLE_FIDE_PROFILE)
        result = get_fide_player("2016192", priority=2, max_retries=3)

        expected_url = (
            f"{settings.API_WORKER_HOST}/lichessapi/api/fide/player/2016192"
            f"?priority=2&max_retries=3"
        )
        mock_apicall.assert_called_once_with(expected_url, 1800)
        self.assertEqual(result["standard"], 2830)
