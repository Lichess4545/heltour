from django import template
from django.core.urlresolvers import reverse

register = template.Library()

@register.simple_tag
def leagueurl(name, league_tag=None, season_id=None, *args, **kwargs):
    if season_id is not None and season_id != '':
        name = "by_season:" + name
        args = [season_id] + list(args)
    if league_tag is not None and league_tag != '':
        name = "by_league:" + name
        args = [league_tag] + list(args)
    return reverse(name, args=args, kwargs=kwargs)

@register.filter
def format_result(result):
    if result is None:
        return ''
    if result == '1/2-1/2':
        return u'\u00BD-\u00BD'
    return result
