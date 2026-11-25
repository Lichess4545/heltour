from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from heltour.api_worker import views as api_worker_views
from heltour.tournament import slackapi


class SlackSecretsTestCase(SimpleTestCase):
    @override_settings(SLACK_API_TOKEN="xoxb-token")
    def test_uses_the_api_token(self):
        sc = slackapi.SlackClient(api_token="invalid")
        self.assertEqual(sc._get_slack_token(), "xoxb-token")

    @override_settings(SLACK_API_TOKEN="")
    def test_refuses_a_missing_api_token(self):

        sc = slackapi.SlackClient(api_token="invalid")
        with self.assertRaisesMessage(ImproperlyConfigured, "SLACK_API_TOKEN"):
            sc._get_slack_token()

    @override_settings(SLACK_CHANNEL_BUILDER_TOKEN="xoxp-token")
    def test_uses_the_channel_builder_token(self):

        sc = slackapi.SlackClient(api_token="invalid")
        self.assertEqual(sc._get_slack_channel_builder_token(), "xoxp-token")

    @override_settings(SLACK_CHANNEL_BUILDER_TOKEN="")
    def test_refuses_a_missing_channel_builder_token(self):

        sc = slackapi.SlackClient(api_token="invalid")
        with self.assertRaisesMessage(ImproperlyConfigured, "SLACK_CHANNEL_BUILDER_TOKEN"):
            sc._get_slack_channel_builder_token()

    @override_settings(SLACK_WEBHOOK_URL="https://hooks.slack.com/services/x")
    def test_uses_the_webhook_url(self):
        sc = slackapi.SlackClient(api_token="invalid")
        self.assertEqual(sc._get_slack_webhook(), "https://hooks.slack.com/services/x")

    @override_settings(SLACK_WEBHOOK_URL="")
    @patch("heltour.tournament.slackapi.requests.post")
    def test_skips_messages_without_a_webhook_url(self, post):
        sc = slackapi.SlackClient(api_token="invalid")
        with self.assertLogs("heltour.tournament.slackapi", level="ERROR"):
            sc.channel_message(channel="#general", text="hello")
        post.assert_not_called()


class LichessSecretsTestCase(SimpleTestCase):
    @override_settings(LICHESS_API_TOKEN="lip_token")
    def test_uses_the_api_token(self):
        self.assertEqual(api_worker_views._get_lichess_api_token(), "lip_token")

    @override_settings(LICHESS_API_TOKEN="")
    def test_calls_anonymously_without_an_api_token(self):
        self.assertIsNone(api_worker_views._get_lichess_api_token())
