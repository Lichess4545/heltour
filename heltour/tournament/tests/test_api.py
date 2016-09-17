import json

from django.test import TestCase, Client
from heltour.tournament.models import *
from django.core.urlresolvers import reverse

def createCommonAPIData():
    team_count = 4
    round_count = 3
    board_count = 2

    league = League.objects.create(name='Team League', tag='team', competitor_type='team')
    season = Season.objects.create(league=league, name='Team Season', tag='team', rounds=round_count, boards=board_count)
    league2 = League.objects.create(name='Lone League', tag='lone')
    season2 = Season.objects.create(league=league2, name='Lone Season', tag='lone', rounds=round_count, boards=board_count)

    player_num = 1
    for n in range(1, team_count + 1):
        team = Team.objects.create(season=season, number=n, name='Team %s' % n)
        TeamScore.objects.create(team=team)
        for b in range(1, board_count + 1):
            player = Player.objects.create(lichess_username='Player%d' % player_num)
            player_num += 1
            TeamMember.objects.create(team=team, player=player, board_number=b)

class _ApiTestsBase(TestCase):
    def setUp(self):
        self.api_key = ApiKey.objects.create(name='test_key')
        self.client = Client(HTTP_AUTHORIZATION="Token {}".format(self.api_key.secret_token))


class TestPlayerJoinedSlack(_ApiTestsBase):
    def setUp(self):
        super(TestPlayerJoinedSlack, self).setUp()
        createCommonAPIData()

    def test_template(self):
        player = Player.objects.get(lichess_username='Player1')
        self.assertFalse(player.in_slack_group)
        url = reverse('api:player_joined_slack')

        response = self.client.post(url, data={})
        self.assertEqual(400, response.status_code)

        data = {'name': 'ThisDoesntExist'}
        response = self.client.post(url, data=data)
        self.assertEqual(0, response.json()['updated'])
        self.assertEqual('not_found', response.json()['error'])

        data['name'] = 'player1'
        response = self.client.post(url, data=data)
        self.assertEqual(1, response.json()['updated'])

        player = Player.objects.get(lichess_username='Player1')
        self.assertTrue(player.in_slack_group)


