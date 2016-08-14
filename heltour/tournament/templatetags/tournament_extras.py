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
def resultclass(tie_score, my_score, other_score=None):
    # If other_score is specified, assume the match may be incomplete and only display results that are clinched
    if my_score is None:
        return ''
    elif my_score > tie_score:
        return 'cell-win'
    elif other_score is None and my_score < tie_score or other_score is not None and other_score > tie_score:
        return 'cell-loss'
    elif my_score == tie_score and (other_score is None or other_score == tie_score):
        return 'cell-tie'
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
