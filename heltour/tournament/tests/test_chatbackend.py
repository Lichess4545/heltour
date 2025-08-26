from unittest.mock import ANY, call, patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from heltour.tournament.chatbackend import (
    bold,
    channel_message,
    channellink,
    chatbackend,
    chatbackend_render,
    chatbackend_url,
    create_team_channel,
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
    userlink_ping,
    userlink_silent,
)
from heltour.tournament.slackapi import SlackGroup, SlackUser
from heltour.tournament.tests.testutils import Shush, createCommonLeagueData, get_team


@override_settings(USE_CHATBACKEND="zulip")
class ZulipFormatTestCase(SimpleTestCase):
    def test_bold(self):
        self.assertEqual(bold("some text"), "**some text**")

    def test_channellink(self):
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

    def test_chatbackend_str(self):
        self.assertEqual(chatbackend(), "Zulip")

    def test_chatbackend_render(self):
        self.assertTrue(chatbackend_render())

    def test_chatbackend_url(self):
        self.assertEqual(chatbackend_url(), "https://lichess4545-test.zulipchat.com")

    def test_dm_link(self):
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
            "https://lichess4545-test.zulipchat.com/#narrow/dm/U666,U001,878065-group",
        )

    def test_inlinecode(self):
        self.assertEqual(inlinecode("some text"), "`some text`")

    def test_italic(self):
        self.assertEqual(italic("some text"), "*some text*")

    def test_link(self):
        self.assertEqual(
            link(text="Lichess4545", url="https://lichess4545.com"),
            "[Lichess4545](https://lichess4545.com)",
        )

    def test_ping_mods(self):
        self.assertEqual(ping_mods(), "@*mods4545*")

    def test_userlink_ping(self):
        self.assertEqual(userlink_ping("Tranzoo"), "@**Tranzoo**")

    def test_userlink_silent(self):
        self.assertEqual(userlink_silent("glbert"), "@_**glbert**")

    # TODO: find a good way to make the following tests work without a local import
    #    @patch("zulip.Client")
    #    def test_channel_message(self, client):
    #        client.return_value.register.return_value = {
    #            "result": "success",
    #            "max_topic_length": 100,
    #            "max_message_length": 1000,
    #            "max_stream_name_length": 100,
    #            "max_stream_description_length": 1000,
    #        }
    #        client.return_value.send_message.return_value = {
    #            "result": "success",
    #        }
    #        with Shush():
    #            channel_message(channel="testchannel", text="testing")
    #        client.return_value.send_message.assert_called_with(
    #            {
    #                "type": "channel",
    #                "to": "testchannel",
    #                "content": "testing",
    #                "topic": "(no topic)",
    #            }
    #        )

    #    @patch("zulip.Client")
    #    def test_control_message(self, client):
    #        client.return_value.register.return_value = {
    #            "result": "success",
    #            "max_topic_length": 100,
    #            "max_message_length": 1000,
    #            "max_stream_name_length": 100,
    #            "max_stream_description_length": 1000,
    #        }
    #        client.return_value.send_message.return_value = {
    #            "result": "success",
    #        }
    #        with Shush():
    #            send_control_message(text="testing control messages")
    #        client.return_value.send_message.assert_called_with(
    #            {
    #                "type": "channel",
    #                "to": "msg-forward",
    #                "content": "testing control messages",
    #                "topic": "control",
    #            }
    #        )

    # @patch("zulip.Client")
    # def test_direct_user_message(self, client):
    #    client.return_value.register.return_value = {
    #        "result": "success",
    #        "max_topic_length": 100,
    #        "max_message_length": 1000,
    #        "max_stream_name_length": 100,
    #        "max_stream_description_length": 1000,
    #    }
    #    client.return_value.send_message.return_value = {
    #        "result": "success",
    #    }
    #    with Shush():
    #        direct_user_message(
    #            username="lakinwecker", userid="0001", text="testing direct messages"
    #        )
    #    client.return_value.send_message.assert_called_with(
    #        {
    #            "type": "direct",
    #            "to": [1],
    #            "content": "testing direct messages",
    #        }
    #    )

    # @patch("zulip.Client")
    # def test_multiple_user_message(self, client):
    #    client.return_value.register.return_value = {
    #        "result": "success",
    #        "max_topic_length": 100,
    #        "max_message_length": 1000,
    #        "max_stream_name_length": 100,
    #        "max_stream_description_length": 1000,
    #    }
    #    client.return_value.send_message.return_value = {
    #        "result": "success",
    #    }
    #    with Shush():
    #        multiple_user_message(
    #            usernames=["lakinwecker", "glbert"],
    #            userids=["0001", "0002"],
    #            text="testing direct messages to multiple users",
    #        )
    #    client.return_value.send_message.assert_called_with(
    #        {
    #            "type": "direct",
    #            "to": [1, 2, settings.ZULIP_LISTENING_BOT],
    #            "content": "testing direct messages to multiple users",
    #        }
    #    )

    # @patch("zulip.Client")
    # def test_get_user(self, client):
    #    client.return_value.register.return_value = {
    #        "result": "success",
    #        "max_topic_length": 100,
    #        "max_message_length": 1000,
    #        "max_stream_name_length": 100,
    #        "max_stream_description_length": 1000,
    #    }
    #    client.return_value.get_user_by_id.return_value = {
    #        "result": "success",
    #        "user": {
    #            "user_id": 2,
    #            "timezone": "CET",
    #            "email": "no@fakeimail",
    #            "full_name": "glbert",
    #        },
    #    }
    #    result = get_user(user_id="0002")
    #    client.return_value.get_user_by_id.assert_called_once_with(2)
    #    self.assertEqual(
    #        result,
    #        SlackUser(
    #            id="2",
    #            name_deprecated=ANY,
    #            real_name=ANY,
    #            display_name="glbert",
    #            email="no@fakeimail",
    #            tz_offset=7200.0,
    #        ),
    #    )

    # @patch("zulip.Client")
    # def test_get_user_list(self, client):
    #    client.return_value.register.return_value = {
    #        "result": "success",
    #        "max_topic_length": 100,
    #        "max_message_length": 1000,
    #        "max_stream_name_length": 100,
    #        "max_stream_description_length": 1000,
    #    }
    #    client.return_value.get_users.return_value = {
    #        "result": "success",
    #        "members": [
    #            {
    #                "user_id": 1,
    #                "timezone": "UTC",
    #                "delivery_email": "lakinwecker@example.com",
    #                "full_name": "lakinwecker",
    #            },
    #            {
    #                "user_id": 2,
    #                "timezone": "CET",
    #                "delivery_email": "no@fakeimail",
    #                "full_name": "glbert",
    #            },
    #        ],
    #    }
    #    result = get_user_list()
    #    client.return_value.get_users.assert_called_once_with()
    #    self.assertEqual(
    #        result,
    #        [
    #            SlackUser(
    #                id="1",
    #                name_deprecated=ANY,
    #                real_name=ANY,
    #                display_name="lakinwecker",
    #                email="lakinwecker@example.com",
    #                tz_offset=0.0,
    #            ),
    #            SlackUser(
    #                id="2",
    #                name_deprecated=ANY,
    #                real_name=ANY,
    #                display_name="glbert",
    #                email="no@fakeimail",
    #                tz_offset=7200.0,
    #            ),
    #        ],
    #    )

    # @patch("zulip.Client")
    # def test_invite_user(self, client):
    #    client.return_value.register.return_value = {
    #        "result": "success",
    #        "max_topic_length": 100,
    #        "max_message_length": 1000,
    #        "max_stream_name_length": 100,
    #        "max_stream_description_length": 1000,
    #    }
    #    client.return_value.call_endpoint.return_value = {
    #        "result": "success",
    #    }
    #    with Shush():
    #        invite_user("sgis@glbert.com")
    #    client.return_value.call_endpoint.assert_called_once_with(
    #        url="/invites",
    #        method="POST",
    #        request={
    #            "invitee_emails": "sgis@glbert.com",
    #            "invite_expires_in_minutes": 40320,
    #            "invite_as": 600,
    #            "stream_ids": [],
    #            "include_realm_default_subscriptions": "true",
    #            "notify_referrer_on_join": "false",
    #        },
    #    )


