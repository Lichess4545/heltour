from django.test import Client, TestCase

from heltour.tournament.models import (
    ApiKey,
    League,
    Player,
    Season,
    Team,
    TeamMember,
    TeamScore,
)


def createCommonAPIData():
    team_count = 4
    round_count = 3
    board_count = 2

    league = League.objects.create(
        name="Team League", tag="team", competitor_type="team"
    )
    season = Season.objects.create(
        league=league,
        name="Team Season",
        tag="team",
        rounds=round_count,
        boards=board_count,
    )
    league2 = League.objects.create(name="Lone League", tag="lone")
    Season.objects.create(
        league=league2,
        name="Lone Season",
        tag="lone",
        rounds=round_count,
        boards=board_count,
    )

    player_num = 1
    for n in range(1, team_count + 1):
        team = Team.objects.create(season=season, number=n, name="Team %s" % n)
        TeamScore.objects.create(team=team)
        for b in range(1, board_count + 1):
            player = Player.objects.create(lichess_username="Player%d" % player_num)
            player_num += 1
            TeamMember.objects.create(team=team, player=player, board_number=b)


class _ApiTestsBase(TestCase):
    def setUp(self):
        self.api_key = ApiKey.objects.create(name="test_key")
        self.client = Client(
            HTTP_AUTHORIZATION="Token {}".format(self.api_key.secret_token)
        )
