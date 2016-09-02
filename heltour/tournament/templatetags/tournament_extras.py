from django import template
from django.core.urlresolvers import reverse

register = template.Library()

@register.simple_tag
def leagueurl(name, league_tag=None, season_tag=None, *args, **kwargs):
    if season_tag is not None and season_tag != '':
        name = "by_season:" + name
        args = [season_tag] + list(args)
    if league_tag is not None and league_tag != '':
        name = "by_league:" + name
        args = [league_tag] + list(args)
    return reverse(name, args=args, kwargs=kwargs)

@register.simple_tag
def resultclass(score, opp_score):
    if score is None or score == '' or opp_score is None or opp_score == '':
        return ''
    elif score > opp_score:
        return 'cell-win'
    elif score < opp_score:
        return 'cell-loss'
    else:
        return 'cell-tie'

@register.simple_tag
def highlightclass(highlights, player):
    for name, players in highlights:
        if player in players:
            return 'player-%s' % name
    return ''

@register.filter
def format_result(result):
    if result is None:
        return ''
    return result.replace('1/2', u'\u00BD')

@register.filter
def date_or_q(datetime):
    if datetime is None:
        return '?'
    return datetime.date()

@register.filter
def percent(number, decimal_digits=0):
    return ('{:.' + str(decimal_digits) + '%}').format(number)
