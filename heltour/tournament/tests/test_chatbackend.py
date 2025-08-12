from unittest.mock import patch
from django.test import TestCase, SimpleTestCase, override_settings

from heltour.tournament.tests.testutils import createCommonLeagueData
from heltour.tournament.chatbackend import (
    bold,
    channellink,
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
                channelprefix="#", channelid="someid", channel="testchannel", topic="tests"
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
            dm_link(usernames=["glbert", "lakinwecker"], userids=["U666", "U001"], add_bot=False),
            "https://lichess4545-test.zulipchat.com/#narrow/dm/U666,U001-group",
        )
        self.assertEqual(
            dm_link(usernames=["glbert", "lakinwecker"], userids=["U666", "U001"], add_bot=True),
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


@override_settings(USE_CHATBACKEND="slack")
class SlackFormatTestCase(SimpleTestCase):
    def test_bold(self):
        self.assertEqual(bold("some text"), "*some text*")

    def test_channellink(self):
        self.assertEqual(
            channellink(
                channelprefix="#", channelid="someid", channel="testchannel", topic="tests"
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
            dm_link(usernames=["glbert", "lakinwecker"], userids=["U666", "U001"], add_bot=False),
            "https://lichess4545.slack.com/messages/@glbert,@lakinwecker",
        )
        self.assertEqual(
            dm_link(usernames=["glbert", "lakinwecker"], userids=["U666", "U001"], add_bot=True),
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
