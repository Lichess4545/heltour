from heltour.tournament.models import *
from django.core.urlresolvers import reverse


def set_rating(player, rating, rating_type='classical'):
    player.profile = {'perfs': {rating_type: {'rating': rating}}}


def create_reg(season, name):
    return Registration.objects.create(season=season, status='pending', lichess_username=name,
                                       slack_username=name,
                                       email='a@test.com', classical_rating=1500,
                                       peak_classical_rating=1600,
                                       has_played_20_games=True, already_in_slack_group=True,
                                       previous_season_alternate='new',
                                       can_commit=True, agreed_to_rules=True,
                                       alternate_preference='full_time')


def league_tag(league_type):
    return '%sleague' % league_type


def season_tag(league_type):
    return '%sseason' % league_type


def league_url(league_type, page_name):
    return reverse('by_league:%s' % page_name, args=[league_tag(league_type)])


def season_url(league_type, page_name):
    return reverse('by_league:by_season:%s' % page_name,
                   args=[league_tag(league_type), season_tag(league_type)])


def get_season(league_type):
    return Season.objects.get(tag='%sseason' % league_type)


def createCommonLeagueData():
    team_count = 4
    round_count = 3
    board_count = 2

    league = League.objects.create(name='Team League', tag=league_tag('team'),
                                   competitor_type='team',
                                   rating_type='classical')
    season = Season.objects.create(league=league, name='Test Season', tag=season_tag('team'),
                                   rounds=round_count, boards=board_count)
    league2 = League.objects.create(name='Lone League', tag=league_tag('lone'),
                                    competitor_type='lone',
                                    rating_type='classical')
    season2 = Season.objects.create(league=league2, name='Test Season', tag=season_tag('lone'),
                                    rounds=round_count)

    player_num = 1
    for n in range(1, team_count + 1):
        team = Team.objects.create(season=season, number=n, name='Team %s' % n)
        TeamScore.objects.create(team=team)
        for b in range(1, board_count + 1):
            player = Player.objects.create(lichess_username='Player%d' % player_num)
            sp = SeasonPlayer.objects.create(season=season2, player=player)
            LonePlayerScore.objects.create(season_player=sp)
            player_num += 1
            TeamMember.objects.create(team=team, player=player, board_number=b)
