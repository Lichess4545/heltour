from datetime import timedelta
from unittest.mock import ANY, call, patch

from django.test import TestCase
from django.utils import timezone

from heltour.tournament.lichessapi import ApiClientError
from heltour.tournament.models import (
    Alternate,
    Broadcast,
    BroadcastRound,
    League,
    LeagueChannel,
    LonePlayerPairing,
    LonePlayerScore,
    OauthToken,
    Player,
    PlayerBye,
    PlayerPairing,
    Round,
    Season,
    SeasonPlayer,
    Team,
    TeamMember,
    TeamPairing,
    TeamPlayerPairing,
    TeamScore,
)
from heltour.tournament.slackapi import NameTaken, SlackError, SlackGroup
from django.core.cache import cache

from heltour.tournament.tasks import (
    _create_broadcast_grouping,
    _create_or_update_broadcast,
    _create_or_update_broadcast_round,
    _create_team_string,
    _find_closest_rating,
    _start_league_games,
    _start_unscheduled_games,
    active_player_usernames,
    create_broadcast,
    create_broadcast_round,
    create_team_channel,
    fetch_players_to_update,
    populate_historical_ratings,
    start_games,
    update_broadcast,
    update_broadcast_round,
    update_player_ratings,
    update_tv_state,
    validate_season_tokens,
)
from heltour.tournament.tests.testutils import (
    Shush,
    create_reg,
    createCommonLeagueData,
    get_league,
    get_player,
    get_round,
    get_season,
    set_rating,
)


