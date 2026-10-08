from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase

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
                f"{settings.API_WORKER_HOST}/lichessapi/broadcast/new?priority=0&"
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
                f"{settings.API_WORKER_HOST}/lichessapi/broadcast/fakeid/edit?priority=0&"
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
                f"{settings.API_WORKER_HOST}/lichessapi/broadcast/fakeid/new?priority=0&"
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
                f"{settings.API_WORKER_HOST}/lichessapi/broadcast/round/fakeroundid/edit?priority=0&"
                "max_retries=2&content_type=application/x-www-form-urlencoded&"
                "format=application/json"
            ),
            timeout=30,
            post_data="name=Round 0&syncIds=gamelink1 gamelink2&status=started",
        )


class SendMailTestCase(SimpleTestCase):
    def _send(self, response):
        with patch(
            "heltour.tournament.lichessapi._apicall_with_error_parsing",
            return_value=response,
        ):
            send_mail("someone", "subject", "text")

    def test_ok_json_is_success(self):
        with self.assertNoLogs("heltour.tournament.lichessapi", level="ERROR"):
            self._send('{"ok":true}')

    def test_plain_ok_is_success(self):
        with self.assertNoLogs("heltour.tournament.lichessapi", level="ERROR"):
            self._send("ok")

    def test_error_json_is_logged(self):
        with self.assertLogs("heltour.tournament.lichessapi", level="ERROR"):
            self._send('{"error":"Cannot send a message to this user"}')

    def test_unexpected_text_is_logged(self):
        with self.assertLogs("heltour.tournament.lichessapi", level="ERROR"):
            self._send("nope")
