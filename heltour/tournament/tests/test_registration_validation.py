from django.test import TestCase

from heltour.tournament.models import (
    League,
    Player,
    Registration,
    Season,
    ValidationStatus,
)

NORMAL_PROFILE = {"perfs": {"classical": {"rating": 1500, "games": 100}}}
PROVISIONAL_PROFILE = {
    "perfs": {"classical": {"rating": 1500, "prov": True, "games": 5}}
}


def _create_season(tag_prefix="val", **overrides):
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


def _create_player(username, account_status="normal", profile=None):
    player = Player.objects.create(
        lichess_username=username,
        account_status=account_status,
        profile=profile or NORMAL_PROFILE,
    )
    return player


def _create_reg(season, player, agreed_to_rules=True, agreed_to_tos=True, fide_id=""):
    return Registration.objects.create(
        season=season,
        status="pending",
        player=player,
        email="a@test.com",
        has_played_20_games=True,
        can_commit=True,
        agreed_to_rules=agreed_to_rules,
        agreed_to_tos=agreed_to_tos,
        alternate_preference="full_time",
        fide_id=fide_id,
    )


class ValidationOkTest(TestCase):
    def test_defaults_pass(self):
        season = _create_season()
        player = _create_player("goodplayer")
        reg = _create_reg(season, player)
        reg.refresh_validation()
        self.assertTrue(reg.validation_ok)

    def test_closed_account(self):
        season = _create_season()
        player = _create_player("closedplayer", account_status="closed")
        reg = _create_reg(season, player)
        reg.refresh_validation()
        self.assertFalse(reg.validation_ok)

    def test_zero_rating(self):
        season = _create_season()
        player = _create_player("noratingplayer", profile={"perfs": {}})
        reg = _create_reg(season, player)
        reg.refresh_validation()
        self.assertFalse(reg.validation_ok)

    def test_account_check_disabled(self):
        season = _create_season(tag_prefix="noacct", validate_account_status=False)
        player = _create_player("closedok", account_status="closed")
        reg = _create_reg(season, player)
        reg.refresh_validation()
        self.assertTrue(reg.validation_ok)

    def test_rating_check_disabled(self):
        season = _create_season(tag_prefix="norat", validate_has_rating=False)
        player = _create_player("noratok", profile={"perfs": {}})
        reg = _create_reg(season, player)
        reg.refresh_validation()
        self.assertTrue(reg.validation_ok)

    def test_all_disabled(self):
        season = _create_season(
            tag_prefix="alloff",
            validate_account_status=False,
            validate_has_rating=False,
        )
        player = _create_player(
            "anyplayer", account_status="closed", profile={"perfs": {}}
        )
        reg = _create_reg(season, player)
        reg.refresh_validation()
        self.assertTrue(reg.validation_ok)


class ValidationWarningTest(TestCase):
    def test_defaults_no_issues(self):
        season = _create_season(tag_prefix="wok")
        player = _create_player("cleanplayer")
        reg = _create_reg(season, player)
        reg.refresh_validation()
        self.assertFalse(reg.validation_warning)

    def test_provisional(self):
        season = _create_season(tag_prefix="wprov")
        player = _create_player("provplayer", profile=PROVISIONAL_PROFILE)
        reg = _create_reg(season, player)
        reg.refresh_validation()
        self.assertTrue(reg.validation_warning)

    def test_no_rules_agreement(self):
        season = _create_season(tag_prefix="wrule")
        player = _create_player("norules")
        reg = _create_reg(season, player, agreed_to_rules=False)
        reg.refresh_validation()
        self.assertTrue(reg.validation_warning)

    def test_no_tos_agreement(self):
        season = _create_season(tag_prefix="wtos")
        player = _create_player("notos")
        reg = _create_reg(season, player, agreed_to_tos=False)
        reg.refresh_validation()
        self.assertTrue(reg.validation_warning)

    def test_provisional_disabled(self):
        season = _create_season(tag_prefix="wnoprov", validate_not_provisional=False)
        player = _create_player("provok", profile=PROVISIONAL_PROFILE)
        reg = _create_reg(season, player)
        reg.refresh_validation()
        self.assertFalse(reg.validation_warning)

    def test_rules_disabled(self):
        season = _create_season(tag_prefix="wnorule", validate_agreed_to_rules=False)
        player = _create_player("rulesok")
        reg = _create_reg(season, player, agreed_to_rules=False)
        reg.refresh_validation()
        self.assertFalse(reg.validation_warning)

    def test_tos_disabled(self):
        season = _create_season(tag_prefix="wnotos", validate_agreed_to_tos=False)
        player = _create_player("tosok")
        reg = _create_reg(season, player, agreed_to_tos=False)
        reg.refresh_validation()
        self.assertFalse(reg.validation_warning)

    def test_all_disabled(self):
        season = _create_season(
            tag_prefix="walloff",
            validate_not_provisional=False,
            validate_agreed_to_rules=False,
            validate_agreed_to_tos=False,
        )
        player = _create_player("wallplayer", profile=PROVISIONAL_PROFILE)
        reg = _create_reg(season, player, agreed_to_rules=False, agreed_to_tos=False)
        reg.refresh_validation()
        self.assertFalse(reg.validation_warning)


