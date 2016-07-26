from django import template
from django.core.urlresolvers import reverse

register = template.Library()

@register.simple_tag
def leagueurl(name, league_id=None, season_id=None, *args, **kwargs):
    if season_id is not None and season_id != '':
        name = "by_season:" + name
        args = [season_id] + list(args)
    if league_id is not None and league_id != '':
        name = "by_league:" + name
        args = [league_id] + list(args)
    return reverse(name, args=args, kwargs=kwargs)