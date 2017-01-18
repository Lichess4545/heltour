from django import template
from django.core.urlresolvers import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone
from datetime import timedelta

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

@register.simple_tag(takes_context=True)
def rating(context, player):
    return player.rating_for(context['league']) or '?'

@register.simple_tag(takes_context=True)
def player_rating(context, obj_with_player_rating):
    return obj_with_player_rating.player_rating_display(context['league']) or '?'

@register.simple_tag(takes_context=True)
def white_rating(context, pairing):
    return pairing.white_rating_display(context['league']) or '?'

@register.simple_tag(takes_context=True)
def black_rating(context, pairing):
    return pairing.black_rating_display(context['league']) or '?'

@register.simple_tag(takes_context=True)
def seed_rating(context, season_player):
    return season_player.seed_rating_display(context['league']) or '?'

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
def formatscore(score):
    if str(score) == '0.5':
        return u'\u00BD'
    return str(score).replace('.0', '').replace('.5', u'\u00BD')

@register.filter
def forfeitchar(score):
    if score == 1:
        return 'X'
    elif score == 0.5:
        return 'Z'
    elif score == 0:
        return 'F'
    return ''

@register.filter
def date_or_q(datetime):
    if datetime is None:
        return '?'
    return datetime.date()

@register.filter
def label_right(input_element):
    return mark_safe('%s<label for="id_%s">%s</label></td>' % (input_element, input_element.name, input_element.label))

@register.filter
def percent(number, decimal_digits=0):
    return ('{:.' + str(decimal_digits) + '%}').format(number)

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def time_from_now(datetime):
    delta = datetime - timezone.now()
    if delta < timedelta(0):
        return '0 hours'
    if delta.days > 0:
        days = delta.days
        if delta.seconds > 3600 * 12:
            days += 1
        if days == 1:
            return '1 day'
        else:
            return '%d days' % days
    elif delta.seconds >= 3600:
        hours = delta.seconds / 3600
        if delta.seconds > 3600 / 2:
            hours += 1
        if hours == 1:
            return '1 hour'
        else:
            return '%d hours' % hours
    else:
        minutes = delta.seconds / 60
        if minutes == 1:
            return '1 minutes'
        else:
            return '%d minutes' % hours
