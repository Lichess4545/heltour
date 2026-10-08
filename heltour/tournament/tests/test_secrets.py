from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from heltour.api_worker import views as api_worker_views
from heltour.tournament import slackapi, spreadsheet


class SlackSecretsTestCase(SimpleTestCase):
    @override_settings(SLACK_API_TOKEN="xoxb-token")
    def test_uses_the_api_token(self):
        self.assertEqual(slackapi._get_slack_token(), "xoxb-token")

    @override_settings(SLACK_API_TOKEN="")
    def test_refuses_a_missing_api_token(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "SLACK_API_TOKEN"):
            slackapi._get_slack_token()

    @override_settings(SLACK_CHANNEL_BUILDER_TOKEN="xoxp-token")
    def test_uses_the_channel_builder_token(self):
        self.assertEqual(slackapi._get_slack_channel_builder_token(), "xoxp-token")

    @override_settings(SLACK_CHANNEL_BUILDER_TOKEN="")
    def test_refuses_a_missing_channel_builder_token(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "SLACK_CHANNEL_BUILDER_TOKEN"):
            slackapi._get_slack_channel_builder_token()

    @override_settings(SLACK_WEBHOOK_URL="https://hooks.slack.com/services/x")
    def test_uses_the_webhook_url(self):
        self.assertEqual(slackapi._get_slack_webhook(), "https://hooks.slack.com/services/x")

    @override_settings(SLACK_WEBHOOK_URL="")
    @patch("heltour.tournament.slackapi.requests.post")
    def test_skips_messages_without_a_webhook_url(self, post):
        slackapi.send_message("#general", "hello")
        post.assert_not_called()


class LichessSecretsTestCase(SimpleTestCase):
    @override_settings(LICHESS_API_TOKEN="lip_token")
    def test_uses_the_api_token(self):
        self.assertEqual(api_worker_views._get_lichess_api_token(), "lip_token")

    @override_settings(LICHESS_API_TOKEN="")
    def test_calls_anonymously_without_an_api_token(self):
        self.assertIsNone(api_worker_views._get_lichess_api_token())


class GoogleSecretsTestCase(SimpleTestCase):
    @override_settings(GOOGLE_SERVICE_ACCOUNT_KEY='{"type": "service_account"}')
    @patch("heltour.tournament.spreadsheet.gspread.authorize")
    @patch("heltour.tournament.spreadsheet.ServiceAccountCredentials.from_json_keyfile_dict")
    def test_parses_the_service_account_key(self, from_json_keyfile_dict, authorize):
        spreadsheet._open_doc("https://docs.google.com/spreadsheets/d/x")
        from_json_keyfile_dict.assert_called_once_with(
            {"type": "service_account"}, ["https://spreadsheets.google.com/feeds"]
        )

    @override_settings(GOOGLE_SERVICE_ACCOUNT_KEY="")
    def test_refuses_a_missing_service_account_key(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "GOOGLE_SERVICE_ACCOUNT_KEY"):
            spreadsheet._open_doc("https://docs.google.com/spreadsheets/d/x")
