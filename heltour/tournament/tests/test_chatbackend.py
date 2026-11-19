from unittest.mock import ANY, Mock, call, patch

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
    italic,
    link,
    multiple_user_message,
    ping_mods,
    send_control_message,
    set_user,
    userlink_ping,
    userlink_silent,
)
from heltour.tournament.slackapi import SlackClient, SlackGroup, SlackUser
from heltour.tournament.tests.testutils import Shush, createCommonLeagueData, get_team
from heltour.tournament.zulipapi import ZulipClient


#@override_settings(USE_CHATBACKEND="slack", SLACK_API_TOKEN="pretend-token")
@patch(
    "heltour.tournament.chatbackend.notifier",
    return_value=SlackClient(api_token="pretend_token"),
)
class SlackFormatTestCase(SimpleTestCase):
    def test_bold(self, sc):
        self.assertEqual(bold("some text"), "*some text*")

    def test_channellink(self, sc):
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

    def test_chatbackend_str(self, sc):
        self.assertEqual(chatbackend(), "Slack")

    def test_chatbackend_render(self, sc):
        self.assertTrue(chatbackend_render())

    def test_chatbackend_url(self, sc):
        self.assertEqual(chatbackend_url(), "https://lichess4545.slack.com")

    def test_dm_link(self, sc):
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

    def test_inlinecode(self, sc):
        self.assertEqual(inlinecode("some text"), "`some text`")

    def test_link(self, sc):
        self.assertEqual(
            link(text="Lichess4545", url="https://lichess4545.com"),
            "<https://lichess4545.com|Lichess4545>",
        )

    def test_ping_mods(self, sc):
        self.assertEqual(ping_mods(), "@chesster summon mods")

    def test_userlink_ping(self, sc):
        self.assertEqual(userlink_ping("Tranzoo"), "<@Tranzoo>")

    def test_userlink_silent(self, sc):
        self.assertEqual(userlink_silent("lakinwecker"), "<@lakinwecker>")

    @patch(
        "heltour.tournament.slackapi.SlackClient._get_slack_webhook",
        return_value="someurl",
    )
    @patch("requests.post")
    def test_channel_message(self, post, webhook, sc):
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

    @patch(
        "heltour.tournament.slackapi.SlackClient._get_slack_webhook",
        return_value="someurl",
    )
    @patch("requests.post")
    def test_control_message(self, post, webhook, sc):
        post.return_value.text = "ok"
        with Shush():
            send_control_message(text="testing control messages")
        post.assert_called_with("someurl", json={"text": "testing control messages"})

    @patch(
        "heltour.tournament.slackapi.SlackClient._get_slack_webhook",
        return_value="someurl",
    )
    @patch("requests.post")
    def test_direct_user_message(self, post, webhook, sc):
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

    @patch(
        "heltour.tournament.slackapi.SlackClient._get_slack_webhook",
        return_value="someurl",
    )
    @patch("requests.post")
    def test_multiple_user_message(self, post, webhook, sc):
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

    @patch(
        "heltour.tournament.slackapi.SlackClient._get_slack_token",
        return_value="faketoken",
    )
    @patch("requests.get")
    def test_get_user(self, get, token, sc):
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
                lichess_username="",
            ),
        )

    @patch(
        "heltour.tournament.slackapi.SlackClient._get_slack_token",
        return_value="faketoken",
    )
    @patch("requests.get")
    def test_get_user_list(self, get, token, sc):
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
                    lichess_username="",
                ),
                SlackUser(
                    id="0002",
                    name_deprecated=ANY,
                    real_name=ANY,
                    display_name="glbert-disp",
                    email="example@fakeimail",
                    tz_offset="0",
                    lichess_username="",
                ),
            ],
        )

    @patch(
        "heltour.tournament.slackapi.SlackClient._get_slack_token",
        return_value="faketoken",
    )
    @patch("requests.get")
    def test_inivite_user(self, get, token, sc):
        get.return_value.json.return_value = {
            "ok": True,
        }
        invite_user("sgis@glbert.com")
        token.assert_called_once()
        get.assert_called_once_with(
            "https://slack.com/api/users.admin.invite",
            params={"token": "faketoken", "email": "sgis@glbert.com"},
        )


@override_settings(USE_CHATBACKEND="slack", SLACK_API_TOKEN="pretend-token")
@patch(
    "heltour.tournament.chatbackend.notifier",
    return_value=SlackClient(api_token="pretend-token"),
)
class TeamChannelCreation(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.t = get_team("Team 1")

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
        sc,
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
            [call("id1", ["1", "2"]), call("id1", [settings.SLACK_LISTENING_BOT_ID])],
            any_order=True,
        )
        set_group_topic.assert_called_once_with("id1", "channel topic")
        leave_group.assert_called_once()
        send_message.assert_called_once_with("#channelname", "welcome to your channel")
        self.assertEqual("id1", get_team("Team 1").slack_channel)


