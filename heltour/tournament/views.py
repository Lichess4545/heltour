import itertools
import json
import math
import re
from collections import defaultdict, namedtuple
from datetime import timedelta

import reversion
from cacheops.query import cached_as
from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from django.core.exceptions import SuspiciousOperation
from django.core.mail.message import EmailMessage
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count, F, Max
from django.db.models.query import Prefetch
from django.http.response import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views.generic import View
from icalendar import Calendar, Event

from heltour.tournament import alternates_manager, lichessapi, oauth, signals, uptime
from heltour.tournament.trf16_export import season_to_trf16
from heltour.tournament.forms import (
    ContactForm,
    DeleteNominationForm,
    ModRequestForm,
    NominateForm,
    NotificationsForm,
    RegistrationForm,
    TvFilterForm,
    TvTimezoneForm,
)
from heltour.tournament.models import (
    LONE_TIEBREAK_OPTIONS,
    MOD_REQUEST_SENDER,
    PLAYER_NOTIFICATION_TYPES,
    Alternate,
    AlternateAssignment,
    AlternateBucket,
    Document,
    GameNomination,
    InviteCode,
    League,
    LeagueDocument,
    LonePlayerPairing,
    LonePlayerScore,
    ModRequest,
    NavItem,
    PerfRatingCalc,
    Player,
    PlayerAvailability,
    PlayerBye,
    PlayerNotificationSetting,
    PlayerPairing,
    PlayerPresence,
    PlayerPresenceEvent,
    PlayerSetting,
    Registration,
    Round,
    Season,
    SeasonDocument,
    SeasonPlayer,
    SeasonPrize,
    SeasonPrizeWinner,
    Team,
    TeamBye,
    TeamMember,
    TeamPairing,
    TeamPlayerPairing,
    TeamScore,
    logger,
)
from heltour.tournament.templatetags.tournament_extras import leagueurl

# Helpers for view caching definitions
common_team_models = [League, Season, Round, Team]
common_lone_models = [League, Season, Round, LonePlayerScore, LonePlayerPairing, PlayerPairing,
                      PlayerBye, SeasonPlayer,
                      Player, SeasonPrize, SeasonPrizeWinner]


# default page size for pages using Paginator
DEFAULT_PAGE_SIZE: int = 20

# -------------------------------------------------------------------------------
# Base classes

class BaseView(View):
    def get(self, request, *args, **kwargs):
        self.read_context()
        self.read_user_data()
        return self.preprocess() or self.view(*self.args, **self.kwargs)

    def post(self, request, *args, **kwargs):
        if not hasattr(self, 'view_post'):
            return super(BaseView, self).post(request, *args, **kwargs)
        self.read_context()
        self.read_user_data()
        return self.preprocess() or self.view_post(*self.args, **self.kwargs)

    def read_context(self):
        self.extra_context = {}

    def render(self, template, context):
        context.update(self.extra_context)
        return render(self.request, template, context)

    def preprocess(self):
        if not hasattr(self, '_preprocess'):
            return None
        return self._preprocess()

    def read_user_data(self):
        self.dark_mode = False
        self.zen_mode = False

        if self.request.user.is_authenticated:
            player_setting = PlayerSetting.objects \
                .filter(player__lichess_username__iexact=self.request.user.username).first()
            if player_setting:
                self.dark_mode = player_setting.dark_mode
                self.zen_mode = player_setting.zen_mode
        else:
            self.dark_mode = self.request.session.get('dark_mode', False)
            self.zen_mode = self.request.session.get('zen_mode', False)
        self.extra_context['dark_mode'] = self.dark_mode
        self.extra_context['zen_mode'] = self.zen_mode
        self.user_data = {
            'username': self.request.user.username,
            'is_staff': self.request.user.is_staff,
            'dark_mode': self.dark_mode,
            'zen_mode': self.zen_mode,
        }


class LeagueView(BaseView):
    def read_context(self):
        league_tag = self.kwargs.pop('league_tag')
        season_tag = self.kwargs.pop('season_tag', None)
        self.league = _get_league(league_tag)
        self.season = _get_season(league_tag, season_tag, True)
        self.extra_context = {}

    def render(self, template, context):
        registration_season = Season.get_registration_season(self.league, self.season)
        context.update({
            'league': self.league,
            'season': self.season,
            'registration_season': registration_season,
            'nav_tree': _get_nav_tree(self.league.tag,
                                      self.season.tag if self.season is not None else None),
            'other_leagues': League.objects.filter(is_active=True).order_by(
                'display_order').exclude(pk=self.league.pk)
        })
        context.update(self.extra_context)
        return render(self.request, template, context)


class SeasonView(LeagueView):
    def get(self, request, *args, **kwargs):
        self.read_context()
        self.read_user_data()
        if not self._season_specified:
            return redirect('by_league:by_season:%s' % request.resolver_match.url_name, *self.args,
                            league_tag=self.league.tag, season_tag=self.season.tag, **self.kwargs)
        return self.preprocess() or self.view(*self.args, **self.kwargs)

    def read_context(self):
        league_tag = self.kwargs.pop('league_tag')
        season_tag = self.kwargs.pop('season_tag', None)
        self.set_league_and_season(league_tag, season_tag)
        self._season_specified = season_tag is not None
        self.extra_context = {}
        section_list = self.season.section_list()
        if len(section_list) > 1:
            self.extra_context['section_list'] = section_list

    def set_league_and_season(self, league_tag, season_tag):
        self.league = _get_league(league_tag)
        self.season = _get_season(league_tag, season_tag, False)


class LoginRequiredMixin:
    def _preprocess(self):
        if not self.request.user.is_authenticated:
            self.request.session['login_redirect'] = self.request.build_absolute_uri()
            return redirect('by_league:login', self.league.tag)
        self.extra_context['player'] = self.player

    @property
    def player(self):
        return Player.get_or_create(self.request.user.username)


class ICalMixin:
    def ical_from_pairings_list(self, pairings, calendar_title, uid_component):
        cal = Calendar()
        cal.add('prodid', '-//{}//www.lichess4545.com//'.format(calendar_title))
        cal.add('version', '2.0')

        has_league = hasattr(self, 'league')
        league = self.league if has_league else None

        for pairing in pairings:
            if not has_league:
                round_ = pairing.get_round()
                if not round_:
                    continue
                league = round_.season.league
            time_control_seconds = league.time_control_total()
            if time_control_seconds:
                game_duration = timedelta(seconds=time_control_seconds * 2)
            else:
                game_duration = timedelta(hours=3)

            ical_event = Event()
            if has_league and league.is_team_league():
                ical_event.add('summary', '{} ({}) vs {} ({})'.format(
                    pairing.white.lichess_username,
                    pairing.white_team_name(),
                    pairing.black.lichess_username,
                    pairing.black_team_name(),
                ))
            else:
                ical_event.add('summary', '{} vs {}'.format(
                    pairing.white.lichess_username,
                    pairing.black.lichess_username,
                ))

            ical_event.add('dtstart', pairing.scheduled_time)
            ical_event.add('dtend', pairing.scheduled_time + game_duration)
            ical_event.add('dtstamp', pairing.scheduled_time + game_duration)
            ical_event['uid'] = 'lichess4545.{}.events.{}'.format(
                uid_component,
                pairing.id,
            )
            cal.add_component(ical_event)

        response = HttpResponse(cal.to_ical(), content_type="text/calendar")
        response['Content-Disposition'] = 'attachment; filename={}.ics'.format(
            slugify(calendar_title)
        )
        return response


# -------------------------------------------------------------------------------
# Actual views

class HomeView(BaseView):
    def view(self):
        leagues = League.objects.filter(is_active=True).order_by('display_order')

        context = {
            'leagues': leagues,
            'display_fwcc_banner': settings.DISPLAY_FWCC_BANNER,
            'fwutcc_banner_enabled': settings.FWUTCC_BANNER_ENABLED,
            'fwutcc_banner_url': settings.FWUTCC_BANNER_URL,
        }
        return self.render('tournament/home.html', context)


class LeagueHomeView(LeagueView):
    def view(self):
        if self.league.is_team_league():
            return self.team_view()
        else:
            return self.lone_view()

    def team_view(self):
        other_leagues = League.objects.filter(is_active=True).exclude(pk=self.league.pk).order_by(
            'display_order')

        rules_doc = LeagueDocument.objects.filter(league=self.league, type='rules').first()
        rules_doc_tag = rules_doc.tag if rules_doc is not None else None
        intro_doc = LeagueDocument.objects.filter(league=self.league, type='intro').first()

        if self.season is None:
            context = {
                'rules_doc_tag': rules_doc_tag,
                'intro_doc': intro_doc,
                'can_edit_document': self.request.user.has_perm('tournament.change_document',
                                                                self.league),
                'other_leagues': other_leagues,
            }
            return self.render('tournament/team_league_home.html', context)

        _, completed_seasons = _get_season_lists(self.league)

        team_scores = list(enumerate(sorted(
            TeamScore.objects.filter(team__season=self.season).select_related('team').nocache(),
            reverse=True)[:5], 1))

        context = {
            'team_scores': team_scores,
            'completed_seasons': completed_seasons,
            'rules_doc_tag': rules_doc_tag,
            'intro_doc': intro_doc,
            'can_edit_document': self.request.user.has_perm('tournament.change_document',
                                                            self.league),
            'other_leagues': other_leagues,
        }
        return self.render('tournament/team_league_home.html', context)

    def lone_view(self):
        other_leagues = League.objects.filter(is_active=True).exclude(pk=self.league.pk).order_by(
            'display_order')

        rules_doc = LeagueDocument.objects.filter(league=self.league, type='rules').first()
        rules_doc_tag = rules_doc.tag if rules_doc is not None else None
        intro_doc = LeagueDocument.objects.filter(league=self.league, type='intro').first()

        if self.season is None:
            context = {
                'rules_doc_tag': rules_doc_tag,
                'intro_doc': intro_doc,
                'can_edit_document': self.request.user.has_perm('tournament.change_document',
                                                                self.league),
                'other_leagues': other_leagues,
            }
            return self.render('tournament/lone_league_home.html', context)

        _, completed_seasons = _get_season_lists(self.league)

        current_seasons = self.season.section_list()
        current_seasons_with_more = []
        for season in current_seasons:
            player_scores = _lone_player_scores(season, final=True)[:5]

            if self.season.is_completed:
                prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season=season)
                player_highlights = _get_player_highlights(prize_winners)
            else:
                player_highlights = []
            current_seasons_with_more.append((season, player_scores, player_highlights))

        tiebreak_names = dict(LONE_TIEBREAK_OPTIONS)
        lone_tiebreaks = self.league.get_lone_tiebreaks()
        first_tiebreak = (lone_tiebreaks[0], tiebreak_names.get(lone_tiebreaks[0], "TB")) if lone_tiebreaks else None

        context = {
            'current_seasons_with_more': current_seasons_with_more,
            'completed_seasons': completed_seasons,
            'rules_doc_tag': rules_doc_tag,
            'intro_doc': intro_doc,
            'can_edit_document': self.request.user.has_perm('tournament.change_document',
                                                            self.league),
            'other_leagues': other_leagues,
            'first_tiebreak': first_tiebreak,
        }
        return self.render('tournament/lone_league_home.html', context)


class SeasonLandingView(SeasonView):
    def view(self):
        # Check if this is a knockout tournament
        if self.season.league.pairing_type.startswith('knockout'):
            knockout_view = KnockoutSeasonLandingView()
            knockout_view.request = self.request
            knockout_view.args = self.args
            knockout_view.kwargs = self.kwargs
            knockout_view.league = self.league
            knockout_view.season = self.season
            knockout_view.extra_context = getattr(self, 'extra_context', {})
            # Only set player if this view has it (LoginRequiredMixin)
            if hasattr(self, 'player'):
                knockout_view.player = self.player
            else:
                knockout_view.player = None
            knockout_view.user_data = getattr(self, 'user_data', {})
            return knockout_view.view()
        
        if self.league.is_team_league():
            return self.team_view()
        else:
            return self.lone_view()

    def team_view(self):
        @cached_as(SeasonDocument, Document, TeamScore, TeamPairing, *common_team_models)
        def _view(league_tag, season_tag, user_data):
            if self.season.is_completed:
                return self.team_completed_season_view()

            current_seasons, completed_seasons = _get_season_lists(self.league)
            has_more_seasons = len(current_seasons) + len(completed_seasons) > 1

            active_round = Round.objects.filter(season=self.season, publish_pairings=True,
                                                is_completed=False, start_date__lt=timezone.now(),
                                                end_date__gt=timezone.now()) \
                .order_by('-number') \
                .first()
            last_round = Round.objects.filter(season=self.season, is_completed=True).order_by(
                '-number').first()
            last_round_pairings = last_round.teampairing_set.all() if last_round is not None else None
            team_scores = list(enumerate(
                sorted(TeamScore.objects.filter(team__season=self.season), reverse=True)[:5], 1))

            links_doc = SeasonDocument.objects.filter(season=self.season, type='links').first()

            context = {
                'has_more_seasons': has_more_seasons,
                'current_seasons': current_seasons,
                'completed_seasons': completed_seasons,
                'active_round': active_round,
                'last_round': last_round,
                'last_round_pairings': last_round_pairings,
                'team_scores': team_scores,
                'links_doc': links_doc,
                'can_edit_document': self.request.user.has_perm('tournament.change_document',
                                                                self.league),
            }
            return self.render('tournament/team_season_landing.html', context)

        return _view(self.league.tag, self.season.tag, self.user_data)

    def lone_view(self):
        @cached_as(SeasonDocument, Document, *common_lone_models)
        def _view(league_tag, season_tag, user_data):
            if self.season.is_completed:
                return self.lone_completed_season_view()

            current_seasons, completed_seasons = _get_season_lists(self.league)
            has_more_seasons = len(current_seasons) + len(completed_seasons) > 1

            active_round = Round.objects.filter(season=self.season, publish_pairings=True,
                                                is_completed=False, start_date__lt=timezone.now(),
                                                end_date__gt=timezone.now()) \
                .order_by('-number') \
                .first()
            last_round = Round.objects.filter(season=self.season, is_completed=True).order_by(
                '-number').first()
            last_round_pairings = last_round.loneplayerpairing_set.exclude(result='').order_by(
                'pairing_order')[:10].nocache() if last_round is not None else None
            player_scores = _lone_player_scores(self.season, final=True)[:5]

            links_doc = SeasonDocument.objects.filter(season=self.season, type='links').first()

            tiebreak_names = dict(LONE_TIEBREAK_OPTIONS)
            lone_tiebreaks = self.league.get_lone_tiebreaks()
            first_tiebreak = (lone_tiebreaks[0], tiebreak_names.get(lone_tiebreaks[0], "TB")) if lone_tiebreaks else None

            context = {
                'has_more_seasons': has_more_seasons,
                'current_seasons': current_seasons,
                'completed_seasons': completed_seasons,
                'active_round': active_round,
                'last_round': last_round,
                'last_round_pairings': last_round_pairings,
                'player_scores': player_scores,
                'links_doc': links_doc,
                'first_tiebreak': first_tiebreak,
                'can_edit_document': self.request.user.has_perm('tournament.change_document',
                                                                self.league),
            }
            return self.render('tournament/lone_season_landing.html', context)

        return _view(self.league.tag, self.season.tag, self.user_data)

    def team_completed_season_view(self):
        current_seasons, completed_seasons = _get_season_lists(self.league)
        has_more_seasons = len(current_seasons) + len(completed_seasons) > 1

        round_numbers = list(range(1, self.season.rounds + 1))
        team_scores = list(enumerate(sorted(
            TeamScore.objects.filter(team__season=self.season).select_related('team').nocache(),
            reverse=True), 1))

        first_team = team_scores[0][1] if len(team_scores) > 0 else None
        second_team = team_scores[1][1] if len(team_scores) > 1 else None
        third_team = team_scores[2][1] if len(team_scores) > 2 else None

        links_doc = SeasonDocument.objects.filter(season=self.season, type='links').first()

        # Get tiebreaks configuration for the league
        from heltour.tournament.models import TEAM_TIEBREAK_OPTIONS
        tiebreak_names = dict(TEAM_TIEBREAK_OPTIONS)
        tiebreaks = []
        for tb in self.league.get_team_tiebreaks():
            if tb in tiebreak_names:
                display_name = tiebreak_names[tb]
                if ' - ' in display_name:
                    display_name = display_name.split(' - ')[0]
                tiebreaks.append((tb, display_name))

        context = {
            'has_more_seasons': has_more_seasons,
            'current_seasons': current_seasons,
            'completed_seasons': completed_seasons,
            'round_numbers': round_numbers,
            'team_scores': team_scores,
            'first_team': first_team,
            'second_team': second_team,
            'third_team': third_team,
            'links_doc': links_doc,
            'tiebreaks': tiebreaks,
            'can_edit_document': self.request.user.has_perm('tournament.change_document',
                                                            self.league),
        }
        return self.render('tournament/team_completed_season_landing.html', context)

    def lone_completed_season_view(self):
        current_seasons, completed_seasons = _get_season_lists(self.league)
        has_more_seasons = len(current_seasons) + len(completed_seasons) > 1

        round_numbers = list(range(1, self.season.rounds + 1))
        player_scores = _lone_player_scores(self.season)

        first_player = player_scores[0][1] if len(player_scores) > 0 else None
        second_player = player_scores[1][1] if len(player_scores) > 1 else None
        third_player = player_scores[2][1] if len(player_scores) > 2 else None

        ribbons = SeasonPrizeWinner.objects.filter(season_prize__season=self.season,
                                                   season_prize__max_rating__isnull=False,
                                                   season_prize__rank=1)

        prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season=self.season)
        player_highlights = _get_player_highlights(prize_winners)

        links_doc = SeasonDocument.objects.filter(season=self.season, type='links').first()

        tiebreak_names = dict(LONE_TIEBREAK_OPTIONS)
        tiebreaks = []
        for tb in self.league.get_lone_tiebreaks():
            if tb in tiebreak_names:
                tiebreaks.append((tb, tiebreak_names[tb]))

        context = {
            'has_more_seasons': has_more_seasons,
            'current_seasons': current_seasons,
            'completed_seasons': completed_seasons,
            'round_numbers': round_numbers,
            'player_scores': player_scores,
            'first_player': first_player,
            'second_player': second_player,
            'third_player': third_player,
            'ribbons': ribbons,
            'player_highlights': player_highlights,
            'links_doc': links_doc,
            'tiebreaks': tiebreaks,
            'can_edit_document': self.request.user.has_perm('tournament.change_document',
                                                            self.league),
        }
        return self.render('tournament/lone_completed_season_landing.html', context)


def _build_presence_events_map(round_, can_view):
    """Group PlayerPresenceEvents for a round by (pairing_id, player_id).

    Returns an empty dict when the viewer lacks permission or the round is
    missing, so the template never sees protected data.
    """
    if not can_view or round_ is None:
        return {}
    events_map = {}
    qs = (
        PlayerPresenceEvent.objects.filter(round=round_)
        .select_related("player")
        .order_by("timestamp")
    )
    for ev in qs:
        events_map.setdefault((ev.pairing_id, ev.player_id), []).append(ev)
    return events_map


class PairingsView(SeasonView):
    def view(self, round_number=None, team_number=None):
        # Check if this is a knockout tournament
        if self.season.league.pairing_type.startswith('knockout'):
            knockout_view = KnockoutPairingsView()
            knockout_view.request = self.request
            knockout_view.args = self.args
            knockout_view.kwargs = self.kwargs
            knockout_view.league = self.league
            knockout_view.season = self.season
            knockout_view.extra_context = getattr(self, 'extra_context', {})
            # Only set player if this view has it (LoginRequiredMixin)
            if hasattr(self, 'player'):
                knockout_view.player = self.player
            else:
                knockout_view.player = None
            knockout_view.user_data = getattr(self, 'user_data', {})
            return knockout_view.view(round_number, team_number)
        
        if self.league.is_team_league():
            return self.team_view(round_number, team_number)
        else:
            return self.lone_view(round_number, team_number)

    @staticmethod
    def _summarize_pairings(pairings):
        finished = started = remaining = 0
        for p in pairings:
            if p.result:
                finished += 1
            elif p.game_link:
                started += 1
            else:
                remaining += 1
        return {
            'total': finished + started + remaining,
            'finished': finished,
            'started': started,
            'remaining': remaining,
        }

    def _player_status(self, player, pairing, presences, in_contact_period, contact_deadline):
        if player is None:
            return (None, 'no player')
        if (player is pairing.white and pairing.white_confirmed) or (player is pairing.black and pairing.black_confirmed):
            return ('confirmed', 'confirmed')
        pres = presences.get((player.pk, pairing.pk))
        if in_contact_period:
            if not pres or not pres.first_msg_time:
                return (None, 'no contact yet')
            else:
                return ('yes', 'in contact')
        else:
            if not pres or not pres.first_msg_time:
                return ('no', 'unresponsive')
            elif pres.first_msg_time > contact_deadline:
                return ('alert', 'late contact')
            else:
                return ('yes', 'in contact')

    def get_team_context(self, league_tag, season_tag, round_number, team_number,
                         can_change_pairing):
        specified_round = round_number is not None
        round_number_list = [round_.number for round_ in Round.objects.filter(season=self.season,
                                                                              publish_pairings=True).order_by(
            '-number')]
        if round_number is None:
            try:
                round_number = round_number_list[0]
            except IndexError:
                pass
        team_list = self.season.team_set.order_by('name')
        team_pairings = TeamPairing.objects.filter(round__number=round_number,
                                                   round__season=self.season) \
            .order_by('pairing_order') \
            .select_related('white_team', 'black_team') \
            .nocache()

        # Get team byes for this round
        team_byes = list(TeamBye.objects.filter(round__number=round_number,
                                               round__season=self.season) \
                         .select_related('team') \
                         .nocache())

        if team_number is not None:
            current_team = get_object_or_404(team_list, number=team_number)
            team_pairings = team_pairings.filter(white_team=current_team) | team_pairings.filter(
                black_team=current_team)
            team_byes = [bye for bye in team_byes if bye.team == current_team]
        else:
            current_team = None

        pairing_lists = [list(
            team_pairing.teamplayerpairing_set.order_by('board_number')
                .select_related('white', 'black')
                .nocache()
        ) for team_pairing in team_pairings]
        round_ = Round.objects.filter(number=round_number, season=self.season).first()
        presences = {(pp.player_id, pp.pairing_id): pp for pp in
                     PlayerPresence.objects.filter(round=round_)}
        presence_events_map = _build_presence_events_map(round_, can_change_pairing)
        if pairing_lists:
            contact_deadline = round_.start_date + self.league.get_leaguesetting().contact_period
            in_contact_period = timezone.now() < contact_deadline

        def status(player, pairing):
            return self._player_status(
                player,
                pairing,
                presences,
                in_contact_period,
                contact_deadline
            )

        # Add presences
        pairing_lists = [
            [((p,) + status(p.white_team_player(), p) + status(p.black_team_player(), p)) for p in
             p_list]
            for p_list in pairing_lists
        ]
        unavailable_players = {pa.player for pa in
                               PlayerAvailability.objects.filter(round__season=self.season,
                                                                 round__number=round_number,
                                                                 is_available=False) \
                                   .select_related('player')
                                   .nocache()}
        captains = {tm.player for tm in
                    TeamMember.objects.filter(team__season=self.season, is_captain=True)}

        # Show the legend if at least one the players in the visible pairings is unavailable
        show_legend = len(unavailable_players & (
            {p[0].white for plist in pairing_lists for p in plist} | {p[0].black for plist in
                                                                      pairing_lists for p in
                                                                      plist})) > 0

        flat_pairings = [p[0] for plist in pairing_lists for p in plist]
        return {
            'round_number': round_number,
            'round_id': round_.pk if round_ else None,
            'round_number_list': round_number_list,
            'current_team': current_team,
            'team_list': team_list,
            'pairing_lists': pairing_lists,
            'pairings_summary': self._summarize_pairings(flat_pairings),
            'team_byes': team_byes,
            'captains': captains,
            'unavailable_players': unavailable_players,
            'show_legend': show_legend,
            'specified_round': specified_round,
            'specified_team': team_number is not None,
            'can_edit': can_change_pairing,
            'presence_events_map': presence_events_map,
            'can_view_presence_log': can_change_pairing,
        }

    def team_view(self, round_number=None, team_number=None):
        @cached_as(TeamScore, TeamPairing, TeamBye, TeamMember, SeasonPlayer, AlternateAssignment, Player,
                   PlayerAvailability, TeamPlayerPairing,
                   PlayerPairing, *common_team_models)
        def _view(league_tag, season_tag, round_number, team_number, user_data, can_change_pairing):
            context = self.get_team_context(league_tag, season_tag, round_number, team_number,
                                            can_change_pairing)
            return self.render('tournament/team_pairings.html', context)

        return _view(
            self.league.tag, self.season.tag, round_number, team_number, self.user_data,
            self.request.user.has_perm('tournament.change_pairing', self.league))

    def get_lone_context(self, round_number=None, team_number=None):
        specified_round = round_number is not None
        round_number_list = [round_.number for round_ in Round.objects.filter(season=self.season,
                                                                              publish_pairings=True).order_by(
            '-number')]
        if round_number is None:
            try:
                round_number = round_number_list[0]
            except IndexError:
                pass
        round_ = Round.objects.filter(number=round_number, season=self.season).first()
        pairings = LonePlayerPairing.objects.filter(round=round_).order_by(
            'pairing_order').select_related('white', 'black').nocache()
        byes = PlayerBye.objects.filter(round=round_).order_by('type', 'player_rank',
                                                               'player__lichess_username').select_related(
            'player').nocache()

        next_pairing_order = 0
        for p in pairings:
            next_pairing_order = max(next_pairing_order, p.pairing_order + 1)

        # Find duplicate players
        player_refcounts = {}
        for p in pairings:
            player_refcounts[p.white] = player_refcounts.get(p.white, 0) + 1
            player_refcounts[p.black] = player_refcounts.get(p.black, 0) + 1
        for b in byes:
            player_refcounts[b.player] = player_refcounts.get(b.player, 0) + 1
        duplicate_players = {k for k, v in list(player_refcounts.items()) if v > 1}

        active_players = {sp.player for sp in
                          SeasonPlayer.objects.filter(season=self.season, is_active=True)}

        can_change_pairing = self.request.user.has_perm('tournament.change_pairing', self.league)

        presences = {(pp.player_id, pp.pairing_id): pp for pp in
                     PlayerPresence.objects.filter(round=round_)}
        presence_events_map = _build_presence_events_map(round_, can_change_pairing)
        if pairings:
            contact_deadline = round_.start_date + self.league.get_leaguesetting().contact_period
            in_contact_period = timezone.now() < contact_deadline

        def pairing_error(pairing):
            if not self.request.user.is_staff:
                return None
            if pairing.white is None or pairing.black is None:
                return 'Missing player'
            if pairing.white in duplicate_players:
                return 'Duplicate player: %s' % pairing.white.lichess_username
            if pairing.black in duplicate_players:
                return 'Duplicate player: %s' % pairing.black.lichess_username
            if not round_.is_completed and pairing.white not in active_players:
                return 'Inactive player: %s' % pairing.white.lichess_username
            if not round_.is_completed and pairing.black not in active_players:
                return 'Inactive player: %s' % pairing.black.lichess_username
            return None

        def bye_error(bye):
            if not self.request.user.is_staff:
                return None
            if bye.player in duplicate_players:
                return 'Duplicate player: %s' % bye.player.lichess_username
            if not round_.is_completed and bye.player not in active_players:
                return 'Inactive player: %s' % bye.player.lichess_username
            return None

        def status(player, pairing):
            return self._player_status(
                player,
                pairing,
                presences,
                in_contact_period,
                contact_deadline
            )

        # Add errors
        pairings = [(p, pairing_error(p)) + status(p.white, p) + status(p.black, p) for p in
                    pairings]
        byes = [(b, bye_error(b)) for b in byes]

        return {
            'round_': round_,
            'round_number_list': round_number_list,
            'pairings': pairings,
            'byes': byes,
            'specified_round': specified_round,
            'next_pairing_order': next_pairing_order,
            'duplicate_players': duplicate_players,
            'can_edit': can_change_pairing,
            'presence_events_map': presence_events_map,
            'can_view_presence_log': can_change_pairing,
        }

    def lone_view(self, round_number=None, team_number=None):
        context = self.get_lone_context(round_number, team_number)
        return self.render('tournament/lone_pairings.html', context)