class CombinedStandardAndPredefinedTest(TestCase):
    def test_standard_and_predefined_both_active(self):
        season = _create_season(
            tag_prefix="combo",
            validate_predefined_list_contains_username=True,
            validate_predefined_list_contains_fide_id=True,
            validate_predefined_list_contains_username_fide_id_together=True,
            predefined_player_list="comboplayer,12345",
        )
        player = _create_player("comboplayer")
        reg = _create_reg(season, player, fide_id="12345")
        reg.refresh_validation()
        self.assertTrue(reg.validation_ok)
        self.assertFalse(reg.validation_warning)

    def test_predefined_pairing_fails_while_standard_passes(self):
        season = _create_season(
            tag_prefix="combofail",
            validate_predefined_list_contains_username_fide_id_together=True,
            predefined_player_list="someone_else,12345",
        )
        player = _create_player("combofailplayer")
        reg = _create_reg(season, player, fide_id="12345")
        reg.refresh_validation()
        # FIDE matches but username doesn't → validation_ok=False
        self.assertFalse(reg.validation_ok)

    def test_standard_fails_while_predefined_passes(self):
        season = _create_season(
            tag_prefix="combofail2",
            validate_predefined_list_contains_username=True,
            validate_predefined_list_contains_fide_id=True,
            validate_predefined_list_contains_username_fide_id_together=True,
            predefined_player_list="combofail2player,12345",
        )
        player = _create_player("combofail2player", account_status="closed")
        reg = _create_reg(season, player, fide_id="12345")
        reg.refresh_validation()
        # account_status check fails → validation_ok=False
        self.assertFalse(reg.validation_ok)