@override_settings(USE_CHATBACKEND="/dev/null")
class DevNullFormatTestCase(SimpleTestCase):
    def test_bold(self):
        self.assertEqual(bold("some text"), "some text")

    def test_channellink(self):
        self.assertEqual(
            channellink(
                channelprefix="#",
                channelid="someid",
                channel="testchannel",
                topic="tests",
            ),
            "",
        )
        self.assertEqual(
            channellink(channelid="someid", channel="testchannel", topic="tests"),
            "",
        )
        self.assertEqual(channellink(channel="testchannel"), "")

    def test_chatbackend_str(self):
        self.assertEqual(chatbackend(), "/dev/null")

    def test_chatbackend_render(self):
        self.assertFalse(chatbackend_render())

    def test_chatbackend_url(self):
        self.assertEqual(chatbackend_url(), "")

    def test_dm_link(self):
        self.assertEqual(
            dm_link(
                usernames=["glbert", "lakinwecker"],
                userids=["U666", "U001"],
                add_bot=False,
            ),
            "",
        )
        self.assertEqual(
            dm_link(
                usernames=["glbert", "lakinwecker"],
                userids=["U666", "U001"],
                add_bot=True,
            ),
            "",
        )

    def test_inlinecode(self):
        self.assertEqual(inlinecode("some text"), "some text")

    def test_link(self):
        self.assertEqual(
            link(text="Lichess4545", url="https://lichess4545.com"),
            "https://lichess4545.com",
        )

    def test_ping_mods(self):
        self.assertEqual(ping_mods(), "")

    def test_userlink_ping(self):
        self.assertEqual(userlink_ping("Tranzoo"), "Tranzoo")

    def test_userlink_silent(self):
        self.assertEqual(userlink_silent("lakinwecker"), "lakinwecker")

    # in the following functions we expect nothing to happen,
    # so nothing to assert
    def test_empty_functions(self):
        channel_message(channel="testchannel", text="testing")
        send_control_message(text="testing control messages")
        direct_user_message(
            username="lakinwecker", userid="0001", text="testing direct messages"
        )
        multiple_user_message(
            usernames=["lakinwecker", "chesster"],
            userids=["0001", "0002"],
            text="testing direct messages to multiple users",
        )
        invite_user("sgis@glbert.com")

    def test_get_user(self):
        result = get_user(user_id="0002")
        self.assertEqual(
            result,
            SlackUser(
                id="",
                display_name="",
                email="",
                tz_offset=0,
                real_name="",
                name_deprecated="",
            ),
        )

    def test_get_user_list(self):
        result = get_user_list()
        self.assertEqual(result, [])


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
            "https://lichess4545.slack.com/messages/@glbert,@lakinwecker",
        )
        self.assertEqual(
            dm_link(
                usernames=["glbert", "lakinwecker"],
                userids=["U666", "U001"],
                add_bot=True,
            ),
            "https://lichess4545.slack.com/messages/@glbert,@lakinwecker,@chesster",
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

    @patch("heltour.tournament.slackapi._get_slack_webhook", return_value="someurl")
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

    @patch("heltour.tournament.slackapi._get_slack_webhook", return_value="someurl")
    @patch("requests.post")
    def test_control_message(self, post, webhook):
        post.return_value.text = "ok"
        with Shush():
            send_control_message(text="testing control messages")
        post.assert_called_with("someurl", json={"text": "testing control messages"})

    @patch("heltour.tournament.slackapi._get_slack_webhook", return_value="someurl")
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

    @patch("heltour.tournament.slackapi._get_slack_webhook", return_value="someurl")
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

    @patch("heltour.tournament.slackapi._get_slack_token", return_value="faketoken")
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

    @patch("heltour.tournament.slackapi._get_slack_token", return_value="faketoken")
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

    @patch("heltour.tournament.slackapi._get_slack_token", return_value="faketoken")
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

    # TODO: find a good way to make the following test work without local imports
    # @override_settings(USE_CHATBACKEND="zulip")
    # @patch("reversion.create_revision")
    # @patch("reversion.set_comment")
    # @patch("zulip.Client")
    # def test_zulip_create_team_channels(
    #    self,
    #    client,
    #    r_comment,
    #    r_revision,
    # ):
    #    zulip_success = {
    #        "result": "success",
    #        "stream_id": 125,
    #    }

    #    client.return_value.register.return_value = {
    #        "result": "success",
    #        "max_topic_length": 100,
    #        "max_message_length": 1000,
    #        "max_stream_name_length": 100,
    #        "max_stream_description_length": 1000,
    #    }
    #    client.return_value.add_subscriptions.return_value = zulip_success
    #    client.return_value.send_message.return_value = zulip_success
    #    client.return_value.get_stream_id.return_value = zulip_success
    #    with Shush():
    #        create_team_channel(
    #            team=self.t,
    #            channel_name="channelname",
    #            user_ids=["1", "2"],
    #            topic="channel topic",
    #            intro_message="welcome to your channel",
    #        )
    #    userids = [1, 2, settings.ZULIP_LISTENING_BOT, settings.ZULIP_HELTOUR_BOT]
    #    client.return_value.add_subscriptions.assert_called_once_with(
    #        streams=[
    #            {
    #                "name": "channelname",
    #                "description": "channel topic",
    #                "invite_only": True,
    #                "history_public_to_subscribers": False,
    #            }
    #        ],
    #        principals=userids,
    #        invite_only=True,
    #        history_public_to_subscribers=False,
    #        can_add_subscribers_group={
    #            "direct_members": userids,
    #            "direct_subgroups": [],
    #        },
    #        can_remove_subscribers_group={
    #            "direct_members": userids,
    #            "direct_subgroups": [],
    #        },
    #        can_administer_channel_group={
    #            "direct_members": userids,
    #            "direct_subgroups": [],
    #        },
    #    )
    #    client.return_value.send_message.assert_called_once_with(
    #        {
    #            "type": "channel",
    #            "to": 125,
    #            "content": "welcome to your channel",
    #            "topic": "Welcome!",
    #        }
    #    )
    #    client.return_value.get_stream_id.assert_called_once_with("channelname")
    #    self.assertEqual("125", get_team("Team 1").slack_channel)

    @override_settings(USE_CHATBACKEND="slack")
    @patch(
        "heltour.tournament.slackapi.create_group",
        return_value=SlackGroup("id1", "channelname"),
    )
    @patch("heltour.tournament.slackapi.invite_to_group")
    @patch("heltour.tournament.slackapi.set_group_topic")
    @patch("heltour.tournament.slackapi.leave_group")
    @patch("heltour.tournament.slackapi.send_message")
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
        create_team_channel(
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

    @override_settings(USE_CHATBACKEND="/dev/null")
    def test_devnull_create_team_channels(self):
        create_team_channel(
            team=self.t,
            channel_name="channelname",
            user_ids=["1", "2"],
            topic="channel topic",
            intro_message="welcome to your channel",
        )
        # we do not expect anthing to happen.