class ICalPairingsView(PairingsView, ICalMixin):
    def view(self, round_number=None, team_number=None):
        if self.league.is_team_league():
            return self.team_view(round_number, team_number)
        else:
            return self.lone_view(round_number, team_number)

    def team_view(self, round_number=None, team_number=None):
        context = self.get_team_context(
            self.league.tag, self.season.tag, round_number, team_number,
            self.request.user.has_perm('tournament.change_pairing', self.league))
        calendar_title = ""
        if context['current_team']:
            calendar_title = "{} Games".format(context['current_team'])
            uid_component = slugify(context['current_team'].name)
        else:
            calendar_title = "{} Games".format(self.league.name)
            uid_component = 'all'
        full_pairings_list = []
        for pairing_list in context['pairing_lists']:
            for pairing, _, _, _, _ in pairing_list:
                if pairing.scheduled_time is None:
                    continue
                full_pairings_list.append(pairing)
        return self.ical_from_pairings_list(full_pairings_list, calendar_title, uid_component)

    def lone_view(self, round_number=None, team_number=None):
        context = self.get_lone_context(round_number, team_number)
        calendar_title = "{} Games".format(self.league.name)
        uid_component = 'all'

        full_pairings_list = []
        for pairing, error, _, _, _, _ in context['pairings']:
            if error:
                continue
            if pairing.scheduled_time is None:
                continue
            full_pairings_list.append(pairing)
        return self.ical_from_pairings_list(full_pairings_list, calendar_title, uid_component)


class TeamPairingBlockView(PairingsView):
    """Returns the rendered HTML for a single team_pairing block.

    Used by the live pairings JS to swap one block in place when its result or
    game link changes, without reloading the whole page.
    """

    def view(self, pairing_id):
        import logging
        log = logging.getLogger("heltour.api.block")
        if not self.league.is_team_league():
            log.warning("block 404: league %s is not a team league", self.league.tag)
            raise Http404()
        try:
            pp = PlayerPairing.objects.get(pk=pairing_id)
        except PlayerPairing.DoesNotExist:
            log.warning("block 404: pairing %s not found", pairing_id)
            raise Http404()
        try:
            tp = pp.teamplayerpairing.team_pairing
        except (AttributeError, TeamPlayerPairing.DoesNotExist):
            log.warning("block 404: pairing %s has no team_pairing", pairing_id)
            raise Http404()
        if tp.round.season_id != self.season.pk:
            log.warning(
                "block 404: pairing %s in season %s, requested season %s",
                pairing_id, tp.round.season_id, self.season.pk,
            )
            raise Http404()

        can_change_pairing = self.request.user.has_perm(
            'tournament.change_pairing', self.league
        )
        context = self.get_team_context(
            self.league.tag, self.season.tag, tp.round.number, None,
            can_change_pairing,
        )
        matching = next(
            (pl for pl in context['pairing_lists']
             if pl and pl[0][0].team_pairing_id == tp.pk),
            None,
        )
        if matching is None:
            raise Http404(
                "team_pairing %s not in round %s pairing_lists"
                % (tp.pk, tp.round.number)
            )

        return self.render(
            'tournament/_team_pairing_block.html',
            {**context, 'pairing_list': matching, 'show_calendar': False, 'flash': True},
        )


class ICalPlayerView(BaseView, ICalMixin):
    def view(self, username):
        player = get_object_or_404(Player, lichess_username__iexact=username)
        calendar_title = "{} Chess Games".format(player.lichess_username)
        uid_component = 'all'
        pairings = player.pairings.exclude(scheduled_time=None)
        return self.ical_from_pairings_list(pairings, calendar_title, uid_component)


class RegisterView(LoginRequiredMixin, LeagueView):

    def view(self, post=False):
        doc_url: str = ''
        reg_season = Season.get_registration_season(self.league, self.season)
        if reg_season is None:
            return self.render('tournament/registration_closed.html', {})
        if not Registration.can_register(self.request.user, reg_season):
            return redirect('by_league:league_home', self.league.tag)

        with cache.lock(f'update_create_registration-{self.request.user.id}-{reg_season.id}'):
            instance = Registration.get_latest_registration(self.request.user, reg_season)
            player = Player.get_or_create(lichess_username=self.request.user.username)
            if post:
                form = RegistrationForm(
                    self.request.POST,
                    instance=instance,
                    season=reg_season,
                    player=player,
                )
                if form.is_valid():
                    with reversion.create_revision():
                        reversion.set_comment('Submitted registration.')
                        registration = form.save()

                    # Only store email in session if the field exists
                    if 'email' in form.cleaned_data:
                        self.request.session['reg_email'] = form.cleaned_data['email']
                    
                    # Store registration ID in session to check team assignment
                    self.request.session['reg_id'] = registration.id

                    return redirect(leagueurl('registration_success', league_tag=self.league.tag,
                                              season_tag=self.season.tag))
            else:
                rules_doc = LeagueDocument.objects.filter(league=self.league, type='rules').first()
                if rules_doc is not None:
                    doc_url = reverse('by_league:document', args=[self.league.tag, rules_doc.tag])
                form = RegistrationForm(
                    instance=instance,
                    season=reg_season,
                    player=player,
                    rules_url=doc_url,
                )
                # Only set email initial value if the field exists
                if 'email' in form.fields:
                    form.fields['email'].initial = player.email
                rating_provisional = player.provisional_for(reg_season.league)
                # Only set has_played_20_games initial value if the field exists
                if 'has_played_20_games' in form.fields:
                    form.fields['has_played_20_games'].initial = not rating_provisional

            context = {
                'form': form,
                'registration_season': reg_season,
                'rules_url': doc_url,
            }
            if not post and self.league.show_provisional_warning:
                context['rating_provisional'] = rating_provisional
            return self.render('tournament/register.html', context)

    def view_post(self):
        return self.view(post=True)


class RegistrationSuccessView(SeasonView):
    def view(self):
        reg_season = Season.get_registration_season(self.league, self.season)
        if reg_season is None:
            return self.render('tournament/registration_closed.html', {})

        context = {
            'registration_season': reg_season,
            'email': self.request.session.get('reg_email')
        }
        
        # Check if user registered with a team invite code
        reg_id = self.request.session.get('reg_id')
        if reg_id:
            try:
                registration = Registration.objects.get(pk=reg_id)
                context['registration'] = registration
                if registration.invite_code_used:
                    if registration.invite_code_used.code_type == 'captain' and self.league.is_team_league():
                        # Captain code on a team league - needs to create team
                        context['is_captain'] = True
                        context['needs_team_setup'] = True
                    elif registration.invite_code_used.code_type == 'team_member':
                        # Team member code - check if they were assigned to a team
                        if registration.player:
                            team_member = TeamMember.objects.filter(
                                player=registration.player,
                                team__season=registration.season
                            ).select_related('team').first()
                            if team_member:
                                context['assigned_team'] = team_member.team
                else:
                    # No invite code used - still check if player is on a team
                    if registration.player:
                        team_member = TeamMember.objects.filter(
                            player=registration.player,
                            team__season=registration.season
                        ).select_related('team').first()
                        if team_member:
                            context['assigned_team'] = team_member.team
            except Registration.DoesNotExist:
                pass
        
        return self.render('tournament/registration_success.html', context)


class ModRequestView(LoginRequiredMixin, SeasonView):
    def view(self, req_type, post=False):

        if req_type not in MOD_REQUEST_SENDER:
            raise Http404

        if post:
            form = ModRequestForm(self.request.POST)
            if form.is_valid():
                with reversion.create_revision():
                    reversion.set_comment('Submitted mod request.')
                    modreq = form.save(commit=False)
                    modreq.season = self.season
                    modreq.type = req_type
                    modreq.requester = self.player
                    modreq.status = 'pending'
                    modreq.screenshot = self.request.FILES.get('screenshot')
                    modreq.save()
                return redirect(
                    leagueurl('modrequest_success', self.league.tag, self.season.tag, req_type))
        else:
            form = ModRequestForm()

        context = {
            'form': form,
            'req_type': ModRequest(type=req_type).get_type_display()
        }
        return self.render('tournament/modrequest.html', context)

    def view_post(self, req_type):
        return self.view(req_type, post=True)


class ModRequestSuccessView(SeasonView):
    def view(self, req_type):
        context = {
            'req_type': ModRequest(type=req_type).get_type_display()
        }
        return self.render('tournament/modrequest_success.html', context)


class RostersView(SeasonView):
    def view(self):
        # Check if this is a knockout tournament
        if self.season.league.pairing_type.startswith('knockout'):
            return redirect('by_league:by_season:knockout_bracket', 
                          league_tag=self.league.tag, season_tag=self.season.tag)
        
        @cached_as(TeamMember, SeasonPlayer, Alternate, AlternateAssignment, AlternateBucket,
                   Player, PlayerAvailability, *common_team_models)
        def _view(league_tag, season_tag, user_data, can_edit, show_gender):
            if self.league.competitor_type != 'team':
                raise Http404
            if self.season is None:
                context = {
                    'can_edit': self.request.user.has_perm('tournament.manage_players',
                                                           self.league),
                    'show_gender': show_gender,
                }
                return self.render('tournament/team_rosters.html', context)

            teams = Team.objects.filter(season=self.season).select_related(
                'season__league'
            ).prefetch_related(
                Prefetch('teammember_set', queryset=TeamMember.objects.select_related('player'))
            ).nocache()
            # Sort teams by average rating (highest to lowest)
            teams = sorted(teams, key=lambda team: team.average_rating() or 0, reverse=True)
            board_numbers = list(range(1, self.season.boards + 1))

            alternates = Alternate.objects.filter(season_player__season=self.season)
            alternates_by_board = [sorted(
                alternates.filter(board_number=n)
                    .select_related('season_player__registration', 'season_player__player')
                    .nocache(),
                key=lambda alt: alt.priority_date()
            ) for n in board_numbers]
            alternate_rows = list(enumerate(itertools.zip_longest(*alternates_by_board), 1))
            if len(alternate_rows) == 0:
                alternate_rows.append((1, [None for _ in board_numbers]))

            current_round = Round.objects.filter(season=self.season,
                                                 publish_pairings=True).order_by('-number').first()
            scheduled_alternates = {assign.player for assign in
                                    AlternateAssignment.objects.filter(round=current_round)
                                        .select_related('player')
                                        .nocache()}
            unavailable_players = {pa.player for pa in
                                   PlayerAvailability.objects.filter(round__season=self.season,
                                                                     round=current_round,
                                                                     is_available=False) \
                                       .select_related('player')
                                       .nocache()}
            unresponsive_players = {sp.player for sp in
                                    SeasonPlayer.objects.filter(season=self.season,
                                                                unresponsive=True)
                                        .select_related('player')
                                        .nocache()}
            games_missed_by_player = {sp.player: sp.games_missed for sp in
                                      SeasonPlayer.objects.filter(season=self.season)
                                          .select_related('player')
                                          .nocache()}
            yellow_card_players = {player for player, games_missed in
                                   list(games_missed_by_player.items()) if games_missed == 1}
            red_card_players = {player for player, games_missed in
                                list(games_missed_by_player.items()) if games_missed >= 2}

            # Show the legend if we have any data that might need it
            show_legend = len(
                scheduled_alternates | unavailable_players | unresponsive_players | yellow_card_players | red_card_players) > 0

            context = {
                'teams': teams,
                'board_numbers': board_numbers,
                'alternate_rows': alternate_rows,
                'scheduled_alternates': scheduled_alternates,
                'unresponsive_players': unresponsive_players,
                'unavailable_players': unavailable_players,
                'yellow_card_players': yellow_card_players,
                'red_card_players': red_card_players,
                'show_legend': show_legend,
                'can_edit': can_edit,
                'show_gender': show_gender,
            }
            return self.render('tournament/team_rosters.html', context)

        return _view(self.league.tag, self.season.tag, self.user_data,
                     self.request.user.has_perm('tournament.manage_players', self.league),
                     self.request.user.has_perm('tournament.view_dashboard', self.league))


class StandingsView(SeasonView):
    def view(self, section=None):
        # Check if this is a knockout tournament
        if self.season.league.pairing_type.startswith('knockout'):
            return redirect('by_league:by_season:knockout_bracket', 
                          league_tag=self.league.tag, season_tag=self.season.tag)
        
        if self.league.is_team_league():
            return self.team_view()
        else:
            return self.lone_view(section)

    def team_view(self):
        @cached_as(TeamScore, TeamPairing, TeamBye, *common_team_models)
        def _view(league_tag, season_tag, user_data):
            round_numbers = list(range(1, self.season.rounds + 1))
            
            # Use proper sort key based on season status
            if self.season.is_completed:
                def sort_key(s): return s.final_standings_sort_key()
            else:
                def sort_key(s): return s.intermediate_standings_sort_key()
                
            raw_team_scores = TeamScore.objects.filter(team__season=self.season).select_related('team').nocache()
            team_scores = list(enumerate(sorted(raw_team_scores, key=sort_key, reverse=True), 1))
            # Get configured tiebreaks for display
            # Get tiebreak names from the model choices
            from heltour.tournament.models import TEAM_TIEBREAK_OPTIONS
            tiebreak_names = dict(TEAM_TIEBREAK_OPTIONS)
            
            tiebreaks = []
            for tb in self.league.get_team_tiebreaks():
                if tb in tiebreak_names:
                    # Use short display name for Extended SB variants
                    display_name = tiebreak_names[tb]
                    if ' - ' in display_name:
                        display_name = display_name.split(' - ')[0]
                    tiebreaks.append((tb, display_name))
            
            context = {
                'round_numbers': round_numbers,
                'team_scores': team_scores,
                'tiebreaks': tiebreaks,
            }
            return self.render('tournament/team_standings.html', context)

        return _view(self.league.tag, self.season.tag, self.user_data)

    def lone_view(self, section=None):
        @cached_as(*common_lone_models)
        def _view(league_tag, season_tag, section, user_data):
            round_numbers = list(range(1, self.season.rounds + 1))
            player_scores = _lone_player_scores(self.season)

            has_ljp = False
            for _, ps, _ in player_scores:
                if ps.late_join_points > 0:
                    has_ljp = True

            if section is not None:
                match = re.match(r'u(\d+)', section)
                if match is not None:
                    max_rating = int(match.group(1))
                    player_scores = [ps for ps in player_scores if
                                     ps[1].season_player.seed_rating_display() is not None and
                                     ps[1].season_player.seed_rating_display() < max_rating]

            player_sections = [('u%d' % sp.max_rating, 'U%d' % sp.max_rating) for sp in
                               SeasonPrize.objects.filter(season=self.season).exclude(
                                   max_rating=None).order_by('max_rating')]
            section_dict = {k: (k, v) for k, v in player_sections}
            current_section = section_dict.get(section, None)

            if self.season.is_completed:
                prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season=self.season)
            else:
                prize_winners = SeasonPrizeWinner.objects.filter(
                    season_prize__season__league=self.league)
            player_highlights = _get_player_highlights(prize_winners)

            # Build tiebreak display list from league config
            tiebreak_names = dict(LONE_TIEBREAK_OPTIONS)
            tiebreaks = []
            for tb in self.league.get_lone_tiebreaks():
                if tb in tiebreak_names:
                    tiebreaks.append((tb, tiebreak_names[tb]))

            context = {
                'round_numbers': round_numbers,
                'player_scores': player_scores,
                'has_ljp': has_ljp,
                'player_sections': player_sections,
                'current_section': current_section,
                'player_highlights': player_highlights,
                'tiebreaks': tiebreaks,
            }
            return self.render('tournament/lone_standings.html', context)

        return _view(self.league.tag, self.season.tag, section, self.user_data)


def _get_player_highlights(prize_winners):
    return [
        ('gold', {pw.player for pw in
                  prize_winners.filter(season_prize__rank=1, season_prize__max_rating=None)}),
        ('silver', {pw.player for pw in
                    prize_winners.filter(season_prize__rank=2, season_prize__max_rating=None)}),
        ('bronze', {pw.player for pw in
                    prize_winners.filter(season_prize__rank=3, season_prize__max_rating=None)}),
        ('blue', {pw.player for pw in prize_winners.filter(season_prize__rank=1).exclude(
            season_prize__max_rating=None)})
    ]


@cached_as(LonePlayerScore, LonePlayerPairing, PlayerPairing, PlayerBye, SeasonPlayer, Player)
def _lone_player_scores(season, final=False, sort_by_seed=False, include_current=False):
    # For efficiency, rather than having LonePlayerScore.round_scores() do independent
    # calculations, we populate a few common data structures and use those as parameters.

    if sort_by_seed:
        def sort_key(s): return s.season_player.seed_rating_display() or 0
    elif season.is_completed or final:
        def sort_key(s): return s.final_standings_sort_key()
    else:
        def sort_key(s): return s.intermediate_standings_sort_key()
    raw_player_scores = LonePlayerScore.objects.filter(season_player__season=season) \
        .select_related('season_player__player', 'season_player__season__league').nocache()
    player_scores = list(enumerate(sorted(raw_player_scores, key=sort_key, reverse=True), 1))
    player_number_dict = {p.season_player.player: n for n, p in player_scores}

    pairings = LonePlayerPairing.objects.filter(round__season=season).select_related('white',
                                                                                     'black').nocache()
    white_pairings_dict = defaultdict(list)
    black_pairings_dict = defaultdict(list)
    for p in pairings:
        if p.white is not None:
            white_pairings_dict[p.white].append(p)
        if p.black is not None:
            black_pairings_dict[p.black].append(p)

    byes = PlayerBye.objects.filter(round__season=season).select_related('round',
                                                                         'player').nocache()
    byes_dict = defaultdict(list)
    for bye in byes:
        byes_dict[bye.player].append(bye)

    rounds = Round.objects.filter(season=season).order_by('number')

    # rounds = [round_ for round_ in Round.objects.filter(season=season).order_by('number') if round_.is_completed or (include_current and round_.publish_pairings)]

    def round_scores(player_score):
        return list(player_score.round_scores(rounds, player_number_dict, white_pairings_dict,
                                              black_pairings_dict, byes_dict, include_current))

    return [(n, ps, round_scores(ps)) for n, ps in player_scores]


class CrosstableView(SeasonView):
    def view(self):
        @cached_as(TeamScore, TeamPairing, *common_team_models)
        def _view(league_tag, season_tag, user_data):
            if self.league.competitor_type != 'team':
                raise Http404
            team_scores = list(enumerate(sorted(
                TeamScore.objects.filter(team__season=self.season).select_related('team').nocache(),
                reverse=True), 1))
            teams = [ts.team for _, ts in team_scores]
            team_scores = [(n, ts, ts.cross_scores(teams)) for n, ts in team_scores]
            context = {
                'team_scores': team_scores,
            }
            return self.render('tournament/team_crosstable.html', context)

        return _view(self.league.tag, self.season.tag, self.user_data)


class WallchartView(SeasonView):
    def view(self):
        @cached_as(*common_lone_models)
        def _view(league_tag, season_tag, user_data):
            if self.league.is_team_league():
                raise Http404
            round_numbers = list(range(1, self.season.rounds + 1))
            player_scores = _lone_player_scores(self.season, sort_by_seed=True,
                                                include_current=True)

            if self.season.is_completed:
                prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season=self.season)
            else:
                prize_winners = SeasonPrizeWinner.objects.filter(
                    season_prize__season__league=self.season.league)
            player_highlights = _get_player_highlights(prize_winners)

            context = {
                'round_numbers': round_numbers,
                'player_scores': player_scores,
                'player_highlights': player_highlights,
            }
            return self.render('tournament/lone_wallchart.html', context)

        return _view(self.league.tag, self.season.tag, self.user_data)


