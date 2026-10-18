from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from heltour.tournament.alternates_manager import (
    alternate_accepted,
    alternate_declined,
    do_alternate_search,
    mark_unresponsive_alternates,
    tick,
)
from heltour.tournament import signals
from heltour.tournament.models import (
    Alternate,
    AlternateSearch,
    AlternatesManagerSetting,
    Player,
    PlayerAvailability,
    Round,
    SeasonPlayer,
    TeamPairing,
    TeamPlayerPairing,
)
from heltour.tournament.tests.testutils import (
    Shush,
    createCommonLeagueData,
    get_league,
    get_player,
    get_round,
    get_season,
    get_team,
)


class AlternatesManagerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.l = get_league(league_type="team")
        cls.s = get_season(league_type="team")
        cls.r = get_round(league_type="team", round_number=1)
        cls.t1 = get_team("Team 1")
        cls.p1 = get_player("Player1")
        cls.setting = AlternatesManagerSetting.objects.create(league=cls.l)
        cls.palt = Player.objects.create(lichess_username="AltPlayer")
        cls.spalt = SeasonPlayer.objects.create(season=cls.s, player=cls.palt)
        cls.alt = Alternate.objects.create(season_player=cls.spalt, board_number=1)

    def test_do_empty_alternate_search(self):
        do_alternate_search(
            season=self.s, round_=self.r, board_number=1, setting=self.setting
        )
        self.assertEqual(AlternateSearch.objects.all().count(), 0)

    @patch("heltour.tournament.signals.alternate_needed.send")
    def test_alternate_search(self, altneeded):
        PlayerAvailability.objects.create(
            player=self.p1,
            round=self.r,
            is_available=False,
        )
        with Shush():
            do_alternate_search(
                season=self.s, round_=self.r, board_number=1, setting=self.setting
            )
        self.assertEqual(AlternateSearch.objects.all().count(), 1)
        alt_s = AlternateSearch.objects.all().first()
        self.assertEqual(alt_s.board_number, 1)
        self.assertEqual(alt_s.team, self.t1)
        self.assertTrue(altneeded.called)
        self.assertEqual(altneeded.call_args.kwargs["alternate"], self.alt)
        self.assertEqual(
            altneeded.call_args.kwargs["accept_url"],
            "/teamleague/season/teamseason/round/1/alternate/accept/",
        )
        self.assertEqual(
            altneeded.call_args.kwargs["decline_url"],
            "/teamleague/season/teamseason/round/1/alternate/decline/",
        )


class UnresponsiveDeadlineTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.l = get_league(league_type="team")
        cls.s = get_season(league_type="team")
        cls.r = get_round(league_type="team", round_number=1)
        cls.t1 = get_team("Team 1")
        cls.t2 = get_team("Team 2")
        cls.p1 = get_player("Player1")
        cls.setting = AlternatesManagerSetting.objects.create(league=cls.l)
        cls.palt = Player.objects.create(lichess_username="AltPlayer")
        cls.spalt = SeasonPlayer.objects.create(season=cls.s, player=cls.palt)
        cls.alt = Alternate.objects.create(season_player=cls.spalt, board_number=1)

    def contact(self, alt, age):
        alt.status = "contacted"
        alt.last_contact_date = timezone.now() - age
        alt.save()

    def just_over_deadline(self):
        return self.setting.unresponsive_interval + timedelta(minutes=1)

    def just_under_deadline(self):
        return self.setting.unresponsive_interval - timedelta(minutes=1)

    @patch("heltour.tournament.signals.alternate_unresponsive.send")
    def test_overdue_alternate_is_marked_and_demoted(self, altunresp):
        self.contact(self.alt, self.just_over_deadline())
        with Shush():
            mark_unresponsive_alternates(
                season=self.s, round_=self.r, setting=self.setting
            )
        self.alt.refresh_from_db()
        self.assertEqual(self.alt.status, "unresponsive")
        self.assertIsNotNone(self.alt.priority_date_override)
        self.assertTrue(altunresp.called)
        self.assertEqual(altunresp.call_args.kwargs["alternate"], self.alt)

    @patch("heltour.tournament.signals.alternate_unresponsive.send")
    def test_alternate_within_deadline_is_not_marked(self, altunresp):
        self.contact(self.alt, self.just_under_deadline())
        with Shush():
            mark_unresponsive_alternates(
                season=self.s, round_=self.r, setting=self.setting
            )
        self.alt.refresh_from_db()
        self.assertEqual(self.alt.status, "contacted")
        self.assertIsNone(self.alt.priority_date_override)
        self.assertFalse(altunresp.called)

    def test_demoted_alternate_sorts_to_the_bottom(self):
        palt2 = Player.objects.create(lichess_username="AltPlayer2")
        spalt2 = SeasonPlayer.objects.create(season=self.s, player=palt2)
        alt2 = Alternate.objects.create(season_player=spalt2, board_number=1)
        self.assertEqual(sorted([alt2, self.alt])[0], self.alt)
        self.contact(self.alt, self.just_over_deadline())
        with Shush():
            mark_unresponsive_alternates(
                season=self.s, round_=self.r, setting=self.setting
            )
        self.alt.refresh_from_db()
        self.assertEqual(sorted([alt2, self.alt])[0], alt2)

    def test_unresponsive_alternate_can_still_decline(self):
        self.contact(self.alt, self.just_over_deadline())
        with Shush():
            mark_unresponsive_alternates(
                season=self.s, round_=self.r, setting=self.setting
            )
            self.alt.refresh_from_db()
            alternate_declined(self.alt)
        self.alt.refresh_from_db()
        self.assertEqual(self.alt.status, "declined")

    def test_unresponsive_alternate_can_still_accept(self):
        # A published round with an open board-1 spot on team 1
        self.setting.contact_before_round_start = False
        self.setting.save()
        self.r.publish_pairings = True
        with Shush():
            self.r.save()
        p3 = get_player("Player3")
        tp = TeamPairing.objects.create(white_team=self.t1, black_team=self.t2,
                                        round=self.r, pairing_order=1)
        pp = TeamPlayerPairing.objects.create(team_pairing=tp, board_number=1,
                                              white=self.p1, black=p3)
        PlayerAvailability.objects.create(player=self.p1, round=self.r,
                                          is_available=False)
        AlternateSearch.objects.create(round=self.r, team=self.t1, board_number=1,
                                       status="started")
        self.contact(self.alt, self.just_over_deadline())
        with Shush():
            mark_unresponsive_alternates(
                season=self.s, round_=self.r, setting=self.setting
            )
            self.alt.refresh_from_db()
            self.assertEqual(self.alt.status, "unresponsive")
            result = alternate_accepted(self.alt)
        self.assertTrue(result)
        self.alt.refresh_from_db()
        self.assertEqual(self.alt.status, "accepted")
        pp.refresh_from_db()
        self.assertEqual(pp.white, self.palt)


    @patch("heltour.tournament.signals.alternate_unresponsive.send")
    def test_tick_marks_overdue_alternates(self, altunresp):
        self.setting.contact_before_round_start = False
        self.setting.save()
        self.r.publish_pairings = True
        with Shush():
            self.r.save()
        # An existing search means tick() skips the round-start reset
        AlternateSearch.objects.create(round=self.r, team=self.t1, board_number=1,
                                      status="all_contacted")
        self.contact(self.alt, self.just_over_deadline())
        with Shush():
            tick(self.s)
        self.alt.refresh_from_db()
        self.assertEqual(self.alt.status, "unresponsive")
        self.assertTrue(altunresp.called)

    @patch("heltour.tournament.signals.alternate_unresponsive.send")
    def test_marking_and_notification_happen_only_once(self, altunresp):
        self.contact(self.alt, self.just_over_deadline())
        with Shush():
            mark_unresponsive_alternates(
                season=self.s, round_=self.r, setting=self.setting
            )
            mark_unresponsive_alternates(
                season=self.s, round_=self.r, setting=self.setting
            )
        self.assertEqual(altunresp.call_count, 1)

    @patch("heltour.tournament.slackapi.send_message")
    def test_unresponsive_notification_text(self, send_message):
        self.l.enable_notifications = True
        with Shush():
            self.l.save()
        signals.alternate_unresponsive.send(sender=None, round_=self.r,
                                            alternate=self.alt,
                                            response_time=timedelta(hours=24))
        self.assertTrue(send_message.called)
        target, text = send_message.call_args.args
        self.assertEqual(target.lower(), "@altplayer")
        self.assertIn("moved to the bottom", text)
        self.assertIn("24 hours", text)
        self.assertIn("still accept", text)


