from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from heltour.tournament.forms import RegistrationForm
from heltour.tournament.models import (
    InviteCode,
    League,
    Player,
    Registration,
    RegistrationMode,
    Round,
    Season,
    SeasonPlayer,
    Team,
    TeamMember,
)
from heltour.tournament.tests.testutils import Shush, get_valid_registration_form_data


class LoneInviteCodeTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create(
            username="loneadmin", password="password", is_superuser=True, is_staff=True
        )

        cls.league = League.objects.create(
            name="Lone Invite League",
            tag="loneinvite",
            competitor_type="lone",
            rating_type="classical",
            registration_mode=RegistrationMode.INVITE_ONLY,
            require_name=True,
            email_required=True,
        )
        cls.season = Season.objects.create(
            league=cls.league,
            name="Lone Invite Season",
            tag="loneinviteseason",
            rounds=6,
        )

        start_date = timezone.now()
        for i in range(1, 7):
            Round.objects.create(
                season=cls.season,
                number=i,
                start_date=start_date + timedelta(weeks=i - 1),
                end_date=start_date + timedelta(weeks=i),
                publish_pairings=False,
                is_completed=False,
            )

        cls.open_league = League.objects.create(
            name="Lone Open League",
            tag="loneopen",
            competitor_type="lone",
            rating_type="classical",
            registration_mode=RegistrationMode.OPEN,
        )
        cls.open_season = Season.objects.create(
            league=cls.open_league,
            name="Lone Open Season",
            tag="loneopenseason",
            rounds=6,
        )

        for i in range(1, 7):
            Round.objects.create(
                season=cls.open_season,
                number=i,
                start_date=start_date + timedelta(weeks=i - 1),
                end_date=start_date + timedelta(weeks=i),
                publish_pairings=False,
                is_completed=False,
            )

    def _make_form_data(self, **overrides):
        data = get_valid_registration_form_data()
        # Remove team-only fields that lone leagues delete
        data.pop("friends", None)
        data.pop("avoid", None)
        data.pop("alternate_preference", None)
        data.update(overrides)
        return data

    def test_invite_code_field_present(self):
        player = Player.objects.create(lichess_username="lonefield", rating=1500)
        form = RegistrationForm(season=self.season, player=player)

        self.assertIn("invite_code", form.fields)
        self.assertTrue(form.fields["invite_code"].required)
        field_order = list(form.fields.keys())
        self.assertEqual(field_order[0], "invite_code")

    def test_team_fields_removed(self):
        player = Player.objects.create(lichess_username="loneteamfields", rating=1500)
        form = RegistrationForm(season=self.season, player=player)

        self.assertNotIn("friends", form.fields)
        self.assertNotIn("avoid", form.fields)
        self.assertNotIn("alternate_preference", form.fields)

    def test_registration_with_valid_code_auto_approves(self):
        code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="LONE-CAPTAIN-001",
            code_type="captain",
            created_by=self.admin_user,
        )
        player = Player.objects.create(lichess_username="loneapprove", rating=1600)

        form_data = self._make_form_data(
            email="loneapprove@example.com",
            invite_code=code.code,
        )
        form = RegistrationForm(data=form_data, season=self.season, player=player)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

        with Shush():
            reg = form.save()

        reg.refresh_from_db()
        self.assertEqual(reg.status, "approved")

        sp = SeasonPlayer.objects.get(season=self.season, player=player)
        self.assertTrue(sp.is_active)

        self.assertEqual(reg.invite_code_used, code)

        code.refresh_from_db()
        self.assertIsNotNone(code.used_by)
        self.assertIsNotNone(code.used_at)
        self.assertEqual(code.used_by, player)

    def test_no_team_or_team_member_created(self):
        code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="LONE-NOTEAM-001",
            code_type="captain",
            created_by=self.admin_user,
        )
        player = Player.objects.create(lichess_username="lonenoteam", rating=1650)

        form_data = self._make_form_data(
            email="lonenoteam@example.com",
            invite_code=code.code,
        )
        form = RegistrationForm(data=form_data, season=self.season, player=player)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

        with Shush():
            form.save()

        self.assertEqual(Team.objects.filter(season=self.season).count(), 0)
        self.assertEqual(
            TeamMember.objects.filter(player=player, team__season=self.season).count(), 0
        )

    def test_multiple_players_register_independently(self):
        codes = InviteCode.create_batch(
            league=self.league,
            season=self.season,
            count=3,
            created_by=self.admin_user,
            code_type="captain",
        )

        for i, code in enumerate(codes):
            player = Player.objects.create(
                lichess_username=f"lonemulti{i}", rating=1500 + i * 50
            )
            form_data = self._make_form_data(
                email=f"lonemulti{i}@example.com",
                invite_code=code.code,
            )
            form = RegistrationForm(data=form_data, season=self.season, player=player)
            self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

            with Shush():
                reg = form.save()

            reg.refresh_from_db()
            self.assertEqual(reg.status, "approved")

        self.assertEqual(
            SeasonPlayer.objects.filter(season=self.season).count(), 3
        )
        self.assertEqual(Team.objects.filter(season=self.season).count(), 0)

    def test_invalid_code_rejected(self):
        player = Player.objects.create(lichess_username="lonebadcode", rating=1500)
        form_data = self._make_form_data(
            email="lonebadcode@example.com",
            invite_code="DOES-NOT-EXIST-999",
        )
        form = RegistrationForm(data=form_data, season=self.season, player=player)

        self.assertFalse(form.is_valid())
        self.assertIn("invite_code", form.errors)
        self.assertIn("Invalid invite code", str(form.errors["invite_code"]))

    def test_used_code_rejected(self):
        used_player = Player.objects.create(lichess_username="loneused1", rating=1500)
        code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="LONE-USED-001",
            code_type="captain",
            created_by=self.admin_user,
        )
        code.mark_used(used_player)

        new_player = Player.objects.create(lichess_username="loneused2", rating=1500)
        form_data = self._make_form_data(
            email="loneused2@example.com",
            invite_code="LONE-USED-001",
        )
        form = RegistrationForm(data=form_data, season=self.season, player=new_player)

        self.assertFalse(form.is_valid())
        self.assertIn("invite_code", form.errors)
        self.assertIn("already been used", str(form.errors["invite_code"]))

    def test_code_case_insensitive(self):
        code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="LONE-CASE-TEST",
            code_type="captain",
            created_by=self.admin_user,
        )
        player = Player.objects.create(lichess_username="lonecase", rating=1500)

        form_data = self._make_form_data(
            email="lonecase@example.com",
            invite_code="lone-case-test",
        )
        form = RegistrationForm(data=form_data, season=self.season, player=player)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

        with Shush():
            reg = form.save()

        reg.refresh_from_db()
        self.assertEqual(reg.status, "approved")

    def test_open_lone_league_no_invite_field(self):
        player = Player.objects.create(lichess_username="loneopenreg", rating=1500)
        form = RegistrationForm(season=self.open_season, player=player)

        self.assertNotIn("invite_code", form.fields)

        form_data = self._make_form_data(email="loneopenreg@example.com")
        form = RegistrationForm(
            data=form_data, season=self.open_season, player=player
        )
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

        with Shush():
            reg = form.save()

        reg.refresh_from_db()
        self.assertEqual(reg.status, "pending")

    def test_registration_saves_player_data(self):
        code = InviteCode.objects.create(
            league=self.league,
            season=self.season,
            code="LONE-DATA-001",
            code_type="captain",
            created_by=self.admin_user,
        )
        player = Player.objects.create(lichess_username="lonedata", rating=1500)

        form_data = self._make_form_data(
            email="lonedata@example.com",
            first_name="Alice",
            last_name="Wonder",
            invite_code=code.code,
        )
        form = RegistrationForm(data=form_data, season=self.season, player=player)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

        with Shush():
            reg = form.save()

        reg.refresh_from_db()
        self.assertEqual(reg.first_name, "Alice")
        self.assertEqual(reg.last_name, "Wonder")
        self.assertEqual(reg.email, "lonedata@example.com")
        self.assertEqual(reg.season, self.season)
        self.assertEqual(reg.player, player)