class StatsView(SeasonView):
    def view(self):
        if self.league.is_team_league():
            return self.team_view()
        else:
            return self.lone_view()

    def team_view(self):
        @cached_as(League, Season, Round, TeamPlayerPairing, PlayerPairing)
        def _view(league_tag, season_tag, user_data):
            all_pairings = PlayerPairing.objects.filter(
                teamplayerpairing__team_pairing__round__season=self.season) \
                .select_related('teamplayerpairing', 'white', 'black') \
                .nocache()

            def count_results(board_num=None):
                total = 0.0
                counts = [0, 0, 0, 0]
                rating_delta = 0
                for p in all_pairings:
                    if board_num is not None and p.teamplayerpairing.board_number != board_num:
                        continue
                    if p.game_link == '' or p.result == '' or not p.game_played():
                        # Don't count forfeits etc
                        continue
                    total += 1
                    if p.white_rating_display(self.league) is not None and p.black_rating_display(
                        self.league) is not None:
                        rating_delta += p.white_rating_display(
                            self.league) - p.black_rating_display(self.league)
                    if p.result == '1-0':
                        counts[0] += 1
                        counts[3] += 1
                    elif p.result == '0-1':
                        counts[2] += 1
                        counts[3] -= 1
                    elif p.result == '1/2-1/2':
                        counts[1] += 1
                if total == 0:
                    return board_num, tuple(counts), (0, 0, 0, 0), 0.0
                percents = (
                    counts[0] / total, counts[1] / total, counts[2] / total, counts[3] / total)
                return board_num, tuple(counts), percents, rating_delta / total

            _, total_counts, total_percents, total_rating_delta = count_results()
            boards = [count_results(board_num=n) for n in self.season.board_number_list()]

            context = {
                'has_win_rate_stats': total_counts != (0, 0, 0, 0),
                'total_rating_delta': total_rating_delta,
                'total_counts': total_counts,
                'total_percents': total_percents,
                'boards': boards,
            }
            return self.render('tournament/team_stats.html', context)

        return _view(self.league.tag, self.season.tag, self.user_data)

    def lone_view(self):
        @cached_as(League, Season, Round, LonePlayerPairing, PlayerPairing, SeasonPlayer)
        def _view(league_tag, season_tag, user_data):
            season_players = self.season.seasonplayer_set.order_by('player__rating').select_related(
                'player').nocache()
            active_player_ratings = [sp.player.player_rating_display(self.league) for sp in
                                     season_players.filter(is_active=True)]
            active_player_ratings = [r for r in active_player_ratings if r is not None]
            all_player_ratings = [sp.player.player_rating_display(self.league) for sp in
                                  season_players]
            all_player_ratings = [r for r in all_player_ratings if r is not None]

            all_pairings = PlayerPairing.objects.filter(
                loneplayerpairing__round__season=self.season) \
                .select_related('loneplayerpairing', 'white', 'black') \
                .nocache()
            total = 0.0
            rating_total = 0.0
            counts = [0, 0, 0, 0]
            rating_delta = 0
            abs_rating_delta = 0
            rating_delta_counts = [0, 0, 0, 0, 0, 0]
            upset_counts = [0, 0, 0, 0, 0, 0]
            for p in all_pairings:
                if p.game_link == '' or p.result == '' or not p.game_played():
                    # Don't count forfeits etc
                    continue
                total += 1
                if p.white_rating_display(self.league) is not None and p.black_rating_display(
                    self.league) is not None:
                    d = p.white_rating_display(self.league) - p.black_rating_display(self.league)
                    rating_delta += d
                    abs_rating_delta += abs(d)
                    rating_delta_index = int(min(math.floor(abs(d) / 100.0), 5))
                    rating_delta_counts[rating_delta_index] += 1
                    if math.copysign(1,
                                     p.white_rating_display(self.league) - p.black_rating_display(
                                         self.league)) == p.black_score() - p.white_score() \
                        and p.white_rating_display(self.league) != p.black_rating_display(
                        self.league):
                        upset_counts[rating_delta_index] += 1
                    if p.white_score() == p.black_score():
                        upset_counts[rating_delta_index] += 0.5
                    rating_total += 1
                if p.result == '1-0':
                    counts[0] += 1
                    counts[3] += 1
                elif p.result == '0-1':
                    counts[2] += 1
                    counts[3] -= 1
                elif p.result == '1/2-1/2':
                    counts[1] += 1

            if total == 0:
                return self.render('tournament/lone_stats.html', {
                    'active_player_ratings': active_player_ratings,
                    'all_player_ratings': all_player_ratings,
                })

            win_counts = tuple(counts)
            win_percents = tuple((c / total for c in counts))
            win_rating_delta = rating_delta / total
            rating_delta_average = abs_rating_delta / total
            rating_delta_counts = tuple(rating_delta_counts)
            rating_delta_percents = tuple((c / total for c in rating_delta_counts))
            upset_percents = tuple((c1 / float(c2) if c2 > 0 else 0 for c1, c2 in
                                    zip(upset_counts, rating_delta_counts)))

            context = {
                'has_win_rate_stats': win_counts != (0, 0, 0, 0),
                'win_rating_delta': win_rating_delta,
                'win_counts': win_counts,
                'win_percents': win_percents,
                'has_rating_delta_stats': rating_delta_counts != (0, 0, 0, 0, 0, 0),
                'rating_delta_counts': rating_delta_counts,
                'rating_delta_percents': rating_delta_percents,
                'rating_delta_average': rating_delta_average,
                'upset_percents': upset_percents,
                'active_player_ratings': active_player_ratings,
                'all_player_ratings': all_player_ratings,
            }
            return self.render('tournament/lone_stats.html', context)

        return _view(self.league.tag, self.season.tag, self.user_data)


class ActivePlayerTableView(LeagueView):
    @cached_as(PlayerPairing)
    def view(self, page: int = 1):
        tablesums = self.league.get_active_players()

        paginator = Paginator(tablesums, DEFAULT_PAGE_SIZE)
        page_obj = paginator.get_page(page)

        pks = [player.player_id for player in page_obj.object_list]
        seasondatafull = SeasonPlayer.objects.filter(player__pk__in = pks, season__league=self.league).values("player__pk").annotate(
                season_count = Count("player__pk"),
                ).values("player__lichess_username", "player__pk", "season_count")

        seasondata = {pl["player__pk"]: [pl["player__lichess_username"], pl["season_count"]] for pl in seasondatafull}

        oneplayer = namedtuple('oneplayer', ['game_count', 'lichess_username', 'season_count', 'last_played'])
        subtable = []

        for player in page_obj.object_list:
            subtable.append(oneplayer._make([player.game_count, *seasondata[player.player_id], player.last_played]))

        context = {
            "page_obj": page_obj,
            "subtable": subtable,
        }

        if page == 1:
            total_players = len(tablesums)
            total_games = 0
            for player in tablesums:
                total_games += player.game_count
            total_games = int(total_games/2) # there's always 2 players that play the game.
            context.update({"total_games": total_games, "total_players": total_players})

        return self.render("tournament/active_players.html", context)


class BoardScoresView(SeasonView):
    def view(self, board_number):
        if self.league.is_team_league():
            return self.team_view(board_number)
        else:
            raise Http404

    def team_view(self, board_number):
        @cached_as(League, Season, Round, TeamPlayerPairing, PlayerPairing)
        def _view(league_tag, season_tag, user_data, board_number):
            board_pairings = PlayerPairing.objects.filter(
                teamplayerpairing__team_pairing__round__season=self.season) \
                .exclude(white=None).exclude(black=None) \
                .select_related('teamplayerpairing', 'white', 'black') \
                .order_by('teamplayerpairing__team_pairing__round__number') \
                .nocache()

            class PlayerScore():
                def __init__(self, player):
                    self.player = player
                    self.name = player.lichess_username
                    self.score = 0
                    self.score_total = 0
                    self.perf = PerfRatingCalc()
                    self.perf_rating = None
                    self.eligible = True

            ps_dict = {}  # Player -> PlayerScore
            games_dict = defaultdict(list)  # Player -> list of PlayerPairing

            for pairing in board_pairings:
                games_dict[pairing.white].append(pairing)
                games_dict[pairing.black].append(pairing)

                if pairing.teamplayerpairing.board_number != int(board_number):
                    continue
                white_ps = ps_dict[pairing.white] = ps_dict.get(pairing.white,
                                                                PlayerScore(pairing.white))
                black_ps = ps_dict[pairing.black] = ps_dict.get(pairing.black,
                                                                PlayerScore(pairing.black))

                white_game_score = pairing.white_score()
                if white_game_score is not None:
                    white_ps.score += white_game_score
                    white_ps.score_total += 1
                    if pairing.game_played():
                        white_ps.perf.add_game(white_game_score,
                                               pairing.black_rating_display(self.league))

                black_game_score = pairing.black_score()
                if black_game_score is not None:
                    black_ps.score += black_game_score
                    black_ps.score_total += 1
                    if pairing.game_played():
                        black_ps.perf.add_game(black_game_score,
                                               pairing.white_rating_display(self.league))

            def process_playerscore(ps):
                # Exclude players that played primarily on other boards
                total_game_count = len(games_dict[ps.player])
                if ps.score_total < total_game_count / 2.0 or ps.score_total < 2:
                    return False
                # Precalculate perf rating
                ps.perf_rating = ps.perf.calculate()
                # Try to calculate an overall perf rating if you can't get one just for the board
                if ps.perf_rating is None:
                    ps.perf = PerfRatingCalc()
                    for g in games_dict[ps.player]:
                        if g.game_played():
                            if g.white == ps.player:
                                ps.perf.add_game(g.white_score(),
                                                 g.black_rating_display(self.league))
                            else:
                                ps.perf.add_game(g.black_score(),
                                                 g.white_rating_display(self.league))
                    ps.perf_rating = ps.perf.calculate()
                    ps.eligible = False
                return True

            ps_list = [ps for ps in list(ps_dict.values()) if process_playerscore(ps)]
            ps_list.sort(key=lambda ps: (ps.perf_rating or 0, ps.score, -ps.score_total),
                         reverse=True)

            context = {
                'board_number': board_number,
                'player_scores': ps_list
            }
            return self.render('tournament/team_board_scores.html', context)

        return _view(self.league.tag, self.season.tag, self.user_data, board_number)


