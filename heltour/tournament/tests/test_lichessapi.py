from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from heltour.tournament.lichessapi import (
    send_mail,
    update_or_create_broadcast,
    update_or_create_broadcast_round,
)


class NoShowTestCase(SimpleTestCase):
    @patch(
        "heltour.tournament.lichessapi._apicall_with_error_parsing", return_value="{}"
    )
    def test_create_broadcast(self, apicall):
        update_or_create_broadcast(name="new broadcast", nrounds=1)
        apicall.assert_called_once_with(
            url=(
                "http://localhost:8880/lichessapi/broadcast/new?priority=0&"
                "max_retries=2&content_type=application/x-www-form-urlencoded&"
                "format=application/json"
            ),
            timeout=30,
            post_data=(
                "name=new broadcast&info.format=1-round Team Swiss&"
                "info.location=lichess.org&info.tc=45+45&teamTable=true"
            ),
        )

    @patch(
        "heltour.tournament.lichessapi._apicall_with_error_parsing", return_value="{}"
    )
    def test_update_broadcast(self, apicall):
        update_or_create_broadcast(
            broadcast_id="fakeid", name="new broadcast", nrounds=1
        )
        apicall.assert_called_once_with(
            url=(
                "http://localhost:8880/lichessapi/broadcast/fakeid/edit?priority=0&"
                "max_retries=2&content_type=application/x-www-form-urlencoded&"
                "format=application/json"
            ),
            timeout=30,
            post_data=(
                "name=new broadcast&info.format=1-round Team Swiss&"
                "info.location=lichess.org&info.tc=45+45&teamTable=true"
            ),
        )

    def test_create_broadcast_round_valueerrors(self):
        with self.assertRaises(ValueError):
            update_or_create_broadcast_round()
        with self.assertRaises(ValueError):
            update_or_create_broadcast_round(
                broadcast_id="fakeid", broadcast_round_id="fake_round_id"
            )
        with self.assertRaises(ValueError):
            update_or_create_broadcast_round(broadcast_id="fakeid", status="incorrect")

    @patch(
        "heltour.tournament.lichessapi._apicall_with_error_parsing", return_value="{}"
    )
    def test_create_broadcast_round(self, apicall):
        update_or_create_broadcast_round(
            broadcast_id="fakeid",
            game_links=["gamelink1", "gamelink2"],
        )
        apicall.assert_called_once_with(
            url=(
                "http://localhost:8880/lichessapi/broadcast/fakeid/new?priority=0&"
                "max_retries=2&content_type=application/x-www-form-urlencoded&"
                "format=application/json"
            ),
            timeout=30,
            post_data="name=Round 0&syncIds=gamelink1 gamelink2&status=started",
        )

    @patch(
        "heltour.tournament.lichessapi._apicall_with_error_parsing", return_value="{}"
    )
    def test_update_broadcast_round(self, apicall):
        update_or_create_broadcast_round(
            broadcast_round_id="fakeroundid",
            game_links=["gamelink1", "gamelink2"],
        )
        apicall.assert_called_once_with(
            url=(
                "http://localhost:8880/lichessapi/broadcast/round/fakeroundid/edit?priority=0&"
                "max_retries=2&content_type=application/x-www-form-urlencoded&"
                "format=application/json"
            ),
            timeout=30,
            post_data="name=Round 0&syncIds=gamelink1 gamelink2&status=started",
        )

    @override_settings(API_WORKER_HOST="testhost")
    @patch(
        "heltour.tournament.lichessapi._apicall_with_error_parsing",
        return_value='{"ok": true}',
        autospec=True,
    )
    @patch("heltour.tournament.lichessapi.logger.error", autospec=True)
    def test_send_mail_ok(self, logger, apicall):
        send_mail(
            lichess_username="thomas",
            subject="you're late to your game",
            text="please join it",
        )
        apicall.assert_called_once_with(
            url="testhost/lichessapi/inbox/thomas?priority=0&max_retries=5",
            timeout=1800,
            post_data={"text": "you're late to your game\nplease join it"},
        )
        logger.assert_not_called()

    @override_settings(API_WORKER_HOST="testhost")
    @patch(
        "heltour.tournament.lichessapi._apicall_with_error_parsing",
        return_value='{"error": "this request is invalid because ..."}',
        autospec=True,
    )
    @patch("heltour.tournament.lichessapi.logger.error", autospec=True)
    def test_send_mail_fail(self, logger, apicall):
        send_mail(
            lichess_username="ivan",
            subject="prison",
            text="don't murder people"
        )
        apicall.assert_called_once_with(
            url="testhost/lichessapi/inbox/ivan?priority=0&max_retries=5",
            timeout=1800,
            post_data={"text": "prison\ndon't murder people"},
        )
        logger.assert_called_once_with(
            "Error sending mail: {'error': 'this request is invalid because ...'}"
        )
