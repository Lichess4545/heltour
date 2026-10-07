from unittest.mock import ANY, patch

from django.test import TestCase
from django.utils import timezone

from heltour.tournament.models import League, LeagueSetting, LonePlayerPairing, PlayerBye, PlayerPairing
from heltour.tournament.notify import notify_players_game_scheduled, notify_players_round_start, send_bye_notification
from heltour.tournament.tests.testutils import (
    Shush,
    createCommonLeagueData,
    get_league,
    get_player,
    get_round,
)


class PairingNotificationsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.l = get_league("lone")
        cls.l.enable_notifications = True
        cls.l.save()
        p1 = get_player("Player1")
        p2 = get_player("Player2")
        cls.p3 = get_player("Player3")
        p4 = get_player("Player4")
        p5 = get_player("Player5")
        p6 = get_player("Player6")
        cls.r1 = get_round("lone", round_number=1)
        cls.r1.publish_pairings = True
        with Shush():
            cls.r1.save()
        cls.lp1 = LonePlayerPairing.objects.create(
            white=p1,
            black=p2,
            round=cls.r1,
            pairing_order=1,
            scheduled_time=timezone.now(),
        )
        LeagueSetting.objects.filter(league=cls.l).update(start_games=True)
        PlayerBye.objects.create(
            round=cls.r1, type="full-point-pairings-bye", player=cls.p3
        )
        PlayerBye.objects.create(round=cls.r1, type="full-point-bye", player=p4)
        PlayerBye.objects.create(round=cls.r1, type="half-point-bye", player=p5)
        PlayerBye.objects.create(round=cls.r1, type="zero-point-bye", player=p6)

    @patch("heltour.tournament.notify.send_pairing_notification")
    def test_notify_scheduled_game(self, pn):
        notify_players_game_scheduled(pairing=self.lp1, round_=self.r1)
        self.assertTrue(pn.called)
        self.assertEqual(pn.call_args.kwargs["type_"], "game_scheduled")
        self.assertEqual(pn.call_args.kwargs["pairing"], self.lp1)

    @patch("heltour.tournament.notify._message_user", autospec=True)
    @patch("heltour.tournament.notify._lichess_message", autospec=True)
    def test_bye_notification(self, lim, mu):
        type_ = "round_started"
        subj = "li-subject"
        limsg = "li-test"
        msg = "test"
        player = "player3"
        send_bye_notification(
            type_=type_,
            player=self.p3,
            round_=self.r1,
            im_msg=msg,
            li_subject=subj,
            li_msg=limsg,
        )
        lim.assert_called_once_with(league=self.l, username=player, subject=subj, text=limsg)
        mu.assert_called_once_with(league=self.l, username=player, text=msg)

    @patch("heltour.tournament.notify.send_bye_notification", autospec=True)
    @patch("heltour.tournament.notify.send_pairing_notification", autospec=True)
    def test_notify_players_round_start(self, spn, sbn):
        pp = PlayerPairing.objects.get(pk=self.lp1.pk)
        notify_players_round_start(round_=self.r1)
        spn.assert_called_once_with(type_="round_started", pairing=pp, im_msg=ANY, mp_msg=ANY, li_subject=ANY, li_msg=ANY)
        # sbn importantly not called more than once for non-pairing byes.
        sbn.assert_called_once_with(type_="round_started", player=self.p3, round_=self.r1, im_msg=ANY, li_subject=ANY, li_msg=ANY)