class LeagueDashboardView(LeagueView):
    def view(self):
        if self.league.is_team_league():
            return self.team_view()
        else:
            return self.lone_view()
    
    def post(self, request, *args, **kwargs):
        """Handle POST requests for knockout tournament advancement, match creation, and cache clearing."""
        self.read_context()
        self.read_user_data()
        
        # Handle cache clearing
        if 'clear_cache' in request.POST:
            return self._handle_cache_clear()
        
        # Handle tournament advancement (knockout tournaments only)
        if ('advance_tournament' in request.POST 
            and self.season.league.pairing_type.startswith('knockout')):
            return self._handle_knockout_advancement()
        
        # Handle creating missing matches for multi-match knockouts
        if ('create_missing_matches' in request.POST
            and self.season.league.pairing_type.startswith('knockout')):
            return self._handle_create_missing_matches()

        if 'validate_tokens' in request.POST:
            return self._handle_validate_tokens()

        if 'update_fide_ratings' in request.POST:
            return self._handle_update_fide_ratings()

        if 'backfill_fide_data' in request.POST:
            return self._handle_backfill_fide_data()

        # If it's not a knockout-related request, fall back to GET behavior
        return self.view()
    
    def _handle_cache_clear(self):
        """Clear all caches."""
        try:
            from django.contrib import messages
            from django.core.cache import cache
            
            # Clear Django cache
            cache.clear()
            
            # Clear cacheops cache if available
            try:
                from cacheops import invalidate_all
                invalidate_all()
                messages.success(self.request, "All caches cleared successfully (Django cache + cacheops)!")
            except ImportError:
                messages.success(self.request, "Django cache cleared successfully!")
                
        except Exception as e:
            from django.contrib import messages
            messages.error(self.request, f"Error clearing cache: {str(e)}")

        return self.view()

    def _handle_validate_tokens(self):
        from django.contrib import messages
        signals.do_validate_season_tokens.send(
            sender=self.__class__, season_id=self.season.pk
        )
        messages.success(
            self.request,
            "Token validation started. Refresh this page to see results.",
        )
        return self.view()

    def _handle_update_fide_ratings(self):
        from django.contrib import messages
        from heltour.tournament.tasks import update_fide_ratings
        update_fide_ratings.delay()
        messages.success(
            self.request,
            "FIDE ratings update started. This runs in the background.",
        )
        return self.view()

    def _handle_backfill_fide_data(self):
        from django.contrib import messages
        from heltour.tournament.tasks import backfill_fide_data_for_season
        backfill_fide_data_for_season.delay(self.season.pk)
        messages.success(
            self.request,
            "Backfill started: copying FIDE IDs and gender from registrations to "
            "players, then fetching FIDE profiles. This runs in the background.",
        )
        return self.view()

    def _common_context(self):
        current_season_list, completed_season_list = _get_season_lists(self.league,
                                                                       active_only=False)

        reg_season = self.season
        if not self.season.registration_open:
            for s in self.season.section_list():
                if s.is_active and s.registration_open:
                    reg_season = s
                    break

        pending_reg_count = len(Registration.objects.filter(season=reg_season, status='pending'))
        pending_modreq_count = len(ModRequest.objects.filter(season=self.season, status='pending'))

        team_members = TeamMember.objects.filter(team__season=self.season).select_related(
            'player').nocache()
        alternates = Alternate.objects.filter(season_player__season=self.season).select_related(
            'season_player__player').nocache()
        season_players = set(sp.player for sp in SeasonPlayer.objects.filter(season=self.season,
                                                                             is_active=True).select_related(
            'player').nocache())
        team_players = set(tm.player for tm in team_members)
        alternate_players = set(alt.season_player.player for alt in alternates)
        unassigned_player_count = len(season_players - team_players - alternate_players)

        alternate_search_round = alternates_manager.current_round(self.season)
        alternate_search_count = len(alternates_manager.current_searches(
            alternate_search_round)) if alternate_search_round is not None else None

        last_round = Round.objects.filter(season=self.season, publish_pairings=True,
                                          is_completed=False).order_by('number').first()
        next_round = Round.objects.filter(season=self.season, publish_pairings=False,
                                          is_completed=False).order_by('number').first()

        # Check if this is a knockout tournament
        is_knockout = self.season.league.pairing_type.startswith('knockout')
        knockout_advancement_info = None
        
        if is_knockout and self.request.user.is_staff:
            knockout_advancement_info = self._get_knockout_advancement_info()

        token_validation_status = cache.get(f"token_validation_{self.season.pk}")
        system_api_token_status = lichessapi.check_system_api_token()

        from django_celery_results.models import TaskResult
        recent_task_results = list(
            TaskResult.objects.order_by("-date_created")[:25]
        )

        return {
            'current_season_list': current_season_list,
            'completed_season_list': completed_season_list,
            'pending_reg_count': pending_reg_count,
            'pending_modreq_count': pending_modreq_count,
            'unassigned_player_count': unassigned_player_count,
            'alternate_search_count': alternate_search_count,
            'last_round': last_round,
            'next_round': next_round,
            'reg_season': reg_season,
            'celery_down': uptime.celery.is_down,
            'can_view_dashboard': self.request.user.has_perm('tournament.view_dashboard',
                                                             self.league),
            'can_admin_users': self.request.user.has_module_perms('auth'),
            'is_knockout_tournament': is_knockout,
            'knockout_advancement_info': knockout_advancement_info,
            'token_validation_status': token_validation_status,
            'system_api_token_status': system_api_token_status,
            'recent_task_results': recent_task_results,
        }

    def team_view(self):
        context = self._common_context()
        return self.render('tournament/team_league_dashboard.html', context)

    def lone_view(self):
        context = self._common_context()
        return self.render('tournament/lone_league_dashboard.html', context)
    
    def _get_knockout_advancement_info(self):
        """Get information about knockout tournament advancement status for admin."""
        if not self.request.user.is_staff:
            return None
            
        # If season is already completed, no advancement options should be available
        if self.season.is_completed:
            return {
                'can_advance': False,
                'reason': 'Tournament already completed',
                'round_to_advance': None,
                'tied_matches': [],
                'multi_match_info': None,
                'can_generate_next_match_set': False,
                'is_final_round': False,
            }
        
        try:
            from heltour.tournament.models import KnockoutBracket
            bracket = KnockoutBracket.objects.get(season=self.season)
        except KnockoutBracket.DoesNotExist:
            return {
                'can_advance': False,
                'reason': 'No knockout bracket found',
                'round_to_advance': None,
                'tied_matches': [],
                'multi_match_info': None,
                'can_generate_next_match_set': False,
            }
            
        # Check for multi-match tournament logic first
        is_multi_match = bracket.matches_per_stage > 1
        
        # Find the current round to work with
        # For multi-match tournaments, we might need to work with incomplete rounds
        current_round = None
        last_completed_round = None
        
        if is_multi_match:
            # For multi-match, look for the most recent round with any pairings
            from heltour.tournament.models import TeamPairing
            
            # Find rounds that have pairings, ordered by round number descending
            rounds_with_pairings = Round.objects.filter(
                season=self.season,
                teampairing__isnull=False
            ).distinct().order_by('-number')
            
            if rounds_with_pairings.exists():
                current_round = rounds_with_pairings.first()
            else:
                # No rounds have pairings yet, use Round 1 (first round) for fresh tournaments
                current_round = Round.objects.filter(
                    season=self.season
                ).order_by('number').first()
            
            # Also track the last truly completed round
            last_completed_round = Round.objects.filter(
                season=self.season, 
                is_completed=True
            ).order_by('-number').first()
        else:
            # For single-match, use the last completed round
            last_completed_round = Round.objects.filter(
                season=self.season, 
                is_completed=True
            ).order_by('-number').first()
            current_round = last_completed_round
        
        if not current_round:
            return {
                'can_advance': False,
                'reason': 'No rounds found',
                'round_to_advance': None,
                'tied_matches': [],
                'multi_match_info': None,
                'can_generate_next_match_set': False,
            }
        
        # Special case: if this is a fresh tournament with no pairings yet,
        # show the "Create Missing Matches" option
        if is_multi_match:
            from heltour.tournament.models import TeamPairing
            existing_pairings = TeamPairing.objects.filter(round=current_round).count()
            if existing_pairings == 0:
                # Calculate expected team pairs from active teams
                try:
                    from heltour.tournament.models import Team
                    active_teams = Team.objects.filter(season=current_round.season, is_active=True).count()
                    expected_team_pairs = active_teams // 2
                    total_matches_expected = expected_team_pairs * bracket.matches_per_stage
                except Exception:
                    expected_team_pairs = 0
                    total_matches_expected = 0
                
                return {
                    'can_advance': False,
                    'reason': 'No matches created yet for this round',
                    'round_to_advance': current_round,
                    'tied_matches': [],
                    'multi_match_info': {
                        'is_complete': False,
                        'reason': 'No matches created yet. Use "Create Missing Matches" to generate initial match set.',
                        'expected_team_pairs': expected_team_pairs,
                        'completed_team_pairs': 0,
                        'total_matches_expected': total_matches_expected,
                        'total_matches_actual': 0,
                        'total_matches_completed': 0,
                        'incomplete_pairs': [],
                        'matches_per_stage': bracket.matches_per_stage,
                        'status_message': f'Ready to create match 1 of {bracket.matches_per_stage}',
                    },
                    'can_generate_next_match_set': True,  # Allow creating first match set
                }
        
        # Get multi-match completion info
        multi_match_info = None
        if is_multi_match:
            try:
                multi_match_info = self._get_multi_match_completion_info(current_round, bracket)
            except Exception as e:
                # If we can't get multi-match info (e.g., no pairings exist), create a minimal info object
                logger.error(f"ERROR: Could not get multi-match info for round {current_round.number}: {str(e)}")
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
                logger.error("This should NOT happen if pairings exist!")
                # Calculate expected team pairs from active teams
                try:
                    from heltour.tournament.models import Team
                    active_teams = Team.objects.filter(season=current_round.season, is_active=True).count()
                    expected_team_pairs = active_teams // 2
                    total_matches_expected = expected_team_pairs * bracket.matches_per_stage
                except Exception:
                    expected_team_pairs = 0
                    total_matches_expected = 0
                
                multi_match_info = {
                    'is_complete': False,
                    'reason': 'No pairings found for this round',
                    'expected_team_pairs': expected_team_pairs,
                    'completed_team_pairs': 0,
                    'total_matches_expected': total_matches_expected,
                    'total_matches_actual': 0,
                    'total_matches_completed': 0,
                    'incomplete_pairs': [],
                    'matches_per_stage': bracket.matches_per_stage,
                    'status_message': f'Ready to create match 1 of {bracket.matches_per_stage}',
                }
        
        # For multi-match tournaments, check if we can generate next match set
        can_generate_next_match_set = False
        if is_multi_match and multi_match_info:
            # Can generate next match set if:
            # 1. All existing matches are complete (have results)
            # 2. We haven't reached the total expected matches for this stage
            # 3. We have some matches created (not a fresh tournament)
            
            all_existing_complete = (
                multi_match_info['total_matches_actual'] > 0 and  # Have some matches
                multi_match_info['total_matches_completed'] == multi_match_info['total_matches_actual']  # All complete
            )
            has_missing_matches = (
                multi_match_info['total_matches_actual'] < multi_match_info['total_matches_expected']
            )
            
            # Determine if we can generate next match set:
            if multi_match_info['total_matches_actual'] == 0:
                # Fresh tournament - can create initial matches
                can_generate_next_match_set = True
            elif has_missing_matches and all_existing_complete:
                # Current match set is complete, can create next set
                can_generate_next_match_set = True
            else:
                # Either all matches created OR current matches not complete yet
                can_generate_next_match_set = False
            
            # Check if we're ready to advance to next round
            if multi_match_info['is_complete']:
                # All matches for this stage are complete, can check for advancement
                pass
            else:
                # Not all matches complete/created yet
                return {
                    'can_advance': False,
                    'reason': multi_match_info['reason'],
                    'round_to_advance': current_round,
                    'tied_matches': [],
                    'multi_match_info': multi_match_info,
                    'can_generate_next_match_set': can_generate_next_match_set,
                }
        
        # Check the round to advance from (for single-match or completed multi-match)
        round_to_advance = last_completed_round if last_completed_round else current_round
        
        # Check for tied matches that need manual tiebreak resolution
        tied_matches = []
        if self.league.competitor_type == 'team':
            if is_multi_match:
                # For multi-match, check aggregate ties
                tied_matches = self._get_multi_match_tied_pairs(round_to_advance, bracket)
            else:
                # For single-match, check individual pairing ties
                tied_pairings = TeamPairing.objects.filter(
                    round=round_to_advance,
                    white_points__isnull=False,
                    black_points__isnull=False,
                    manual_tiebreak_value__isnull=True
                ).filter(
                    white_points=F('black_points')
                ).select_related('white_team', 'black_team')
                
                for pairing in tied_pairings:
                    tied_matches.append({
                        'id': pairing.id,
                        'competitor1': pairing.white_team.name,
                        'competitor2': pairing.black_team.name,
                        'score': pairing.white_points,
                    })
        else:
            # Individual tournaments - handle ties differently
            # For now, assume individual tournaments don't need manual tiebreak resolution
            pass
        
        # Determine if we can advance
        can_advance = len(tied_matches) == 0
        reason = None
        if not can_advance:
            reason = f"{len(tied_matches)} tied match(es) require manual tiebreak resolution"
        
        # Check if this is the final scheduled round
        is_final_round = False
        if hasattr(self.season, 'rounds') and self.season.rounds and round_to_advance:
            is_final_round = round_to_advance.number >= self.season.rounds
        
        return {
            'can_advance': can_advance,
            'reason': reason,
            'round_to_advance': round_to_advance,
            'tied_matches': tied_matches,
            'is_final_round': is_final_round,
            'multi_match_info': multi_match_info,
            'can_generate_next_match_set': can_generate_next_match_set,
        }
    
    def _handle_knockout_advancement(self):
        """Handle POST request to advance the knockout tournament."""
        if not self.request.user.is_staff:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Only staff can advance tournaments")
        
        try:
            from heltour.tournament.pairinggen import advance_knockout_tournament
            from django.contrib import messages
            from django.shortcuts import redirect
            
            # Find the round to advance from
            # For multi-match tournaments, we need to use the advancement info logic
            # since rounds may not be formally marked complete even when all matches are done
            advancement_info = self._get_knockout_advancement_info()
            round_to_advance = advancement_info.get('round_to_advance')
            
            if not round_to_advance:
                messages.error(self.request, "No rounds ready to advance from")
                return redirect(self.request.path)
            
            # For compatibility, set last_completed_round for the rest of the logic
            last_completed_round = round_to_advance
            
            # Check for unresolved tied matches
            if not advancement_info['can_advance']:
                messages.error(self.request, f"Cannot advance tournament: {advancement_info['reason']}")
                return redirect(self.request.path)
            
            # Check if this is the final round - if so, finalize the tournament
            if advancement_info['is_final_round']:
                # Finalize tournament standings instead of creating new round
                self.season.is_completed = True
                self.season.save()
                
                # Calculate final standings and create advancement records
                from heltour.tournament.models import KnockoutBracket, KnockoutAdvancement
                try:
                    bracket = KnockoutBracket.objects.get(season=self.season)
                    
                    # Get winners from the final round
                    if self.league.competitor_type == 'team':
                        # Use the same multi-match logic as advancement
                        if bracket.matches_per_stage > 1:
                            # Multi-match tournament: aggregate scores by team pair
                            from heltour.tournament.pairinggen import _get_multi_match_winners
                            winners = _get_multi_match_winners(last_completed_round, bracket)
                        else:
                            # Single-match tournament: use individual pairing results
                            winners = []
                            team_pairings = TeamPairing.objects.filter(round=last_completed_round).order_by('pairing_order')
                            
                            for pairing in team_pairings:
                                if pairing.black_team_id is None:
                                    # Bye situation - white team advances
                                    winners.append(pairing.white_team)
                                else:
                                    # Determine winner based on points and manual tiebreak
                                    if pairing.manual_tiebreak_value is not None:
                                        if pairing.manual_tiebreak_value > 0:
                                            winners.append(pairing.white_team)
                                        elif pairing.manual_tiebreak_value < 0:
                                            winners.append(pairing.black_team)
                                        # If tiebreak is 0, it's still a tie - this shouldn't happen
                                    elif pairing.white_points is not None and pairing.black_points is not None:
                                        if pairing.white_points > pairing.black_points:
                                            winners.append(pairing.white_team)
                                        elif pairing.black_points > pairing.white_points:
                                            winners.append(pairing.black_team)
                                        # If points are equal and no manual tiebreak, this shouldn't happen
                        
                        # Create advancement records for the final winners
                        # For the final round, winners advance to "final" (not to another round)
                        final_stage = "final"
                        
                        # Determine from_stage - use knockout_stage if set, otherwise calculate it
                        from_stage = last_completed_round.knockout_stage
                        if not from_stage:
                            # Calculate knockout stage based on round number and bracket size
                            from heltour.tournament_core.knockout import get_knockout_stage_name as calc_stage_name
                            teams_remaining = bracket.bracket_size // (2 ** (last_completed_round.number - 1))
                            from_stage = calc_stage_name(teams_remaining)
                        
                        for winner_team in winners:
                            KnockoutAdvancement.objects.get_or_create(
                                bracket=bracket,
                                team=winner_team,
                                from_stage=from_stage,
                                to_stage=final_stage,
                                defaults={
                                    'advanced_date': timezone.now(),
                                }
                            )
                        
                        winner_count = len(winners)
                        messages.success(
                            self.request, 
                            f"Tournament standings finalized! {winner_count} winners determined."
                        )
                    else:
                        # Handle individual tournaments similarly
                        messages.success(self.request, "Tournament standings finalized!")
                        
                except KnockoutBracket.DoesNotExist:
                    messages.success(self.request, "Tournament standings finalized!")
            else:
                # Perform normal advancement to next round
                next_round = advance_knockout_tournament(last_completed_round)
                
                if next_round:
                    messages.success(
                        self.request, 
                        f"Successfully advanced tournament to Round {next_round.number}"
                    )
                else:
                    messages.success(self.request, "Tournament has been completed - all rounds finished")
            
            return redirect(self.request.path)
            
        except Exception as e:
            from django.contrib import messages
            messages.error(self.request, f"Error advancing tournament: {str(e)}")
            return redirect(self.request.path)
    
    def _get_multi_match_completion_info(self, round_obj, bracket):
        """Get detailed completion info for multi-match knockout rounds."""
        from collections import defaultdict
        
        matches_per_stage = bracket.matches_per_stage
        
        # Group team pairings by team pairs
        team_pair_groups = defaultdict(list)
        team_pairings = TeamPairing.objects.filter(round=round_obj).select_related('white_team', 'black_team')
        
        for pairing in team_pairings:
            if pairing.black_team:  # Skip byes
                # Create consistent key for team pair
                team_key = tuple(sorted([pairing.white_team.id, pairing.black_team.id]))
                team_pair_groups[team_key].append(pairing)
        
        # Analyze completion status
        expected_team_pairs = len(team_pair_groups)
        
        # If no pairings exist yet, calculate expected team pairs from seedings
        if expected_team_pairs == 0:
            try:
                from heltour.tournament.models import KnockoutSeeding
                active_teams = Team.objects.filter(season=round_obj.season, is_active=True).count()
                expected_team_pairs = active_teams // 2  # Each pair plays against each other
            except Exception:
                expected_team_pairs = 0
        
        completed_team_pairs = 0
        incomplete_pairs = []
        total_matches_expected = expected_team_pairs * matches_per_stage
        total_matches_actual = len(team_pairings)
        total_matches_completed = 0
        
        for team_key, pairings in team_pair_groups.items():
            team1 = Team.objects.get(id=team_key[0])
            team2 = Team.objects.get(id=team_key[1])
            
            completed_matches = 0
            for pairing in pairings:
                board_pairings = pairing.teamplayerpairing_set.all()
                board_count = board_pairings.count()
                
                # Skip pairings without board pairings - they can't be complete
                if board_count == 0:
                    logger.warning(f"TeamPairing {pairing.id} has no board pairings")
                    continue
                    
                completed_boards = board_pairings.filter(result__isnull=False).exclude(result='').count()
                is_match_completed = completed_boards > 0 and completed_boards == board_count
                if is_match_completed:
                    completed_matches += 1
                    total_matches_completed += 1
            
            if completed_matches == len(pairings) and len(pairings) == matches_per_stage:
                completed_team_pairs += 1
            else:
                incomplete_pairs.append({
                    'team1': team1.name,
                    'team2': team2.name,
                    'completed_matches': completed_matches,
                    'expected_matches': matches_per_stage,
                    'actual_matches': len(pairings),
                })
        
        is_complete = completed_team_pairs == expected_team_pairs and total_matches_actual == total_matches_expected
        
        if not is_complete:
            if total_matches_actual < total_matches_expected:
                reason = f"Only {total_matches_actual}/{total_matches_expected} matches created. Missing {total_matches_expected - total_matches_actual} matches."
            else:
                reason = f"Only {total_matches_completed}/{total_matches_expected} matches completed. {total_matches_expected - total_matches_completed} matches still in progress."
        else:
            reason = "All matches complete"
        
        # Calculate status message
        if total_matches_actual == 0:
            status_message = f'Ready to create match 1 of {matches_per_stage}'
        elif is_complete:
            # All matches are complete
            status_message = f'All {matches_per_stage} matches complete - ready to advance'
        elif expected_team_pairs > 0:
            # Calculate which match we're currently on based on completed matches
            completed_match_sets = total_matches_completed // expected_team_pairs
            current_match_number = completed_match_sets + 1
            
            if total_matches_actual % expected_team_pairs == 0:
                # Complete set of matches created
                if completed_match_sets == matches_per_stage:
                    # All matches complete
                    status_message = f'All {matches_per_stage} matches complete - ready to advance'
                elif completed_match_sets > 0:
                    # Some matches complete, need next set
                    status_message = f'Match {completed_match_sets} of {matches_per_stage} complete'
                else:
                    # First set created but not complete
                    completed_in_current = total_matches_completed % expected_team_pairs
                    status_message = f'Match 1 in progress ({completed_in_current}/{expected_team_pairs} matches completed)'
            else:
                # Partial set of matches created
                actual_in_current = total_matches_actual % expected_team_pairs
                status_message = f'Match {current_match_number} in progress ({actual_in_current}/{expected_team_pairs} matches created)'
        else:
            status_message = f'Ready to create initial matches'
        
        return {
            'is_complete': is_complete,
            'reason': reason,
            'expected_team_pairs': expected_team_pairs,
            'completed_team_pairs': completed_team_pairs,
            'total_matches_expected': total_matches_expected,
            'total_matches_actual': total_matches_actual,
            'total_matches_completed': total_matches_completed,
            'incomplete_pairs': incomplete_pairs,
            'matches_per_stage': matches_per_stage,
            'status_message': status_message,
        }
    
    def _get_multi_match_tied_pairs(self, round_obj, bracket):
        """Get team pairs with tied aggregate scores in multi-match tournaments."""
        from collections import defaultdict
        
        tied_matches = []
        team_pair_groups = defaultdict(list)
        team_pairings = TeamPairing.objects.filter(round=round_obj).select_related('white_team', 'black_team')
        
        for pairing in team_pairings:
            if pairing.black_team:  # Skip byes
                team_key = tuple(sorted([pairing.white_team.id, pairing.black_team.id]))
                team_pair_groups[team_key].append(pairing)
        
        for team_key, pairings in team_pair_groups.items():
            team1 = Team.objects.get(id=team_key[0])
            team2 = Team.objects.get(id=team_key[1])
            
            # Calculate aggregate scores
            total_team1_points = 0.0
            total_team2_points = 0.0
            all_matches_completed = True
            has_manual_tiebreak = False
            
            for pairing in pairings:
                # Check if this match is completed
                board_pairings = pairing.teamplayerpairing_set.all()
                board_count = board_pairings.count()
                
                # Skip pairings without board pairings
                if board_count == 0:
                    all_matches_completed = False
                    break
                    
                completed_boards = board_pairings.filter(result__isnull=False).exclude(result='').count()
                is_match_completed = completed_boards > 0 and completed_boards == board_count
                
                if not is_match_completed:
                    all_matches_completed = False
                    break
                
                # Check for manual tiebreak
                if pairing.manual_tiebreak_value is not None:
                    has_manual_tiebreak = True
                    break
                
                # Add to aggregate scores
                if pairing.white_team.id == team1.id:
                    total_team1_points += pairing.white_points or 0.0
                    total_team2_points += pairing.black_points or 0.0
                else:
                    total_team1_points += pairing.black_points or 0.0
                    total_team2_points += pairing.white_points or 0.0
            
            # Check if this pair is tied and needs manual resolution
            if (all_matches_completed and not has_manual_tiebreak and 
                len(pairings) == bracket.matches_per_stage and
                abs(total_team1_points - total_team2_points) < 0.001):  # Float comparison
                
                tied_matches.append({
                    'id': pairings[0].id,  # Use first pairing ID for link
                    'competitor1': team1.name,
                    'competitor2': team2.name,
                    'score': total_team1_points,
                })
        
        return tied_matches
    
    def _handle_create_missing_matches(self):
        """Handle POST request to create missing matches for multi-match knockout."""
        if not self.request.user.is_staff:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Only staff can create matches")
        
        try:
            from django.contrib import messages
            from django.shortcuts import redirect
            from heltour.tournament.models import KnockoutBracket
            
            messages.info(self.request, "Processing create missing matches request...")
            
            bracket = KnockoutBracket.objects.get(season=self.season)
            
            # Get the round that the dashboard is showing info about
            # Use the SAME logic as _get_knockout_advancement_info to avoid inconsistency
            advancement_info = self._get_knockout_advancement_info()
            active_round = advancement_info.get('round_to_advance')
            
            if not active_round:
                messages.error(self.request, "No active round found for match creation")
                return redirect(self.request.path)
            
            try:
                multi_match_info = self._get_multi_match_completion_info(active_round, bracket)
            except Exception as e:
                logger.error(f"Error getting multi-match info: {str(e)}")
                # Try to handle the specific case of pairings without board pairings
                from heltour.tournament.models import TeamPlayerPairing
                
                # Find and fix any pairings without board pairings
                problem_pairings = TeamPairing.objects.filter(
                    round=active_round
                ).exclude(black_team__isnull=True)  # Exclude byes
                
                fixed_count = 0
                for pairing in problem_pairings:
                    if pairing.teamplayerpairing_set.count() == 0:
                        logger.warning(f"Found pairing without board pairings: {pairing.white_team.name} vs {pairing.black_team.name}")
                        # Create board pairings for this pairing
                        self._create_board_pairings_for_knockout_pairing(pairing, active_round.season.boards)
                        fixed_count += 1
                
                if fixed_count > 0:
                    logger.info(f"Fixed {fixed_count} pairings with missing board pairings")
                    # Try again
                    try:
                        multi_match_info = self._get_multi_match_completion_info(active_round, bracket)
                    except:
                        messages.error(self.request, "Unable to analyze round status. Please check for pairings without board results.")
                        return redirect(self.request.path)
                else:
                    messages.error(self.request, f"Error analyzing round: {str(e)}")
                    return redirect(self.request.path)
            
            # Debug logging
            logger.info(f"Creating missing matches for round {active_round.number}")
            logger.info(f"Expected: {multi_match_info['total_matches_expected']}, Actual: {multi_match_info['total_matches_actual']}")
            logger.info(f"Expected team pairs: {multi_match_info['expected_team_pairs']}")
            logger.info(f"Matches per stage: {multi_match_info['matches_per_stage']}")
            logger.info(f"Multi-match info: {multi_match_info}")
            
            if multi_match_info['total_matches_actual'] >= multi_match_info['total_matches_expected']:
                logger.warning(f"Condition failed: {multi_match_info['total_matches_actual']} >= {multi_match_info['total_matches_expected']}")
                messages.info(self.request, f"All required matches already exist ({multi_match_info['total_matches_actual']}/{multi_match_info['total_matches_expected']})")
                return redirect(self.request.path)
            
            # Create missing matches
            created_count = self._create_missing_knockout_matches(active_round, bracket, multi_match_info)
            
            if created_count > 0:
                messages.success(
                    self.request, 
                    f"Successfully created {created_count} missing matches"
                )
            else:
                messages.info(self.request, "No matches needed to be created")
            
            return redirect(self.request.path)
            
        except ValueError as ve:
            # This is likely the db_to_structure error
            from django.contrib import messages
            import traceback
            logger.error(f"ValueError creating matches: {str(ve)}")
            logger.error(traceback.format_exc())
            
            # Check if this is happening AFTER we created pairings
            logger.info("Checking for recently created pairings without board pairings...")
            recent_pairings = TeamPairing.objects.filter(
                round__season=self.season
            ).order_by('-id')[:10]  # Check last 10 created pairings
            
            for p in recent_pairings:
                board_count = p.teamplayerpairing_set.count()
                if board_count == 0:
                    logger.error(f"Found recent pairing without boards: ID {p.id}, {p.white_team.name} vs {p.black_team.name if p.black_team else 'BYE'}")
            
            messages.error(self.request, f"Error creating matches: {str(ve)}")
            return redirect(self.request.path)
        except Exception as e:
            from django.contrib import messages
            import traceback
            logger.error(f"Error creating matches: {str(e)}")
            logger.error(traceback.format_exc())
            messages.error(self.request, f"Error creating matches: {str(e)}")
            return redirect(self.request.path)
    
    def _create_missing_knockout_matches(self, round_obj, bracket, multi_match_info):
        """Create the missing matches for a multi-match knockout round."""
        from collections import defaultdict
        from django.db import transaction
        import reversion
        
        created_count = 0
        matches_per_stage = bracket.matches_per_stage
        
        # Group existing pairings by team pairs
        team_pair_groups = defaultdict(list)
        existing_pairings = TeamPairing.objects.filter(round=round_obj).select_related('white_team', 'black_team')
        
        logger.info(f"Found {existing_pairings.count()} existing pairings in round {round_obj.number}")
        logger.info(f"Round {round_obj.number} is_completed: {round_obj.is_completed}")
        
        # IMPORTANT: Temporarily mark round as not completed to avoid calculate_scores being called
        # when TeamPairing.save() is executed, before board pairings are created
        original_is_completed = round_obj.is_completed
        if original_is_completed:
            logger.info("Temporarily marking round as incomplete to prevent calculate_scores during pairing creation")
            round_obj.is_completed = False
            round_obj.save()
        
        try:
            for pairing in existing_pairings:
                if pairing.black_team:  # Skip byes
                    team_key = tuple(sorted([pairing.white_team.id, pairing.black_team.id]))
                    team_pair_groups[team_key].append(pairing)
                    logger.info(f"Added pairing {pairing.white_team.name} vs {pairing.black_team.name} to group {team_key}")
            
            # Create missing matches for each team pair
            with transaction.atomic():
                # If no existing pairings, we need to create initial pairings from seedings
                if len(team_pair_groups) == 0:
                    logger.info("No existing pairings found - creating initial tournament pairings from seedings")
                    created_count = self._create_initial_knockout_pairings(round_obj, bracket)
                else:
                    # Handle existing team pairs that need more matches
                    for team_key, existing_pairings_list in team_pair_groups.items():
                        needed_matches = matches_per_stage - len(existing_pairings_list)
                        
                        if needed_matches > 0:
                            team1 = Team.objects.get(id=team_key[0])
                            team2 = Team.objects.get(id=team_key[1])
                            
                            logger.info(f"Creating {needed_matches} matches for {team1.name} vs {team2.name}")
                        
                            # Determine next pairing order
                            max_pairing_order = TeamPairing.objects.filter(round=round_obj).aggregate(
                                max_order=Max('pairing_order')
                            )['max_order'] or 0
                            
                            logger.info(f"DEBUG: Current max_pairing_order: {max_pairing_order}, created_count: {created_count}")
                            
                            for i in range(needed_matches):
                                # For additional matches, alternate colors based on the first match
                                # Get the first match's color assignment
                                first_pairing = existing_pairings_list[0]
                                match_number_in_series = len(existing_pairings_list) + i + 1  # 1-based
                                
                                if match_number_in_series % 2 == 1:
                                    # Odd matches: use same colors as first match
                                    white_team = first_pairing.white_team
                                    black_team = first_pairing.black_team
                                else:
                                    # Even matches: swap colors from first match
                                    white_team = first_pairing.black_team
                                    black_team = first_pairing.white_team
                                
                                logger.info(f"Creating match {match_number_in_series}: {white_team.name} (white) vs {black_team.name} (black)")
                                
                                try:
                                    # Use a nested transaction to ensure atomicity
                                    from django.db import transaction as db_transaction
                                    
                                    with db_transaction.atomic():
                                        with reversion.create_revision():
                                            reversion.set_comment("Created missing multi-match pairing.")
                                            calculated_pairing_order = max_pairing_order + created_count + 1
                                            team_pairing = TeamPairing.objects.create(
                                                white_team=white_team,
                                                black_team=black_team,
                                                round=round_obj,
                                                pairing_order=calculated_pairing_order,
                                            )
                                            logger.info(f"DEBUG: Created pairing: {white_team.name} vs {black_team.name}, pairing_order={calculated_pairing_order} (max_pairing_order={max_pairing_order}, created_count={created_count})")
                                            
                                            # Create board pairings immediately in the same transaction
                                            self._create_board_pairings_for_knockout_pairing(team_pairing, round_obj.season.boards)
                                            
                                            # Verify board pairings were created
                                            board_count = team_pairing.teamplayerpairing_set.count()
                                            logger.info(f"Created {board_count} board pairings for pairing {team_pairing.id}")
                                            
                                            if board_count == 0:
                                                raise ValueError(f"Failed to create board pairings for {white_team.name} vs {black_team.name}")
                                            
                                            created_count += 1
                                except Exception as e:
                                    logger.error(f"Failed to create pairing for {white_team.name} vs {black_team.name}: {str(e)}")
                                    raise
        finally:
            # Restore original is_completed state
            if original_is_completed:
                logger.info("Restoring round completed status")
                round_obj.is_completed = True
                round_obj.save()
                
                # Now it's safe to recalculate scores if needed
                if created_count > 0:
                    logger.info("Recalculating scores after creating all pairings with board pairings")
                    round_obj.season.calculate_scores()
        
        return created_count
    
    def _create_board_pairings_for_knockout_pairing(self, team_pairing, board_count):
        """Create board pairings for a knockout team pairing."""
        import reversion
        
        white_player_list = self._get_player_list_for_team(team_pairing.white_team, team_pairing.round, board_count)
        black_player_list = self._get_player_list_for_team(team_pairing.black_team, team_pairing.round, board_count)
        
        for board_number in range(1, board_count + 1):
            white_player = white_player_list[board_number - 1] if board_number <= len(white_player_list) else None
            black_player = black_player_list[board_number - 1] if board_number <= len(black_player_list) else None
            
            # Alternate colors on even boards
            if board_number % 2 == 0:
                white_player, black_player = black_player, white_player
            
            with reversion.create_revision():
                reversion.set_comment("Created board pairing for multi-match.")
                TeamPlayerPairing.objects.create(
                    team_pairing=team_pairing,
                    board_number=board_number,
                    white=white_player,
                    black=black_player,
                )
    
    def _get_player_list_for_team(self, team, round_obj, board_count):
        """Get list of players for a team in a specific round."""
        # Simplified version - get team members by board order
        team_members = []
        for board_number in range(1, board_count + 1):
            member = TeamMember.objects.filter(team=team, board_number=board_number).first()
            if member:
                team_members.append(member.player)
            else:
                team_members.append(None)
        return team_members
    
    def _create_initial_knockout_pairings(self, round_obj, bracket):
        """Create initial knockout pairings from seedings."""
        from django.db import transaction
        import reversion
        
        # Get seeded teams
        from heltour.tournament.models import KnockoutSeeding
        seedings = KnockoutSeeding.objects.filter(bracket=bracket).order_by('seed_number')
        seeded_teams = [seeding.team for seeding in seedings if seeding.team]
        
        if len(seeded_teams) % 2 != 0:
            raise ValueError(f"Cannot create pairings with odd number of teams: {len(seeded_teams)}")
        
        # Generate pairings based on seeding style using proper bracket positioning
        from heltour.tournament_core.knockout import (
            generate_knockout_seedings_traditional,
            generate_knockout_seedings_adjacent,
        )
        
        team_ids = [team.id for team in seeded_teams]
        
        if bracket.seeding_style == "traditional":
            # Traditional seeding with proper bracket positioning
            pairing_tuples = generate_knockout_seedings_traditional(team_ids)
        else:  # adjacent
            # Adjacent seeding
            pairing_tuples = generate_knockout_seedings_adjacent(team_ids)
        
        # Convert team IDs back to team objects
        team_pairs = []
        for team1_id, team2_id in pairing_tuples:
            team1 = next(team for team in seeded_teams if team.id == team1_id)
            team2 = next(team for team in seeded_teams if team.id == team2_id)
            team_pairs.append((team1, team2))
        
        # Create pairings - only first match of each stage for multi-match
        created_count = 0
        pairing_order = 1
        
        for team1, team2 in team_pairs:
            with reversion.create_revision():
                reversion.set_comment("Created initial knockout pairing from seedings.")
                team_pairing = TeamPairing.objects.create(
                    white_team=team1,
                    black_team=team2,
                    round=round_obj,
                    pairing_order=pairing_order,
                )
                
                # Create board pairings immediately
                self._create_board_pairings_for_knockout_pairing(team_pairing, round_obj.season.boards)
                
                # Verify board pairings were created
                board_count = team_pairing.teamplayerpairing_set.count()
                
                if board_count == 0:
                    raise ValueError(f"Failed to create board pairings for {team1.name} vs {team2.name}")
                
                created_count += 1
                pairing_order += 1
        return created_count


