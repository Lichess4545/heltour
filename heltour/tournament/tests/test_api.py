import json

from django.test import TestCase, Client
from django.utils import timezone

from heltour.tournament.models import *


def createCommonAPIData():
    team_count = 4
    round_count = 3
    board_count = 2

    league = League.objects.create(name='Team League', tag='team', competitor_type='team')
    season = Season.objects.create(league=league, name='Team Season', tag='team',
                                   rounds=round_count, boards=board_count)
    league2 = League.objects.create(name='Lone League', tag='lone')
    season2 = Season.objects.create(league=league2, name='Lone Season', tag='lone',
                                    rounds=round_count, boards=board_count)

    player_num = 1
    for n in range(1, team_count + 1):
        team = Team.objects.create(season=season, number=n, name='Team %s' % n)
        TeamScore.objects.create(team=team)
        for b in range(1, board_count + 1):
            player = Player.objects.create(lichess_username='Player%d' % player_num)
            player_num += 1
            TeamMember.objects.create(team=team, player=player, board_number=b)


class _ApiTestsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.api_key = ApiKey.objects.create(name='test_key')
        cls.client = Client(HTTP_AUTHORIZATION="Token {}".format(cls.api_key.secret_token))


class PlayerContactPresenceEventTests(TestCase):
    """The chat-msg endpoint should append a single first_chat_message
    PlayerPresenceEvent the first time a player chats, and skip on subsequent
    messages (so the log doesn't duplicate per chat line)."""

    @classmethod
    def setUpTestData(cls):
        cls.api_key = ApiKey.objects.create(name="contact_key")
        cls.league = League.objects.create(
            name="Lone League", tag="lone", competitor_type="individual"
        )
        cls.season = Season.objects.create(
            league=cls.league, name="S1", tag="s1", rounds=1, boards=1,
            is_active=True,
        )
        cls.round_ = Round.objects.get(season=cls.season, number=1)
        cls.round_.publish_pairings = True
        cls.round_.start_date = timezone.now() - timezone.timedelta(hours=1)
        cls.round_.end_date = timezone.now() + timezone.timedelta(days=2)
        cls.round_.is_completed = False
        cls.round_.save()
        cls.alice = Player.objects.create(lichess_username="Alice")
        cls.bob = Player.objects.create(lichess_username="Bob")
        cls.pairing = LonePlayerPairing.objects.create(
            round=cls.round_, white=cls.alice, black=cls.bob, pairing_order=1,
        )

    def setUp(self):
        self.client = Client(
            HTTP_AUTHORIZATION="Token {}".format(self.api_key.secret_token)
        )

    def test_first_message_emits_event(self):
        resp = self.client.post(
            "/api/player_contact/", {"sender": "Alice", "recip": "Bob"}
        )
        self.assertEqual(resp.status_code, 200)
        events = PlayerPresenceEvent.objects.filter(
            player=self.alice, event_type="first_chat_message"
        )
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().pairing_id, self.pairing.pk)
        self.assertEqual(events.first().round_id, self.round_.pk)

    def test_subsequent_messages_do_not_emit_event(self):
        for _ in range(3):
            self.client.post(
                "/api/player_contact/", {"sender": "Alice", "recip": "Bob"}
            )
        self.assertEqual(
            PlayerPresenceEvent.objects.filter(
                player=self.alice, event_type="first_chat_message"
            ).count(),
            1,
        )

    def test_each_player_logged_independently(self):
        self.client.post(
            "/api/player_contact/", {"sender": "Alice", "recip": "Bob"}
        )
        self.client.post(
            "/api/player_contact/", {"sender": "Bob", "recip": "Alice"}
        )
        self.assertEqual(
            PlayerPresenceEvent.objects.filter(
                event_type="first_chat_message"
            ).count(),
            2,
        )
