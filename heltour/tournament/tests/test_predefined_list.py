from django.test import TestCase

from heltour.tournament.models import (
    League,
    Player,
    Registration,
    Season,
)


def _create_season(tag_prefix="test", **overrides):
    league = League.objects.create(
        name=f"{tag_prefix} League",
        tag=f"{tag_prefix}league",
        competitor_type="lone",
        rating_type="classical",
    )
    defaults = dict(
        league=league,
        name=f"{tag_prefix} Season",
        tag=f"{tag_prefix}season",
        rounds=3,
    )
    defaults.update(overrides)
    return Season.objects.create(**defaults)


def _create_reg(season, username, fide_id=""):
    player, _ = Player.objects.get_or_create(lichess_username=username)
    return Registration.objects.create(
        season=season,
        status="pending",
        player=player,
        email="a@test.com",
        has_played_20_games=True,
        can_commit=True,
        agreed_to_rules=True,
        agreed_to_tos=True,
        alternate_preference="full_time",
        fide_id=fide_id,
    )


class PredefinedListParsingTest(TestCase):
    def test_empty_list(self):
        season = _create_season()
        self.assertEqual(season.parse_predefined_player_list(), {})

    def test_valid_lines(self):
        season = _create_season(predefined_player_list="alice,12345\nbob,67890")
        result = season.parse_predefined_player_list()
        self.assertEqual(result, {"alice": "12345", "bob": "67890"})

    def test_whitespace_and_blank_lines_skipped(self):
        season = _create_season(
            predefined_player_list="  alice , 12345 \n\n  \nbob,67890\n"
        )
        result = season.parse_predefined_player_list()
        self.assertEqual(result, {"alice": "12345", "bob": "67890"})

    def test_case_insensitive_usernames(self):
        season = _create_season(predefined_player_list="Alice,12345\nBOB,67890")
        result = season.parse_predefined_player_list()
        self.assertEqual(result, {"alice": "12345", "bob": "67890"})

    def test_fide_to_username_reverse_map(self):
        season = _create_season(predefined_player_list="alice,12345\nbob,67890")
        result = season.predefined_fide_to_username()
        self.assertEqual(result, {"12345": "alice", "67890": "bob"})


class PredefinedListValidationTest(TestCase):
    """Tests with all three predefined list flags enabled."""

    def setUp(self):
        self.season = _create_season(
            validate_predefined_list_contains_username=True,
            validate_predefined_list_contains_fide_id=True,
            validate_predefined_list_contains_username_fide_id_together=True,
            validate_has_rating=False,
            validate_account_status=False,
            validate_not_provisional=False,
            validate_agreed_to_rules=False,
            validate_agreed_to_tos=False,
            predefined_player_list="player1,12345\nplayer2,67890",
        )

    def test_both_match(self):
        reg = _create_reg(self.season, "player1", fide_id="12345")
        reg.refresh_validation()
        self.assertTrue(reg.validation_ok)
        self.assertFalse(reg.validation_warning)
        check = reg.predefined_list_check()
        self.assertTrue(check.username_match)
        self.assertTrue(check.fide_match)

    def test_username_match_fide_mismatch(self):
        reg = _create_reg(self.season, "player1", fide_id="99999")
        reg.refresh_validation()
        self.assertTrue(reg.validation_ok)
        self.assertTrue(reg.validation_warning)
        check = reg.predefined_list_check()
        self.assertTrue(check.username_match)
        self.assertFalse(check.fide_match)
        self.assertIn("Known player", check.detail)

    def test_fide_match_username_mismatch(self):
        reg = _create_reg(self.season, "unknown_player", fide_id="12345")
        reg.refresh_validation()
        self.assertFalse(reg.validation_ok)
        self.assertFalse(reg.validation_warning)
        check = reg.predefined_list_check()
        self.assertFalse(check.username_match)
        self.assertTrue(check.fide_match)
        self.assertIn("belongs to player1", check.detail)

    def test_neither_match(self):
        reg = _create_reg(self.season, "unknown_player", fide_id="99999")
        reg.refresh_validation()
        self.assertTrue(reg.validation_ok)
        self.assertTrue(reg.validation_warning)
        check = reg.predefined_list_check()
        self.assertFalse(check.username_match)
        self.assertFalse(check.fide_match)
        self.assertIn("Not in predefined list", check.detail)

    def test_all_flags_off_skips_predefined_checks(self):
        season = _create_season(
            validate_predefined_list_contains_username=False,
            validate_predefined_list_contains_fide_id=False,
            validate_predefined_list_contains_username_fide_id_together=False,
            predefined_player_list="player1,12345",
            tag_prefix="std",
        )
        reg = _create_reg(season, "stdplayer", fide_id="99999")
        reg.refresh_validation()
        # Standard defaults: validate_has_rating=True, rating=0 → validation_ok=False
        self.assertFalse(reg.validation_ok)