class UserDashboardView(LeagueView):
    def view(self):
        if not self.request.user.is_authenticated:
            return redirect('by_league:league_home', self.league.tag)

        player = Player.get_or_create(self.request.user.username)

        slack_linked = bool(player.slack_user_id)
        slack_linked_just_now = False
        if self.request.session.get('slack_linked'):
            slack_linked_just_now = True
            del self.request.session['slack_linked']

        active_seasons = self.league.season_set.filter(is_completed=False).order_by('-start_date')
        active_seasons_with_sp = [(s, player.seasonplayer_set.filter(season=s).first()) for s in
                                  active_seasons]
        active_seasons_with_sp = [s for s in active_seasons_with_sp if s[1]]
        last_sp = player.seasonplayer_set.filter(season__league=self.league, season__is_active=True,
                                                 season__is_completed=True) \
            .order_by('-season__start_date').first()
        last_season = last_sp.season if last_sp is not None else None

        active_rounds = Round.objects.filter(publish_pairings=True, is_completed=False,
                                             season__is_active=True)

        approved = Registration.objects.filter(
            player__lichess_username=self.request.user.username, status="approved"
        ).exists()

        my_pairings = []
        for r in active_rounds:
            my_pairings += [(r, p) for p in
                            r.pairings.filter(white=player).exclude(black=None) | r.pairings.filter(
                                black=player).exclude(white=None)]

        def sort_order(round_, pairing):
            if pairing.game_link and not pairing.result:
                # In progress
                return (0, 0)
            if pairing.scheduled_time and not pairing.result:
                # Scheduled
                return (1, pairing.scheduled_time)
            # Unscheduled
            return (2, round_.end_date)

        my_pairings.sort(key=lambda r_p: sort_order(r_p[0], r_p[1]))

        # Check if user is a captain without a team for any active season
        captain_without_team_seasons = []
        team_membership_by_season = {}  # Maps season to team membership info
        if self.league.is_team_league():
            for season, sp in active_seasons_with_sp:
                # Check if user has a captain registration but no team
                captain_registration = Registration.objects.filter(
                    player=player,
                    season=season,
                    status='approved',
                    invite_code_used__code_type='captain'
                ).first()
                
                # Check if they're on a team
                team_member = TeamMember.objects.filter(
                    player=player,
                    team__season=season
                ).select_related('team').first()
                
                if team_member:
                    team_membership_by_season[season] = {
                        'team': team_member.team,
                        'is_captain': team_member.is_captain,
                        'is_vice_captain': team_member.is_vice_captain,
                        'can_manage': team_member.is_captain or team_member.is_vice_captain
                    }
                elif captain_registration:
                    captain_without_team_seasons.append(season)

        context = {
            'player': player,
            'slack_linked': slack_linked,
            'slack_linked_just_now': slack_linked_just_now,
            'active_seasons_with_sp': active_seasons_with_sp,
            'last_season': last_season,
            'my_pairings': my_pairings,
            'approved': approved,
            'captain_without_team_seasons': captain_without_team_seasons,
            'team_membership_by_season': team_membership_by_season,
        }
        return self.render('tournament/user_dashboard.html', context)


class DocumentView(LeagueView):
    def view(self, document_tag):
        league_document = LeagueDocument.objects.filter(league=self.league,
                                                        tag=document_tag).first()
        if league_document is None:
            season_document = SeasonDocument.objects.filter(season=self.season,
                                                            tag=document_tag).first()
            if season_document is None:
                raise Http404
            document = season_document.document
        else:
            document = league_document.document

        context = {
            'document': document,
            'is_faq': False,
            'can_edit': self.request.user.has_perm('tournament.change_document', self.league)
        }
        return self.render('tournament/document.html', context)


class TeamCompositionView(LeagueView):
    def view(self):
        # Check same permissions as dashboard
        if not self.request.user.has_perm('tournament.view_dashboard', self.league):
            raise Http404()

        # Only for team leagues
        if not self.league.is_team_league():
            raise Http404()

        # Get all teams for the current season with their members
        teams = Team.objects.filter(
            season=self.season,
            is_active=True
        ).prefetch_related(
            'teammember_set__player'
        ).order_by('name')

        # Build a real-name lookup from this season's registrations so we can
        # fall back to a player's real name when FIDE ID is missing.
        registrations = Registration.objects.filter(
            season=self.season, player__isnull=False
        ).only('player_id', 'first_name', 'last_name')
        real_names_by_player_id = {}
        for reg in registrations:
            full_name = f"{reg.first_name} {reg.last_name}".strip()
            if full_name:
                real_names_by_player_id.setdefault(reg.player_id, full_name)

        team_rows = []
        for team in teams:
            members = []
            for member in team.teammember_set.all():
                player = member.player
                if player.fide_id:
                    identifier = player.fide_id
                elif player.id in real_names_by_player_id:
                    identifier = real_names_by_player_id[player.id]
                else:
                    identifier = player.lichess_username
                members.append({'identifier': identifier})
            team_rows.append({'name': team.name, 'members': members})

        context = {
            'teams': teams,
            'team_rows': team_rows,
        }
        return self.render('tournament/team_composition.html', context)


