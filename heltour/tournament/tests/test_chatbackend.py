from unittest.mock import ANY, call, patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from heltour.tournament.chatbackend import (
    bold,
    cb_create_team_channel,
    channel_message,
    channellink,
    chatbackend,
    chatbackend_render,
    chatbackend_url,
    direct_user_message,
    dm_link,
    get_user,
    get_user_list,
    inlinecode,
    invite_user,
    link,
    multiple_user_message,
    ping_mods,
    send_control_message,
    userlink_ping,
    userlink_silent,
)
from heltour.tournament.slackapi import SlackGroup, SlackUser
from heltour.tournament.tests.testutils import Shush, createCommonLeagueData, get_team


@override_settings(USE_CHATBACKEND="slack")
class SlackFormatTestCase(SimpleTestCase):
    def test_bold(self):
        self.assertEqual(bold("some text"), "*some text*")

    def test_channellink(self):
        self.assertEqual(
            channellink(
                channelprefix="#",
                channelid="someid",
                channel="testchannel",
                topic="tests",
            ),
            "<#someid|testchannel>",
        )
        self.assertEqual(
            channellink(channelid="someid", channel="testchannel", topic="tests"),
            "<#someid|testchannel>",
        )
        self.assertEqual(channellink(channel="testchannel"), "#testchannel")

    def test_chatbackend_str(self):
        self.assertEqual(chatbackend(), "Slack")

    def test_chatbackend_render(self):
        self.assertTrue(chatbackend_render())

    def test_chatbackend_url(self):
        self.assertEqual(chatbackend_url(), "https://lichess4545.slack.com")

    def test_dm_link(self):
        self.assertEqual(
            dm_link(
                usernames=["glbert", "lakinwecker"],
                userids=["U666", "U001"],
                add_bot=False,
            ),
            "https://lichess4545.slack.com/messages/@glbert,@lakinwecker/",
        )
        self.assertEqual(
            dm_link(
                usernames=["glbert", "lakinwecker"],
                userids=["U666", "U001"],
                add_bot=True,
            ),
            "https://lichess4545.slack.com/messages/@glbert,@lakinwecker,@chesster/",
        )

    def test_inlinecode(self):
        self.assertEqual(inlinecode("some text"), "`some text`")

    def test_link(self):
        self.assertEqual(
            link(text="Lichess4545", url="https://lichess4545.com"),
            "<https://lichess4545.com|Lichess4545>",
        )

    def test_ping_mods(self):
        self.assertEqual(ping_mods(), "@chesster summon mods")

    def test_userlink_ping(self):
        self.assertEqual(userlink_ping("Tranzoo"), "<@Tranzoo>")

    def test_userlink_silent(self):
        self.assertEqual(userlink_silent("lakinwecker"), "<@lakinwecker>")

    @patch("heltour.tournament.slackapi.SlackClient._get_slack_webhook", return_value="someurl")
    @patch("requests.post")
    def test_channel_message(self, post, webhook):
        post.return_value.text = "ok"
        with Shush():
            channel_message(channel="testchannel", text="testing")
        post.assert_called_with(
            "someurl",
            json={
                "text": "forward to testchannel",
                "attachments": [{"text": "testing"}],
            },
        )

    @patch("heltour.tournament.slackapi.SlackClient._get_slack_webhook", return_value="someurl")
    @patch("requests.post")
    def test_control_message(self, post, webhook):
        post.return_value.text = "ok"
        with Shush():
            send_control_message(text="testing control messages")
        post.assert_called_with("someurl", json={"text": "testing control messages"})

    @patch("heltour.tournament.slackapi.SlackClient._get_slack_webhook", return_value="someurl")
    @patch("requests.post")
    def test_direct_user_message(self, post, webhook):
        with Shush():
            direct_user_message(
                username="lakinwecker", userid="0001", text="testing direct messages"
            )
        post.assert_called_with(
            "someurl",
            json={
                "text": "forward to @lakinwecker",
                "attachments": [{"text": "testing direct messages"}],
            },
        )

    @patch("heltour.tournament.slackapi.SlackClient._get_slack_webhook", return_value="someurl")
    @patch("requests.post")
    def test_multiple_user_message(self, post, webhook):
        with Shush():
            multiple_user_message(
                usernames=["lakinwecker", "chesster"],
                userids=["0001", "0002"],
                text="testing direct messages to multiple users",
            )
        post.assert_called_with(
            "someurl",
            json={
                "text": "forward to @lakinwecker+@chesster",
                "attachments": [{"text": "testing direct messages to multiple users"}],
            },
        )

    @patch("heltour.tournament.slackapi.SlackClient._get_slack_token", return_value="faketoken")
    @patch("requests.get")
    def test_get_user(self, get, token):
        get.return_value.json.return_value = {
            "ok": True,
            "user": {
                "id": "0002",
                "name": "glbert",
                "profile": {
                    "real_name": "gl bert",
                    "display_name": "glbert-disp",
                    "email": "example@fakeimail",
                },
                "tz_offset": "0",
            },
        }
        result = get_user(user_id="0002")
        token.assert_called_once()
        get.assert_called_once_with(
            "https://slack.com/api/users.info",
            params={"user": "0002", "token": "faketoken"},
        )
        self.assertEqual(
            result,
            SlackUser(
                id="0002",
                real_name=ANY,
                name_deprecated=ANY,
                display_name="glbert-disp",
                email="example@fakeimail",
                tz_offset="0",
            ),
        )

    @patch("heltour.tournament.slackapi.SlackClient._get_slack_token", return_value="faketoken")
    @patch("requests.get")
    def test_get_user_list(self, get, token):
        get.return_value.json.return_value = {
            "ok": True,
            "members": [
                {
                    "id": "0001",
                    "name": "lakinwecker",
                    "profile": {
                        "real_name": "lakin wecker",
                        "display_name": "lakin-disp",
                        "email": "lakinwecker@example.com",
                    },
                    "tz_offset": "-6",
                },
                {
                    "id": "0002",
                    "name": "glbert",
                    "profile": {
                        "real_name": "gl bert",
                        "display_name": "glbert-disp",
                        "email": "example@fakeimail",
                    },
                    "tz_offset": "0",
                },
            ],
        }
        result = get_user_list()
        token.assert_called_once()
        get.assert_called_once_with(
            "https://slack.com/api/users.list",
            params={"token": "faketoken"},
        )
        self.assertEqual(
            result,
            [
                SlackUser(
                    id="0001",
                    name_deprecated=ANY,
                    real_name=ANY,
                    display_name="lakin-disp",
                    email="lakinwecker@example.com",
                    tz_offset="-6",
                ),
                SlackUser(
                    id="0002",
                    name_deprecated=ANY,
                    real_name=ANY,
                    display_name="glbert-disp",
                    email="example@fakeimail",
                    tz_offset="0",
                ),
            ],
        )

    @patch("heltour.tournament.slackapi.SlackClient._get_slack_token", return_value="faketoken")
    @patch("requests.get")
    def test_inivite_user(self, get, token):
        get.return_value.json.return_value = {
            "ok": True,
        }
        invite_user("sgis@glbert.com")
        token.assert_called_once()
        get.assert_called_once_with(
            "https://slack.com/api/users.admin.invite",
            params={"token": "faketoken", "email": "sgis@glbert.com"},
        )