class ComputeValidationTest(TestCase):
    def test_ok_status(self):
        season = _create_season(tag_prefix="compok")
        player = _create_player("compokplayer")
        reg = _create_reg(season, player)
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.OK)
        self.assertEqual(issues, [])

    def test_error_no_rating(self):
        season = _create_season(tag_prefix="compnorat")
        player = _create_player("compnoratplayer", profile={"perfs": {}})
        reg = _create_reg(season, player)
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.ERROR)
        codes = [i["code"] for i in issues]
        self.assertIn("no_rating", codes)

    def test_error_account_not_normal(self):
        season = _create_season(tag_prefix="compacct")
        player = _create_player("compacctplayer", account_status="closed")
        reg = _create_reg(season, player)
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.ERROR)
        codes = [i["code"] for i in issues]
        self.assertIn("account_not_normal", codes)

    def test_warning_provisional(self):
        season = _create_season(tag_prefix="compprov")
        player = _create_player("compprovplayer", profile=PROVISIONAL_PROFILE)
        reg = _create_reg(season, player)
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.WARNING)
        codes = [i["code"] for i in issues]
        self.assertIn("provisional_rating", codes)

    def test_warning_rules_not_agreed(self):
        season = _create_season(tag_prefix="comprule")
        player = _create_player("compruleplayer")
        reg = _create_reg(season, player, agreed_to_rules=False)
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.WARNING)
        codes = [i["code"] for i in issues]
        self.assertIn("rules_not_agreed", codes)

    def test_warning_tos_not_agreed(self):
        season = _create_season(tag_prefix="comptos")
        player = _create_player("comptosplayer")
        reg = _create_reg(season, player, agreed_to_tos=False)
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.WARNING)
        codes = [i["code"] for i in issues]
        self.assertIn("tos_not_agreed", codes)

    def test_error_fide_id_wrong_player(self):
        season = _create_season(
            tag_prefix="compfide",
            validate_predefined_list_contains_username_fide_id_together=True,
            predefined_player_list="realplayer,12345",
        )
        player = _create_player("compfideplayer")
        reg = _create_reg(season, player, fide_id="12345")
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.ERROR)
        codes = [i["code"] for i in issues]
        self.assertIn("fide_id_wrong_player", codes)

    def test_warning_predefined_fide_mismatch(self):
        season = _create_season(
            tag_prefix="compfidem",
            validate_predefined_list_contains_username_fide_id_together=True,
            predefined_player_list="compfidemplayer,12345",
        )
        player = _create_player("compfidemplayer")
        reg = _create_reg(season, player, fide_id="99999")
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.WARNING)
        codes = [i["code"] for i in issues]
        self.assertIn("predefined_fide_mismatch", codes)

    def test_warning_not_in_predefined_list(self):
        season = _create_season(
            tag_prefix="compnotpl",
            validate_predefined_list_contains_username=True,
            predefined_player_list="someone,12345",
        )
        player = _create_player("compnotplplayer")
        reg = _create_reg(season, player, fide_id="99999")
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.WARNING)
        codes = [i["code"] for i in issues]
        self.assertIn("not_in_predefined_list", codes)

    def test_warning_fide_id_not_in_predefined_list(self):
        season = _create_season(
            tag_prefix="compfidenil",
            validate_predefined_list_contains_fide_id=True,
            predefined_player_list="someone,12345",
        )
        player = _create_player("compfidenilplayer")
        reg = _create_reg(season, player, fide_id="99999")
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.WARNING)
        codes = [i["code"] for i in issues]
        self.assertIn("fide_id_not_in_predefined_list", codes)

    def test_warning_fide_id_no_fide_provided(self):
        season = _create_season(
            tag_prefix="compfidenone",
            validate_predefined_list_contains_fide_id=True,
            predefined_player_list="someone,12345",
        )
        player = _create_player("compfidenoneplayer")
        reg = _create_reg(season, player, fide_id="")
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.WARNING)
        codes = [i["code"] for i in issues]
        self.assertIn("fide_id_not_in_predefined_list", codes)

    def test_warning_fide_id_duplicate(self):
        season = _create_season(
            tag_prefix="compfidedup",
            validate_predefined_list_contains_fide_id=True,
            predefined_player_list="player_a,12345",
        )
        player_a = _create_player("compfidedupplayera")
        _create_reg(season, player_a, fide_id="12345")
        player_b = _create_player("compfidedupplayerb")
        reg_b = _create_reg(season, player_b, fide_id="12345")
        status, issues = reg_b.compute_validation()
        codes = [i["code"] for i in issues]
        self.assertIn("fide_id_duplicate", codes)

    def test_multiple_issues_error_wins(self):
        season = _create_season(tag_prefix="compmulti")
        player = _create_player(
            "compmultiplayer", account_status="closed", profile=PROVISIONAL_PROFILE
        )
        reg = _create_reg(season, player, agreed_to_rules=False)
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.ERROR)
        codes = [i["code"] for i in issues]
        self.assertIn("account_not_normal", codes)
        self.assertIn("provisional_rating", codes)
        self.assertIn("rules_not_agreed", codes)
        self.assertGreaterEqual(len(issues), 3)