class GameIdsView(LeagueView):
    def view(self):
        # Check same permissions as dashboard
        if not self.request.user.has_perm('tournament.view_dashboard', self.league):
            raise Http404()
        
        # Get all rounds for the current season
        rounds = Round.objects.filter(season=self.season).order_by('number')
        
        # Organize game IDs by round
        rounds_data = []
        
        for round_obj in rounds:
            round_data = {
                'round_number': round_obj.number,
                'matches': {}
            }
            
            if self.league.is_team_league():
                # Get the number of matches from the knockout bracket if it exists
                max_matches = 1
                try:
                    from heltour.tournament.models import KnockoutBracket
                    knockout_bracket = KnockoutBracket.objects.get(season=self.season)
                    max_matches = knockout_bracket.matches_per_stage
                except KnockoutBracket.DoesNotExist:
                    # Fall back to heuristic
                    is_multi_match = 'return' in self.season.name.lower() or 'multi' in self.season.name.lower()
                    max_matches = 2 if is_multi_match else 1
                
                # Team tournament - group by match number
                team_pairings = TeamPairing.objects.filter(round=round_obj).order_by('pairing_order')
                
                # Initialize all expected matches
                for match_num in range(1, max_matches + 1):
                    round_data['matches'][match_num] = []
                
                if team_pairings.exists():
                    # Simple sequential grouping: first X pairings = match 1, next X = match 2, etc.
                    unique_pairs = set()
                    for p in team_pairings:
                        unique_pairs.add((min(p.white_team_id, p.black_team_id), max(p.white_team_id, p.black_team_id)))
                    total_pairs = len(unique_pairs) if unique_pairs else 1
                    
                    # Group pairings sequentially: first total_pairs go to match 1, next total_pairs to match 2, etc.
                    for i, pairing in enumerate(team_pairings):
                        match_number = (i // total_pairs) + 1
                        # Only show matches up to the expected number
                        if match_number <= max_matches:
                            # Get all board games for this pairing
                            board_pairings = TeamPlayerPairing.objects.filter(team_pairing=pairing).order_by('board_number')
                            game_ids = []
                            for board_pairing in board_pairings:
                                game_id = board_pairing.game_id()
                                if game_id:
                                    game_ids.append(game_id)
                                # Note: Only add game IDs that exist, don't add empty placeholders
                                # This ensures we only show actual games, not expected structure
                            
                            round_data['matches'][match_number].extend(game_ids)
            else:
                # Individual tournament - no match numbers, just round
                lone_pairings = LonePlayerPairing.objects.filter(round=round_obj).order_by('pairing_order')
                game_ids = []
                for pairing in lone_pairings:
                    game_id = pairing.game_id()
                    if game_id:
                        game_ids.append(game_id)
                    else:
                        game_ids.append("")  # Empty placeholder when no game ID
                
                if lone_pairings.exists():
                    round_data['matches'][1] = game_ids  # Single "match" for lone tournaments
                else:
                    # No pairings exist yet - show expected structure
                    active_players = SeasonPlayer.objects.filter(season=self.season, is_active=True).count()
                    if active_players > 0:
                        if active_players % 2 == 0:
                            expected_pairings = active_players // 2
                        else:
                            expected_pairings = (active_players + 1) // 2  # One bye
                        round_data['matches'][1] = [""] * expected_pairings
            
            # Always add round data, even if empty
            rounds_data.append(round_data)
        
        context = {
            'rounds_data': rounds_data,
            'is_team_league': self.league.is_team_league(),
        }
        return self.render('tournament/game_ids.html', context)


class BroadcastPlayersView(LeagueView):
    def view(self):
        if not self.request.user.has_perm('tournament.view_dashboard', self.league):
            raise Http404()

        season_players = SeasonPlayer.objects.filter(
            season=self.season, is_active=True
        ).select_related('player').order_by('player__lichess_username')

        lines = []
        for sp in season_players:
            player = sp.player
            if not player.fide_id:
                continue
            profile = player.fide_profile or {}
            title = profile.get("title", "")
            rating = profile.get(player._fide_rating_key(self.league), "")
            name = profile.get("name", "")
            lines.append(
                f"{player.lichess_username} / {player.fide_id} / {title} / {rating} / {name}"
            )

        context = {
            'lines': "\n".join(lines),
        }
        return self.render('tournament/broadcast_players.html', context)


class TRF16ExportView(LeagueView):
    def view(self):
        if not self.request.user.has_perm('tournament.view_dashboard', self.league):
            raise Http404()

        content = season_to_trf16(self.season)
        filename = f"{self.league.tag}_{self.season.tag}.trf"
        response = HttpResponse(content, content_type="text/plain; charset=utf-8")
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class ContactView(LoginRequiredMixin, LeagueView):
    def view(self, post=False):
        leagues = [self.league] + list(
            League.objects.filter(is_active=True).order_by('display_order').exclude(
                pk=self.league.pk))

        player = Player.get_or_create(self.request.user.username)
        slack_linked = bool(player.slack_user_id)

        if post:
            form = ContactForm(self.request.POST, leagues=leagues)
            if form.is_valid():
                form_contains_links = (
                        'http://' in form.cleaned_data['message']
                        or 'https://' in form.cleaned_data['message']
                    )
                league = League.objects.get(tag=form.cleaned_data['league'])
                for mod in league.leaguemoderator_set.all():
                    if mod.send_contact_emails and mod.player.email and not form_contains_links:
                        sender_email = form.cleaned_data['your_email_address']
                        message = EmailMessage(
                            '[%s] %s' % (league.name, form.cleaned_data['subject']),
                            'Sender:\n%s\n%s\n\nMessage:\n%s' %
                            (form.cleaned_data['your_lichess_username'],
                             sender_email, form.cleaned_data['message']),
                            settings.DEFAULT_FROM_EMAIL,
                            [mod.player.email],
                            reply_to=[sender_email]
                        )
                        message.send()
                return redirect(leagueurl('contact_success', league_tag=self.league.tag))
        else:
            form = ContactForm(leagues=leagues)
            form.fields['your_lichess_username'].initial = player.lichess_username

        context = {
            'form': form,
            'slack_linked': slack_linked,
        }
        return self.render('tournament/contact.html', context)

    def view_post(self):
        return self.view(post=True)


class ContactSuccessView(LeagueView):
    def view(self):
        context = {
        }
        return self.render('tournament/contact_success.html', context)


class AboutView(LeagueView):
    def view(self):
        context = {
            'version': settings.HELTOUR_VERSION,
        }
        return self.render('tournament/about.html', context)


class PlayerProfileView(LeagueView):
    def view(self, username):
        player = get_object_or_404(Player, lichess_username__iexact=username)

        def game_count(season):
            if season.league.is_team_league():
                season_pairings = TeamPlayerPairing.objects.filter(
                    team_pairing__round__season=season)
            else:
                season_pairings = LonePlayerPairing.objects.filter(round__season=season)
            return (season_pairings.filter(white=player) | season_pairings.filter(
                black=player)).count()

        def team(season):
            if season.league.is_team_league():
                team_member = player.teammember_set.filter(team__season=season).first()
                if team_member is not None:
                    return team_member.team
            return None

        leagues = list((League.objects.filter(is_active=True) | League.objects.filter(
            pk=self.league.pk)).order_by('display_order'))
        has_other_seasons = player.seasonplayer_set.exclude(season=self.season).exists()
        other_season_leagues = [(league, [(sp.season, game_count(sp.season), team(sp.season)) for sp in
                                     player.seasonplayer_set \
                                 .filter(season__league=league, season__is_active=True) \
                                 .order_by('-season__start_date')]) \
                                for league in leagues]
        other_season_leagues = [league for league in other_season_leagues if len(league[1]) > 0]

        season_player = SeasonPlayer.objects.filter(season=self.season, player=player).first()

        def season_performance(season, isCurrentSeason=False):
            season_score = 0
            season_score_total = 0
            season_perf = PerfRatingCalc()

            games = defaultdict(list)
            if season is None:
                byes = {}
            elif season.league.is_team_league():
                pairings = TeamPlayerPairing.objects.filter(
                    white=player) | TeamPlayerPairing.objects.filter(black=player)
                for p in pairings.filter(team_pairing__round__season=season).order_by(
                    'team_pairing__round__number').nocache():
                    games[p.team_pairing.round.number].append(p)
                byes = {}
            else:
                pairings = LonePlayerPairing.objects.filter(
                    white=player) | LonePlayerPairing.objects.filter(black=player)
                for p in pairings.filter(round__season=season).order_by('round__number').nocache():
                    games[p.round.number].append(p)
                byes = {b.round.number: b for b in
                        PlayerBye.objects.filter(round__season=season, player=player)}

            history = []
            for round_ in season.round_set.filter(publish_pairings=True).order_by('number'):
                if round_.number in games:
                    for p in games[round_.number]:
                        if p.result == '':
                            continue
                        if isCurrentSeason:
                            history.append((round_, p, None, None))
                        game_score = p.white_score() if p.white == player else p.black_score()
                        if game_score is not None:
                            season_score += game_score
                            season_score_total += 1
                        # Add pairing to performance calculation
                        if p.game_played() and p.white is not None and p.black is not None:
                            sp = SeasonPlayer.objects.filter(season=season,
                                                             player=p.black if p.white == player else p.white).first()
                            if sp is not None and sp.seed_rating is not None:
                                opp_rating = sp.seed_rating
                            else:
                                opp_rating = p.black_rating_display() if p.white == player else p.white_rating_display(
                                    self.league)
                            season_perf.add_game(game_score, opp_rating)
                elif round_.number in byes:
                    bye = byes[round_.number]
                    if isCurrentSeason:
                        history.append((round_, None, bye.get_type_display(), None))
                    season_score += bye.score()
                    season_score_total += 1
            return season_score, season_score_total, season_perf, history, games, byes

        # calculate performance for current season
        season_score, season_score_total, season_perf, history, games, byes = season_performance(
            self.season, isCurrentSeason=True)
        season_perf_rating = season_perf.calculate()

        # calculate performance for all seasons in current league
        career_score = 0
        career_score_total = 0
        career_perf = PerfRatingCalc()

        for season in [sp.season for sp in
                       player.seasonplayer_set.filter(season__league=self.league)]:
            part_career_score, part_career_score_total, part_career_perf, _, _, _ = season_performance(
                season)
            career_score += part_career_score
            career_score_total += part_career_score_total
            career_perf.merge(part_career_perf)
        career_perf = career_perf.calculate()

        team_member = TeamMember.objects.filter(team__season=self.season, player=player).first()
        alternate = Alternate.objects.filter(season_player=season_player).first()

        schedule = []
        for round_ in self.season.round_set.filter(is_completed=False).order_by('number'):
            if round_.number in games and round_.publish_pairings:
                for pairing in games[round_.number]:
                    if pairing.result != '':
                        continue
                    schedule.append((round_, pairing, None, None))
                continue
            if self.season.league.is_team_league():
                assignment = AlternateAssignment.objects.filter(round=round_, player=player).first()
                if assignment is not None and (
                    team_member is None or team_member.team != assignment.team):
                    schedule.append((round_, None, 'Scheduled', assignment.team))
                    continue
                if season_player is None or not season_player.is_active:
                    continue
                if not player.is_available_for(round_):
                    schedule.append((round_, None, 'Unavailable', None))
                    continue
                if team_member is not None:
                    schedule.append((round_, None, 'Scheduled', None))
                    continue
                schedule.append((round_, None, 'Available', None))
            else:
                if round_.number in byes:
                    if round_.publish_pairings:
                        continue
                    schedule.append((round_, None, byes[round_.number].get_type_display(), None))
                    continue
                if not player.is_available_for(round_):
                    schedule.append((round_, None, 'Unavailable', None))
                    continue
                if season_player is None or not season_player.is_active:
                    continue
                schedule.append((round_, None, 'Scheduled', None))

        # Trophy Case stuff
        trophies = player.get_season_prizes(self.league)
        context = {
            'player': player,
            'has_other_seasons': has_other_seasons,
            'other_season_leagues': other_season_leagues,
            'season_player': season_player,
            'history': history,
            'schedule': schedule,
            'team_member': team_member,
            'alternate': alternate,
            'season_perf': season_perf,
            'season_perf_rating': season_perf_rating,
            'season_score': season_score,
            'season_score_total': season_score_total,
            'career_perf': career_perf,
            'career_score': career_score,
            'career_score_total': career_score_total,
            'can_edit': self.request.user.has_perm('tournament.change_season_player', self.league),
            'trophies': trophies,
            'slack_id': settings.SLACK_TEAM_ID,
            'rating_type_label': player.rating_type_display_for(self.league),
        }
        return self.render('tournament/player_profile.html', context)


class TeamProfileView(LeagueView):
    def view(self, team_number):
        team = get_object_or_404(Team, season=self.season, number=team_number)

        member_players = {tm.player for tm in team.teammember_set.all()}
        game_counts = defaultdict(int)
        display_ratings = {}
        for tp in team.pairings.order_by('round__start_date'):
            for p in tp.teamplayerpairing_set.nocache():
                if p.board_number % 2 == (1 if tp.white_team == team else 0):
                    if p.white is not None:
                        game_counts[p.white] += 1
                        display_ratings[p.white] = p.white_rating
                else:
                    if p.black is not None:
                        game_counts[p.black] += 1
                        display_ratings[p.black] = p.black_rating

        prev_members = [(
            player, display_ratings.get(player, None) or player.rating_for(self.league),
            game_count) for player, game_count in sorted(list(game_counts.items()),
                                                         key=lambda i: i[
                                                             0].lichess_username.lower())
            if player not in member_players]

        matches = []
        for round_ in self.season.round_set.filter(publish_pairings=True).order_by('number'):
            if self.season.league.is_team_league():
                pairing = team.pairings.filter(round=round_).first()
            if pairing is not None:
                matches.append((round_, pairing))

        # Check if user can manage this team
        can_manage_team = False
        if self.request.user.is_authenticated:
            if self.request.user.is_staff:
                can_manage_team = True
            else:
                player = Player.get_or_create(self.request.user.username)
                if player:
                    team_member = TeamMember.objects.filter(
                        player=player, team=team
                    ).first()
                    if team_member and (
                        team_member.is_captain or team_member.is_vice_captain
                    ):
                        can_manage_team = True

        show_gender = (
            can_manage_team
            or self.request.user.has_perm('tournament.view_dashboard', self.league)
        )

        context = {
            'team': team,
            'prev_members': prev_members,
            'matches': matches,
            "can_manage_team": can_manage_team,
            'show_gender': show_gender,
        }
        return self.render('tournament/team_profile.html', context)


class TeamCreateView(LoginRequiredMixin, SeasonView):
    def view(self):
        from heltour.tournament.forms import TeamCreateForm
        from heltour.tournament.models import InviteCode, TeamMember, Registration

        if not self.league.is_team_league():
            raise Http404("Team creation is only available for team leagues")

        # Check if user is already on a team
        existing_member = TeamMember.objects.filter(
            player=self.player,
            team__season=self.season
        ).first()
        
        if existing_member:
            # Already has a team, redirect to team management
            return redirect(
                'by_league:by_season:team_manage',
                league_tag=self.league.tag,
                season_tag=self.season.tag,
                team_number=existing_member.team.number
            )
        
        # Check if user has a captain invite code
        captain_registration = Registration.objects.filter(
            player=self.player,
            season=self.season,
            status='approved',
            invite_code_used__code_type='captain'
        ).first()
        
        if not captain_registration:
            # Check if they have ANY approved registration
            any_registration = Registration.objects.filter(
                player=self.player,
                season=self.season,
                status='approved'
            ).first()
            
            if any_registration:
                # They have an approved registration but not with a captain code
                # This might be a data issue - let's check if they should be allowed
                # based on other criteria (e.g., they might be a returning captain)
                raise Http404("You must have used a captain invite code during registration to create a team")
            else:
                raise Http404("No approved registration found for this season")
        
        form = TeamCreateForm(season=self.season, player=self.player)
        
        context = {
            'form': form,
            'season': self.season,
            'league': self.league,
        }
        
        return self.render('tournament/team_create.html', context)
    
    def view_post(self):
        from heltour.tournament.forms import TeamCreateForm
        from heltour.tournament.models import TeamMember, Registration

        if not self.league.is_team_league():
            raise Http404("Team creation is only available for team leagues")

        # Check if user already has a team
        existing_member = TeamMember.objects.filter(
            player=self.player,
            team__season=self.season
        ).first()
        
        if existing_member:
            # Already has a team, redirect to team management
            return redirect(
                'by_league:by_season:team_manage',
                league_tag=self.league.tag,
                season_tag=self.season.tag,
                team_number=existing_member.team.number
            )
        
        # Check if user has a captain invite code
        captain_registration = Registration.objects.filter(
            player=self.player,
            season=self.season,
            status='approved',
            invite_code_used__code_type='captain'
        ).first()
        
        if not captain_registration:
            # Check if they have ANY approved registration
            any_registration = Registration.objects.filter(
                player=self.player,
                season=self.season,
                status='approved'
            ).first()
            
            if any_registration:
                # They have an approved registration but not with a captain code
                # This might be a data issue - let's check if they should be allowed
                # based on other criteria (e.g., they might be a returning captain)
                raise Http404("You must have used a captain invite code during registration to create a team")
            else:
                raise Http404("No approved registration found for this season")
        
        form = TeamCreateForm(
            self.request.POST,
            season=self.season,
            player=self.player
        )
        
        if form.is_valid():
            team = form.save()
            return redirect(
                'by_league:by_season:team_manage',
                league_tag=self.league.tag,
                season_tag=self.season.tag,
                team_number=team.number
            )
        
        context = {
            'form': form,
            'season': self.season,
            'league': self.league,
        }
        
        return self.render('tournament/team_create.html', context)


class TeamManageView(LoginRequiredMixin, SeasonView):
    def can_manage_team(self, team):
        """Check if the current user can manage this team"""
        if self.request.user.is_staff:
            return True

        player = self.player
        if not player:
            return False

        team_member = TeamMember.objects.filter(player=player, team=team).first()

        return team_member and (team_member.is_captain or team_member.is_vice_captain)

    def view(self, team_number):
        from heltour.tournament.forms import GenerateTeamInviteCodeForm, BoardOrderForm, TeamNameEditForm

        team = get_object_or_404(Team, season=self.season, number=team_number)

        # Check permissions
        if not self.can_manage_team(team):
            raise Http404("You don't have permission to manage this team")

        # Get team members with their registration status
        team_members = team.teammember_set.select_related("player").order_by(
            "board_number"
        )

        # Get invite codes for this team
        invite_codes = (
            InviteCode.objects.filter(team=team, code_type="team_member")
            .select_related("used_by", "created_by", "created_by_captain")
            .order_by("-date_created")
        )

        # Count codes created by this captain
        captain_codes_count = 0
        if not self.request.user.is_staff:
            captain_codes_count = InviteCode.objects.filter(
                season=self.season, created_by_captain=self.player
            ).count()

        # Check if captain can create more codes
        can_create_codes = (
            self.request.user.is_staff
            or captain_codes_count < self.season.codes_per_captain_limit
        )

        # Get upcoming round and deadline info
        upcoming_round = team.get_upcoming_round()
        board_order_form = BoardOrderForm(
            team=team, user=self.request.user, upcoming_round=upcoming_round
        )
        can_update_boards = (
            upcoming_round.is_board_update_allowed() if upcoming_round else True
        )

        # Initialize team name form
        team_name_form = TeamNameEditForm(team=team)

        context = {
            "team": team,
            "team_members": team_members,
            "invite_codes": invite_codes,
            "can_create_codes": can_create_codes,
            "codes_remaining": self.season.codes_per_captain_limit
            - captain_codes_count,
            "codes_used": captain_codes_count,
            "codes_limit": self.season.codes_per_captain_limit,
            "is_admin": self.request.user.is_staff,
            "board_order_form": board_order_form,
            "team_name_form": team_name_form,
            "upcoming_round": upcoming_round,
            "can_update_boards": can_update_boards or self.request.user.is_staff,
            "board_update_deadline": upcoming_round.get_board_update_deadline()
            if upcoming_round
            else None,
        }

        return self.render("tournament/team_manage.html", context)

    def view_post(self, team_number):
        from heltour.tournament.forms import GenerateTeamInviteCodeForm, BoardOrderForm, TeamNameEditForm

        team = get_object_or_404(Team, season=self.season, number=team_number)

        # Check permissions
        if not self.can_manage_team(team):
            raise Http404("You don't have permission to manage this team")

        action = self.request.POST.get("action")
        form = None  # Initialize form variable

        if action == "update_boards":
            # Handle board order update
            upcoming_round = team.get_upcoming_round()
            board_form = BoardOrderForm(
                self.request.POST,
                team=team,
                user=self.request.user,
                upcoming_round=upcoming_round,
            )

            if board_form.is_valid():
                board_form.save()
                return redirect(
                    "by_league:by_season:team_manage",
                    league_tag=self.league.tag,
                    season_tag=self.season.tag,
                    team_number=team_number,
                )
            else:
                # Re-render page with form errors
                form = board_form

        elif action == "generate_codes":
            # Generate new codes
            form = GenerateTeamInviteCodeForm(
                self.request.POST,
                team=team,
                season=self.season,
                player=self.player if not self.request.user.is_staff else None,
            )

            if form.is_valid():
                form.save(created_by=self.request.user)
                return redirect(
                    "by_league:by_season:team_manage",
                    league_tag=self.league.tag,
                    season_tag=self.season.tag,
                    team_number=team_number,
                )

        elif action == "delete_code":
            # Delete unused code
            code_id = self.request.POST.get("code_id")
            code = get_object_or_404(InviteCode, pk=code_id, team=team)

            if code.is_available():
                code.delete()

            return redirect(
                "by_league:by_season:team_manage",
                league_tag=self.league.tag,
                season_tag=self.season.tag,
                team_number=team_number,
            )
        
        elif action == "update_team_name":
            # Update team name
            form = TeamNameEditForm(self.request.POST, team=team)
            
            if form.is_valid():
                form.save()
                return redirect(
                    "by_league:by_season:team_manage",
                    league_tag=self.league.tag,
                    season_tag=self.season.tag,
                    team_number=team_number,
                )
            else:
                # Re-render page with form errors
                form = form

        # If we get here, re-render the page (either no action or form was invalid)
        # Need to rebuild the context with form errors if applicable
        team = get_object_or_404(Team, season=self.season, number=team_number)
        team_members = team.teammember_set.select_related("player").order_by(
            "board_number"
        )
        invite_codes = (
            InviteCode.objects.filter(team=team, code_type="team_member")
            .select_related("used_by", "created_by", "created_by_captain")
            .order_by("-date_created")
        )

        captain_codes_count = 0
        if not self.request.user.is_staff:
            captain_codes_count = InviteCode.objects.filter(
                season=self.season, created_by_captain=self.player
            ).count()

        can_create_codes = (
            self.request.user.is_staff
            or captain_codes_count < self.season.codes_per_captain_limit
        )

        # Get upcoming round for board updates
        upcoming_round = team.get_upcoming_round()

        context = {
            "team": team,
            "team_members": team_members,
            "invite_codes": invite_codes,
            "can_create_codes": can_create_codes,
            "codes_remaining": self.season.codes_per_captain_limit
            - captain_codes_count,
            "codes_used": captain_codes_count,
            "codes_limit": self.season.codes_per_captain_limit,
            "is_admin": self.request.user.is_staff,
            "upcoming_round": upcoming_round,
            "can_update_boards": (
                upcoming_round.is_board_update_allowed() if upcoming_round else True
            )
            or self.request.user.is_staff,
            "board_update_deadline": upcoming_round.get_board_update_deadline()
            if upcoming_round
            else None,
        }

        # Add form with errors if it exists
        if form is not None and not form.is_valid():
            if action == "generate_codes":
                context["form"] = form
                context["form_errors"] = form.errors
            elif action == "update_boards":
                context["board_order_form"] = form
                context["board_form_errors"] = form.errors
            elif action == "update_team_name":
                context["team_name_form"] = form
                context["team_name_form_errors"] = form.errors
        else:
            # Default forms if no errors
            context["board_order_form"] = BoardOrderForm(
                team=team, user=self.request.user, upcoming_round=upcoming_round
            )
            context["team_name_form"] = TeamNameEditForm(team=team)

        return self.render("tournament/team_manage.html", context)


class NominateView(LoginRequiredMixin, SeasonView):
    def view(self, post=False):
        can_nominate = False
        current_nominations = []
        form = None
        player = self.player

        if self.league.is_team_league():
            season_pairings = PlayerPairing.objects.filter(
                teamplayerpairing__team_pairing__round__season=self.season).nocache()
        else:
            season_pairings = PlayerPairing.objects.filter(
                loneplayerpairing__round__season=self.season).nocache()

        max_nominations = self.league.get_leaguesetting().max_game_nominations_per_user

        if player is not None:
            if self.league.get_leaguesetting().limit_game_nominations_to_participants:
                player_pairings = season_pairings.filter(white=player) | season_pairings.filter(
                    black=player)
                can_nominate = player_pairings.count() > 0
            else:
                can_nominate = True

            if can_nominate and self.season.nominations_open:
                current_nominations = GameNomination.objects.filter(season=self.season,
                                                                    nominating_player=player)

                if post:
                    form = NominateForm(self.season, player, current_nominations, max_nominations,
                                        season_pairings, self.request.POST)
                    if form.is_valid():
                        if form.cleaned_data['game_link'] != '':
                            GameNomination.objects.create(season=self.season,
                                                          nominating_player=player,
                                                          game_link=form.cleaned_data['game_link'],
                                                          pairing=form.pairing)
                            return redirect('by_league:by_season:nominate', self.league.tag,
                                            self.season.tag)
                else:
                    form = NominateForm(self.season, player, current_nominations, max_nominations,
                                        season_pairings)

        context = {
            'form': form,
            'can_nominate': can_nominate,
            'max_nominations': max_nominations,
            'current_nominations': current_nominations,
        }
        return self.render('tournament/nominate.html', context)

    def view_post(self):
        return self.view(post=True)


class DeleteNominationView(LoginRequiredMixin, SeasonView):
    def view(self, nomination_id, post=False):
        form = None

        if not self.season.nominations_open:
            return redirect('by_league:by_season:nominate', self.league.tag, self.season.tag)

        nomination_to_delete = GameNomination.objects.filter(season=self.season,
                                                             nominating_player=self.player,
                                                             pk=nomination_id).first()
        if nomination_to_delete is None:
            return redirect('by_league:by_season:nominate', self.league.tag, self.season.tag)

        if post:
            form = DeleteNominationForm(self.request.POST)
            if form.is_valid():
                nomination_to_delete.delete()
                return redirect('by_league:by_season:nominate', self.league.tag, self.season.tag)
        else:
            form = DeleteNominationForm()

        context = {
            'form': form,
            'nomination_to_delete': nomination_to_delete,
        }
        return self.render('tournament/nomination_delete.html', context)

    def view_post(self, nomination_id):
        return self.view(nomination_id, post=True)


class ScheduleView(LoginRequiredMixin, LeagueView):
    def view(self, post=False):
        times = self.player.availabletime_set.filter(
            league=self.league) if self.player is not None else None

        context = {
            'player': self.player,
            'times': times,
        }
        return self.render('tournament/schedule.html', context)

    def view_post(self):
        return self.view(post=True)

class ConfirmScheduledTimeView(LoginRequiredMixin, LeagueView):
    def view(self, post=False):
        player = self.player

        active_rounds = Round.objects.filter(publish_pairings=True, is_completed=False,
                                             season__is_active=True)
        next_pairings = []
        for r in active_rounds:
            next_pairings += [(r, p) for p in
                            r.pairings.filter(white=player).exclude(scheduled_time=None) | r.pairings.filter(
                                black=player).exclude(scheduled_time=None)]

        context = {
            'player': player,
            'next_pairings': next_pairings
        }

        if post:
            for r in active_rounds:
                for p in r.pairings:
                    field_name = '%s_%s' % (r.number, p)
                    if self.request.POST.get('id') == field_name:
                        if p.white == player:
                            p.white_confirmed = not p.white_confirmed
                        else:
                            p.black_confirmed = not p.black_confirmed
                        p.save()
                        return redirect('/%s/confirm_scheduled_time' % self.league.tag)


        return self.render('tournament/confirm_scheduled_time.html', context)

    def view_post(self):
        return self.view(post=True)


class AvailabilityView(LoginRequiredMixin, SeasonView):
    def view(self, post=False):
        player = self.player

        if not post and not SeasonPlayer.objects.filter(player=player, season=self.season).exists():
            # Look for another section this player is participating in
            section_list = self.season.section_list()
            active_sp = player.seasonplayer_set.filter(season__in=section_list,
                                                       is_active=True).first()
            if active_sp:
                return redirect('by_league:by_season:edit_availability', self.league.tag,
                                active_sp.season.tag)
            inactive_sp = player.seasonplayer_set.filter(season__in=section_list).first()
            if inactive_sp:
                return redirect('by_league:by_season:edit_availability', self.league.tag,
                                inactive_sp.season.tag)

        player_list = [player]
        include_current_round = self.league.competitor_type == 'team'
        if include_current_round:
            round_list = list(self.season.round_set.order_by('number').filter(is_completed=False))
        else:
            round_list = list(
                self.season.round_set.order_by('number').filter(publish_pairings=False))
        round_data = None

        if player is not None:
            # Add team members if the user is a captain
            team_member = TeamMember.objects.filter(player=player, team__season=self.season).first()
            if team_member is not None and (team_member.is_captain or team_member.is_vice_captain):
                team = team_member.team
                for tm in team.teammember_set.order_by('board_number').select_related(
                    'player').nocache():
                    if tm.player not in player_list:
                        player_list.append(tm.player)

            availability_set = PlayerAvailability.objects.filter(player__in=player_list,
                                                                 round__in=round_list).nocache()
            is_available_dict = {(av.round_id, av.player_id): av.is_available for av in
                                 availability_set}
            
            season_player_set = SeasonPlayer.objects.filter(player__in=player_list, season=self.season).nocache()
            has_red_card_dict = {sp.player : sp.card_color == "red" for sp in season_player_set}
            
            if self.league.is_team_league() and len(round_list) > 0:
                #games can only be scheduled for the current round
                game_is_scheduled_dict = {(round_list[0], sp.player) : sp.has_scheduled_game_in_round(round_list[0]) for sp in season_player_set}
            else:
                game_is_scheduled_dict = {}
            
            if post:
                for r in round_list:
                    for p in player_list:
                        field_name = 'av_r%d_%s' % (r.number, p.lichess_username)
                        is_available = self.request.POST.get(field_name) != 'on'
                        
                        season_player = SeasonPlayer.objects.filter(player=p, season=self.season).first()
                        can_update_availability = season_player is not None and season_player.card_color != 'red' and not game_is_scheduled_dict.get((r, p), False)
                        
                        if (is_available != is_available_dict.get((r.id, p.id), True) and can_update_availability):
                            PlayerAvailability.objects.update_or_create(player=p, round=r,
                                                                        defaults={
                                                                            'is_available': is_available})
                return redirect('by_league:by_season:edit_availability', self.league.tag,
                                self.season.tag)

            round_data = [(r, [(p, is_available_dict.get((r.id, p.id), True), has_red_card_dict.get(p, False) or game_is_scheduled_dict.get((r, p), False)) for p in player_list])
                          for r in round_list]

        context = {
            'player_list': player_list,
            'round_data': round_data,
        }
        return self.render('tournament/availability.html', context)

    def view_post(self):
        return self.view(post=True)

    def set_league_and_season(self, league_tag, season_tag):
        self.league = _get_league(league_tag)
        if self.request.user.is_authenticated:
            league_seasons = self.league.season_set.filter(is_completed=False)
            active_sp = self.player.seasonplayer_set.filter(season__in=league_seasons,
                                                            is_active=True) \
                .order_by('-season__start_date', 'season__section__order', '-season__id').first()
            if active_sp:
                self.season = active_sp.season
                return
        self.season = _get_season(league_tag, season_tag, False)


class AlternatesView(SeasonView):
    def view(self):
        if self.league.competitor_type != 'team':
            raise Http404

        round_ = alternates_manager.current_round(self.season)
        if round_ is None:
            context = {
                'active_round': None
            }
            return self.render('tournament/alternates.html', context)

        searches = alternates_manager.current_searches(round_)
        assignments = AlternateAssignment.objects.filter(round=round_).order_by(
            'date_modified').select_related('team', 'player').nocache()

        def team_member(s):
            return TeamMember.objects.filter(team=s.team, board_number=s.board_number).first()

        open_spots = [(s.board_number, s.team, team_member(s), s.date_created) for s in searches]
        filled_spots = [(aa.board_number, aa.team, aa.player, aa.date_modified) for aa in
                        assignments]

        def with_status(alt):
            date = alt.last_contact_date if alt.status == 'contacted' else None
            status = alt.get_status_display()
            if status == 'Waiting':
                if alt.season_player.games_missed >= 2:
                    status = 'Red Card'
                elif not alt.season_player.player.is_available_for(round_):
                    status = 'Unavailable'
                elif (
                    round_.pairings.filter(white=alt.season_player.player) | round_.pairings.filter(
                    black=alt.season_player.player)).exists():
                    status = 'Scheduled'
            if status == 'Unresponsive':
                status = 'Unresponsive'
            return (alt, status, date)

        def alternate_board(n):
            all_alts = sorted(alternates.filter(board_number=n))
            alts_with_status = [with_status(alt) for alt in all_alts]
            eligible_alts = [(alt, status, date) for alt, status, date in alts_with_status if
                             status in ('Waiting', 'Contacted')]
            ineligible_alts = [(alt, status, date) for alt, status, date in alts_with_status if
                               status not in ('Waiting', 'Contacted')]
            return (n, eligible_alts, ineligible_alts)

        alternates = Alternate.objects.filter(season_player__season=self.season) \
            .select_related('season_player__registration', 'season_player__player') \
            .nocache()
        alternates_by_board = [alternate_board(n) for n in self.season.board_number_list()]

        context = {
            'active_round': round_,
            'open_spots': open_spots,
            'filled_spots': filled_spots,
            'alternates_by_board': alternates_by_board
        }
        return self.render('tournament/alternates.html', context)


class AlternateAcceptView(LoginRequiredMixin, SeasonView):
    def view(self, round_number, post=False):
        round_number = int(round_number)

        round_ = alternates_manager.current_round(self.season)

        alt = Alternate.objects.filter(season_player__season=self.season,
                                       season_player__player=self.player).first()
        show_button = False
        if alt is None:
            msg = 'You are not an alternate in %s.' % self.season
        elif round_ is None:
            msg = 'There is no round currently in progress.'
        elif round_.number != round_number:
            msg = 'The alternate search for round %d is over.' % round_number
        elif alt.status == 'accepted':
            msg = 'You have already accepted a game for round %d.' % round_.number
        elif alt.status == 'declined':
            msg = 'You have already declined a game for round %d.' % round_.number
        elif alt.status == 'unresponsive':
            msg = 'You did not respond in time this round. Please make sure to accept or decline a game in time to maintain your priority on the alternate list.'
        elif alt.status == 'contacted':
            # OK
            if post:
                if alternates_manager.alternate_accepted(alt):
                    msg = 'You have been assigned to a team for round %d. Please check Slack for more info.' % round_.number
                else:
                    msg = 'Sorry, no games are currently available for round %d.' % round_.number
            else:
                start_time = round_.start_date.strftime(
                    '%Y-%m-%d %H:%M') if not round_.publish_pairings else 'now'
                end_time = round_.end_date.strftime('%Y-%m-%d %H:%M')
                msg = 'Please confirm you can play a game for round %d. You must have multiple times you can play between %s and %s (UTC).' \
                      % (round_.number, start_time, end_time)
                show_button = True
        else:
            msg = 'Sorry, no games are currently available for round %d.' % round_.number

        context = {
            'msg': msg,
            'show_button': show_button
        }
        return self.render('tournament/alternate_accept.html', context)

    def view_post(self, round_number):
        return self.view(round_number, post=True)


class AlternateDeclineView(LoginRequiredMixin, SeasonView):
    def view(self, round_number, post=False):
        round_number = int(round_number)

        round_ = alternates_manager.current_round(self.season)

        alt = Alternate.objects.filter(season_player__season=self.season,
                                       season_player__player=self.player).first()
        show_button = False
        if alt is None:
            msg = 'You are not an alternate in %s.' % self.season
        elif round_ is None:
            msg = 'There is no round currently in progress.'
        elif round_.number != round_number:
            msg = 'The alternate search for round %d is over.' % round_number
        elif alt.status == 'accepted':
            msg = 'You have already accepted a game for round %d.' % round_.number
        elif alt.status == 'declined':
            msg = 'You have already declined a game for round %d.' % round_.number
        elif alt.status == 'unresponsive':
            msg = 'You did not respond in time this round. Please make sure to accept or decline a game in time to maintain your priority on the alternate list.'
        elif alt.status == 'contacted' or alt.status == 'waiting':
            # OK
            if post:
                alternates_manager.alternate_declined(alt)
                msg = 'You will not receive any more game offers for round %d. Thank you for your response.' % round_.number
            else:
                msg = 'Please confirm you do not want to play a game during round %d.' % (
                    round_.number)
                show_button = True

        context = {
            'msg': msg,
            'show_button': show_button
        }
        return self.render('tournament/alternate_decline.html', context)

    def view_post(self, round_number):
        return self.view(round_number, post=True)


class NotificationsView(LoginRequiredMixin, SeasonView):
    def view(self, post=False):
        player = self.player
        if post:
            form = NotificationsForm(self.league, player, self.request.POST)
            if form.is_valid():
                PlayerNotificationSetting.objects.filter(player=player, league=self.league).delete()
                for type_, _ in PLAYER_NOTIFICATION_TYPES:
                    if type_ == 'alternate_needed' and self.league.competitor_type != 'team':
                        continue
                    setting = PlayerNotificationSetting(player=player, league=self.league,
                                                        type=type_)
                    setting.enable_lichess_mail = form.cleaned_data[type_ + '_lichess']
                    setting.enable_slack_im = form.cleaned_data[type_ + '_slack']
                    setting.enable_slack_mpim = form.cleaned_data[type_ + '_slack_wo']
                    setting.offset = timedelta(minutes=form.cleaned_data[type_ + '_offset']) if (
                                                                                                    type_ + '_offset') in form.cleaned_data else None
                    setting.save()
        else:
            form = NotificationsForm(self.league, player)

        context = {
            'form': form
        }
        return self.render('tournament/notifications.html', context)

    def view_post(self):
        return self.view(post=True)


class SiteLoginView(View):
    def get(self, request, *args, **kwargs):
        return oauth.redirect_for_authorization(request, None, None)


class LoginView(LeagueView):
    def view(self, secret_token=None):
        return oauth.redirect_for_authorization(self.request, self.league.tag, secret_token)


class LoginFailedView(BaseView):
    def view(self):
        return self.render('tournament/login_failed.html',
                           {'lichess': settings.LICHESS_NAME,
                            'lichess_link': settings.LICHESS_DOMAIN})


class OAuthCallbackView(View):
    def get(self, request, *args, **kwargs):
        return oauth.login_with_code(request, request.GET.get('code'), request.GET.get('state'))


class LogoutView(LeagueView):
    def view(self, post=False):
        if post:
            logout(self.request)
            return redirect('by_league:league_home', self.league.tag)

        return self.render('tournament/logout.html', {})

    def view_post(self):
        return self.view(post=True)


class TvView(LeagueView):
    def view(self):
        leagues = list((League.objects.filter(is_active=True) | League.objects.filter(
            pk=self.league.pk)).order_by('display_order'))
        if self.season.is_active and not self.season.is_completed:
            active_season = self.season
        else:
            active_season = _get_default_season(self.league.tag, True)

        boards = active_season.board_number_list() if active_season is not None and active_season.boards is not None else None
        teams = active_season.team_set.order_by('name') if active_season is not None else None

        filter_form = TvFilterForm(current_league=self.league, leagues=leagues, boards=boards,
                                   teams=teams)
        timezone_form = TvTimezoneForm()

        context = {
            'filter_form': filter_form,
            'timezone_form': timezone_form,
            'json': json.dumps(_tv_json(self.league)),
        }
        return self.render('tournament/tv.html', context)


class TvJsonView(LeagueView):
    def view(self):
        league_tag = self.request.GET.get('league')
        if league_tag == 'all':
            league = None
        elif league_tag is not None:
            league = League.objects.filter(tag=league_tag).first()
        else:
            league = self.league
        try:
            board = int(self.request.GET.get('board', ''))
        except ValueError:
            board = None
        try:
            team = int(self.request.GET.get('team', ''))
        except ValueError:
            team = None
        return JsonResponse(_tv_json(league, board, team))


class ToggleDarkModeView(BaseView):
    def view(self):
        original_value = False
        if self.request.user.is_authenticated:
            player = Player.get_or_create(self.request.user.username)
            player_setting, _ = PlayerSetting.objects.get_or_create(player=player)
            original_value = player_setting.dark_mode
            player_setting.dark_mode = not original_value
            player_setting.save()
        else:
            original_value = self.request.session.get('dark_mode', False)
        self.request.session['dark_mode'] = not original_value

        redirect_url = self.request.GET.get('redirect_url')
        try:
            if redirect_url and url_has_allowed_host_and_scheme(redirect_url, settings.ALLOWED_HOSTS):
                return redirect(redirect_url)
        except (ValueError, SuspiciousOperation, NoReverseMatch) as e:
            logger.warning(f'Redirect URL Validation failed: {e}')
        return redirect('home')


class ToggleZenModeView(BaseView):
    def view(self):
        original_value = False
        if self.request.user.is_authenticated:
            player = Player.get_or_create(self.request.user.username)
            player_setting, _ = PlayerSetting.objects.get_or_create(player=player)
            original_value = player_setting.zen_mode
            player_setting.zen_mode = not original_value
            player_setting.save()
        else:
            original_value = self.request.session.get('zen_mode', False)
        self.request.session['zen_mode'] = not original_value

        redirect_url = self.request.GET.get('redirect_url')
        try:
            if redirect_url and url_has_allowed_host_and_scheme(redirect_url, settings.ALLOWED_HOSTS):
                return redirect(redirect_url)
        except (ValueError, SuspiciousOperation, NoReverseMatch) as e:
            logger.warning(f'Redirect URL Validation failed: {e}')
        return redirect('home')


def _tv_json(league, board=None, team=None):
    def export_game(game, league, board, team):
        if hasattr(game, 'teamplayerpairing'):
            game_season = game.teamplayerpairing.team_pairing.round.season
            game_league = game_season.league
            return {
                'id': game.game_id(),
                'white_name': game.white.lichess_username,
                'white_rating': game.white_rating_display(league),
                'black_name': game.black.lichess_username,
                'black_rating': game.black_rating_display(league),
                'time': game.scheduled_time.isoformat() if game.scheduled_time is not None else None,
                'league': game_league.tag,
                'season': game_season.tag,
                'white_team': {
                    'name': game.teamplayerpairing.white_team_name(),
                    'number': game.teamplayerpairing.white_team().number,
                    'score': game.teamplayerpairing.white_team_match_score(),
                },
                'black_team': {
                    'name': game.teamplayerpairing.black_team_name(),
                    'number': game.teamplayerpairing.black_team().number,
                    'score': game.teamplayerpairing.black_team_match_score(),
                },
                'board_number': game.teamplayerpairing.board_number,
                'matches_filter': (
                                      league is None and game_league.is_active or league == game_league) and
                                  (
                                      board is None or board == game.teamplayerpairing.board_number) and
                                  # TODO: Team filter can do weird things if there are multiple active seasons
                                  (
                                      team is None or team == game.teamplayerpairing.white_team().number or team == game.teamplayerpairing.black_team().number)
            }
        elif hasattr(game, 'loneplayerpairing'):
            game_season = game.loneplayerpairing.round.season
            game_league = game_season.league
            return {
                'id': game.game_id(),
                'white_name': game.white.lichess_username,
                'white_rating': game.white_rating_display(league),
                'black_name': game.black.lichess_username,
                'black_rating': game.black_rating_display(league),
                'time': game.scheduled_time.isoformat() if game.scheduled_time is not None else None,
                'league': game_league.tag,
                'season': game_season.tag,
                'matches_filter': (
                                      league is None and game_league.is_active or league == game_league) and board is None and team is None
            }

    current_games = PlayerPairing.objects.filter(result='').exclude(tv_state='hide').exclude(
        game_link='').order_by('scheduled_time') \
        .select_related('teamplayerpairing__team_pairing__round__season__league',
                        'teamplayerpairing__team_pairing__black_team',
                        'teamplayerpairing__team_pairing__white_team',
                        'loneplayerpairing__round__season__league',
                        'white', 'black').nocache()
    scheduled_games = PlayerPairing.objects.filter(result='', game_link='',
                                                   scheduled_time__gt=timezone.now() - timedelta(
                                                       minutes=20)).order_by('scheduled_time') \
        .select_related('teamplayerpairing__team_pairing__round__season__league',
                        'teamplayerpairing__team_pairing__black_team',
                        'teamplayerpairing__team_pairing__white_team',
                        'loneplayerpairing__round__season__league',
                        'white', 'black').nocache()

    @cached_as(League, Season, Round, Team, TeamScore, Player, PlayerPairing, TeamPlayerPairing,
               TeamPairing, LonePlayerPairing)
    def get_games(league, board, team):
        return [export_game(g, league, board, team) for g in current_games]

    @cached_as(League, Season, Round, Team, TeamScore, Player, PlayerPairing, TeamPlayerPairing,
               TeamPairing, LonePlayerPairing)
    def get_schedule(league, board, team):
        return [export_game(g, league, board, team) for g in scheduled_games]

    games = get_games(league, board, team)
    schedule = get_schedule(league, board, team)
    game_ids = [g['id'] for g in games]
    return {'games': games,
            'schedule': schedule,
            'watch': lichessapi.watch_games(game_ids)}


# -------------------------------------------------------------------------------
# Helper functions

def _get_league(league_tag, allow_none=False):
    if league_tag is None:
        return _get_default_league(allow_none)
    else:
        return get_object_or_404(League, tag=league_tag)


def _get_default_league(allow_none=False):
    try:
        return League.objects.filter(is_default=True).order_by('id')[0]
    except IndexError:
        league = League.objects.order_by('id').first()
        if not allow_none and league is None:
            raise Http404
        return league


def _get_season(league_tag, season_tag, allow_none=False):
    if season_tag is None:
        return _get_default_season(league_tag, allow_none)
    else:
        return get_object_or_404(Season, league=_get_league(league_tag), tag=season_tag)


def _get_default_season(league_tag, allow_none=False):
    season = Season.objects.filter(league=_get_league(league_tag), is_active=True).order_by(
        '-start_date', 'section__order', '-id').first()
    if not allow_none and season is None:
        raise Http404
    return season


def _get_season_lists(league, active_only=True):
    season_list = Season.objects.filter(league=league).order_by('-start_date', 'section__order',
                                                                '-id')
    if active_only:
        season_list = season_list.filter(is_active=True)
    current_season_list = [s for s in season_list if not s.is_completed]
    completed_season_list = [s for s in season_list if s.is_completed]
    return current_season_list, completed_season_list


@cached_as(NavItem)
def _get_nav_tree(league_tag, season_tag):
    league = _get_league(league_tag)
    all_items = league.navitem_set.order_by('order')
    root_items = [item for item in all_items if item.parent_id is None]

    def transform(item):
        text = item.text
        url = item.path
        if item.season_relative and season_tag is not None:
            url = '/season/%s' % season_tag + url
        if item.league_relative:
            url = '/%s' % league_tag + url
        children = [transform(child) for child in all_items if child.parent_id == item.id]
        append_separator = item.append_separator
        return (text, url, children, append_separator)

    return [transform(item) for item in root_items]


# -------------------------------------------------------------------------------
# Knockout Tournament Views

class KnockoutBracketView(SeasonView):
    """View for displaying knockout tournament brackets."""
    
    @property 
    def player(self):
        """Get player if available, otherwise return None."""
        if hasattr(self, '_player'):
            return self._player
        return None
    
    @player.setter
    def player(self, value):
        self._player = value
    
    def view(self):
        if not self.season.league.pairing_type.startswith('knockout'):
            raise Http404("This season is not a knockout tournament")
            
        from heltour.tournament.models import KnockoutBracket, KnockoutSeeding, KnockoutAdvancement
        from heltour.tournament_core.knockout import get_knockout_stage_name
        
        # Get the knockout bracket
        try:
            bracket = KnockoutBracket.objects.get(season=self.season)
        except KnockoutBracket.DoesNotExist:
            # No bracket exists yet
            context = {
                'bracket_rounds': None,
                'bracket': None,
                'bracket_info': None,
                'advancements': None,
            }
            return self.render('tournament/knockout_bracket.html', context)
        
        # Get all rounds for this season
        all_rounds = Round.objects.filter(season=self.season).order_by('number')
        
        # Build bracket visualization data - show all rounds even if not created yet
        bracket_rounds = []
        
        # Calculate total rounds needed for complete tournament
        if bracket:
            total_tournament_rounds = int(math.log2(bracket.bracket_size))
        else:
            total_tournament_rounds = all_rounds.count() if all_rounds else 1
        
        # Show scheduled rounds + 1 additional round (to see where winners would go)
        scheduled_rounds = total_tournament_rounds
        if hasattr(self.season, 'rounds') and self.season.rounds:
            scheduled_rounds = self.season.rounds
            # Show one additional round past the scheduled ones (but not more than total possible)
            display_rounds = min(scheduled_rounds + 1, total_tournament_rounds)
        else:
            display_rounds = total_tournament_rounds
        
        for round_num in range(1, display_rounds + 1):
            # Try to get existing round, or create placeholder
            round_obj = all_rounds.filter(number=round_num).first()
            
            # Calculate teams remaining in this round
            teams_remaining = bracket.bracket_size // (2 ** (round_num - 1)) if bracket else 2
            
            # Special handling for the final displayed round when showing individual winners
            if round_num == scheduled_rounds + 1 and round_num <= display_rounds:
                # This is the winner display round
                if teams_remaining == 1:
                    stage_name = "Winner"
                else:
                    stage_name = f"Winners (Top {teams_remaining})"
            else:
                stage_name = get_knockout_stage_name(teams_remaining)
            
            if round_obj:
                # Existing round - process normally
                if self.league.competitor_type == 'team':
                    pairings = TeamPairing.objects.filter(round=round_obj).select_related(
                        'white_team', 'black_team'
                    ).prefetch_related(
                        'white_team__knockoutseeding_set',
                        'black_team__knockoutseeding_set'
                    )
                else:
                    pairings = LonePlayerPairing.objects.filter(round=round_obj).select_related(
                        'white', 'black'
                    )
                
                # Convert pairings to match data and calculate bracket positions
                matches = []
                
                # If no pairings exist for this round, create placeholder matches
                if not pairings.exists():
                    expected_matches = teams_remaining // 2
                    for i in range(expected_matches):
                        matches.append({
                            'is_bye': False,
                            'is_winner_slot': False,
                            'competitor1': None,
                            'competitor2': None,
                            'seed1': None,
                            'seed2': None,
                            'competitor1_score': None,
                            'competitor2_score': None,
                            'competitor1_won': False,
                            'competitor2_won': False,
                            'is_tie': False,
                            'completed': False,
                            'manual_tiebreak': False,
                            'round_number': round_num,
                            'pairing_id': None,
                            'needs_tiebreak': False,
                            'pairing_order': i + 1,
                            'is_placeholder': True,
                        })
                else:
                    # Process actual pairings
                    # For multi-match tournaments, group by team pair to show each pair only once
                    if self.league.competitor_type == 'team' and bracket and bracket.matches_per_stage > 1:
                        # Group pairings by team pair
                        from collections import defaultdict
                        team_pair_groups = defaultdict(list)
                        team_pair_primary = {}  # Track the primary pairing for each team pair
                        
                        for pairing in pairings:
                            if pairing.black_team:  # Skip byes (handle separately)
                                team_key = tuple(sorted([pairing.white_team.id, pairing.black_team.id]))
                                team_pair_groups[team_key].append(pairing)
                                # Use the first pairing as primary (lowest pairing_order)
                                if team_key not in team_pair_primary or pairing.pairing_order < team_pair_primary[team_key].pairing_order:
                                    team_pair_primary[team_key] = pairing
                        
                        # Process byes first
                        for pairing in pairings:
                            if pairing.black_team_id is None:
                                seeding = pairing.white_team.knockoutseeding_set.filter(bracket=bracket).first()
                                matches.append({
                                    'is_bye': True,
                                    'competitor': pairing.white_team,
                                    'seed': seeding.seed_number if seeding else None,
                                    'pairing_order': pairing.pairing_order,
                                })
                        
                        # Then process team pairs using only the primary pairing
                        logger.info(f"Processing {len(team_pair_primary)} unique team pairs for multi-match bracket")
                        for team_key, primary_pairing in team_pair_primary.items():
                            pairing = primary_pairing
                            # Regular match - check if this is multi-match tournament
                            white_seeding = pairing.white_team.knockoutseeding_set.filter(bracket=bracket).first()
                            black_seeding = pairing.black_team.knockoutseeding_set.filter(bracket=bracket).first()
                            
                            # For multi-match tournaments, aggregate scores across all matches for this team pair
                            aggregated_scores = self._get_aggregated_team_pair_scores(pairing, round_obj)
                            competitor1_score = aggregated_scores['white_total']
                            competitor2_score = aggregated_scores['black_total']
                            existing_matches_completed = aggregated_scores['all_completed']
                            has_manual_tiebreak = aggregated_scores['has_manual_tiebreak']
                            
                            # Check if all expected matches have been created for this team pair
                            expected_matches = bracket.matches_per_stage
                            actual_matches = aggregated_scores.get('match_count', 0)
                            all_completed = existing_matches_completed and actual_matches >= expected_matches
                                    
                            # Determine winner from aggregated scores
                            if has_manual_tiebreak:
                                # Find the pairing with the manual tiebreak value
                                manual_tiebreak_val = None
                                team_pair_pairings = TeamPairing.objects.filter(
                                    round=round_obj
                                ).filter(
                                    models.Q(white_team=pairing.white_team, black_team=pairing.black_team) |
                                    models.Q(white_team=pairing.black_team, black_team=pairing.white_team)
                                ).exclude(black_team__isnull=True)
                                
                                for tp in team_pair_pairings:
                                    if tp.manual_tiebreak_value is not None:
                                        # Adjust tiebreak value based on team orientation
                                        if tp.white_team == pairing.white_team:
                                            manual_tiebreak_val = tp.manual_tiebreak_value
                                        else:
                                            # Teams are flipped, so flip the tiebreak value
                                            manual_tiebreak_val = -tp.manual_tiebreak_value
                                        break
                                
                                if manual_tiebreak_val is not None:
                                    competitor1_won = manual_tiebreak_val > 0
                                    competitor2_won = manual_tiebreak_val < 0
                                    is_tie = manual_tiebreak_val == 0
                                else:
                                    # Fallback to score comparison if no tiebreak found
                                    competitor1_won = competitor1_score > competitor2_score
                                    competitor2_won = competitor2_score > competitor1_score
                                    is_tie = competitor1_score == competitor2_score
                            else:
                                competitor1_won = competitor1_score > competitor2_score
                                competitor2_won = competitor2_score > competitor1_score
                                is_tie = competitor1_score == competitor2_score
                            
                            # Get individual match scores for multi-match display
                            match_scores = []
                            team_pair_pairings = TeamPairing.objects.filter(
                                round=round_obj
                            ).filter(
                                models.Q(white_team=pairing.white_team, black_team=pairing.black_team) |
                                models.Q(white_team=pairing.black_team, black_team=pairing.white_team)
                            ).exclude(black_team__isnull=True).order_by('pairing_order')
                            
                            for match_pairing in team_pair_pairings:
                                # Normalize scores based on team orientation
                                if match_pairing.white_team == pairing.white_team:
                                    match_scores.append({
                                        'white_score': match_pairing.white_points or 0,
                                        'black_score': match_pairing.black_points or 0,
                                    })
                                else:
                                    # Teams are flipped
                                    match_scores.append({
                                        'white_score': match_pairing.black_points or 0,
                                        'black_score': match_pairing.white_points or 0,
                                    })
                            
                            # Pad match_scores with zeros for missing matches in multi-match tournaments
                            expected_matches = bracket.matches_per_stage
                            while len(match_scores) < expected_matches:
                                match_scores.append({
                                    'white_score': 0,
                                    'black_score': 0,
                                })
                            
                            # Check if we have any completed matches (for partial results display)
                            has_any_results = competitor1_score > 0 or competitor2_score > 0
                            
                            matches.append({
                                'is_bye': False,
                                'competitor1': pairing.white_team,
                                'competitor2': pairing.black_team,
                                'seed1': white_seeding.seed_number if white_seeding else None,
                                'seed2': black_seeding.seed_number if black_seeding else None,
                                'competitor1_score': competitor1_score,
                                'competitor2_score': competitor2_score,
                                'competitor1_won': competitor1_won,
                                'competitor2_won': competitor2_won,
                                'is_tie': is_tie,
                                'completed': all_completed,
                                'has_partial_results': has_any_results and not all_completed,  # Show partial if we have results but not all matches are completed
                                'manual_tiebreak': has_manual_tiebreak,
                                'round_number': round_obj.number,
                                'pairing_id': pairing.id,  # Add pairing ID for admin links
                                'needs_tiebreak': is_tie and not has_manual_tiebreak and all_completed,
                                'pairing_order': pairing.pairing_order,
                                'match_scores': match_scores,  # Individual match scores
                                'is_multi_match': bracket.matches_per_stage > 1,
                            })
                    else:
                        # Single match tournament or individual tournament - process all pairings
                        logger.info(f"Processing ALL {pairings.count()} pairings for single-match tournament")
                        for pairing in pairings:
                            if self.league.competitor_type == 'team':
                                if pairing.black_team_id is None:
                                    # Bye
                                    seeding = pairing.white_team.knockoutseeding_set.filter(bracket=bracket).first()
                                    matches.append({
                                        'is_bye': True,
                                        'competitor': pairing.white_team,
                                        'seed': seeding.seed_number if seeding else None,
                                        'pairing_order': pairing.pairing_order,
                                    })
                                else:
                                    # Regular match
                                    white_seeding = pairing.white_team.knockoutseeding_set.filter(bracket=bracket).first()
                                    black_seeding = pairing.black_team.knockoutseeding_set.filter(bracket=bracket).first()
                                    
                                    competitor1_score = pairing.white_points
                                    competitor2_score = pairing.black_points
                                    all_completed = self._is_team_match_completed(pairing)
                                    has_manual_tiebreak = pairing.manual_tiebreak_value is not None
                                    
                                    # Determine winner (considering manual tiebreak)
                                    if pairing.manual_tiebreak_value is not None:
                                        # Manual tiebreak overrides point-based winner
                                        competitor1_won = pairing.manual_tiebreak_value > 0
                                        competitor2_won = pairing.manual_tiebreak_value < 0
                                        is_tie = pairing.manual_tiebreak_value == 0
                                    else:
                                        # Standard point-based winner determination
                                        competitor1_won = pairing.white_points > pairing.black_points
                                        competitor2_won = pairing.black_points > pairing.white_points
                                        is_tie = pairing.white_points == pairing.black_points and pairing.white_points is not None
                                    
                                    matches.append({
                                        'is_bye': False,
                                        'competitor1': pairing.white_team,
                                        'competitor2': pairing.black_team,
                                        'seed1': white_seeding.seed_number if white_seeding else None,
                                        'seed2': black_seeding.seed_number if black_seeding else None,
                                        'competitor1_score': competitor1_score,
                                        'competitor2_score': competitor2_score,
                                        'competitor1_won': competitor1_won,
                                        'competitor2_won': competitor2_won,
                                        'is_tie': is_tie,
                                        'completed': all_completed,
                                        'manual_tiebreak': has_manual_tiebreak,
                                        'round_number': round_obj.number,
                                        'pairing_id': pairing.id,  # Add pairing ID for admin links
                                        'needs_tiebreak': is_tie and not has_manual_tiebreak and all_completed,
                                        'pairing_order': pairing.pairing_order,
                                    })
                            else:
                                # Individual tournament logic (no seeding model for players yet)
                                if pairing.black_id is None:
                                    # Bye
                                    matches.append({
                                        'is_bye': True,
                                        'competitor': pairing.white,
                                        'seed': None,  # No seeding for individual tournaments yet
                                    })
                                else:
                                    # Regular match
                                    # Determine winner based on result
                                    if pairing.result in ['1-0', '1X-0F']:
                                        competitor1_won, competitor2_won = True, False
                                    elif pairing.result in ['0-1', '0F-1X']:
                                        competitor1_won, competitor2_won = False, True
                                    elif pairing.result == '1/2-1/2':
                                        competitor1_won, competitor2_won = False, False
                                    else:
                                        competitor1_won = competitor2_won = False
                                
                                    matches.append({
                                        'is_bye': False,
                                        'competitor1': pairing.white,
                                        'competitor2': pairing.black,
                                        'seed1': None,  # No seeding for individual tournaments yet
                                        'seed2': None,  # No seeding for individual tournaments yet
                                        'competitor1_score': 1.0 if competitor1_won else (0.5 if pairing.result == '1/2-1/2' else 0.0),
                                        'competitor2_score': 1.0 if competitor2_won else (0.5 if pairing.result == '1/2-1/2' else 0.0),
                                        'competitor1_won': competitor1_won,
                                        'competitor2_won': competitor2_won,
                                        'is_tie': pairing.result == '1/2-1/2',
                                        'completed': pairing.result != '',
                                        'manual_tiebreak': False,  # Individual tournaments don't have manual tiebreaks per pairing
                                        'round_number': round_obj.number,
                                    })
            
                # Sort matches for proper bracket visualization
                # For knockout tournaments, we need to arrange matches so that winners flow logically
                if bracket and matches:
                    matches = self._sort_matches_for_bracket_display(matches, round_num, bracket.bracket_size)
            else:
                # Placeholder round - create empty matches or winner slots
                matches = []
                
                # Check if this is the round after the last scheduled round (showing individual winners)
                if round_num == scheduled_rounds + 1:
                    # This round shows individual winners, not pairings
                    # Get actual winners from advancement records if tournament is completed
                    from heltour.tournament.models import KnockoutAdvancement
                    actual_winners = []
                    
                    if bracket and self.season.is_completed:
                        # Get winners from advancement records or from the last round
                        # First try to get winners from advancement records (more reliable for completed tournaments)
                        final_advancement_records = KnockoutAdvancement.objects.filter(
                            bracket=bracket, 
                            to_stage='final'
                        ).order_by('date_created')
                        
                        if final_advancement_records.exists():
                            # Use advancement records (preferred for completed tournaments)
                            for adv in final_advancement_records:
                                actual_winners.append(adv.team)
                        else:
                            # Fallback: calculate winners from the last round
                            last_round = Round.objects.filter(season=self.season).order_by('-number').first()
                            if last_round and self.league.competitor_type == 'team':
                                if bracket.matches_per_stage > 1:
                                    # Multi-match tournament: use proper aggregation
                                    from heltour.tournament.pairinggen import _get_multi_match_winners
                                    actual_winners = _get_multi_match_winners(last_round, bracket)
                                else:
                                    # Single-match tournament: use individual pairing results
                                    team_pairings = TeamPairing.objects.filter(round=last_round).order_by('pairing_order')
                                    
                                    for pairing in team_pairings:
                                        winner = None
                                        if pairing.black_team_id is None:
                                            # Bye situation - white team advances
                                            winner = pairing.white_team
                                        else:
                                            # Determine winner based on points and manual tiebreak
                                            if pairing.manual_tiebreak_value is not None:
                                                if pairing.manual_tiebreak_value > 0:
                                                    winner = pairing.white_team
                                                elif pairing.manual_tiebreak_value < 0:
                                                    winner = pairing.black_team
                                            elif pairing.white_points is not None and pairing.black_points is not None:
                                                if pairing.white_points > pairing.black_points:
                                                    winner = pairing.white_team
                                                elif pairing.black_points > pairing.white_points:
                                                    winner = pairing.black_team
                                        
                                        if winner:
                                            actual_winners.append(winner)
                    
                    for i in range(teams_remaining):
                        # Use actual winner if available, otherwise show placeholder
                        winner = actual_winners[i] if i < len(actual_winners) else None
                        
                        matches.append({
                            'is_bye': False,
                            'is_winner_slot': True,  # New flag for individual winner display
                            'competitor1': winner,  # Actual winner or None for placeholder
                            'competitor2': None,
                            'seed1': None,
                            'seed2': None,
                            'competitor1_score': None,
                            'competitor2_score': None,
                            'competitor1_won': False,
                            'competitor2_won': False,
                            'is_tie': False,
                            'completed': winner is not None,  # Completed if we have a winner
                            'manual_tiebreak': False,
                            'round_number': round_num,
                            'pairing_id': None,
                            'needs_tiebreak': False,
                            'pairing_order': i + 1,
                            'is_placeholder': winner is None,  # Only placeholder if no winner
                            'winner_position': i + 1,  # Position number for this winner
                        })
                else:
                    # Regular placeholder matches for future rounds
                    expected_matches = teams_remaining // 2
                    for i in range(expected_matches):
                        matches.append({
                            'is_bye': False,
                            'is_winner_slot': False,
                            'competitor1': None,
                            'competitor2': None,
                            'seed1': None,
                            'seed2': None,
                            'competitor1_score': None,
                            'competitor2_score': None,
                            'competitor1_won': False,
                            'competitor2_won': False,
                            'is_tie': False,
                            'completed': False,
                            'manual_tiebreak': False,
                            'round_number': round_num,
                            'pairing_id': None,
                            'needs_tiebreak': False,
                            'pairing_order': i + 1,
                            'is_placeholder': True,
                        })
            
            # Determine if this round is scheduled
            is_scheduled = round_num <= scheduled_rounds
            
            bracket_rounds.append({
                'stage_name': stage_name,
                'round': round_obj,
                'matches': matches,
                'round_number': round_num,
                'is_placeholder': round_obj is None,
                'is_scheduled': is_scheduled,
            })
        
        # Get recent advancements
        advancements = KnockoutAdvancement.objects.filter(bracket=bracket).select_related(
            'team' if self.league.competitor_type == 'team' else 'player'
        ).order_by('-advanced_date')[:10]
        
        # Add competitor info to advancements
        advancement_list = []
        for advancement in advancements:
            competitor = advancement.team if self.league.competitor_type == 'team' else advancement.player
            
            # Get seed number from seeding data
            seed_number = None
            if self.league.competitor_type == 'team':
                seeding = competitor.knockoutseeding_set.filter(bracket=bracket).first()
                if seeding:
                    seed_number = seeding.seed_number
            # TODO: Add individual player seeding when implemented
            
            advancement_list.append({
                'competitor': competitor,
                'to_stage': advancement.to_stage,
                'seed_number': seed_number,
            })
        
        # Debug logging
        logger.info(f"Bracket view: {len(bracket_rounds)} rounds")
        for i, round_data in enumerate(bracket_rounds):
            logger.info(f"Round {i+1}: {len(round_data['matches'])} matches")
            
        context = {
            'bracket_rounds': bracket_rounds,
            'bracket': bracket,  # Template expects this object
            'bracket_info': {
                'bracket_size': bracket.bracket_size,
                'seeding_style': bracket.seeding_style,
                'games_per_match': bracket.games_per_match,
                'total_rounds': len(bracket_rounds),
            },
            'advancements': advancement_list,
        }
        
        return self.render('tournament/knockout_bracket.html', context)
    
    def _sort_matches_for_bracket_display(self, matches, round_number, bracket_size):
        """Sort matches for proper bracket visualization order."""
        if not matches:
            return matches
        
        # For first round of knockout brackets, we need to arrange matches in proper bracket order
        # The pairing_order field doesn't reflect bracket positions - it's just sequential
        # We need to calculate the proper bracket positions based on seeds
        if round_number == 1:
            return self._calculate_bracket_positions_for_first_round(matches, bracket_size)
        else:
            # For later rounds, use pairing_order as bracket structure is already established
            return sorted(matches, key=lambda m: m.get('pairing_order', 999))
    
    def _calculate_bracket_positions_for_first_round(self, matches, bracket_size):
        """Calculate proper bracket positions for first round matches based on seeds."""
        from heltour.tournament_core.knockout import _build_standard_bracket_positions
        
        # Separate byes from regular matches
        byes = [m for m in matches if m.get('is_bye', False)]
        regular_matches = [m for m in matches if not m.get('is_bye', False)]
        
        if not regular_matches:
            return matches
            
        # For matches without seed information, fall back to pairing_order
        matches_without_seeds = [m for m in regular_matches if m.get('seed1') is None or m.get('seed2') is None]
        if matches_without_seeds:
            # Can't calculate bracket positions without seeds, fall back to pairing_order
            return sorted(matches, key=lambda m: m.get('pairing_order', 999))
        
        # Create a mapping of traditional pairings to bracket positions
        num_matches = len(regular_matches)
        bracket_positions = _build_standard_bracket_positions(num_matches)
        
        # Create traditional seeding pairs (1v32, 2v31, etc.) to find the mapping
        traditional_pairs = []
        for i in range(num_matches):
            # Traditional seeding pairs: seed i+1 with seed n-i
            seed1 = i + 1
            seed2 = bracket_size - i
            traditional_pairs.append((seed1, seed2))
        
        # Find each match's position in the traditional order
        match_positions = []
        for match in regular_matches:
            match_seed1 = match.get('seed1', 0)
            match_seed2 = match.get('seed2', 0)
            
            # Find this match in the traditional pairs
            traditional_index = None
            for i, (trad_seed1, trad_seed2) in enumerate(traditional_pairs):
                if ((match_seed1 == trad_seed1 and match_seed2 == trad_seed2) or
                    (match_seed1 == trad_seed2 and match_seed2 == trad_seed1)):
                    traditional_index = i
                    break
            
            if traditional_index is not None:
                # Get the bracket position for this traditional index
                bracket_position = bracket_positions[traditional_index]
                match_positions.append((bracket_position, match))
            else:
                # Fallback: couldn't find in traditional pairs, use pairing_order
                match_positions.append((match.get('pairing_order', 999), match))
        
        # Sort by bracket position
        match_positions.sort(key=lambda x: x[0])
        sorted_matches = [match for _, match in match_positions]
        
        # Add byes at the end (they don't have bracket positions)
        return sorted_matches + byes
    
    def _get_aggregated_team_pair_scores(self, primary_pairing, round_obj):
        """Get aggregated scores across all matches for a team pair in multi-match tournaments."""
        from django.db.models import Q
        
        # Find all pairings for this specific team pair in this round
        # We need to find pairings where the two teams are the same as in primary_pairing,
        # but they might be in either white/black position due to color alternation
        team_pair_pairings = TeamPairing.objects.filter(
            round=round_obj
        ).filter(
            (Q(white_team=primary_pairing.white_team) & Q(black_team=primary_pairing.black_team)) |
            (Q(white_team=primary_pairing.black_team) & Q(black_team=primary_pairing.white_team))
        ).exclude(black_team__isnull=True)  # Exclude byes
        
        white_total = 0.0
        black_total = 0.0
        all_completed = True
        has_manual_tiebreak = False
        match_count = team_pair_pairings.count()
        
        for pairing in team_pair_pairings:
            # Check if this pairing is completed
            if not self._is_team_match_completed(pairing):
                all_completed = False
                continue
            
            # Add scores based on team orientation
            if pairing.white_team == primary_pairing.white_team:
                # Same orientation as primary pairing
                white_total += pairing.white_points or 0.0
                black_total += pairing.black_points or 0.0
            else:
                # Flipped orientation (teams switched white/black)
                white_total += pairing.black_points or 0.0
                black_total += pairing.white_points or 0.0
            
            # Check for manual tiebreaks
            if pairing.manual_tiebreak_value is not None:
                has_manual_tiebreak = True
        
        return {
            'white_total': white_total,
            'black_total': black_total,
            'all_completed': all_completed,
            'has_manual_tiebreak': has_manual_tiebreak,
            'match_count': match_count,
        }

    def _is_team_match_completed(self, team_pairing):
        """Check if all board pairings for a team match have results."""
        board_pairings = team_pairing.teamplayerpairing_set.all()
        if not board_pairings.exists():
            return False
        return all(board_pairing.result != '' for board_pairing in board_pairings)


class KnockoutSeasonLandingView(SeasonView):
    """Modified season landing view for knockout tournaments."""
    
    @property 
    def player(self):
        """Get player if available, otherwise return None."""
        if hasattr(self, '_player'):
            return self._player
        return None
    
    @player.setter
    def player(self, value):
        self._player = value
    
    def view(self):
        if not self.season.league.pairing_type.startswith('knockout'):
            # Fall back to regular season landing
            return SeasonLandingView.view(self)
        
        # Handle POST request for tournament advancement
        if self.request.method == 'POST' and 'advance_tournament' in self.request.POST:
            return self._handle_advancement()
            
        from heltour.tournament.models import KnockoutBracket, KnockoutAdvancement
        from heltour.tournament_core.knockout import get_knockout_stage_name
        
        current_seasons, completed_seasons = _get_season_lists(self.league)
        has_more_seasons = len(current_seasons) + len(completed_seasons) > 1
        
        # Get active round
        active_round = Round.objects.filter(
            season=self.season, 
            publish_pairings=True,
            is_completed=False, 
            start_date__lt=timezone.now(),
            end_date__gt=timezone.now()
        ).order_by('-number').first()
        
        # Get bracket status
        try:
            bracket = KnockoutBracket.objects.get(season=self.season)
            bracket_status = self._get_bracket_status(bracket)
        except KnockoutBracket.DoesNotExist:
            bracket_status = None
        
        # Get recent results
        recent_results = self._get_recent_results()
        
        # Get finalist preview or elimination summary
        finalist_preview = self._get_finalist_preview(bracket_status)
        elimination_summary = self._get_elimination_summary() if not finalist_preview else None
        
        # Get advancement status for admin users
        advancement_info = self._get_advancement_info() if self.request.user.is_staff else None
        
        links_doc = SeasonDocument.objects.filter(season=self.season, type='links').first()
        
        context = {
            'has_more_seasons': has_more_seasons,
            'current_seasons': current_seasons,
            'completed_seasons': completed_seasons,
            'active_round': active_round,
            'bracket_status': bracket_status,
            'recent_results': recent_results,
            'finalist_preview': finalist_preview,
            'elimination_summary': elimination_summary,
            'advancement_info': advancement_info,
            'links_doc': links_doc,
            'can_edit_document': self.request.user.has_perm('tournament.change_document', self.league),
        }
        
        return self.render('tournament/knockout_season_landing.html', context)
    
    def _get_bracket_status(self, bracket):
        """Get current status of the knockout bracket."""
        from heltour.tournament_core.knockout import get_knockout_stage_name
        
        rounds = Round.objects.filter(season=self.season).order_by('number')
        total_rounds = len(rounds)
        completed_rounds = rounds.filter(is_completed=True).count()
        
        # Calculate progress
        progress_percentage = int((completed_rounds / max(total_rounds, 1)) * 100)
        
        # Get current stage
        if completed_rounds >= total_rounds:
            # Tournament complete
            current_stage = "completed"
            next_stage = None
            remaining_count = 1
            
            # Get champion
            if self.league.competitor_type == 'team':
                last_pairing = TeamPairing.objects.filter(
                    round__season=self.season
                ).order_by('-round__number').first()
                if last_pairing and last_pairing.result:
                    champion = last_pairing.white_team if last_pairing.white_points > last_pairing.black_points else last_pairing.black_team
                else:
                    champion = None
            else:
                last_pairing = LonePlayerPairing.objects.filter(
                    round__season=self.season
                ).order_by('-round__number').first()
                if last_pairing and last_pairing.result:
                    champion = last_pairing.white if last_pairing.result in ['1-0', '1X-0F'] else last_pairing.black
                else:
                    champion = None
        else:
            # Tournament in progress
            current_round = completed_rounds + 1
            current_teams_remaining = bracket.bracket_size // (2 ** (current_round - 1))
            current_stage = get_knockout_stage_name(current_teams_remaining)
            if current_round < total_rounds:
                next_teams_remaining = bracket.bracket_size // (2 ** current_round)
                next_stage = get_knockout_stage_name(next_teams_remaining)
            else:
                next_stage = None
            remaining_count = bracket.bracket_size // (2 ** completed_rounds)
            champion = None
        
        return {
            'is_completed': completed_rounds >= total_rounds,
            'current_stage': current_stage,
            'next_stage': next_stage,
            'remaining_count': remaining_count,
            'progress_percentage': progress_percentage,
            'champion': champion,
        }
    
    def _get_recent_results(self):
        """Get recent match results."""
        if self.league.competitor_type == 'team':
            recent_pairings = TeamPairing.objects.filter(
                round__season=self.season,
                round__is_completed=True
            ).select_related(
                'white_team', 'black_team'
            ).prefetch_related(
                'teamplayerpairing_set'
            ).order_by('-round__number', '-pairing_order')[:20]  # Get more records to filter from
            
            results = []
            for pairing in recent_pairings:
                if pairing.black_team_id and self._is_team_match_completed(pairing):  # Not a bye and completed
                    results.append({
                        'competitor1': pairing.white_team,
                        'competitor2': pairing.black_team,
                        'competitor1_score': pairing.white_points,
                        'competitor2_score': pairing.black_points,
                        'competitor1_won': pairing.white_points > pairing.black_points,
                        'competitor2_won': pairing.black_points > pairing.white_points,
                        'manual_tiebreak': pairing.manual_tiebreak_value is not None,
                    })
                    if len(results) >= 5:  # Limit to 5 recent results for display
                        break
            return results
        else:
            # Individual tournament results
            recent_pairings = LonePlayerPairing.objects.filter(
                round__season=self.season,
                round__is_completed=True
            ).exclude(result='').select_related(
                'white', 'black'
            ).order_by('-round__number', '-pairing_order')[:5]
            
            results = []
            for pairing in recent_pairings:
                if pairing.black_id:  # Not a bye
                    if pairing.result in ['1-0', '1X-0F']:
                        comp1_score, comp2_score = 1.0, 0.0
                        comp1_won, comp2_won = True, False
                    elif pairing.result in ['0-1', '0F-1X']:
                        comp1_score, comp2_score = 0.0, 1.0
                        comp1_won, comp2_won = False, True
                    else:  # Draw
                        comp1_score, comp2_score = 0.5, 0.5
                        comp1_won, comp2_won = False, False
                    
                    results.append({
                        'competitor1': pairing.white,
                        'competitor2': pairing.black,
                        'competitor1_score': comp1_score,
                        'competitor2_score': comp2_score,
                        'competitor1_won': comp1_won,
                        'competitor2_won': comp2_won,
                        'manual_tiebreak': False,
                    })
            return results
    
    def _get_finalist_preview(self, bracket_status):
        """Get preview of finalists or next stage competitors."""
        if not bracket_status or bracket_status['remaining_count'] > 4:
            return None
            
        # Get competitors in current stage (semifinals or finals)
        current_round = Round.objects.filter(
            season=self.season,
            is_completed=False
        ).order_by('number').first()
        
        if not current_round:
            return None
            
        competitors = []
        if self.league.competitor_type == 'team':
            pairings = TeamPairing.objects.filter(round=current_round).select_related(
                'white_team', 'black_team'
            ).prefetch_related('white_team__knockoutseeding_set', 'black_team__knockoutseeding_set')
            
            for pairing in pairings:
                if pairing.white_team:
                    seeding = pairing.white_team.knockoutseeding_set.first()
                    competitors.append({
                        'name': pairing.white_team.name,
                        'number': pairing.white_team.number,
                        'seed': seeding.seed_number if seeding else None,
                    })
                if pairing.black_team:
                    seeding = pairing.black_team.knockoutseeding_set.first()
                    competitors.append({
                        'name': pairing.black_team.name, 
                        'number': pairing.black_team.number,
                        'seed': seeding.seed_number if seeding else None,
                    })
        else:
            pairings = LonePlayerPairing.objects.filter(round=current_round).select_related(
                'white', 'black'
            )
            
            for pairing in pairings:
                if pairing.white:
                    competitors.append({
                        'lichess_username': pairing.white.lichess_username,
                        'seed': None,  # No seeding for individual tournaments yet
                    })
                if pairing.black:
                    competitors.append({
                        'lichess_username': pairing.black.lichess_username,
                        'seed': None,  # No seeding for individual tournaments yet
                    })
        
        return competitors
    
    def _get_elimination_summary(self):
        """Get summary of recent eliminations."""
        # This would require tracking eliminations, which we can implement later
        # For now, return empty list
        return []
    
    def _get_advancement_info(self):
        """Get information about tournament advancement status for admin."""
        if not self.request.user.is_staff:
            return None
            
        # Find the most recent completed round
        last_completed_round = Round.objects.filter(
            season=self.season, 
            is_completed=True
        ).order_by('-number').first()
        
        if not last_completed_round:
            return {
                'can_advance': False,
                'reason': 'No completed rounds found',
                'round_to_advance': None,
                'tied_matches': [],
            }
        
        # Check for tied matches that need manual tiebreak resolution
        tied_matches = []
        if self.league.competitor_type == 'team':
            tied_pairings = TeamPairing.objects.filter(
                round=last_completed_round,
                white_points__isnull=False,
                black_points__isnull=False,
                manual_tiebreak_value__isnull=True
            ).filter(
                white_points=F('black_points')
            ).select_related('white_team', 'black_team')
            
            for pairing in tied_pairings:
                tied_matches.append({
                    'id': pairing.id,
                    'competitor1': pairing.white_team.name,
                    'competitor2': pairing.black_team.name,
                    'score': pairing.white_points,
                })
        else:
            # Individual tournaments - handle ties differently
            # For now, assume individual tournaments don't need manual tiebreak resolution
            pass
        
        # Determine if we can advance
        can_advance = len(tied_matches) == 0
        reason = None
        if not can_advance:
            reason = f"{len(tied_matches)} tied match(es) require manual tiebreak resolution"
        
        return {
            'can_advance': can_advance,
            'reason': reason,
            'round_to_advance': last_completed_round,
            'tied_matches': tied_matches,
        }
    
    def _handle_advancement(self):
        """Handle POST request to advance the knockout tournament."""
        if not self.request.user.is_staff:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Only staff can advance tournaments")
        
        try:
            from heltour.tournament.pairinggen import advance_knockout_tournament
            from django.contrib import messages
            from django.shortcuts import redirect
            
            # Find the round to advance from
            last_completed_round = Round.objects.filter(
                season=self.season, 
                is_completed=True
            ).order_by('-number').first()
            
            if not last_completed_round:
                messages.error(self.request, "No completed rounds found to advance from")
                return redirect(self.request.path)
            
            # Check for unresolved tied matches
            advancement_info = self._get_advancement_info()
            if not advancement_info['can_advance']:
                messages.error(self.request, f"Cannot advance tournament: {advancement_info['reason']}")
                return redirect(self.request.path)
            
            # Perform the advancement
            next_round = advance_knockout_tournament(last_completed_round)
            
            if next_round:
                messages.success(
                    self.request, 
                    f"Successfully advanced tournament to Round {next_round.number}"
                )
            else:
                messages.success(self.request, "Tournament has been completed - all rounds finished")
            
            return redirect(self.request.path)
            
        except Exception as e:
            from django.contrib import messages
            messages.error(self.request, f"Error advancing tournament: {str(e)}")
            return redirect(self.request.path)

    def _is_team_match_completed(self, team_pairing):
        """Check if all board pairings for a team match have results."""
        board_pairings = team_pairing.teamplayerpairing_set.all()
        if not board_pairings.exists():
            return False
        return all(board_pairing.result != '' for board_pairing in board_pairings)


class KnockoutPairingsView(PairingsView):
    """Modified pairings view for knockout tournaments."""
    
    @property 
    def player(self):
        """Get player if available, otherwise return None."""
        if hasattr(self, '_player'):
            return self._player
        return None
    
    @player.setter
    def player(self, value):
        self._player = value
    
    def view(self, round_number=None, team_number=None):
        if not self.season.league.pairing_type.startswith('knockout'):
            # Fall back to regular pairings view
            return super().view(round_number, team_number)
        
        if self.league.is_team_league():
            return self.knockout_team_view(round_number, team_number)
        else:
            return self.knockout_lone_view(round_number, team_number)
    
    def knockout_team_view(self, round_number=None, team_number=None):
        """Knockout-specific team pairings view."""
        from heltour.tournament.models import KnockoutBracket
        from heltour.tournament_core.knockout import get_knockout_stage_name
        
        # Get the knockout bracket
        try:
            bracket = KnockoutBracket.objects.get(season=self.season)
        except KnockoutBracket.DoesNotExist:
            bracket = None
        
        # For multi-match tournaments, use custom context to show all matches between teams
        if bracket and bracket.matches_per_stage > 1 and team_number:
            context = self.get_knockout_multi_match_context(
                self.league.tag, self.season.tag, round_number, team_number, bracket,
                self.request.user.has_perm('tournament.change_pairing', self.league)
            )
        else:
            # Get context from parent class but modify for knockout
            context = self.get_team_context(
                self.league.tag, self.season.tag, round_number, team_number,
                self.request.user.has_perm('tournament.change_pairing', self.league)
            )
        
        # Add knockout-specific information
        if bracket and context['round_number']:
            teams_remaining = bracket.bracket_size // (2 ** (context['round_number'] - 1))
            current_stage = get_knockout_stage_name(teams_remaining)
            context['current_stage'] = current_stage
            
            # Convert round number list to include stage names
            stage_rounds = []
            for rnum in context['round_number_list']:
                rnum_teams_remaining = bracket.bracket_size // (2 ** (rnum - 1))
                stage_name = get_knockout_stage_name(rnum_teams_remaining)
                stage_rounds.append({
                    'round_number': rnum,
                    'stage_name': stage_name,
                })
            context['round_number_list'] = stage_rounds
            
            # Add stage info
            total_pairings = len(context['pairing_lists']) if context['pairing_lists'] else 0
            total_competitors = total_pairings * 2
            context['stage_info'] = {
                'stage_name': current_stage,
                'total_matches': total_pairings,
                'total_competitors': total_competitors,
                'games_per_match': bracket.games_per_match,
            }
        
        return self.render('tournament/knockout_pairings.html', context)
    
    def get_knockout_multi_match_context(self, league_tag, season_tag, round_number, team_number, bracket, can_change_pairing):
        """Get context for multi-match knockout tournaments showing all matches between two teams."""
        specified_round = round_number is not None
        round_number_list = [round_.number for round_ in Round.objects.filter(season=self.season,
                                                                              publish_pairings=True).order_by('-number')]
        if round_number is None:
            try:
                round_number = round_number_list[0]
            except IndexError:
                pass
        
        team_list = self.season.team_set.order_by('name')
        current_team = get_object_or_404(team_list, number=team_number)
        
        # Find ALL pairings involving this team in this round
        from django.db.models import Q
        team_pairings = TeamPairing.objects.filter(
            round__number=round_number,
            round__season=self.season
        ).filter(
            Q(white_team=current_team) | Q(black_team=current_team)
        ).order_by('pairing_order').select_related('white_team', 'black_team').nocache()
        
        # For multi-match, group pairings by opponent team
        from collections import defaultdict
        opponent_pairings = defaultdict(list)
        
        for pairing in team_pairings:
            if pairing.black_team is None:  # Bye
                opponent_pairings['BYE'].append(pairing)
            else:
                # Determine opponent
                opponent = pairing.black_team if pairing.white_team == current_team else pairing.white_team
                # Use opponent ID as key to ensure consistency
                opponent_pairings[opponent.id].append(pairing)
        
        # Convert to list format expected by template with aggregation info
        pairing_lists = []
        opponent_aggregates = {}
        
        for opponent_id, pairings in opponent_pairings.items():
            if opponent_id == 'BYE':
                # Handle bye case
                for pairing in pairings:
                    board_pairings = list(
                        pairing.teamplayerpairing_set.order_by('board_number')
                        .select_related('white', 'black')
                        .nocache()
                    )
                    pairing_lists.append(board_pairings)
            else:
                # Calculate aggregate scores for this opponent
                total_current_team_points = 0.0
                total_opponent_points = 0.0
                all_completed = True
                
                for pairing in pairings:
                    if not self._is_team_match_completed(pairing):
                        all_completed = False
                        continue
                    
                    # Add scores based on team orientation
                    if pairing.white_team == current_team:
                        total_current_team_points += pairing.white_points or 0.0
                        total_opponent_points += pairing.black_points or 0.0
                    else:
                        total_current_team_points += pairing.black_points or 0.0
                        total_opponent_points += pairing.white_points or 0.0
                
                # Store aggregate info for this opponent
                opponent_team = pairings[0].white_team if pairings[0].white_team != current_team else pairings[0].black_team
                opponent_aggregates[opponent_id] = {
                    'opponent_team': opponent_team,
                    'current_team_total': total_current_team_points,
                    'opponent_total': total_opponent_points,
                    'all_completed': all_completed,
                    'match_count': len(pairings),
                }
                
                # Show all matches against this opponent
                for pairing in pairings:
                    board_pairings = list(
                        pairing.teamplayerpairing_set.order_by('board_number')
                        .select_related('white', 'black')
                        .nocache()
                    )
                    pairing_lists.append(board_pairings)
        
        # Get team byes for this round
        team_byes = list(TeamBye.objects.filter(
            round__number=round_number,
            round__season=self.season,
            team=current_team
        ).select_related('team').nocache())
        
        round_ = Round.objects.filter(number=round_number, season=self.season).first()
        presences = {(pp.player_id, pp.pairing_id): pp for pp in
                     PlayerPresence.objects.filter(round=round_)}
        presence_events_map = _build_presence_events_map(round_, can_change_pairing)

        if pairing_lists:
            contact_deadline = round_.start_date + self.league.get_leaguesetting().contact_period
            in_contact_period = timezone.now() < contact_deadline
        else:
            contact_deadline = None
            in_contact_period = False
        
        def status(player, pairing):
            return self._player_status(
                player, pairing, presences, in_contact_period, contact_deadline
            ) if pairing_lists else (None, '')
        
        # Add presences to match the format expected by the template
        pairing_lists = [
            [((p,) + status(p.white_team_player(), p) + status(p.black_team_player(), p)) for p in
             p_list]
            for p_list in pairing_lists
        ]
        
        # Get unavailable players
        unavailable_players = {pa.player for pa in
                               PlayerAvailability.objects.filter(round__season=self.season,
                                                                 round__number=round_number,
                                                                 is_available=False) \
                                   .select_related('player')
                                   .nocache()}
        
        # Get captains
        captains = {tm.player for tm in
                    TeamMember.objects.filter(team__season=self.season, is_captain=True)}
        
        context = {
            'round_number': round_number,
            'round_number_list': round_number_list,
            'specified_round': specified_round,
            'pairing_lists': pairing_lists,
            'team_list': team_list,
            'current_team': current_team,
            'status': status,
            'team_byes': team_byes,
            'can_change_pairing': can_change_pairing,
            'captains': captains,
            'unavailable_players': unavailable_players,
            'show_legend': len(unavailable_players) > 0,
            'specified_team': True,
            'can_edit': can_change_pairing,
            'presence_events_map': presence_events_map,
            'can_view_presence_log': can_change_pairing,
            'is_multi_match': True,
            'matches_per_stage': bracket.matches_per_stage,
            'opponent_aggregates': opponent_aggregates,  # Add aggregate data for template
        }
        
        return context
    
    def _is_team_match_completed(self, team_pairing):
        """Check if all board pairings for a team match have results."""
        board_pairings = team_pairing.teamplayerpairing_set.all()
        if not board_pairings.exists():
            return False
        return all(board_pairing.result != '' for board_pairing in board_pairings)
    
    def _player_status(self, player, pairing, presences, in_contact_period, contact_deadline):
        """Get player status for pairings display."""
        if player is None:
            return (None, 'no player')
        if (player is pairing.white and pairing.white_confirmed) or (player is pairing.black and pairing.black_confirmed):
            return ('confirmed', 'confirmed')
        pres = presences.get((player.pk, pairing.pk))
        if in_contact_period:
            if not pres or not pres.first_msg_time:
                return (None, 'no contact yet')
            else:
                return ('yes', 'in contact')
        else:
            if not pres or not pres.first_msg_time:
                return ('no', 'unresponsive')
            elif pres.first_msg_time > contact_deadline:
                return ('alert', 'late contact')
            else:
                return ('yes', 'in contact')
    
    def knockout_lone_view(self, round_number=None, team_number=None):
        """Knockout-specific individual pairings view."""
        # Similar to team view but for individual tournaments
        context = self.get_lone_context(round_number, team_number)
        
        # Add knockout-specific modifications here if needed
        # For now, use regular lone pairings template
        return self.render('tournament/lone_pairings.html', context)
