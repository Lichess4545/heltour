from unittest.mock import ANY, patch

from django.test import TestCase
from django.utils import timezone

from heltour.tournament.automod import automod_noshow, automod_unresponsive
from heltour.tournament.models import (
    LonePlayerPairing,
    PlayerPresence,
    PlayerPairing,
    PlayerAvailability,
    TeamPairing,
    TeamPlayerPairing,
)
from heltour.tournament.tests.testutils import (
    createCommonLeagueData,
    get_player,
    get_round,
    get_team,
)


class NoShowTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.rd = get_round("team", round_number=1)
        cls.player1 = get_player("Player1")
        cls.player2 = get_player("Player2")
        cls.pairing = LonePlayerPairing.objects.create(
            round=cls.rd,
            white=cls.player1,
            black=cls.player2,
            game_link="",
            scheduled_time=timezone.now(),
            pairing_order=1,
            tv_state="default",
        )
        PlayerPresence.objects.create(
            player=cls.player1, pairing=cls.pairing, round=cls.rd
        )
        PlayerPresence.objects.create(
            player=cls.player2, pairing=cls.pairing, round=cls.rd
        )
        cls.gameid = "NKop9IyD"
        cls.game_link = f"https://lichess.org/{cls.gameid}"

    @patch("heltour.tournament.signals.notify_noshow.send", autospec=True)
    def test_has_moves(self, noshow_sender):
        self.pairing.tv_state = "has_moves"
        automod_noshow(self.pairing)
        # pairing has moves, so the noshow_sender should not have been called.
        noshow_sender.assert_not_called()

    @patch("heltour.tournament.signals.notify_noshow.send", autospec=True)
    def test_has_result(self, noshow_sender):
        self.pairing.result = "1-0"
        automod_noshow(self.pairing)
        # pairing has a result, so the noshow_sender should not have been called.
        noshow_sender.assert_not_called()

    @patch("heltour.tournament.signals.notify_noshow.send", autospec=True)
    def test_has_game_link(self, noshow_sender):
        self.pairing.game_link = self.game_link
        automod_noshow(self.pairing)
        # pairing has a game_link, so the noshow_sender should not have been called.
        noshow_sender.assert_not_called()

    @patch("heltour.tournament.signals.notify_noshow.send", autospec=True)
    def test_no_confirmed_black_noshows(self, noshow_sender):
        PlayerPresence.objects.filter(
            player=self.player1, pairing=self.pairing, round=self.rd
        ).update(online_for_game=False)
        PlayerPresence.objects.filter(
            player=self.player2, pairing=self.pairing, round=self.rd
        ).update(online_for_game=True)
        automod_noshow(self.pairing)
        # assert noshow by black
        noshow_sender.assert_called_once_with(
            sender=automod_unresponsive,
            player=self.pairing.black,
            opponent=self.pairing.white,
            round_=self.rd,
        )

    @patch("heltour.tournament.signals.notify_noshow.send", autospec=True)
    def test_no_confirmed_white_noshows(self, noshow_sender):
        PlayerPresence.objects.filter(
            player=self.player1, pairing=self.pairing, round=self.rd
        ).update(online_for_game=True)
        PlayerPresence.objects.filter(
            player=self.player2, pairing=self.pairing, round=self.rd
        ).update(online_for_game=False)
        automod_noshow(self.pairing)
        # assert noshow by black
        noshow_sender.assert_called_once_with(
            sender=automod_unresponsive,
            player=self.pairing.white,
            opponent=self.pairing.black,
            round_=self.rd,
        )

    @patch(
        "heltour.tournament.lichessapi.get_game_meta",
        return_value={"moves": "1.e4 e5 2.Ke2"},
        autospec=True,
    )
    @patch("heltour.tournament.signals.notify_noshow.send", autospec=True)
    def test_confirmed_has_moves(self, noshow_sender, game_meta):
        self.pairing.white_confirmed = True
        self.pairing.black_confirmed = True
        self.pairing.game_link = self.game_link
        automod_noshow(self.pairing)
        game_meta.assert_called_once_with(self.gameid, priority=ANY, timeout=ANY)
        # game_meta indicates that there are moves, there is no noshow.
        noshow_sender.assert_not_called()

    @patch(
        "heltour.tournament.lichessapi.get_game_meta",
        return_value={"moves": "1.e4"},
        autospec=True,
    )
    @patch("heltour.tournament.signals.notify_noshow.send", autospec=True)
    def test_confirmed_black_no_shows(self, noshow_sender, game_meta):
        PlayerPresence.objects.filter(
            player=self.player1, pairing=self.pairing, round=self.rd
        ).update(online_for_game=True)
        PlayerPresence.objects.filter(
            player=self.player2, pairing=self.pairing, round=self.rd
        ).update(online_for_game=False)
        self.pairing.white_confirmed = True
        self.pairing.black_confirmed = True
        self.pairing.game_link = self.game_link
        automod_noshow(self.pairing)
        game_meta.assert_called_once_with(self.gameid, priority=ANY, timeout=ANY)
        # assert noshow by black
        noshow_sender.assert_called_once_with(
            sender=automod_unresponsive,
            player=self.pairing.white,
            opponent=self.pairing.black,
            round_=self.rd,
        )

    @patch(
        "heltour.tournament.lichessapi.get_game_meta",
        return_value={"moves": "1.e4"},
        autospec=True,
    )
    @patch("heltour.tournament.signals.notify_noshow.send", autospec=True)
    def test_confirmed_white_no_shows(self, noshow_sender, game_meta):
        PlayerPresence.objects.filter(
            player=self.player1, pairing=self.pairing, round=self.rd
        ).update(online_for_game=False)
        PlayerPresence.objects.filter(
            player=self.player2, pairing=self.pairing, round=self.rd
        ).update(online_for_game=True)
        self.pairing.white_confirmed = True
        self.pairing.black_confirmed = True
        self.pairing.game_link = self.game_link
        automod_noshow(self.pairing)
        self.assertTrue(game_meta.called)
        game_meta.assert_called_once_with(self.gameid, priority=ANY, timeout=ANY)
        # assert a noshow by white
        noshow_sender.assert_called_once_with(
            sender=automod_unresponsive,
            player=self.pairing.black,
            opponent=self.pairing.white,
            round_=self.rd,
        )


class AutomodUnresponsiveTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.r1 = get_round(league_type="team", round_number=1)
        cls.t1 = get_team(team_name="Team 1")
        cls.t2 = get_team(team_name="Team 2")
        cls.p1 = get_player(player_name="Player1")
        cls.p2 = get_player(player_name="Player2")
        cls.p3 = get_player(player_name="Player3")
        cls.p4 = get_player(player_name="Player4")
        cls.tp1 = TeamPairing.objects.create(
            white_team=cls.t1, black_team=cls.t2, round=cls.r1, pairing_order=1
        )
        cls.tpp1 = TeamPlayerPairing.objects.create(
            team_pairing=cls.tp1, board_number=1, white=cls.p1, black=cls.p3
        )
        cls.tpp2 = TeamPlayerPairing.objects.create(
            team_pairing=cls.tp1, board_number=2, white=cls.p2, black=cls.p4
        )
        cls.pp1 = PlayerPairing.objects.get(pk=cls.tpp1.pk)
        cls.pp2 = PlayerPairing.objects.get(pk=cls.tpp2.pk)

    @patch("heltour.tournament.signals.notify_mods_unresponsive.send", autospec=True)
    @patch(
        "heltour.tournament.signals.notify_opponent_unresponsive.send", autospec=True
    )
    @patch("heltour.tournament.automod.player_unresponsive", autospec=True)
    def test_automod_unresponsive_white(
        self, p_unresponsive, notify_opponent, notify_mods
    ):
        PlayerPresence.objects.create(
            player=self.p3,
            pairing=self.tpp1,
            round=self.r1,
            first_msg_time=timezone.now(),
        )
        PlayerAvailability.objects.create(
            round=self.r1, player=self.p2, is_available=False
        )
        automod_unresponsive(round_=self.r1)
        p_unresponsive.assert_called_once_with(
            round_=self.r1,
            pairing=self.pp1,
            player=self.p1,
            # note: groups is changed as a side effect,
            # which we did not mock.
            groups={"warning": [], "yellow": [], "red": []},
        )
        notify_opponent.assert_called_once_with(
            sender=automod_unresponsive,
            round_=self.r1,
            player=self.p3,
            opponent=self.p1,
            pairing=self.pp1,
        )
        notify_mods.assert_called_once_with(
            sender=automod_unresponsive,
            round_=self.r1,
            warnings=[],
            yellows=[],
            reds=[],
        )

    @patch("heltour.tournament.signals.notify_mods_unresponsive.send", autospec=True)
    @patch(
        "heltour.tournament.signals.notify_opponent_unresponsive.send", autospec=True
    )
    @patch("heltour.tournament.automod.player_unresponsive", autospec=True)
    def test_automod_unresponsive_black(
        self, p_unresponsive, notify_opponent, notify_mods
    ):
        PlayerPresence.objects.create(
            player=self.p2,
            pairing=self.tpp2,
            round=self.r1,
            first_msg_time=timezone.now(),
        )
        PlayerAvailability.objects.create(
            round=self.r1, player=self.p1, is_available=False
        )
        automod_unresponsive(round_=self.r1)
        p_unresponsive.assert_called_once_with(
            round_=self.r1,
            pairing=self.pp2,
            player=self.p4,
            # note: groups is changed as a side effect,
            # which we did not mock.
            groups={"warning": [], "yellow": [], "red": []},
        )
        notify_opponent.assert_called_once_with(
            sender=automod_unresponsive,
            round_=self.r1,
            player=self.p2,
            opponent=self.p4,
            pairing=self.pp2,
        )
        notify_mods.assert_called_once_with(
            sender=automod_unresponsive,
            round_=self.r1,
            warnings=[],
            yellows=[],
            reds=[],
        )