## Zulip Tests
class FakeZulipClient(ZulipClient):
    def __init__(self):
        self.client = Mock()
        self.max_topic_length=100
        self.max_message_length=1000
        self.max_stream_name_length=100
        self.max_stream_description_length=1000
        self.client.send_message.return_value = {
            "result": "success"
        }
        self.client.get_user_by_id.return_value={
            "result": "success",
            "user": {
                "user_id": 2,
                "timezone": "MST",
                "email": "no@fakeimail",
                "full_name": "glbert",
                "profile_data": {
                    settings.ZULIP_LICHESS_CUSTOM_FIELD_ID: {"value": "blind_gilbert"}
                }
            },
        }
        self.client.get_members.return_value={
            "result": "success",
            "members": [
                {
                    "user_id": 1,
                    "timezone": "UTC",
                    "delivery_email": "lakinwecker@example.com",
                    "full_name": "lakinwecker",
                    "profile_data": {
                        settings.ZULIP_LICHESS_CUSTOM_FIELD_ID: {"value": "lakin"}
                    }
                },
                {
                    "user_id": 2,
                    "timezone": "MST",
                    "delivery_email": "no@fakeimail",
                    "full_name": "glbert",
                    "profile_data": {
                        settings.ZULIP_LICHESS_CUSTOM_FIELD_ID: {"value": "glbert"}
                    }
                },
            ],
        }


@patch(
    "heltour.tournament.chatbackend.notifier",
    return_value=FakeZulipClient(),
)
class ZulipFormatTestCase(SimpleTestCase):
    def test_bold(self, nf):
        self.assertEqual(bold("some text"), "**some text**")

    def test_channellink(self, nf):
        self.assertEqual(
            channellink(
                channelprefix="#",
                channelid="someid",
                channel="testchannel",
                topic="tests",
            ),
            "#**testchannel>tests**",
        )
        self.assertEqual(
            channellink(channelid="someid", channel="testchannel", topic="tests"),
            "#**testchannel>tests**",
        )
        self.assertEqual(channellink(channel="testchannel"), "#**testchannel**")

    def test_chatbackend_str(self, nf):
        self.assertEqual(chatbackend(), "Zulip")

    def test_chatbackend_render(self, nf):
        self.assertTrue(chatbackend_render())

    def test_chatbackend_url(self, nf):
        self.assertEqual(chatbackend_url(), "https://lichess4545-test.zulipchat.com")

    def test_dm_link(self, nf):
        self.assertEqual(
            dm_link(
                usernames=["glbert", "lakinwecker"],
                userids=["U666", "U001"],
                add_bot=False,
            ),
            "https://lichess4545-test.zulipchat.com/#narrow/dm/U666,U001-group",
        )
        self.assertEqual(
            dm_link(
                usernames=["glbert", "lakinwecker"],
                userids=["U666", "U001"],
                add_bot=True,
            ),
            f"https://lichess4545-test.zulipchat.com/#narrow/dm/U666,U001,{settings.ZULIP_LISTENING_BOT}-group",
        )

    def test_inlinecode(self, nf):
        self.assertEqual(inlinecode("some text"), "`some text`")

    def test_italic(self, nf):
        self.assertEqual(italic("some text"), "*some text*")

    def test_link(self, nf):
        self.assertEqual(
            link(text="Lichess4545", url="https://lichess4545.com"),
            "[Lichess4545](https://lichess4545.com)",
        )

    def test_ping_mods(self, nf):
        self.assertEqual(ping_mods(), "@*mods4545*")

    def test_userlink_ping(self, nf):
        self.assertEqual(userlink_ping("Tranzoo"), "@**Tranzoo**")

    def test_userlink_silent(self, nf):
        self.assertEqual(userlink_silent("glbert"), "@_**glbert**")

    def test_channel_message(self, nf):
        with Shush():
            channel_message(channel="testchannel", text="testing")
        nf().client.send_message.assert_called_once_with(
            {
                "type": "channel",
                "to": "testchannel",
                "content": "testing",
                "topic": "(no topic)",
            }
        )

    def test_control_message(self, nf):
        with Shush():
            send_control_message(text="testing control messages")
        nf().client.send_message.assert_called_with(
            {
                "type": "channel",
                "to": "msg-forward",
                "content": "testing control messages",
                "topic": "control",
            }
        )

    def test_direct_user_message(self, nf):
        with Shush():
            direct_user_message(
                username="lakinwecker", userid="0001", text="testing direct messages"
            )
        nf().client.send_message.assert_called_with(
            {
                "type": "direct",
                "to": [1],
                "content": "testing direct messages",
            }
        )

    def test_multiple_user_message(self, nf):
        nf().client.reset_mock()
        with Shush():
            multiple_user_message(
                usernames=["lakinwecker", "glbert"],
                userids=["0001", "0002"],
                text="testing direct messages to multiple users",
            )
        nf().client.send_message.assert_called_once_with(
            {
                "type": "direct",
                "to": [1, 2, settings.ZULIP_LISTENING_BOT],
                "content": "testing direct messages to multiple users",
            }
        )

    def test_get_user(self, nf):
        result = get_user(user_id="0002")
        nf().client.get_user_by_id.assert_called_once_with(
            2, include_custom_profile_fields=True
        )
        self.assertEqual(
            result,
            SlackUser(
                id="2",
                name_deprecated="",
                real_name="",
                display_name="glbert",
                email="no@fakeimail",
                tz_offset=-25200.0,
                lichess_username="blind_gilbert"
            ),
        )


    def test_get_user_list(self, nf):
        result = get_user_list()
        nf().client.get_members.assert_called_once_with(
            {"include_custom_profile_fields": True}
        )
        self.assertEqual(
            result,
            [
                SlackUser(
                    id="1",
                    name_deprecated="",
                    real_name="",
                    display_name="lakinwecker",
                    email="lakinwecker@example.com",
                    tz_offset=0.0,
                    lichess_username="lakin"
                ),
                SlackUser(
                    id="2",
                    name_deprecated="",
                    real_name="",
                    display_name="glbert",
                    email="no@fakeimail",
                    tz_offset=-25200.0,
                    lichess_username="glbert"
                ),
            ],
        )

    def test_set_user(self, nf):
        nf().client.update_user_by_id.return_value = {"result": "success"}
        set_user(user_id="2", lichess_username="glbert")
        nf().client.update_user_by_id.assert_called_once_with(
            2,
            profile_data=[
                {"id": settings.ZULIP_LICHESS_CUSTOM_FIELD_ID, "value": "glbert"}
            ],
        )

    @patch("heltour.tournament.zulipapi.Client")
    def test_invite_user(self, client, nf):
        client.return_value.register.return_value = {
            "result": "success",
            "max_topic_length": 100,
            "max_message_length": 1000,
            "max_stream_name_length": 100,
            "max_stream_description_length": 1000,
        }
        client.return_value.call_endpoint.return_value = {
            "result": "success",
        }
        with Shush():
            invite_user("sgis@glbert.com")
        client.return_value.call_endpoint.assert_called_once_with(
            url="/invites",
            method="POST",
            request={
                "invitee_emails": "sgis@glbert.com",
                "invite_expires_in_minutes": 40320,
                "invite_as": 600,
                "stream_ids": [],
                "include_realm_default_subscriptions": "true",
                "notify_referrer_on_join": "false",
            },
        )


