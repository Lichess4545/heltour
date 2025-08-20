from unittest.mock import patch
from django.test import SimpleTestCase, override_settings

from heltour.tournament.tests.testutils import Shush
from heltour.tournament.chatbackend import (
    bold,
    channellink,
    channel_message,
    chatbackend,
    chatbackend_url,
    dm_link,
    inlinecode,
    italic,
    link,
    ping_mods,
    userlink_ping,
    userlink_silent,
)


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
        post.assert_called_with('someurl', json={'text': 'forward to testchannel', 'attachments': [{'text': 'testing'}]})