class UnresponsiveAlternateViewsTestCase(TestCase):
    """End-to-end: the accept/decline links keep working for unresponsive alts."""

    accept_url = "/teamleague/season/teamseason/round/1/alternate/accept/"
    decline_url = "/teamleague/season/teamseason/round/1/alternate/decline/"

    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.l = get_league(league_type="team")
        cls.s = get_season(league_type="team")
        cls.r = get_round(league_type="team", round_number=1)
        cls.t1 = get_team("Team 1")
        cls.t2 = get_team("Team 2")
        cls.p1 = get_player("Player1")
        cls.setting = AlternatesManagerSetting.objects.create(
            league=cls.l, contact_before_round_start=False)
        cls.palt = Player.objects.create(lichess_username="AltPlayer")
        cls.user = User.objects.create_user("AltPlayer", password="test")
        cls.spalt = SeasonPlayer.objects.create(season=cls.s, player=cls.palt)
        cls.alt = Alternate.objects.create(season_player=cls.spalt, board_number=1)

    def make_unresponsive_with_open_spot(self):
        Round.objects.filter(pk=self.r.pk).update(
            start_date=timezone.now() - timedelta(days=1),
            end_date=timezone.now() + timedelta(days=6))
        self.r.refresh_from_db()
        self.r.publish_pairings = True
        with Shush():
            self.r.save()
        tp = TeamPairing.objects.create(white_team=self.t1, black_team=self.t2,
                                        round=self.r, pairing_order=1)
        self.pp = TeamPlayerPairing.objects.create(team_pairing=tp, board_number=1,
                                                   white=self.p1,
                                                   black=get_player("Player3"))
        PlayerAvailability.objects.create(player=self.p1, round=self.r,
                                          is_available=False)
        AlternateSearch.objects.create(round=self.r, team=self.t1, board_number=1,
                                       status="started")
        self.alt.status = "contacted"
        self.alt.last_contact_date = (timezone.now()
                                      - self.setting.unresponsive_interval
                                      - timedelta(minutes=1))
        self.alt.save()
        with Shush():
            mark_unresponsive_alternates(
                season=self.s, round_=self.r, setting=self.setting
            )
        self.alt.refresh_from_db()
        self.assertEqual(self.alt.status, "unresponsive")

    def test_unresponsive_alternate_can_accept_via_view(self):
        self.make_unresponsive_with_open_spot()
        self.client.login(username="AltPlayer", password="test")
        response = self.client.get(self.accept_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_button"])
        self.assertIn("still accept", response.context["msg"])
        with Shush():
            response = self.client.post(self.accept_url)
        self.assertIn("assigned to a team", response.context["msg"])
        self.alt.refresh_from_db()
        self.assertEqual(self.alt.status, "accepted")
        self.pp.refresh_from_db()
        self.assertEqual(self.pp.white, self.palt)

    def test_unresponsive_alternate_can_decline_via_view(self):
        self.make_unresponsive_with_open_spot()
        self.client.login(username="AltPlayer", password="test")
        response = self.client.get(self.decline_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_button"])
        with Shush():
            response = self.client.post(self.decline_url)
        self.assertIn("Thank you for your response", response.context["msg"])
        self.alt.refresh_from_db()
        self.assertEqual(self.alt.status, "declined")
