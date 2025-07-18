from datetime import timedelta
from unittest.mock import patch, ANY

from django.test import TestCase
from django.utils import timezone

from heltour.tournament.lichessapi import ApiClientError
from heltour.tournament.models import (
    Broadcast,
    League,
    OauthToken,
    Player,
    Round,
    SeasonPlayer,
    Team,
    TeamPairing,
    TeamPlayerPairing,
)
from heltour.tournament.slackapi import NameTaken, SlackError, SlackGroup
from heltour.tournament.tasks import (
    _create_broadcast_grouping,
    _create_or_update_broadcast,
    _create_or_update_broadcast_round,
    _create_team_string,
    active_player_usernames,
    create_team_channel,
    start_games,
    update_player_ratings,
)
from heltour.tournament.tests.testutils import (
    Shush,
    createCommonLeagueData,
    get_league,
    get_player,
    get_round,
    get_season,
)


class TestHelpers(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.playernames = ["Player" + str(i) for i in range(1, 9)]

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
        side_effect=[
            ApiClientError('{"tokens": ["blah2"]}'),
            {
                "id": "RVAcwgg7",
                "games": [{"id": "KT837Aut", "black": "player3", "white": "player1"}],
            },
        ],
    )
    def test_start_invalid_token(self, *args):
        TeamPlayerPairing.objects.filter(board_number=1).update(black_confirmed=True)
        # start_games writes to the log, disable that temporarily for nicer test output
        with Shush():
            start_games()
        tpp2 = TeamPlayerPairing.objects.get(board_number=2)
        tpp1 = TeamPlayerPairing.objects.get(board_number=1)
        # test that the tpp2 game link was not set
        self.assertEqual(tpp2.game_link, "")
        # test that the ttp1 game was set, that is a bad token pairing was removed and the remaining pairing still used
        self.assertEqual(tpp1.game_link, "https://lichess.org/KT837Aut")
        # test that the expiry of the bad token was set to a time in the past
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
        self.assertEqual(
            Team.objects.get(pk=self.team_ids[0]["pk"]).slack_channel, "g1"
        )

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
        self.assertEqual(Team.objects.get(pk=self.team_ids[0]["pk"]).slack_channel, "")


class TestBroadcasts(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        League.objects.filter(name="Team League").update(time_control="10+10")
        cls.s = get_season(league_type="team")
        cls.s.create_broadcast = True
        cls.s.broadcast_title_override = "Amazing Broadcast Title"
        cls.s.save()
        Broadcast.objects.create(lichess_id="testslug1", season=cls.s, first_board=1)
        Broadcast.objects.create(lichess_id="testslug2", season=cls.s, first_board=11)
        Broadcast.objects.create(lichess_id="testslug3", season=cls.s, first_board=21)
        cls.r1 = get_round(league_type="team", round_number=1)
        cls.r1.start_date = timezone.now()
        cls.r1.save()


    def test_create_team_string(self):
        teamstring = _create_team_string(self.s)
        self.assertEqual(
            teamstring,
            "Team 1%3B%20Player1%0A"
            "Team 1%3B%20Player2%0A"
            "Team 2%3B%20Player3%0A"
            "Team 2%3B%20Player4%0A"
            "Team 3%3B%20Player5%0A"
            "Team 3%3B%20Player6%0A"
            "Team 4%3B%20Player7%0A"
            "Team 4%3B%20Player8",
        )

    def test_create_broadcast_grouping(self):
        bcs = Broadcast.objects.all()
        groupings = _create_broadcast_grouping(
            broadcasts=bcs, title="Testing the Title"
        )
        self.assertEqual(
            groupings,
            "Testing the Title\n"
            "testslug1 | Boards 1 - 10\n"
            "testslug2 | Boards 11 - 20\n"
            "testslug3 | Boards 21 - ",
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
    @patch("heltour.tournament.tasks.MAX_GAMES_LICHESS_BROADCAST", 10)
    def test_create_or_update_broadcast(self, lichessapi, teamstring):
        broadcastid = _create_or_update_broadcast(season=self.s)
        teamstring.assert_called_once_with(season=self.s)
        lichessapi.assert_called_once_with(
            broadcast_id="",
            name="Amazing Broadcast Title Boards 1 to 10",
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
        return_value={"round": {"id": "someroundid"}}
    )
    def test_create_or_update_broadcast_round(self, lichessapi):
        broadcast_round_id = _create_or_update_broadcast_round(self.r1, first_board=1)
        lichessapi.assert_called_once_with(
            broadcast_id='testslug1',
            broadcast_round_id='',
            round_number=1,
            game_links=[],
            startsAt=ANY,
        )
        self.assertEqual(broadcast_round_id, "someroundid")
