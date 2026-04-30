from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone, formats
from datetime import timedelta
from heltour.tournament.models import Registration, format_score

register = template.Library()


@register.simple_tag(takes_context=True)
def player_display_name(context, player):
    league = context.get('league')
    if league and league.show_fide_names:
        fide_name = (player.fide_profile or {}).get('name', '')
        if fide_name:
            return f'{fide_name} ({player.lichess_username})'
    return player.lichess_username


_GENDER_BADGE_BG = {
    "male": "#2c5e8e",
    "female": "#7ea3c8",
}


@register.simple_tag
def gender_badge(player):
    """Render a colored 1-letter gender badge for a player. Returns empty
    safe-string when the player has no gender set."""
    gender = getattr(player, "gender", "")
    if not gender:
        return ""
    bg = _GENDER_BADGE_BG.get(gender, "#777")
    title = player.get_gender_display()
    letter = gender[:1].upper()
    return mark_safe(
        f'<span class="gender-badge" style="background-color: {bg};" '
        f'title="{title}">{letter}</span>'
    )


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
def white_team_rating(context, pairing):
    return pairing.white_team_rating(context['league']) or '?'


@register.simple_tag(takes_context=True)
def black_team_rating(context, pairing):
    return pairing.black_team_rating(context['league']) or '?'


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
    return format_score(score)


@register.filter
def date_or_q(datetime, fmt=None):
    if datetime is None:
        return '?'
    if fmt is not None:
        return datetime.strftime(fmt)
    return datetime.date()


@register.filter
def label_right(input_element):
    return mark_safe('%s<label for="id_%s">%s</label></td>' % (
        input_element, input_element.name, input_element.label))


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
            return '1 minute'
        else:
            return '%d minutes' % minutes


@register.filter
def date_el(datetime, arg=None):
    if not datetime:
        return ''
    return mark_safe('<time datetime="%s">%s</time>' % (
        datetime.isoformat(), formats.date_format(datetime, arg)))

@register.filter
def mean(lst):
    if len(lst) == 0:
        return ''
    return sum(lst) / len(lst)


@register.filter
def median(lst):
    c = len(lst)
    if c == 0:
        return ''
    if c % 2 == 0:
        return (lst[c // 2 - 1] + lst[c // 2]) / 2
    return lst[int(c // 2)]


@register.filter
def maximum(lst):
    if len(lst) == 0:
        return ''
    return max(lst)


@register.filter
def minimum(lst):
    if len(lst) == 0:
        return ''
    return min(lst)


@register.filter
def can_register(user, season):
    return Registration.can_register(user, season)


@register.filter
def is_registered(user, season):
    return Registration.is_registered(user, season)


@register.filter
def get_team_status(user, season):
    """Get the team status for a user in a season.
    
    Returns a dict with:
    - has_team: bool
    - is_captain: bool
    - team: Team object or None
    - needs_setup: bool (captain without team)
    """
    from heltour.tournament.models import Player, TeamMember, Registration
    
    if not user.is_authenticated or not season:
        return None
    
    try:
        player = Player.objects.get(lichess_username__iexact=user.username)
    except Player.DoesNotExist:
        return None
    
    # Check if user is on a team
    team_member = TeamMember.objects.filter(
        player=player,
        team__season=season
    ).select_related('team').first()
    
    if team_member:
        return {
            'has_team': True,
            'is_captain': team_member.is_captain,
            'team': team_member.team,
            'needs_setup': False
        }
    
    # Check if user is a captain who needs to set up team (team leagues only)
    if season.league.is_team_league():
        registration = Registration.objects.filter(
            player=player,
            season=season,
            status='approved',
            invite_code_used__code_type='captain'
        ).first()

        if registration:
            return {
                'has_team': False,
                'is_captain': True,
                'team': None,
                'needs_setup': True
            }
    
    return {
        'has_team': False,
        'is_captain': False,
        'team': None,
        'needs_setup': False
    }


@register.filter
def is_invite_only_league(league):
    """Check if a league is invite-only."""
    from heltour.tournament.models import RegistrationMode
    return league and league.registration_mode == RegistrationMode.INVITE_ONLY


def concat(str1, str2):
    return str(str1) + str(str2)


@register.filter
def get_tiebreak_display(score, tiebreak_name):
    """Get the display value for a specific tiebreak from a TeamScore or LonePlayerScore."""
    if hasattr(score, 'get_tiebreak_display'):
        return score.get_tiebreak_display(tiebreak_name)
    return ""
