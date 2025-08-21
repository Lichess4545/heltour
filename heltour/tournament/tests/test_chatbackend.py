from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from heltour.tournament.chatbackend import (
    bold,
    channel_message,
    channellink,
    chatbackend,
    chatbackend_url,
    direct_user_message,
    dm_link,
    inlinecode,
    italic,
    link,
    multiple_user_message,
    ping_mods,
    send_control_message,
    userlink_ping,
    userlink_silent,
)
from heltour.tournament.tests.testutils import Shush


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

    #@patch("zulip.Client")
    #def test_multiple_user_message(self, client):
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