class TeamChannelCreation(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.t = get_team("Team 1")

    @override_settings(USE_CHATBACKEND="slack")
    @patch(
        "heltour.tournament.slackapi.SlackClient._create_group",
        return_value=SlackGroup("id1", "channelname"),
    )
    @patch("heltour.tournament.slackapi.SlackClient._invite_to_group")
    @patch("heltour.tournament.slackapi.SlackClient._set_group_topic")
    @patch("heltour.tournament.slackapi.SlackClient._leave_group")
    @patch("heltour.tournament.slackapi.SlackClient.channel_message")
    @patch("reversion.create_revision")
    @patch("reversion.set_comment")
    def test_slack_create_team_channels(
        self,
        r_comment,
        r_revision,
        send_message,
        leave_group,
        set_group_topic,
        invite_to_group,
        create_group,
    ):
        cb_create_team_channel(
            team=self.t,
            channel_name="channelname",
            user_ids=["1", "2"],
            topic="channel topic",
            intro_message="welcome to your channel",
        )
        create_group.assert_called_once_with("channelname")
        invite_to_group.assert_has_calls(
            [call("id1", ["1", "2"]), call("id1", settings.SLACK_LISTENING_BOT_ID)],
            any_order=True,
        )
        set_group_topic.assert_called_once_with("id1", "channel topic")
        leave_group.assert_called_once()
        send_message.assert_called_once_with("#channelname", "welcome to your channel")
        self.assertEqual("id1", get_team("Team 1").slack_channel)