class IndependentPredefinedFlagsTest(TestCase):
    def test_username_only_ignores_fide_mismatch(self):
        season = _create_season(
            tag_prefix="uonly",
            validate_predefined_list_contains_username=True,
            predefined_player_list="uonlyplayer,12345",
        )
        player = _create_player("uonlyplayer")
        reg = _create_reg(season, player, fide_id="99999")
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.OK)
        codes = [i["code"] for i in issues]
        self.assertNotIn("predefined_fide_mismatch", codes)
        self.assertNotIn("fide_id_not_in_predefined_list", codes)

    def test_username_only_warns_unknown_player(self):
        season = _create_season(
            tag_prefix="uonlywarn",
            validate_predefined_list_contains_username=True,
            predefined_player_list="someone,12345",
        )
        player = _create_player("uonlywarnplayer")
        reg = _create_reg(season, player, fide_id="99999")
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.WARNING)
        codes = [i["code"] for i in issues]
        self.assertIn("not_in_predefined_list", codes)

    def test_fide_only_ignores_unknown_username(self):
        season = _create_season(
            tag_prefix="fonly",
            validate_predefined_list_contains_fide_id=True,
            predefined_player_list="someone,12345",
        )
        player = _create_player("fonlyplayer")
        reg = _create_reg(season, player, fide_id="12345")
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.OK)
        codes = [i["code"] for i in issues]
        self.assertNotIn("not_in_predefined_list", codes)

    def test_fide_only_warns_unknown_fide(self):
        season = _create_season(
            tag_prefix="fonlywarn",
            validate_predefined_list_contains_fide_id=True,
            predefined_player_list="someone,12345",
        )
        player = _create_player("fonlywarnplayer")
        reg = _create_reg(season, player, fide_id="99999")
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.WARNING)
        codes = [i["code"] for i in issues]
        self.assertIn("fide_id_not_in_predefined_list", codes)

    def test_pairing_only_errors_on_stolen_fide(self):
        season = _create_season(
            tag_prefix="pstolen",
            validate_predefined_list_contains_username_fide_id_together=True,
            predefined_player_list="realplayer,12345",
        )
        player = _create_player("pstolenplayer")
        reg = _create_reg(season, player, fide_id="12345")
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.ERROR)
        codes = [i["code"] for i in issues]
        self.assertIn("fide_id_wrong_player", codes)

    def test_pairing_only_warns_on_fide_mismatch(self):
        season = _create_season(
            tag_prefix="pmismatch",
            validate_predefined_list_contains_username_fide_id_together=True,
            predefined_player_list="pmismatchplayer,12345",
        )
        player = _create_player("pmismatchplayer")
        reg = _create_reg(season, player, fide_id="99999")
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.WARNING)
        codes = [i["code"] for i in issues]
        self.assertIn("predefined_fide_mismatch", codes)

    def test_pairing_only_ok_when_neither_in_list(self):
        season = _create_season(
            tag_prefix="pneither",
            validate_predefined_list_contains_username_fide_id_together=True,
            predefined_player_list="someone,12345",
        )
        player = _create_player("pneitherplayer")
        reg = _create_reg(season, player, fide_id="99999")
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.OK)

    def test_all_flags_off_skips_all_predefined_checks(self):
        season = _create_season(
            tag_prefix="alloff",
            validate_predefined_list_contains_username=False,
            validate_predefined_list_contains_fide_id=False,
            validate_predefined_list_contains_username_fide_id_together=False,
            predefined_player_list="someone,12345",
        )
        player = _create_player("alloffplayer")
        reg = _create_reg(season, player, fide_id="12345")
        status, issues = reg.compute_validation()
        self.assertEqual(status, ValidationStatus.OK)
        self.assertEqual(issues, [])


class RefreshValidationTest(TestCase):
    def test_persists_to_db(self):
        season = _create_season(tag_prefix="persist")
        player = _create_player("persistplayer", account_status="closed")
        reg = _create_reg(season, player)
        reg.refresh_validation()
        reloaded = Registration.objects.get(pk=reg.pk)
        self.assertEqual(reloaded.validation_status, ValidationStatus.ERROR)
        self.assertTrue(len(reloaded.validation_issues) > 0)

    def test_ok_persists(self):
        season = _create_season(tag_prefix="persistok")
        player = _create_player("persistokplayer")
        reg = _create_reg(season, player)
        reg.refresh_validation()
        reloaded = Registration.objects.get(pk=reg.pk)
        self.assertEqual(reloaded.validation_status, ValidationStatus.OK)
        self.assertEqual(reloaded.validation_issues, [])

    def test_warning_persists(self):
        season = _create_season(tag_prefix="persistwarn")
        player = _create_player("persistwarnplayer", profile=PROVISIONAL_PROFILE)
        reg = _create_reg(season, player)
        reg.refresh_validation()
        reloaded = Registration.objects.get(pk=reg.pk)
        self.assertEqual(reloaded.validation_status, ValidationStatus.WARNING)
        codes = [i["code"] for i in reloaded.validation_issues]
        self.assertIn("provisional_rating", codes)

    def test_validation_warning_false_for_error(self):
        season = _create_season(tag_prefix="errnotwarn")
        player = _create_player(
            "errntwplayer", account_status="closed", profile=PROVISIONAL_PROFILE
        )
        reg = _create_reg(season, player)
        reg.refresh_validation()
        self.assertFalse(reg.validation_ok)
        self.assertFalse(reg.validation_warning)
        self.assertEqual(reg.validation_status, ValidationStatus.ERROR)