class TestHelpers(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.playernames = ["Player" + str(i) for i in range(1, 9)]
        cls.s = get_season("team")
        cls.s.registration_open = True
        cls.s.save()
        cls.now = timezone.now()

    def test_username_helpers(self, *args):
        self.assertEqual(
            active_player_usernames(), self.playernames
        )  # names are Player1, ..., Player8

    def test_username_duplicates(self):
        SeasonPlayer.objects.create(
            season=get_season("team"), player=get_player("Player1")
        )
        self.assertEqual(SeasonPlayer.objects.all().count(), 9)
        self.assertEqual(
            active_player_usernames(), self.playernames
        )  # no duplicate names

    @patch("django.utils.timezone.now")
    def test_fetch_players(self, now):
        now.return_value = self.now
        create_reg(season=self.s, name="lakinwecker")
        # reg is not included as it was updated recently.
        self.assertEqual(fetch_players_to_update(), self.playernames)
        playerlist = []
        # create a number of older regs
        now.return_value = self.now - timedelta(hours=48)
        for counter in range(1, 30):
            create_reg(season=self.s, name=f"RegPlayer{counter}")
            playerlist.append(f"RegPlayer{counter}")
            now.return_value += timedelta(seconds=1)
        # set time back to now
        now.return_value = self.now
        self.assertEqual(fetch_players_to_update(), self.playernames + playerlist[0:3])
        # push some player to the front by changing the modified date
        now.return_value = self.now - timedelta(hours=72)
        ch_playername = "RegPlayer12"
        Player.objects.get(lichess_username=ch_playername).save()
        now.return_value = self.now
        self.assertEqual(
            fetch_players_to_update(),
            self.playernames + [ch_playername] + playerlist[0:2],
        )


class TestUpdateRatings(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.l960 = League.objects.create(
            name="c960 League",
            tag="960league",
            competitor_type="lone",
            rating_type="chess960",
        )

    @patch(
        "heltour.tournament.lichessapi.enumerate_user_metas",
        return_value=[
            {"id": "Player1", "perfs": {"classical": {"games": 25, "rating": 2200}}},
            {
                "id": "Player2",
                "perfs": {
                    "chess960": {"games": 12, "rating": 1000},
                    "classical": {"games": 10, "rating": 1800},
                },
            },
        ],
    )
    def test_update_ratings(self, *args):
        # updating player ratings writes to the log, disable that temporarily for nicer test output
        with Shush():
            update_player_ratings()
        tl = get_league("team")
        p2 = get_player("Player2")
        self.assertEqual(get_player("Player1").rating_for(league=tl), 2200)
        self.assertEqual(p2.rating_for(league=tl), 1800)
        self.assertEqual(p2.rating_for(league=self.l960), 1000)
        self.assertEqual(get_player("Player3").rating_for(league=tl), 0)


class TestUpdateTVState(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        r = get_round(league_type="lone", round_number=1)
        p1 = get_player("Player1")
        p2 = get_player("Player2")
        lpp = LonePlayerPairing.objects.create(
            round=r,
            white=p1,
            black=p2,
            game_link="fakelink",
            pairing_order=1,
        )
        cls.lpppk = lpp.pk

    @patch(
        "heltour.tournament.lichessapi.get_game_meta",
        return_value={
            "status": "stalemate",
            "moves": "d4 Nf6",
        },
        autospec=True,
    )
    @patch(
        "heltour.tournament.tasks.get_gameid_from_gamelink",
        return_value="fakeid",
        autospec=True,
    )
    @patch("heltour.tournament.lichessapi.add_watch")
    def test_stalemate(self, addwatch, gamelink, gamemeta):
        update_tv_state()
        gamemeta.assert_called_once_with("fakeid", priority=1, timeout=300)
        self.assertEqual("1/2-1/2", LonePlayerPairing.objects.get(pk=self.lpppk).result)
        addwatch.assert_not_called()

    @patch(
        "heltour.tournament.lichessapi.get_game_meta",
        return_value={
            "status": "insufficientMaterialClaim",
            "moves": "e4 c5 Nf3",
        },
        autospec=True,
    )
    @patch(
        "heltour.tournament.tasks.get_gameid_from_gamelink",
        return_value="fakeid",
        autospec=True,
    )
    @patch("heltour.tournament.lichessapi.add_watch")
    def test_insufficientmaterialclaim(self, addwatch, gamelink, gamemeta):
        update_tv_state()
        gamemeta.assert_called_once_with("fakeid", priority=1, timeout=300)
        self.assertEqual("1/2-1/2", LonePlayerPairing.objects.get(pk=self.lpppk).result)
        addwatch.assert_not_called()


@patch("heltour.tournament.lichessapi.add_watch", return_value=None)
class TestAutostartGames(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        team1 = Team.objects.get(number=1)
        team2 = Team.objects.get(number=2)
        Round.objects.filter(season__league__name="Team League", number=1).update(
            publish_pairings=True, start_date=timezone.now()
        )
        rd = get_round(league_type="team", round_number=1)
        rd.season.league.get_leaguesetting().start_games = True
        rd.season.league.get_leaguesetting().save()
        tp = TeamPairing.objects.create(
            white_team=team1, black_team=team2, round=rd, pairing_order=0
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp,
            board_number=1,
            white=team1.teammember_set.get(board_number=1).player,
            black=team2.teammember_set.get(board_number=1).player,
            white_confirmed=True,
            black_confirmed=False,
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp,
            board_number=2,
            white=team2.teammember_set.get(board_number=2).player,
            black=team1.teammember_set.get(board_number=2).player,
            white_confirmed=True,
            black_confirmed=True,
        )
        TeamPlayerPairing.objects.filter(team_pairing=tp).update(
            scheduled_time=timezone.now() + timedelta(minutes=5)
        )
        o1 = OauthToken.objects.create(
            access_token="blah1", expires=timezone.now() + timedelta(minutes=10)
        )
        o2 = OauthToken.objects.create(
            access_token="blah2", expires=timezone.now() + timedelta(minutes=10)
        )
        o3 = OauthToken.objects.create(
            access_token="blah3", expires=timezone.now() + timedelta(minutes=10)
        )
        o4 = OauthToken.objects.create(
            access_token="blah4", expires=timezone.now() + timedelta(minutes=10)
        )
        Player.objects.filter(
            lichess_username=team1.teammember_set.get(
                board_number=1
            ).player.lichess_username
        ).update(oauth_token=o1)
        Player.objects.filter(
            lichess_username=team1.teammember_set.get(
                board_number=2
            ).player.lichess_username
        ).update(oauth_token=o2)
        Player.objects.filter(
            lichess_username=team2.teammember_set.get(
                board_number=1
            ).player.lichess_username
        ).update(oauth_token=o3)
        Player.objects.filter(
            lichess_username=team2.teammember_set.get(
                board_number=2
            ).player.lichess_username
        ).update(oauth_token=o4)

    @patch(
        "heltour.tournament.lichessapi.bulk_start_games",
        return_value={
            "id": "RVAcwgg7",
            "games": [{"id": "NKop9IyD", "black": "player2", "white": "player4"}],
        },
    )
    def test_start_game(self, *args):
        # start_games writes to the log, disable that temporarily for nicer test output
        with Shush():
            start_games()
        tpp2 = TeamPlayerPairing.objects.get(board_number=2)
        tpp1 = TeamPlayerPairing.objects.get(board_number=1)
        self.assertEqual(tpp2.game_link, "https://lichess.org/NKop9IyD")
        self.assertEqual(tpp1.game_link, "")

    @patch(
        "heltour.tournament.lichessapi.bulk_start_games",
        return_value={
            "id": "RVAcwgg7",
            "games": [
                {"id": "NKop9IyD", "black": "player2", "white": "player4"},
                {"id": "KT837Aut", "black": "player3", "white": "player1"},
            ],
        },
    )
    def test_start_games(self, *args):
        TeamPlayerPairing.objects.filter(board_number=1).update(black_confirmed=True)
        # start_games writes to the log, disable that temporarily for nicer test output
        with Shush():
            start_games()
        tpp2 = TeamPlayerPairing.objects.get(board_number=2)
        tpp1 = TeamPlayerPairing.objects.get(board_number=1)
        self.assertEqual(tpp2.game_link, "https://lichess.org/NKop9IyD")
        self.assertEqual(tpp1.game_link, "https://lichess.org/KT837Aut")

    @patch(
        "heltour.tournament.lichessapi.bulk_start_games",
        side_effect=ApiClientError('{"tokens": ["blah2"]}'),
    )
    def test_start_invalid_token_no_retry(self, mock_bulk, *args):
        TeamPlayerPairing.objects.filter(board_number=1).update(black_confirmed=True)
        with Shush():
            start_games()
        tpp2 = TeamPlayerPairing.objects.get(board_number=2)
        tpp1 = TeamPlayerPairing.objects.get(board_number=1)
        # No retry — neither game link should be set
        self.assertEqual(tpp2.game_link, "")
        self.assertEqual(tpp1.game_link, "")
        # bulk_start_games called exactly once (no retry)
        mock_bulk.assert_called_once()
        # Bad token still expired so it won't be reused
        tpp2.black.refresh_from_db()
        self.assertTrue(
            tpp2.black.oauth_token.expires < timezone.now() - timedelta(minutes=30)
        )


class TestTeamChannel(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.team_ids = Team.objects.all().order_by("pk").values("pk")

    @patch(
        "heltour.tournament.slackapi.create_group",
        side_effect=[
            SlackGroup(id="g1", name="g1"),
            SlackGroup(id="g2", name="g2"),
            SlackGroup(id="g3", name="g3"),
            SlackGroup(id="g4", name="g4"),
        ],
    )
    @patch("heltour.tournament.slackapi.invite_to_group")
    @patch("heltour.tournament.slackapi.set_group_topic")
    @patch("heltour.tournament.slackapi.leave_group")
    @patch("heltour.tournament.slackapi.send_message")
    def test_create_team_channel(
        self, send_message, leave_group, set_group_topic, invite_to_group, create_group
    ):
        with Shush():
            create_team_channel(self.team_ids)
        self.assertTrue(create_group.called)
        self.assertEqual(create_group.call_count, 4)
        self.assertTrue(invite_to_group.called)
        self.assertEqual(
            invite_to_group.call_count, 8
        )  # 4 teams, 1 call for team members, 1 for chesster
        self.assertTrue(set_group_topic.called)
        self.assertEqual(set_group_topic.call_count, 4)
        self.assertTrue(leave_group.called)
        self.assertEqual(leave_group.call_count, 4)
        self.assertTrue(send_message.called)
        self.assertTrue(send_message.call_count, 4)
        # Check that teams have slack channels assigned
        teams_with_channels = Team.objects.exclude(slack_channel="").count()
        self.assertEqual(teams_with_channels, 4)

    @patch(
        "heltour.tournament.slackapi.create_group",
        side_effect=[
            NameTaken,
            SlackGroup(id="g2", name="g2"),
            SlackGroup(id="g3", name="g3"),
            SlackGroup(id="g4", name="g4"),
        ],
    )
    @patch("heltour.tournament.slackapi.invite_to_group", side_effect=SlackError)
    @patch("heltour.tournament.slackapi.set_group_topic", side_effect=SlackError)
    @patch("heltour.tournament.slackapi.leave_group", side_effect=SlackError)
    @patch("heltour.tournament.slackapi.send_message")
    def test_create_team_channel_errors(
        self, send_message, leave_group, set_group_topic, invite_to_group, create_group
    ):
        with Shush():
            create_team_channel(self.team_ids)
        # Check that the first team doesn't have a slack channel due to NameTaken error
        teams_without_channels = Team.objects.filter(slack_channel="").count()
        self.assertEqual(teams_without_channels, 1)


@patch("heltour.tournament.tasks.MAX_GAMES_LICHESS_BROADCAST", 2)
class TestBroadcasts(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData(team_count=6)
        League.objects.filter(name="Team League").update(time_control="10+10")
        cls.s = get_season(league_type="team")
        cls.s.create_broadcast = True
        cls.s.broadcast_title_override = "Amazing Broadcast Title"
        cls.s.save()
        Broadcast.objects.create(lichess_id="testslug1", season=cls.s, first_board=1)
        cls.bc2 = Broadcast.objects.create(
            lichess_id="testslug2", season=cls.s, first_board=3
        )
        cls.bc3 = Broadcast.objects.create(
            lichess_id="testslug3", season=cls.s, first_board=5
        )
        cls.r1 = get_round(league_type="team", round_number=1)
        cls.r1.start_date = timezone.now()
        cls.r1.save()
        cls.t1 = Team.objects.get(number=1)
        cls.t2 = Team.objects.get(number=2)

    def test_create_team_string(self):
        teamstring = _create_team_string(self.s)
        self.assertEqual(
            teamstring,
            "Team%201%3B%20Player1%0A"
            "Team%201%3B%20Player2%0A"
            "Team%202%3B%20Player3%0A"
            "Team%202%3B%20Player4%0A"
            "Team%203%3B%20Player5%0A"
            "Team%203%3B%20Player6%0A"
            "Team%204%3B%20Player7%0A"
            "Team%204%3B%20Player8%0A"
            "Team%205%3B%20Player9%0A"
            "Team%205%3B%20Player10%0A"
            "Team%206%3B%20Player11%0A"
            "Team%206%3B%20Player12",
        )

    def test_create_broadcast_grouping(self):
        bcs = Broadcast.objects.all()
        groupings = _create_broadcast_grouping(
            broadcasts=bcs, title="Testing the Title"
        )
        self.assertEqual(
            groupings,
            "Testing the Title\n"
            "testslug1 | Boards 1 - 2\n"
            "testslug2 | Boards 3 - 4\n"
            "testslug3 | Boards 5 - ",
        )

    @patch(
        "heltour.tournament.tasks._create_team_string",
        return_value="invalid_team_string",
        autospec=True,
    )
    @patch(
        "heltour.tournament.lichessapi.update_or_create_broadcast",
        return_value={"tour": {"id": "testid"}},
        autospec=True,
    )
    def test_create_or_update_broadcast(self, lichessapi, teamstring):
        broadcastid = _create_or_update_broadcast(season=self.s)
        teamstring.assert_called_once_with(season=self.s)
        lichessapi.assert_called_once_with(
            broadcast_id="",
            name="Amazing Broadcast Title Boards 1 to 2",
            nrounds=3,
            format_="Team Swiss",
            tc="10%2b10",
            teamTable=True,
            grouping="",
            teams="invalid_team_string",
            players="",
            infoplayers="",
            markdown="This is the broadcast for season teamseason of the Team League "
            "league, a classical tournament with a 10%2b10 time control played "
            "exclusively on lichess. For more information or to sign up, "
            "visit [our website](https://lichess4545.com).",
        )
        self.assertEqual(broadcastid, "testid")

    @patch(
        "heltour.tournament.lichessapi.update_or_create_broadcast_round",
        autospec=True,
        return_value={"round": {"id": "someroundid"}},
    )
    def test_create_or_update_broadcast_round(self, lichessapi):
        broadcast_round_id = _create_or_update_broadcast_round(self.r1, first_board=1)
        lichessapi.assert_called_once_with(
            broadcast_id="testslug1",
            broadcast_round_id="",
            round_number=1,
            game_links=[],
            startsAt=ANY,
        )
        self.assertEqual(broadcast_round_id, "someroundid")

    @patch(
        "heltour.tournament.lichessapi.update_or_create_broadcast_round",
        autospec=True,
        return_value={"round": {"id": "roundidbc3"}},
    )
    @patch(
        "heltour.tournament.models.get_gameid_from_gamelink",
        autospec=True,
        return_value="patchlink",
    )
    def test_update_broadcast_round(self, gamelink, lichessapi):
        BroadcastRound.objects.create(
            broadcast=self.bc3, round_id=self.r1, lichess_id="roundidbc3"
        )
        BroadcastRound.objects.create(
            broadcast=self.bc2, round_id=self.r1, lichess_id="roundidbc2"
        )

        team3 = Team.objects.get(number=3)
        team4 = Team.objects.get(number=4)
        team5 = Team.objects.get(number=5)
        team6 = Team.objects.get(number=6)
        tp1 = TeamPairing.objects.create(
            white_team=self.t1, black_team=self.t2, round=self.r1, pairing_order=1
        )
        tp2 = TeamPairing.objects.create(
            white_team=team3, black_team=team4, round=self.r1, pairing_order=2
        )
        tp3 = TeamPairing.objects.create(
            white_team=team5, black_team=team6, round=self.r1, pairing_order=3
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp1,
            board_number=1,
            white=self.t1.teammember_set.get(board_number=1).player,
            black=self.t2.teammember_set.get(board_number=1).player,
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp1,
            board_number=2,
            white=self.t2.teammember_set.get(board_number=2).player,
            black=self.t1.teammember_set.get(board_number=2).player,
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp2,
            board_number=1,
            white=team3.teammember_set.get(board_number=1).player,
            black=team4.teammember_set.get(board_number=1).player,
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp2,
            board_number=2,
            white=team4.teammember_set.get(board_number=2).player,
            black=team3.teammember_set.get(board_number=2).player,
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp3,
            board_number=1,
            white=team5.teammember_set.get(board_number=1).player,
            black=team6.teammember_set.get(board_number=1).player,
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp3,
            board_number=2,
            white=team6.teammember_set.get(board_number=2).player,
            black=team5.teammember_set.get(board_number=2).player,
            game_link="https://lichess.org/fakelink",
        )
        broadcast_round_id2 = _create_or_update_broadcast_round(self.r1, first_board=3)
        self.assertEqual(broadcast_round_id2, "")
        self.assertFalse(
            TeamPlayerPairing.objects.get(team_pairing=tp3, board_number=2).broadcasted
        )
        broadcast_round_id3 = _create_or_update_broadcast_round(self.r1, first_board=5)
        lichessapi.assert_called_once_with(
            broadcast_id="",
            broadcast_round_id="roundidbc3",
            round_number=1,
            game_links=["patchlink"],
            startsAt=ANY,
        )
        self.assertEqual(broadcast_round_id3, "roundidbc3")
        self.assertTrue(
            TeamPlayerPairing.objects.get(team_pairing=tp3, board_number=2).broadcasted
        )

    @patch("heltour.tournament.tasks._create_or_update_broadcast_round")
    def test_update_broadcast_round_no_update(self, coubr):
        BroadcastRound.objects.create(
            broadcast=self.bc3, round_id=self.r1, lichess_id="roundidbc3"
        )
        tp1 = TeamPairing.objects.create(
            white_team=self.t1, black_team=self.t2, round=self.r1, pairing_order=1
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp1,
            board_number=1,
            white=self.t1.teammember_set.get(board_number=1).player,
            black=self.t2.teammember_set.get(board_number=1).player,
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp1,
            board_number=2,
            white=self.t2.teammember_set.get(board_number=2).player,
            black=self.t1.teammember_set.get(board_number=2).player,
            game_link="fakelink",
            broadcasted=True,
        )
        with Shush():
            update_broadcast_round(round_id=self.r1.pk)
        coubr.assert_not_called()

    @patch("heltour.tournament.tasks._create_or_update_broadcast_round")
    def test_update_broadcast_round_update(self, coubr):
        BroadcastRound.objects.create(
            broadcast=self.bc3, round_id=self.r1, lichess_id="roundidbc3"
        )
        tp1 = TeamPairing.objects.create(
            white_team=self.t1, black_team=self.t2, round=self.r1, pairing_order=1
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp1,
            board_number=1,
            white=self.t1.teammember_set.get(board_number=1).player,
            black=self.t2.teammember_set.get(board_number=1).player,
        )
        TeamPlayerPairing.objects.create(
            team_pairing=tp1,
            board_number=2,
            white=self.t2.teammember_set.get(board_number=2).player,
            black=self.t1.teammember_set.get(board_number=2).player,
            game_link="fakelink",
        )
        with Shush():
            update_broadcast_round(round_id=self.r1.pk)
        # called only once since we only created one broadcast round for board 5+
        coubr.assert_called_once_with(round_=self.r1, first_board=5)

    @patch(
        "heltour.tournament.tasks._create_broadcast_grouping",
        return_value="patchgroup",
    )
    @patch(
        "heltour.tournament.tasks._create_or_update_broadcast_round",
        return_value="fakerdid",
    )
    def test_create_broadcast_round(self, coubr, cbg):
        with Shush():
            create_broadcast_round(round_id=self.r1.pk)
        coubr.assert_has_calls(
            calls=[
                call(round_=self.r1, first_board=1),
                call(round_=self.r1, first_board=3),
                call(round_=self.r1, first_board=5),
            ],
            any_order=True,
        )
        cbg.assert_called_once()

    @patch("heltour.tournament.tasks._create_or_update_broadcast")
    def test_update_broadcast(self, coub):
        with Shush():
            update_broadcast(season_id=self.s.pk)
        with Shush():
            update_broadcast(season_id=self.s.pk, first_board=5)
        coub.assert_has_calls(
            calls=[
                call(season=self.s, broadcast_id="testslug1", first_board=1),
                call(season=self.s, broadcast_id="testslug3", first_board=5),
            ]
        )

    @patch(
        "heltour.tournament.tasks._create_or_update_broadcast", return_value="bcslug"
    )
    def test_create_broadcast(self, coub):
        sl = get_season("lone")
        sl.create_broadcast = True
        sl.save()
        with Shush():
            create_broadcast(season_id=self.s.pk, first_board=1)
        coub.assert_not_called()
        with Shush():
            create_broadcast(season_id=sl.pk, first_board=1)
        coub.assert_called_with(season=sl, first_board=1)
        self.assertTrue(Broadcast.objects.filter(season=sl, first_board=1).exists())
        with Shush():
            create_broadcast(season_id=sl.pk, first_board=3)
        coub.assert_called_with(season=sl, first_board=3)
        self.assertTrue(Broadcast.objects.filter(season=sl, first_board=3).exists())
        self.assertEqual(
            Broadcast.objects.get(season=sl, first_board=3).lichess_id, "bcslug"
        )


class TestStartUnscheduledGamesLock(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()

    @patch("heltour.tournament.tasks._start_unscheduled_games_inner")
    def test_lock_prevents_concurrent_execution(self, mock_inner):
        round_ = get_round(league_type="lone", round_number=1)
        lock = cache.lock(f"start_games_round_{round_.pk}", timeout=120)
        lock.acquire(blocking=False)
        try:
            with Shush():
                _start_unscheduled_games(round_.pk)
            mock_inner.assert_not_called()
        finally:
            lock.release()

    @patch("heltour.tournament.tasks._start_unscheduled_games_inner")
    def test_runs_when_lock_available(self, mock_inner):
        round_ = get_round(league_type="lone", round_number=1)
        with Shush():
            _start_unscheduled_games(round_.pk)
        mock_inner.assert_called_once_with(round_.pk)


class TestIdempotentGameLinkSave(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.round_ = get_round(league_type="lone", round_number=1)
        cls.p1 = get_player("Player1")
        cls.p2 = get_player("Player2")

    def setUp(self):
        self.lpp = LonePlayerPairing.objects.create(
            round=self.round_,
            white=self.p1,
            black=self.p2,
            game_link="",
            pairing_order=1,
        )

    @patch("heltour.tournament.tasks._notify_game_started")
    @patch("heltour.tournament.lichessapi.bulk_start_games")
    def test_does_not_overwrite_existing_game_link(self, mock_bulk, mock_notify):
        existing_link = "https://lichess.org/existing123"
        self.lpp.game_link = existing_link
        self.lpp.save()
        mock_bulk.return_value = {
            "id": "bulk123",
            "games": [
                {
                    "id": "newgame456",
                    "white": self.p1.lichess_username.lower(),
                    "black": self.p2.lichess_username.lower(),
                }
            ],
        }
        with Shush():
            _start_league_games(
                tokens="tok1:tok2",
                clock=600,
                increment=5,
                do_clockstart=False,
                clockstart=0,
                clockstart_in=0,
                variant="standard",
                leaguename="Lone League",
                league_games=LonePlayerPairing.objects.filter(pk=self.lpp.pk),
            )
        self.lpp.refresh_from_db()
        self.assertEqual(self.lpp.game_link, existing_link)

    @patch("heltour.tournament.tasks._notify_game_started")
    @patch("heltour.tournament.lichessapi.bulk_start_games")
    def test_sets_game_link_when_blank(self, mock_bulk, mock_notify):
        mock_bulk.return_value = {
            "id": "bulk123",
            "games": [
                {
                    "id": "newgame456",
                    "white": self.p1.lichess_username.lower(),
                    "black": self.p2.lichess_username.lower(),
                }
            ],
        }
        with Shush():
            _start_league_games(
                tokens="tok1:tok2",
                clock=600,
                increment=5,
                do_clockstart=False,
                clockstart=0,
                clockstart_in=0,
                variant="standard",
                leaguename="Lone League",
                league_games=LonePlayerPairing.objects.filter(pk=self.lpp.pk),
            )
        self.lpp.refresh_from_db()
        self.assertIn("newgame456", self.lpp.game_link)

    @patch("heltour.tournament.tasks._expire_bad_tokens")
    @patch("heltour.tournament.lichessapi.bulk_start_games")
    def test_no_retry_on_api_error(self, mock_bulk, mock_expire):
        error_body = '{"tokens": ["bad_tok_abc"]}'
        mock_bulk.side_effect = ApiClientError(
            f"API failure: CLIENT-ERROR: [400] {error_body}"
        )
        with Shush():
            result = _start_league_games(
                tokens="bad_tok_abc:tok2",
                clock=600,
                increment=5,
                do_clockstart=False,
                clockstart=0,
                clockstart_in=0,
                variant="standard",
                leaguename="Lone League",
                league_games=LonePlayerPairing.objects.filter(pk=self.lpp.pk),
            )
        self.assertIsNone(result)
        mock_bulk.assert_called_once()
        mock_expire.assert_called_once_with(
            league_games=ANY, bad_token="bad_tok_abc"
        )
        self.lpp.refresh_from_db()
        self.assertEqual(self.lpp.game_link, "")


class TestValidateSeasonTokens(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()

    def setUp(self):
        self.season = get_season("lone")
        self.p1 = get_player("Player1")
        self.p2 = get_player("Player2")
        SeasonPlayer.objects.filter(season=self.season).exclude(
            player__in=[self.p1, self.p2]
        ).update(is_active=False)
        cache.delete(f"token_validation_{self.season.pk}")

    @patch("heltour.tournament.lichessapi.get_admin_token")
    @patch("heltour.tournament.lichessapi.test_oauth_token")
    def test_all_tokens_valid(self, mock_test, mock_admin):
        token = OauthToken.objects.create(
            access_token="valid_tok_1",
            token_type="admin challenge token",
            expires=timezone.now() + timedelta(days=28),
            account_username=self.p1.lichess_username,
            scope="challenge:write",
        )
        Player.objects.filter(pk=self.p1.pk).update(oauth_token=token)
        token2 = OauthToken.objects.create(
            access_token="valid_tok_2",
            token_type="admin challenge token",
            expires=timezone.now() + timedelta(days=28),
            account_username=self.p2.lichess_username,
            scope="challenge:write",
        )
        Player.objects.filter(pk=self.p2.pk).update(oauth_token=token2)
        mock_test.return_value = {
            "valid_tok_1": {"scopes": "challenge:write"},
            "valid_tok_2": {"scopes": "challenge:write"},
        }
        with Shush():
            validate_season_tokens(self.season.pk)
        mock_admin.assert_not_called()
        result = cache.get(f"token_validation_{self.season.pk}")
        self.assertIsNotNone(result)
        self.assertTrue(result["success"])
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["failed"], [])

    @patch("heltour.tournament.lichessapi.get_admin_token")
    @patch("heltour.tournament.lichessapi.test_oauth_token")
    def test_refreshes_invalid_tokens(self, mock_test, mock_admin):
        token = OauthToken.objects.create(
            access_token="bad_tok",
            token_type="admin challenge token",
            expires=timezone.now() + timedelta(days=28),
            account_username=self.p1.lichess_username,
            scope="challenge:write",
        )
        Player.objects.filter(pk=self.p1.pk).update(oauth_token=token)
        mock_test.return_value = {}
        mock_admin.return_value = {
            self.p1.lichess_username: "refreshed_tok_1",
            self.p2.lichess_username: "refreshed_tok_2",
        }
        with Shush():
            validate_season_tokens(self.season.pk)
        mock_admin.assert_called_once()
        result = cache.get(f"token_validation_{self.season.pk}")
        self.assertTrue(result["success"])
        self.assertIn(self.p1.lichess_username, result["refreshed"])
        self.assertIn(self.p2.lichess_username, result["refreshed"])
        self.assertEqual(result["failed"], [])

    @patch("heltour.tournament.lichessapi.get_admin_token")
    @patch("heltour.tournament.lichessapi.test_oauth_token")
    def test_records_failed_tokens(self, mock_test, mock_admin):
        token = OauthToken.objects.create(
            access_token="bad_tok",
            token_type="admin challenge token",
            expires=timezone.now() + timedelta(days=28),
            account_username=self.p1.lichess_username,
            scope="challenge:write",
        )
        Player.objects.filter(pk=self.p1.pk).update(oauth_token=token)
        mock_test.return_value = {}
        mock_admin.return_value = {}
        with Shush():
            validate_season_tokens(self.season.pk)
        result = cache.get(f"token_validation_{self.season.pk}")
        self.assertFalse(result["success"])
        self.assertGreater(len(result["failed"]), 0)


def _create_fide_league(rating_type="fide_standard"):
    """Create a FIDE-rated league with a season and rounds."""
    league = League.objects.create(
        name="FIDE League",
        tag="fideleague",
        competitor_type="lone",
        rating_type=rating_type,
    )
    now = timezone.now()
    # Season.save() auto-creates rounds via update_or_create, so we just set
    # start_date and round_duration to get the dates we want.
    season = Season.objects.create(
        league=league,
        name="FIDE Season",
        tag="fideseason",
        rounds=3,
        start_date=now - timedelta(days=21),
        round_duration=timedelta(days=7),
    )
    # Mark first two rounds as completed with pairings published
    Round.objects.filter(season=season, number__lte=2).update(
        publish_pairings=True, is_completed=True
    )
    Round.objects.filter(season=season, number=3).update(
        publish_pairings=True, is_completed=False
    )
    return league, season


def _create_fide_player(username, fide_rating, rating_type="standard"):
    """Create a player with a FIDE rating profile."""
    player = Player.objects.create(
        lichess_username=username,
        fide_id="12345",
        fide_profile={rating_type: fide_rating},
    )
    # Also set a different Lichess rating so we can detect if the wrong one is used
    set_rating(player, fide_rating + 500)
    player.save()
    return player


class TestPopulateHistoricalRatingsFide(TestCase):
    """Tests that populate_historical_ratings uses FIDE ratings for FIDE-rated leagues."""

    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season = _create_fide_league()
        cls.r1 = Round.objects.get(season=cls.season, number=1)
        cls.r2 = Round.objects.get(season=cls.season, number=2)
        cls.r3 = Round.objects.get(season=cls.season, number=3)

        cls.alice = _create_fide_player("FideAlice", 2100)
        cls.bob = _create_fide_player("FideBob", 1900)

        cls.sp_alice = SeasonPlayer.objects.create(
            season=cls.season, player=cls.alice, seed_rating=2100
        )
        cls.sp_bob = SeasonPlayer.objects.create(
            season=cls.season, player=cls.bob, seed_rating=1900
        )
        LonePlayerScore.objects.create(season_player=cls.sp_alice)
        LonePlayerScore.objects.create(season_player=cls.sp_bob)

    def test_pairing_with_game_link_uses_fide_rating(self):
        """Pairings with game links in FIDE leagues should use FIDE ratings, not Lichess."""
        pairing = LonePlayerPairing.objects.create(
            round=self.r1,
            white=self.alice,
            black=self.bob,
            game_link="https://lichess.org/abcd1234",
            result="1-0",
            pairing_order=1,
        )
        with Shush():
            populate_historical_ratings()
        pairing.refresh_from_db()
        self.assertEqual(pairing.white_rating, 2100)
        self.assertEqual(pairing.black_rating, 1900)

    def test_pairing_without_game_link_incomplete_round_uses_fide_rating(self):
        """Pairings without game links in incomplete rounds should use FIDE ratings."""
        pairing = LonePlayerPairing.objects.create(
            round=self.r3,  # not completed
            white=self.alice,
            black=self.bob,
            result="1-0",
            pairing_order=1,
        )
        with Shush():
            populate_historical_ratings()
        pairing.refresh_from_db()
        self.assertEqual(pairing.white_rating, 2100)
        self.assertEqual(pairing.black_rating, 1900)

    @patch("heltour.tournament.lichessapi.get_game_meta")
    def test_pairing_without_game_link_completed_round_uses_fide_rating(self, mock_api):
        """Pairings without game links in completed rounds should use FIDE ratings,
        NOT call the Lichess API."""
        pairing = LonePlayerPairing.objects.create(
            round=self.r1,  # completed
            white=self.alice,
            black=self.bob,
            result="1-0",
            pairing_order=1,
        )
        with Shush():
            populate_historical_ratings()
        pairing.refresh_from_db()
        # Should use seed_rating (FIDE) not Lichess API
        self.assertEqual(pairing.white_rating, 2100)
        self.assertEqual(pairing.black_rating, 1900)
        # Lichess API should NOT have been called
        mock_api.assert_not_called()

    def test_player_bye_uses_fide_rating(self):
        """PlayerBye ratings should use FIDE ratings for FIDE leagues."""
        bye = PlayerBye.objects.create(
            round=self.r3,
            player=self.alice,
            type="half-point-bye",
        )
        with Shush():
            populate_historical_ratings()
        bye.refresh_from_db()
        self.assertEqual(bye.player_rating, 2100)

    @patch("heltour.tournament.lichessapi.get_game_meta")
    def test_player_bye_completed_round_uses_fide_rating(self, mock_api):
        """PlayerBye in completed rounds should use FIDE ratings, not Lichess API."""
        bye = PlayerBye.objects.create(
            round=self.r1,  # completed
            player=self.alice,
            type="half-point-bye",
        )
        with Shush():
            populate_historical_ratings()
        bye.refresh_from_db()
        self.assertEqual(bye.player_rating, 2100)
        mock_api.assert_not_called()

    @patch("heltour.tournament.lichessapi.get_game_meta")
    def test_season_player_final_rating_uses_fide_rating(self, mock_api):
        """SeasonPlayer final_rating should use FIDE ratings for completed FIDE seasons."""
        self.season.is_completed = True
        self.season.save()
        try:
            with Shush():
                populate_historical_ratings()
            self.sp_alice.refresh_from_db()
            self.sp_bob.refresh_from_db()
            self.assertEqual(self.sp_alice.final_rating, 2100)
            self.assertEqual(self.sp_bob.final_rating, 1900)
            mock_api.assert_not_called()
        finally:
            self.season.is_completed = False
            self.season.save()
            SeasonPlayer.objects.filter(
                pk__in=[self.sp_alice.pk, self.sp_bob.pk]
            ).update(final_rating=None)


class TestFindClosestRatingFide(TestCase):
    """Tests that _find_closest_rating returns FIDE ratings for FIDE leagues."""

    @classmethod
    def setUpTestData(cls):
        cls.league, cls.season = _create_fide_league()
        cls.r1 = Round.objects.get(season=cls.season, number=1)

        cls.alice = _create_fide_player("FcrAlice", 2100)
        cls.bob = _create_fide_player("FcrBob", 1900)

        cls.sp_alice = SeasonPlayer.objects.create(
            season=cls.season, player=cls.alice, seed_rating=2100
        )
        cls.sp_bob = SeasonPlayer.objects.create(
            season=cls.season, player=cls.bob, seed_rating=1900
        )

    def test_returns_fide_rating_for_fide_league(self):
        """_find_closest_rating should return the FIDE rating for FIDE leagues."""
        result = _find_closest_rating(self.alice, self.r1.end_date, self.season)
        self.assertEqual(result, 2100)

    def test_returns_none_for_none_player(self):
        """_find_closest_rating should return None for a None player."""
        result = _find_closest_rating(None, self.r1.end_date, self.season)
        self.assertIsNone(result)

    @patch("heltour.tournament.lichessapi.get_game_meta")
    def test_does_not_call_lichess_api(self, mock_api):
        """_find_closest_rating should never call Lichess API for FIDE leagues."""
        # Create a pairing with a game link to ensure there's data to tempt the API path
        LonePlayerPairing.objects.create(
            round=self.r1,
            white=self.alice,
            black=self.bob,
            game_link="https://lichess.org/fakelink",
            result="1-0",
            white_rating=2100,
            black_rating=1900,
            pairing_order=1,
        )
        result = _find_closest_rating(self.alice, self.r1.end_date, self.season)
        self.assertEqual(result, 2100)
        mock_api.assert_not_called()

    def test_returns_default_fide_rating_for_no_profile(self):
        """Players without FIDE profile should get the default 1400 rating."""
        player_no_fide = Player.objects.create(
            lichess_username="FcrNoFide",
            fide_id="00000",
            fide_profile={},
        )
        SeasonPlayer.objects.create(season=self.season, player=player_no_fide)
        result = _find_closest_rating(player_no_fide, self.r1.end_date, self.season)
        # rating_for returns 1400 when FIDE profile doesn't have the key
        self.assertEqual(result, 1400)


class TestFindClosestRatingLichess(TestCase):
    """Tests that _find_closest_rating still works correctly for Lichess-rated leagues."""

    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.season = get_season("lone")
        cls.r1 = get_round(league_type="lone", round_number=1)
        cls.r1.start_date = timezone.now() - timedelta(days=14)
        cls.r1.end_date = timezone.now() - timedelta(days=7)
        cls.r1.is_completed = True
        cls.r1.save()
        cls.p1 = get_player("Player1")
        cls.p2 = get_player("Player2")
        set_rating(cls.p1, 1500)
        cls.p1.save()
        set_rating(cls.p2, 1600)
        cls.p2.save()
        SeasonPlayer.objects.filter(
            season=cls.season, player=cls.p1
        ).update(seed_rating=1500)

    def test_returns_seed_rating_when_no_pairings(self):
        """Should return seed_rating when no pairings exist for Lichess league."""
        result = _find_closest_rating(self.p1, self.r1.end_date, self.season)
        self.assertEqual(result, 1500)

    def test_returns_current_rating_when_no_seed_or_pairings(self):
        """Should fall back to current Lichess rating when no seed or pairings."""
        result = _find_closest_rating(self.p2, self.r1.end_date, self.season)
        self.assertEqual(result, 1600)

    def test_does_not_short_circuit_for_lichess_league(self):
        """For non-FIDE leagues, should NOT short-circuit at the FIDE check."""
        # Verify that with no seed_rating and no pairings, it falls through
        # to player.rating_for(league) via the normal path, not the FIDE early return
        SeasonPlayer.objects.filter(
            season=self.season, player=self.p2
        ).update(seed_rating=None)
        result = _find_closest_rating(self.p2, self.r1.end_date, self.season)
        # Should return the Lichess classical rating (1600), not a FIDE rating
        self.assertEqual(result, 1600)


class TestPopulateHistoricalRatingsFideTeam(TestCase):
    """Tests that populate_historical_ratings uses FIDE ratings for FIDE-rated team leagues."""

    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name="FIDE Team League",
            tag="fideteamleague",
            competitor_type="team",
            rating_type="fide_standard",
        )
        now = timezone.now()
        cls.season = Season.objects.create(
            league=cls.league,
            name="FIDE Team Season",
            tag="fideteamseason",
            rounds=2,
            boards=2,
            start_date=now - timedelta(days=14),
            round_duration=timedelta(days=7),
        )
        Round.objects.filter(season=cls.season).update(
            publish_pairings=True, is_completed=True
        )
        cls.r1 = Round.objects.get(season=cls.season, number=1)

        cls.alice = _create_fide_player("FtAlice", 2100)
        cls.bob = _create_fide_player("FtBob", 1900)
        cls.charlie = _create_fide_player("FtCharlie", 2000)
        cls.dave = _create_fide_player("FtDave", 1800)

        team1 = Team.objects.create(season=cls.season, number=1, name="FIDE Team 1")
        team2 = Team.objects.create(season=cls.season, number=2, name="FIDE Team 2")
        TeamScore.objects.create(team=team1)
        TeamScore.objects.create(team=team2)

        cls.tm1 = TeamMember.objects.create(
            team=team1, player=cls.alice, board_number=1
        )
        cls.tm2 = TeamMember.objects.create(
            team=team1, player=cls.bob, board_number=2
        )
        cls.tm3 = TeamMember.objects.create(
            team=team2, player=cls.charlie, board_number=1
        )
        cls.tm4 = TeamMember.objects.create(
            team=team2, player=cls.dave, board_number=2
        )

        for p in [cls.alice, cls.bob, cls.charlie, cls.dave]:
            sp = SeasonPlayer.objects.create(
                season=cls.season, player=p,
                seed_rating=p.rating_for(cls.league),
            )

    @patch("heltour.tournament.lichessapi.get_game_meta")
    def test_team_member_rating_uses_fide(self, mock_api):
        """TeamMember ratings should use FIDE ratings when season is completed."""
        # Reset player_rating to None so populate_historical_ratings will fill it
        TeamMember.objects.filter(
            pk__in=[self.tm1.pk, self.tm2.pk, self.tm3.pk, self.tm4.pk]
        ).update(player_rating=None)
        self.season.is_completed = True
        self.season.save()
        try:
            with Shush():
                populate_historical_ratings()
            self.tm1.refresh_from_db()
            self.tm2.refresh_from_db()
            self.tm3.refresh_from_db()
            self.tm4.refresh_from_db()
            self.assertEqual(self.tm1.player_rating, 2100)
            self.assertEqual(self.tm2.player_rating, 1900)
            self.assertEqual(self.tm3.player_rating, 2000)
            self.assertEqual(self.tm4.player_rating, 1800)
            mock_api.assert_not_called()
        finally:
            self.season.is_completed = False
            self.season.save()
