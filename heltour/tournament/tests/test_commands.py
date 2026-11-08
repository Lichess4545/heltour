import contextlib
import io
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django_comments.models import Comment

from heltour.tournament.models import Player, Registration
from heltour.tournament.tests.testutils import create_reg, createCommonLeagueData, get_season


def confirm(prompt):
    return prompt.split("Type: ")[1].split(" ")[0]


def mistype(prompt):
    return "nope"


class RemoveEmailsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.player = Player.objects.create(lichess_username="alice", email="alice@example.com")
        registration = create_reg(get_season("team"), "alice")
        Registration.objects.filter(pk=registration.pk).update(email="alice@example.com")
        User.objects.create(username="alice", email="alice@example.com")
        Comment.objects.create(
            content_object=cls.player,
            site_id=settings.SITE_ID,
            user_email="alice@example.com",
            comment="hello",
        )

    def _remove_emails(self, answer):
        with patch("builtins.input", side_effect=answer), \
                contextlib.redirect_stdout(io.StringIO()):
            call_command("removeemails")

    def _stored_emails(self):
        return {
            *Player.objects.values_list("email", flat=True),
            *Player.objects.values_list("normalized_email", flat=True),
            *Registration.objects.values_list("email", flat=True),
            *User.objects.values_list("email", flat=True),
            *Comment.objects.values_list("user_email", flat=True),
        } - {""}

    def test_removes_every_stored_email(self):
        self._remove_emails(confirm)
        self.assertEqual(self._stored_emails(), set())

    def test_keeps_the_emails_when_the_confirmation_is_mistyped(self):
        self._remove_emails(mistype)
        self.assertEqual(self._stored_emails(), {"alice@example.com"})