@patch(
    "heltour.tournament.chatbackend.notifier",
    return_value=FakeZulipClient(),
)
class ZulipTeamChannelTest(TestCase):
    def test_cb_create_team_channel(self, nf):
        nf().client.add_subscriptions.return_value = {"result": "success"}
        nf().client.get_stream_id.return_value = {"result": "success", "stream_id": "1337"}
        createCommonLeagueData()
        t1 = get_team("Team 1")
        with Shush():
            cb_create_team_channel(
                team=t1,
                channel_name="S0_Team1",
                user_ids=["1", "2"],
                topic="Welcome!",
                intro_message="Welcome to the new season, Team1",
            )
        nf().client.add_subscriptions.assert_called_once_with(
            streams=[
                {
                    'name': 'S0_Team1',
                    'description': 'Welcome!',
                }
            ],
            principals=[1, 2, settings.ZULIP_LISTENING_BOT, settings.ZULIP_HELTOUR_BOT],
            invite_only=True,
            history_public_to_subscribers=False,
            can_add_subscribers_group={'direct_members': [1, 2, settings.ZULIP_LISTENING_BOT, settings.ZULIP_HELTOUR_BOT], 'direct_subgroups': []},
            can_remove_subscribers_group={'direct_members': [], 'direct_subgroups': []},
            can_administer_channel_group={'direct_members': [], 'direct_subgroups': [settings.ZULIP_CAPTAINS_GROUP]},
        )
        nf().client.get_stream_id.assert_called_once_with("S0_Team1")
        nf().client.send_message.assert_called_once_with({'type': 'channel', 'to': 'S0_Team1', 'content': 'Welcome to the new season, Team1', 'topic': 'Welcome!'})
        self.assertEqual("1337", get_team("Team 1").slack_channel)

