from collections import defaultdict
from datetime import timedelta
from icalendar import Calendar, Event

import itertools
import json
import math
import re
import reversion

from decorators import cached_as
from django.core.mail.message import EmailMessage
from django.db.models.query import Prefetch
from django.http.response import Http404, JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.generic import View
from django.utils.text import slugify
from django.contrib.auth import login
from django.contrib.auth.models import User

from heltour.tournament import slackapi, alternates_manager, uptime, lichessapi
from heltour.tournament.templatetags.tournament_extras import leagueurl
from .forms import *
from .models import *
from heltour.tournament.forms import DeleteNominationForm


# Helpers for view caching definitions
common_team_models = [League, Season, Round, Team]
common_lone_models = [League, Season, Round, LonePlayerScore, LonePlayerPairing, PlayerPairing, PlayerBye, SeasonPlayer,
                      Player, SeasonPrize, SeasonPrizeWinner]


#-------------------------------------------------------------------------------
# Base classes

class BaseView(View):
    def get(self, request, *args, **kwargs):
        self.read_context()
        return self.view(*self.args, **self.kwargs)

    def post(self, request, *args, **kwargs):
        if not hasattr(self, 'view_post'):
            return super(BaseView, self).post(request, *args, **kwargs)
        self.read_context()
        return self.view_post(*self.args, **self.kwargs)

    def read_context(self):
        pass

    def render(self, template, context):
        return render(self.request, template, context)

class LeagueView(BaseView):
    def read_context(self):
        league_tag = self.kwargs.pop('league_tag')
        season_tag = self.kwargs.pop('season_tag', None)
        self.league = _get_league(league_tag)
        self.season = _get_season(league_tag, season_tag, True)

    def render(self, template, context):
        context.update({
            'league': self.league,
            'season': self.season,
            'nav_tree': _get_nav_tree(self.league.tag, self.season.tag if self.season is not None else None),
            'other_leagues': League.objects.filter(is_active=True).order_by('display_order').exclude(pk=self.league.pk)
        })
        return render(self.request, template, context)

class SeasonView(LeagueView):
    def get(self, request, *args, **kwargs):
        self.read_context()
        if not self._season_specified:
            return redirect('by_league:by_season:%s' % request.resolver_match.url_name, *self.args, league_tag=self.league.tag, season_tag=self.season.tag, **self.kwargs)
        return self.view(*self.args, **self.kwargs)

    def read_context(self):
        league_tag = self.kwargs.pop('league_tag')
        season_tag = self.kwargs.pop('season_tag', None)
        self.league = _get_league(league_tag)
        self.season = _get_season(league_tag, season_tag, False)
        self._season_specified = season_tag is not None

class UrlAuthMixin:
    def persist_url_auth(self, secret_token):
        if secret_token is not None:
            auth = PrivateUrlAuth.objects.filter(secret_token=secret_token).first()
            if auth is not None and not auth.is_expired():
                self.request.session['url_auth_token'] = secret_token
                auth.used = True
                auth.save()
            return True
        return False

    def get_authenticated_user(self):
        username = None
        player = None

        secret_token = self.request.session.get('url_auth_token', '')
        auth = PrivateUrlAuth.objects.filter(secret_token=secret_token).first()
        if auth is not None and not auth.is_expired():
            username = auth.authenticated_user
            player = Player.objects.filter(lichess_username__iexact=username).first()
        # Clean up the DB
        for expired_auth in PrivateUrlAuth.objects.filter(expires__lt=timezone.now()):
            expired_auth.delete()
        return username, player

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

#-------------------------------------------------------------------------------
# Actual views

class HomeView(BaseView):
    def view(self):
        leagues = League.objects.filter(is_active=True).order_by('display_order')

        context = {
            'leagues': leagues,
        }
        return self.render('tournament/home.html', context)

class LeagueHomeView(LeagueView):
    def view(self):
        if self.league.competitor_type == 'team':
            return self.team_view()
        else:
            return self.lone_view()

    def team_view(self):
        other_leagues = League.objects.filter(is_active=True).exclude(pk=self.league.pk).order_by('display_order')

        rules_doc = LeagueDocument.objects.filter(league=self.league, type='rules').first()
        rules_doc_tag = rules_doc.tag if rules_doc is not None else None
        intro_doc = LeagueDocument.objects.filter(league=self.league, type='intro').first()

        if self.season is None:
            context = {
                'rules_doc_tag': rules_doc_tag,
                'intro_doc': intro_doc,
                'can_edit_document': self.request.user.has_perm('tournament.change_document', self.league),
                'other_leagues': other_leagues,
            }
            return self.render('tournament/team_league_home.html', context)

        season_list = Season.objects.filter(league=self.league, is_active=True).order_by('-start_date', '-id').exclude(pk=self.season.pk)
        registration_season = Season.objects.filter(league=self.league, registration_open=True).order_by('-start_date').first()

        team_scores = list(enumerate(sorted(TeamScore.objects.filter(team__season=self.season).select_related('team').nocache(), reverse=True)[:5], 1))

        context = {
            'team_scores': team_scores,
            'season_list': season_list,
            'rules_doc_tag': rules_doc_tag,
            'intro_doc': intro_doc,
            'can_edit_document': self.request.user.has_perm('tournament.change_document', self.league),
            'registration_season': registration_season,
            'other_leagues': other_leagues,
        }
        return self.render('tournament/team_league_home.html', context)

    def lone_view(self):
        other_leagues = League.objects.filter(is_active=True).exclude(pk=self.league.pk).order_by('display_order')

        rules_doc = LeagueDocument.objects.filter(league=self.league, type='rules').first()
        rules_doc_tag = rules_doc.tag if rules_doc is not None else None
        intro_doc = LeagueDocument.objects.filter(league=self.league, type='intro').first()

        if self.season is None:
            context = {
                'rules_doc_tag': rules_doc_tag,
                'intro_doc': intro_doc,
                'can_edit_document': self.request.user.has_perm('tournament.change_document', self.league),
                'other_leagues': other_leagues,
            }
            return self.render('tournament/lone_league_home.html', context)

        season_list = Season.objects.filter(league=self.league, is_active=True).order_by('-start_date', '-id').exclude(pk=self.season.pk)
        registration_season = Season.objects.filter(league=self.league, registration_open=True).order_by('-start_date').first()

        player_scores = _lone_player_scores(self.season, final=True)[:5]

        if self.season.is_completed:
            prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season=self.season)
            player_highlights = _get_player_highlights(prize_winners)
        else:
            player_highlights = []

        context = {
            'player_scores': player_scores,
            'season_list': season_list,
            'rules_doc_tag': rules_doc_tag,
            'intro_doc': intro_doc,
            'can_edit_document': self.request.user.has_perm('tournament.change_document', self.league),
            'registration_season': registration_season,
            'other_leagues': other_leagues,
            'player_highlights': player_highlights,
        }
        return self.render('tournament/lone_league_home.html', context)

class SeasonLandingView(SeasonView):
    def view(self):
        if self.league.competitor_type == 'team':
            return self.team_view()
        else:
            return self.lone_view()

    def team_view(self):
        @cached_as(SeasonDocument, Document, TeamScore, TeamPairing, *common_team_models)
        def _view(league_tag, season_tag, is_staff):
            if self.season.is_completed:
                return self.team_completed_season_view()

            default_season, season_list = self.get_season_list()

            active_round = Round.objects.filter(season=self.season, publish_pairings=True, is_completed=False, start_date__lt=timezone.now(), end_date__gt=timezone.now()) \
                                        .order_by('-number') \
                                        .first()
            last_round = Round.objects.filter(season=self.season, is_completed=True).order_by('-number').first()
            last_round_pairings = last_round.teampairing_set.all() if last_round is not None else None
            team_scores = list(enumerate(sorted(TeamScore.objects.filter(team__season=self.season), reverse=True)[:5], 1))

            links_doc = SeasonDocument.objects.filter(season=self.season, type='links').first()

            context = {
                'default_season': default_season,
                'season_list': season_list,
                'active_round': active_round,
                'last_round': last_round,
                'last_round_pairings': last_round_pairings,
                'team_scores': team_scores,
                'links_doc': links_doc,
                'can_edit_document': self.request.user.has_perm('tournament.change_document', self.league),
            }
            return self.render('tournament/team_season_landing.html', context)
        return _view(self.league.tag, self.season.tag, self.request.user.is_staff)

    def lone_view(self):
        @cached_as(SeasonDocument, Document, *common_lone_models)
        def _view(league_tag, season_tag, is_staff):
            if self.season.is_completed:
                return self.lone_completed_season_view()

            default_season, season_list = self.get_season_list()

            active_round = Round.objects.filter(season=self.season, publish_pairings=True, is_completed=False, start_date__lt=timezone.now(), end_date__gt=timezone.now()) \
                                        .order_by('-number') \
                                        .first()
            last_round = Round.objects.filter(season=self.season, is_completed=True).order_by('-number').first()
            last_round_pairings = last_round.loneplayerpairing_set.exclude(result='').order_by('pairing_order')[:10].nocache() if last_round is not None else None
            player_scores = _lone_player_scores(self.season, final=True)[:5]

            links_doc = SeasonDocument.objects.filter(season=self.season, type='links').first()

            context = {
                'default_season': default_season,
                'season_list': season_list,
                'active_round': active_round,
                'last_round': last_round,
                'last_round_pairings': last_round_pairings,
                'player_scores': player_scores,
                'links_doc': links_doc,
                'can_edit_document': self.request.user.has_perm('tournament.change_document', self.league),
            }
            return self.render('tournament/lone_season_landing.html', context)
        return _view(self.league.tag, self.season.tag, self.request.user.is_staff)

    def team_completed_season_view(self):
        default_season, season_list = self.get_season_list()

        round_numbers = list(range(1, self.season.rounds + 1))
        team_scores = list(enumerate(sorted(TeamScore.objects.filter(team__season=self.season).select_related('team').nocache(), reverse=True), 1))

        first_team = team_scores[0][1] if len(team_scores) > 0 else None
        second_team = team_scores[1][1] if len(team_scores) > 1 else None
        third_team = team_scores[2][1] if len(team_scores) > 2 else None

        links_doc = SeasonDocument.objects.filter(season=self.season, type='links').first()

        context = {
            'default_season': default_season,
            'season_list': season_list,
            'round_numbers': round_numbers,
            'team_scores': team_scores,
            'first_team': first_team,
            'second_team': second_team,
            'third_team': third_team,
            'links_doc': links_doc,
            'can_edit_document': self.request.user.has_perm('tournament.change_document', self.league),
        }
        return self.render('tournament/team_completed_season_landing.html', context)

    def lone_completed_season_view(self):
        default_season, season_list = self.get_season_list()

        round_numbers = list(range(1, self.season.rounds + 1))
        player_scores = _lone_player_scores(self.season)

        first_player = player_scores[0][1] if len(player_scores) > 0 else None
        second_player = player_scores[1][1] if len(player_scores) > 1 else None
        third_player = player_scores[2][1] if len(player_scores) > 2 else None

        u1600_winner = SeasonPrizeWinner.objects.filter(season_prize__season=self.season, season_prize__max_rating=1600, season_prize__rank=1).first()
        if u1600_winner is not None:
            u1600_player = find([ps[1] for ps in player_scores], season_player__player=u1600_winner.player)
        else:
            u1600_player = None

        prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season=self.season)
        player_highlights = _get_player_highlights(prize_winners)

        links_doc = SeasonDocument.objects.filter(season=self.season, type='links').first()

        context = {
            'default_season': default_season,
            'season_list': season_list,
            'round_numbers': round_numbers,
            'player_scores': player_scores,
            'first_player': first_player,
            'second_player': second_player,
            'third_player': third_player,
            'u1600_player': u1600_player,
            'player_highlights': player_highlights,
            'links_doc': links_doc,
            'can_edit_document': self.request.user.has_perm('tournament.change_document', self.league),
        }
        return self.render('tournament/lone_completed_season_landing.html', context)

    def get_season_list(self):
        default_season = _get_default_season(self.league.tag, allow_none=True)
        season_list = Season.objects.filter(league=self.league, is_active=True).order_by('-start_date', '-id')
        if default_season:
            season_list = season_list.exclude(pk=default_season.pk)
        return default_season, season_list

class PairingsView(SeasonView):
    def view(self, round_number=None, team_number=None):
        if self.league.competitor_type == 'team':
            return self.team_view(round_number, team_number)
        else:
            return self.lone_view(round_number, team_number)

    def get_team_context(self, league_tag, season_tag, round_number, team_number, is_staff, can_change_pairing):
        specified_round = round_number is not None
        round_number_list = [round_.number for round_ in Round.objects.filter(season=self.season, publish_pairings=True).order_by('-number')]
        if round_number is None:
            try:
                round_number = round_number_list[0]
            except IndexError:
                pass
        team_list = self.season.team_set.order_by('name')
        team_pairings = TeamPairing.objects.filter(round__number=round_number, round__season=self.season) \
                                           .order_by('pairing_order') \
                                           .select_related('white_team', 'black_team') \
                                           .nocache()
        if team_number is not None:
            current_team = get_object_or_404(team_list, number=team_number)
            team_pairings = team_pairings.filter(white_team=current_team) | team_pairings.filter(black_team=current_team)
        else:
            current_team = None
        pairing_lists = [list(
                              team_pairing.teamplayerpairing_set.order_by('board_number')
                                          .select_related('white', 'black')
                                          .nocache()
                        ) for team_pairing in team_pairings]
        unavailable_players = {pa.player for pa in PlayerAvailability.objects.filter(round__season=self.season, round__number=round_number, is_available=False) \
                                                                             .select_related('player')
                                                                             .nocache()}
        captains = {tm.player for tm in TeamMember.objects.filter(team__season=self.season, is_captain=True)}

        # Show the legend if at least one the players in the visible pairings is unavailable
        show_legend = len(unavailable_players & ({p.white for plist in pairing_lists for p in plist} | {p.black for plist in pairing_lists for p in plist})) > 0

        return {
            'round_number': round_number,
            'round_number_list': round_number_list,
            'current_team': current_team,
            'team_list': team_list,
            'pairing_lists': pairing_lists,
            'captains': captains,
            'unavailable_players': unavailable_players,
            'show_legend': show_legend,
            'specified_round': specified_round,
            'specified_team': team_number is not None,
            'can_edit': can_change_pairing
        }

    def team_view(self, round_number=None, team_number=None):
        @cached_as(TeamScore, TeamPairing, TeamMember, SeasonPlayer, AlternateAssignment, Player, PlayerAvailability, TeamPlayerPairing,
                   PlayerPairing, *common_team_models)
        def _view(league_tag, season_tag, round_number, team_number, is_staff, can_change_pairing):
            context = self.get_team_context(league_tag, season_tag, round_number, team_number, is_staff, can_change_pairing)
            return self.render('tournament/team_pairings.html', context)
        return _view(
                     self.league.tag, self.season.tag, round_number, team_number, self.request.user.is_staff,
                     self.request.user.has_perm('tournament.change_pairing', self.league))

    def get_lone_context(self, round_number=None, team_number=None):
        specified_round = round_number is not None
        round_number_list = [round_.number for round_ in Round.objects.filter(season=self.season, publish_pairings=True).order_by('-number')]
        if round_number is None:
            try:
                round_number = round_number_list[0]
            except IndexError:
                pass
        round_ = Round.objects.filter(number=round_number, season=self.season).first()
        pairings = LonePlayerPairing.objects.filter(round=round_).order_by('pairing_order').select_related('white', 'black').nocache()
        byes = PlayerBye.objects.filter(round=round_).order_by('type', 'player_rank', 'player__lichess_username').select_related('player').nocache()

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
        duplicate_players = {k for k, v in player_refcounts.items() if v > 1}

        active_players = {sp.player for sp in SeasonPlayer.objects.filter(season=self.season, is_active=True)}

        can_change_pairing = self.request.user.has_perm('tournament.change_pairing', self.league)

        presences = {(pp.player_id, pp.pairing_id): pp for pp in PlayerPresence.objects.filter(round=round_)}
        if pairings:
            contact_deadline = round_.start_date + timedelta(hours=48)
            in_contact_period = timezone.now() < contact_deadline

        def pairing_error(pairing):
            if not self.request.user.is_staff:
                return None
            if pairing.white == None or pairing.black == None:
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
            if not can_change_pairing:
                return (None, None)
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

        # Add errors
        pairings = [(p, pairing_error(p)) + status(p.white, p) + status(p.black, p) for p in pairings]
        byes = [(b, bye_error(b)) for b in byes]

        return {
            'round_': round_,
            'round_number_list': round_number_list,
            'pairings': pairings,
            'byes': byes,
            'specified_round': specified_round,
            'next_pairing_order': next_pairing_order,
            'duplicate_players': duplicate_players,
            'can_edit': can_change_pairing
        }

    def lone_view(self, round_number=None, team_number=None):
        context = self.get_lone_context(round_number, team_number)
        return self.render('tournament/lone_pairings.html', context)

class ICalPairingsView(PairingsView, ICalMixin):
    def view(self, round_number=None, team_number=None):
        if self.league.competitor_type == 'team':
            return self.team_view(round_number, team_number)
        else:
            return self.lone_view(round_number, team_number)

    def team_view(self, round_number=None, team_number=None):
        context = self.get_team_context(
                                        self.league.tag, self.season.tag, round_number, team_number, self.request.user.is_staff,
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
            for pairing in pairing_list:
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

class ICalPlayerView(BaseView, ICalMixin):
    def view(self, username):
        player = get_object_or_404(Player, lichess_username__iexact=username)
        calendar_title = "{} Chess Games".format(player.lichess_username)
        uid_component = 'all'
        pairings = player.pairings.exclude(scheduled_time=None)
        return self.ical_from_pairings_list(pairings, calendar_title, uid_component)

class RegisterView(LeagueView):
    def view(self, post=False):
        if self.season is not None and self.season.registration_open:
            reg_season = self.season
        else:
            reg_season = Season.objects.filter(league=self.league, registration_open=True).order_by('-start_date').first()
        if reg_season is None:
            return self.render('tournament/registration_closed.html', {})

        if post:
            form = RegistrationForm(self.request.POST, season=reg_season)
            if form.is_valid():
                with reversion.create_revision():
                    reversion.set_comment('Submitted registration.')
                    form.save()
                self.request.session['reg_email'] = form.cleaned_data['email']
                return redirect(leagueurl('registration_success', league_tag=self.league.tag, season_tag=self.season.tag))
        else:
            form = RegistrationForm(season=reg_season)

        context = {
            'form': form,
            'registration_season': reg_season
        }
        return self.render('tournament/register.html', context)

    def view_post(self):
        return self.view(post=True)

class RegistrationSuccessView(SeasonView):
    def view(self):
        if self.season is not None and self.season.registration_open:
            reg_season = self.season
        else:
            reg_season = Season.objects.filter(league=self.league, registration_open=True).order_by('-start_date').first()
        if reg_season is None:
            return self.render('tournament/registration_closed.html', {})

        context = {
            'registration_season': reg_season,
            'email': self.request.session.get('reg_email')
        }
        return self.render('tournament/registration_success.html', context)

class ModRequestView(SeasonView, UrlAuthMixin):
    def view(self, req_type, secret_token=None, post=False):

        if req_type not in MOD_REQUEST_SENDER:
            raise Http404

        if self.persist_url_auth(secret_token):
            return redirect('by_league:by_season:modrequest', self.league.tag, self.season.tag, req_type)
        username, player = self.get_authenticated_user()

        if player and post:
            form = ModRequestForm(self.request.POST)
            if form.is_valid():
                with reversion.create_revision():
                    reversion.set_comment('Submitted mod request.')
                    modreq = form.save(commit=False)
                    modreq.season = self.season
                    modreq.type = req_type
                    modreq.requester = player
                    modreq.status = 'pending'
                    modreq.screenshot = self.request.FILES.get('screenshot')
                    modreq.save()
                return redirect(leagueurl('modrequest_success', self.league.tag, self.season.tag, req_type))
        else:
            form = ModRequestForm()

        context = {
            'form': form,
            'username': username,
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
        @cached_as(TeamMember, SeasonPlayer, Alternate, AlternateAssignment, AlternateBucket, Player, PlayerAvailability, *common_team_models)
        def _view(league_tag, season_tag, is_staff, can_edit):
            if self.league.competitor_type != 'team':
                raise Http404
            if self.season is None:
                context = {
                    'can_edit': self.request.user.has_perm('tournament.manage_players', self.league),
                }
                return self.render('tournament/team_rosters.html', context)

            teams = Team.objects.filter(season=self.season).order_by('number').prefetch_related(
                Prefetch('teammember_set', queryset=TeamMember.objects.select_related('player'))
            ).nocache()
            board_numbers = list(range(1, self.season.boards + 1))

            alternates = Alternate.objects.filter(season_player__season=self.season)
            alternates_by_board = [sorted(
                                          alternates.filter(board_number=n)
                                                    .select_related('season_player__registration', 'season_player__player')
                                                    .nocache(),
                                          key=lambda alt: alt.priority_date()
                                   ) for n in board_numbers]
            alternate_rows = list(enumerate(itertools.izip_longest(*alternates_by_board), 1))
            if len(alternate_rows) == 0:
                alternate_rows.append((1, [None for _ in board_numbers]))

            current_round = Round.objects.filter(season=self.season, publish_pairings=True).order_by('-number').first()
            scheduled_alternates = {assign.player for assign in AlternateAssignment.objects.filter(round=current_round)
                                                                                           .select_related('player')
                                                                                           .nocache()}
            unavailable_players = {pa.player for pa in PlayerAvailability.objects.filter(round__season=self.season, round=current_round, is_available=False) \
                                                                                 .select_related('player')
                                                                                 .nocache()}
            unresponsive_players = {sp.player for sp in SeasonPlayer.objects.filter(season=self.season, unresponsive=True)
                                                                            .select_related('player')
                                                                            .nocache()}
            games_missed_by_player = {sp.player: sp.games_missed for sp in SeasonPlayer.objects.filter(season=self.season)
                                                                                               .select_related('player')
                                                                                               .nocache()}
            yellow_card_players = {player for player, games_missed in games_missed_by_player.items() if games_missed == 1}
            red_card_players = {player for player, games_missed in games_missed_by_player.items() if games_missed >= 2}

            # Show the legend if we have any data that might need it
            show_legend = len(scheduled_alternates | unavailable_players | unresponsive_players | yellow_card_players | red_card_players) > 0

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
            }
            return self.render('tournament/team_rosters.html', context)
        return _view(self.league.tag, self.season.tag, self.request.user.is_staff, self.request.user.has_perm('tournament.manage_players', self.league))

class StandingsView(SeasonView):
    def view(self, section=None):
        if self.league.competitor_type == 'team':
            return self.team_view()
        else:
            return self.lone_view(section)

    def team_view(self):
        @cached_as(TeamScore, TeamPairing, *common_team_models)
        def _view(league_tag, season_tag, is_staff):
            round_numbers = list(range(1, self.season.rounds + 1))
            team_scores = list(enumerate(sorted(TeamScore.objects.filter(team__season=self.season).select_related('team').nocache(), reverse=True), 1))
            context = {
                'round_numbers': round_numbers,
                'team_scores': team_scores,
            }
            return self.render('tournament/team_standings.html', context)
        return _view(self.league.tag, self.season.tag, self.request.user.is_staff)

    def lone_view(self, section=None):
        @cached_as(*common_lone_models)
        def _view(league_tag, season_tag, section, is_staff):
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
                    player_scores = [ps for ps in player_scores if ps[1].season_player.seed_rating_display() < max_rating]

            player_sections = [('u%d' % sp.max_rating, 'U%d' % sp.max_rating) for sp in SeasonPrize.objects.filter(season=self.season).exclude(max_rating=None).order_by('max_rating')]
            section_dict = {k: (k, v) for k, v in player_sections}
            current_section = section_dict.get(section, None)

            if self.season.is_completed:
                prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season=self.season)
            else:
                prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season__league=self.league)
            player_highlights = _get_player_highlights(prize_winners)

            context = {
                'round_numbers': round_numbers,
                'player_scores': player_scores,
                'has_ljp': has_ljp,
                'player_sections': player_sections,
                'current_section': current_section,
                'player_highlights': player_highlights,
            }
            return self.render('tournament/lone_standings.html', context)
        return _view(self.league.tag, self.season.tag, section, self.request.user.is_staff)

def _get_player_highlights(prize_winners):
    return [
        ('gold', {pw.player for pw in prize_winners.filter(season_prize__rank=1, season_prize__max_rating=None)}),
        ('silver', {pw.player for pw in prize_winners.filter(season_prize__rank=2, season_prize__max_rating=None)}),
        ('bronze', {pw.player for pw in prize_winners.filter(season_prize__rank=3, season_prize__max_rating=None)}),
        ('blue', {pw.player for pw in prize_winners.filter(season_prize__rank=1).exclude(season_prize__max_rating=None)})
    ]

@cached_as(LonePlayerScore, LonePlayerPairing, PlayerPairing, PlayerBye, SeasonPlayer, Player)
def _lone_player_scores(season, final=False, sort_by_seed=False, include_current=False):
    # For efficiency, rather than having LonePlayerScore.round_scores() do independent
    # calculations, we populate a few common data structures and use those as parameters.

    if sort_by_seed:
        sort_key = lambda s: s.season_player.seed_rating_display()
    elif season.is_completed or final:
        sort_key = lambda s: s.final_standings_sort_key()
    else:
        sort_key = lambda s: s.pairing_sort_key()
    raw_player_scores = LonePlayerScore.objects.filter(season_player__season=season) \
                                       .select_related('season_player__player', 'season_player__season__league').nocache()
    player_scores = list(enumerate(sorted(raw_player_scores, key=sort_key, reverse=True), 1))
    player_number_dict = {p.season_player.player: n for n, p in player_scores}

    pairings = LonePlayerPairing.objects.filter(round__season=season).select_related('white', 'black').nocache()
    white_pairings_dict = defaultdict(list)
    black_pairings_dict = defaultdict(list)
    for p in pairings:
        if p.white is not None:
            white_pairings_dict[p.white].append(p)
        if p.black is not None:
            black_pairings_dict[p.black].append(p)

    byes = PlayerBye.objects.filter(round__season=season).select_related('round', 'player').nocache()
    byes_dict = defaultdict(list)
    for bye in byes:
        byes_dict[bye.player].append(bye)

    rounds = Round.objects.filter(season=season).order_by('number')
    # rounds = [round_ for round_ in Round.objects.filter(season=season).order_by('number') if round_.is_completed or (include_current and round_.publish_pairings)]

    def round_scores(player_score):
        return list(player_score.round_scores(rounds, player_number_dict, white_pairings_dict, black_pairings_dict, byes_dict, include_current))

    return [(n, ps, round_scores(ps)) for n, ps in player_scores]

class CrosstableView(SeasonView):
    def view(self):
        @cached_as(TeamScore, TeamPairing, *common_team_models)
        def _view(league_tag, season_tag, is_staff):
            if self.league.competitor_type != 'team':
                raise Http404
            team_scores = list(enumerate(sorted(TeamScore.objects.filter(team__season=self.season).select_related('team').nocache(), reverse=True), 1))
            teams = [ts.team for _, ts in team_scores]
            team_scores = [(n, ts, ts.cross_scores(teams)) for n, ts in team_scores]
            context = {
                'team_scores': team_scores,
            }
            return self.render('tournament/team_crosstable.html', context)
        return _view(self.league.tag, self.season.tag, self.request.user.is_staff)

class WallchartView(SeasonView):
    def view(self):
        @cached_as(*common_lone_models)
        def _view(league_tag, season_tag, is_staff):
            if self.league.competitor_type == 'team':
                raise Http404
            round_numbers = list(range(1, self.season.rounds + 1))
            player_scores = _lone_player_scores(self.season, sort_by_seed=True, include_current=True)

            if self.season.is_completed:
                prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season=self.season)
            else:
                prize_winners = SeasonPrizeWinner.objects.filter(season_prize__season__league=self.season.league)
            player_highlights = _get_player_highlights(prize_winners)

            context = {
                'round_numbers': round_numbers,
                'player_scores': player_scores,
                'player_highlights': player_highlights,
            }
            return self.render('tournament/lone_wallchart.html', context)
        return _view(self.league.tag, self.season.tag, self.request.user.is_staff)

class StatsView(SeasonView):
    def view(self):
        if self.league.competitor_type == 'team':
            return self.team_view()
        else:
            return self.lone_view()

    def team_view(self):
        @cached_as(League, Season, Round, TeamPlayerPairing, PlayerPairing)
        def _view(league_tag, season_tag, is_staff):
            all_pairings = PlayerPairing.objects.filter(teamplayerpairing__team_pairing__round__season=self.season) \
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
                    if p.white_rating_display(self.league) is not None and p.black_rating_display(self.league) is not None:
                        rating_delta += p.white_rating_display(self.league) - p.black_rating_display(self.league)
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
                percents = (counts[0] / total, counts[1] / total, counts[2] / total, counts[3] / total)
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
        return _view(self.league.tag, self.season.tag, self.request.user.is_staff)

    def lone_view(self):
        @cached_as(League, Season, Round, LonePlayerPairing, PlayerPairing)
        def _view(league_tag, season_tag, is_staff):
            all_pairings = PlayerPairing.objects.filter(loneplayerpairing__round__season=self.season) \
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
                if p.white_rating_display(self.league) is not None and p.black_rating_display(self.league) is not None:
                    d = p.white_rating_display(self.league) - p.black_rating_display(self.league)
                    rating_delta += d
                    abs_rating_delta += abs(d)
                    rating_delta_index = int(min(math.floor(abs(d) / 100.0), 5))
                    rating_delta_counts[rating_delta_index] += 1
                    if math.copysign(1, p.white_rating_display(self.league) - p.black_rating_display(self.league)) == p.black_score() - p.white_score() \
                        and p.white_rating_display(self.league) != p.black_rating_display(self.league):
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
                return self.render('tournament/lone_stats.html', {})

            win_counts = tuple(counts)
            win_percents = tuple((c / total for c in counts))
            win_rating_delta = rating_delta / total
            rating_delta_average = abs_rating_delta / total
            rating_delta_counts = tuple(rating_delta_counts)
            rating_delta_percents = tuple((c / total for c in rating_delta_counts))
            upset_percents = tuple((c1 / float(c2) if c2 > 0 else 0 for c1, c2 in zip(upset_counts, rating_delta_counts)))

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
            }
            return self.render('tournament/lone_stats.html', context)
        return _view(self.league.tag, self.season.tag, self.request.user.is_staff)

class BoardScoresView(SeasonView):
    def view(self, board_number):
        if self.league.competitor_type == 'team':
            return self.team_view(board_number)
        else:
            raise Http404

    def team_view(self, board_number):
        @cached_as(League, Season, Round, TeamPlayerPairing, PlayerPairing)
        def _view(league_tag, season_tag, is_staff, board_number):
            board_pairings = PlayerPairing.objects.filter(teamplayerpairing__team_pairing__round__season=self.season) \
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

            ps_dict = {} # Player -> PlayerScore
            games_dict = defaultdict(list) # Player -> list of PlayerPairing

            for pairing in board_pairings:
                games_dict[pairing.white].append(pairing)
                games_dict[pairing.black].append(pairing)

                if pairing.teamplayerpairing.board_number != int(board_number):
                    continue
                white_ps = ps_dict[pairing.white] = ps_dict.get(pairing.white, PlayerScore(pairing.white))
                black_ps = ps_dict[pairing.black] = ps_dict.get(pairing.black, PlayerScore(pairing.black))

                white_game_score = pairing.white_score()
                if white_game_score is not None:
                    white_ps.score += white_game_score
                    white_ps.score_total += 1
                    if pairing.game_played():
                        white_ps.perf.add_game(white_game_score, pairing.black_rating_display(self.league))

                black_game_score = pairing.black_score()
                if black_game_score is not None:
                    black_ps.score += black_game_score
                    black_ps.score_total += 1
                    if pairing.game_played():
                        black_ps.perf.add_game(black_game_score, pairing.white_rating_display(self.league))

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
                                ps.perf.add_game(g.white_score(), g.black_rating_display(self.league))
                            else:
                                ps.perf.add_game(g.black_score(), g.white_rating_display(self.league))
                    ps.perf_rating = ps.perf.calculate()
                    ps.eligible = False
                return True

            ps_list = [ps for ps in ps_dict.values() if process_playerscore(ps)]
            ps_list.sort(key=lambda ps: (ps.perf_rating, ps.score, -ps.score_total), reverse=True)

            context = {
                'board_number': board_number,
                'player_scores': ps_list
            }
            return self.render('tournament/team_board_scores.html', context)
        return _view(self.league.tag, self.season.tag, self.request.user.is_staff, board_number)

class LeagueDashboardView(LeagueView):
    def view(self):
        if self.league.competitor_type == 'team':
            return self.team_view()
        else:
            return self.lone_view()

    def _common_context(self):
        default_season = _get_default_season(self.league.tag, allow_none=True)
        season_list = list(Season.objects.filter(league=self.league).order_by('-start_date', '-id'))
        if default_season is not None:
            season_list.remove(default_season)

        pending_reg_count = len(Registration.objects.filter(season=self.season, status='pending'))
        pending_modreq_count = len(ModRequest.objects.filter(season=self.season, status='pending'))

        team_members = TeamMember.objects.filter(team__season=self.season).select_related('player').nocache()
        alternates = Alternate.objects.filter(season_player__season=self.season).select_related('season_player__player').nocache()
        season_players = set(sp.player for sp in SeasonPlayer.objects.filter(season=self.season, is_active=True).select_related('player').nocache())
        team_players = set(tm.player for tm in team_members)
        alternate_players = set(alt.season_player.player for alt in alternates)
        unassigned_player_count = len(season_players - team_players - alternate_players)

        alternate_search_round = alternates_manager.current_round(self.season)
        alternate_search_count = len(alternates_manager.current_searches(alternate_search_round)) if alternate_search_round is not None else None

        last_round = Round.objects.filter(season=self.season, publish_pairings=True, is_completed=False).order_by('number').first()
        next_round = Round.objects.filter(season=self.season, publish_pairings=False, is_completed=False).order_by('number').first()

        return {
            'default_season': default_season,
            'season_list': season_list,
            'pending_reg_count': pending_reg_count,
            'pending_modreq_count': pending_modreq_count,
            'unassigned_player_count': unassigned_player_count,
            'alternate_search_count': alternate_search_count,
            'last_round': last_round,
            'next_round': next_round,
            'celery_down': uptime.celery.is_down,
            'can_view_dashboard': self.request.user.has_perm('tournament.view_dashboard', self.league),
            'can_admin_users': self.request.user.has_module_perms('auth')
        }

    def team_view(self):
        context = self._common_context()
        return self.render('tournament/team_league_dashboard.html', context)

    def lone_view(self):
        context = self._common_context()
        return self.render('tournament/lone_league_dashboard.html', context)

class UserDashboardView(LeagueView):
    def view(self):
        if not self.request.user.is_authenticated():
            return redirect('by_league:league_home', self.league.tag)
        context = {}
        return self.render('tournament/user_dashboard.html', context)

class DocumentView(LeagueView):
    def view(self, document_tag):
        league_document = LeagueDocument.objects.filter(league=self.league, tag=document_tag).first()
        if league_document is None:
            season_document = SeasonDocument.objects.filter(season=self.season, tag=document_tag).first()
            if season_document is None:
                raise Http404
            document = season_document.document
            allow_all_editors = season_document.allow_all_editors
        else:
            document = league_document.document
            allow_all_editors = league_document.allow_all_editors

        context = {
            'document': document,
            'is_faq': False,
            'can_edit': self.request.user.has_perm('tournament.change_document', self.league) \
                        or self.request.user.is_staff and allow_all_editors,
        }
        return self.render('tournament/document.html', context)

class ContactView(LeagueView):
    def view(self, post=False):
        leagues = [self.league] + list(League.objects.filter(is_active=True).order_by('display_order').exclude(pk=self.league.pk))
        if post:
            form = ContactForm(self.request.POST, leagues=leagues)
            if form.is_valid():
                league = League.objects.get(tag=form.cleaned_data['league'])
                for mod in league.leaguemoderator_set.all():
                    if mod.send_contact_emails and mod.player.email:
                        message = EmailMessage(
                            '[%s] %s' % (league.name, form.cleaned_data['subject']),
                            'Sender:\n%s\n%s\n\nMessage:\n%s' %
                                (form.cleaned_data['your_lichess_username'], form.cleaned_data['your_email_address'], form.cleaned_data['message']),
                            settings.DEFAULT_FROM_EMAIL,
                            [mod.player.email]
                        )
                        message.send()
                return redirect(leagueurl('contact_success', league_tag=self.league.tag))
        else:
            form = ContactForm(leagues=leagues)

        context = {
            'form': form,
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
        return self.render('tournament/about.html', {})

class PlayerProfileView(LeagueView):
    def view(self, username):
        player = get_object_or_404(Player, lichess_username__iexact=username)

        def game_count(season):
            if season.league.competitor_type == 'team':
                season_pairings = TeamPlayerPairing.objects.filter(team_pairing__round__season=season)
            else:
                season_pairings = LonePlayerPairing.objects.filter(round__season=season)
            return (season_pairings.filter(white=player) | season_pairings.filter(black=player)).count()

        def team(season):
            if season.league.competitor_type == 'team':
                team_member = player.teammember_set.filter(team__season=season).first()
                if team_member is not None:
                    return team_member.team
            return None

        leagues = list((League.objects.filter(is_active=True) | League.objects.filter(pk=self.league.pk)).order_by('display_order'))
        has_other_seasons = player.seasonplayer_set.exclude(season=self.season).exists()
        other_season_leagues = [(l, [(sp.season, game_count(sp.season), team(sp.season)) for sp in player.seasonplayer_set \
                                                                                                         .filter(season__league=l, season__is_active=True) \
                                                                                                         .order_by('-season__start_date')]) \
                         for l in leagues]
        other_season_leagues = [l for l in other_season_leagues if len(l[1]) > 0]

        season_player = SeasonPlayer.objects.filter(season=self.season, player=player).first()

        if self.season is None:
            games = None
        elif self.season.league.competitor_type == 'team':
            pairings = TeamPlayerPairing.objects.filter(white=player) | TeamPlayerPairing.objects.filter(black=player)
            games = [(p.team_pairing.round, p, p.white_team() if p.white == player else p.black_team()) for p in pairings.filter(team_pairing__round__season=self.season).exclude(result='').order_by('team_pairing__round__number').nocache()]
        else:
            pairings = LonePlayerPairing.objects.filter(white=player) | LonePlayerPairing.objects.filter(black=player)
            games = [(p.round, p, None) for p in pairings.filter(round__season=self.season).exclude(result='').order_by('round__number').nocache()]

        # Calculate performance rating
        season_score = 0
        season_score_total = 0
        season_perf = PerfRatingCalc()
        if games:
            for round_, p, team in games:
                game_score = p.white_score() if p.white == player else p.black_score()
                if game_score is not None:
                    season_score += game_score
                    season_score_total += 1
                # Add pairing to performance calculation
                if p.game_played() and p.white is not None and p.black is not None:
                    sp = SeasonPlayer.objects.filter(season=self.season, player=p.black if p.white == player else p.white).first()
                    if sp is not None and sp.seed_rating is not None:
                        opp_rating = sp.seed_rating
                    else:
                        opp_rating = p.black_rating_display() if p.white == player else p.white_rating_display(self.league)
                    season_perf.add_game(game_score, opp_rating)
        season_perf_rating = season_perf.calculate()

        team_member = TeamMember.objects.filter(team__season=self.season, player=player).first()
        alternate = Alternate.objects.filter(season_player=season_player).first()

        schedule = []
        for round_ in self.season.round_set.filter(is_completed=False).order_by('number'):
            if not round_.publish_pairings:
                pairing = None
            elif self.season.league.competitor_type == 'team':
                pairing = pairings.filter(team_pairing__round=round_).first()
            else:
                pairing = pairings.filter(round=round_).first()
            if pairing is not None:
                if pairing.result != '':
                    continue
                schedule.append((round_, pairing, None, None))
                continue
            if self.season.league.competitor_type == 'team':
                assignment = AlternateAssignment.objects.filter(round=round_, player=player).first()
                if assignment is not None and (team_member is None or team_member.team != assignment.team):
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
                bye = PlayerBye.objects.filter(round=round_, player=player).first()
                if bye is not None:
                    schedule.append((round_, None, bye.get_type_display(), None))
                    continue
                if not player.is_available_for(round_):
                    schedule.append((round_, None, 'Unavailable', None))
                    continue
                if season_player is None or not season_player.is_active:
                    continue
                schedule.append((round_, None, 'Scheduled', None))

        context = {
            'player': player,
            'has_other_seasons': has_other_seasons,
            'other_season_leagues': other_season_leagues,
            'season_player': season_player,
            'games': games,
            'team_member': team_member,
            'alternate': alternate,
            'schedule': schedule,
            'season_perf': season_perf,
            'season_perf_rating': season_perf_rating,
            'season_score': season_score,
            'season_score_total': season_score_total,
            'can_edit': self.request.user.has_perm('tournament.change_season_player', self.league),
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

        prev_members = [(player, display_ratings.get(player, None) or player.rating_for(self.league), game_count) for player, game_count in sorted(game_counts.items(), key=lambda i: i[0].lichess_username.lower()) if player not in member_players]

        matches = []
        for round_ in self.season.round_set.filter(publish_pairings=True).order_by('number'):
            if self.season.league.competitor_type == 'team':
                pairing = team.pairings.filter(round=round_).first()
            if pairing is not None:
                matches.append((round_, pairing))

        context = {
            'team': team,
            'prev_members': prev_members,
            'matches': matches,
        }
        return self.render('tournament/team_profile.html', context)

class NominateView(SeasonView, UrlAuthMixin):
    def view(self, secret_token=None, post=False):
        can_nominate = False
        current_nominations = []
        form = None

        if self.persist_url_auth(secret_token):
            return redirect('by_league:by_season:nominate', self.league.tag, self.season.tag)
        username, player = self.get_authenticated_user()

        if self.league.competitor_type == 'team':
            season_pairings = PlayerPairing.objects.filter(teamplayerpairing__team_pairing__round__season=self.season).nocache()
        else:
            season_pairings = PlayerPairing.objects.filter(loneplayerpairing__round__season=self.season).nocache()


        max_nominations = self.league.get_leaguesetting().max_game_nominations_per_user

        if player is not None:
            if self.league.get_leaguesetting().limit_game_nominations_to_participants:
                player_pairings = season_pairings.filter(white=player) | season_pairings.filter(black=player)
                can_nominate = player_pairings.count() > 0
            else:
                can_nominate = True

            if can_nominate and self.season.nominations_open:
                current_nominations = GameNomination.objects.filter(season=self.season, nominating_player=player)

                if post:
                    form = NominateForm(self.season, player, current_nominations, max_nominations, season_pairings, self.request.POST)
                    if form.is_valid():
                        if form.cleaned_data['game_link'] != '':
                            GameNomination.objects.create(season=self.season, nominating_player=player, game_link=form.cleaned_data['game_link'], pairing=form.pairing)
                            return redirect('by_league:by_season:nominate', self.league.tag, self.season.tag)
                else:
                    form = NominateForm(self.season, player, current_nominations, max_nominations, season_pairings)

        # Clean up the DB
        for expired_auth in PrivateUrlAuth.objects.filter(expires__lt=timezone.now()):
            expired_auth.delete()

        context = {
            'form': form,
            'username': username,
            'can_nominate': can_nominate,
            'max_nominations': max_nominations,
            'current_nominations': current_nominations,
        }
        return self.render('tournament/nominate.html', context)

    def view_post(self):
        return self.view(post=True)

class DeleteNominationView(SeasonView, UrlAuthMixin):
    def view(self, nomination_id, post=False):
        form = None

        username, player = self.get_authenticated_user()

        if player is None or not self.season.nominations_open:
            return redirect('by_league:by_season:nominate', self.league.tag, self.season.tag)

        nomination_to_delete = GameNomination.objects.filter(season=self.season, nominating_player=player, pk=nomination_id).first()
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
            'username': username,
            'nomination_to_delete': nomination_to_delete,
        }
        return self.render('tournament/nomination_delete.html', context)

    def view_post(self, nomination_id):
        return self.view(nomination_id, post=True)

class ScheduleView(LeagueView, UrlAuthMixin):
    def view(self, secret_token=None, post=False):
        if self.persist_url_auth(secret_token):
            return redirect('by_league:edit_schedule', self.league.tag)
        username, player = self.get_authenticated_user()

        times = player.availabletime_set.filter(league=self.league) if player is not None else None

        context = {
            'username': username,
            'player': player,
            'times': times,
        }
        return self.render('tournament/schedule.html', context)

    def view_post(self):
        return self.view(post=True)

class AvailabilityView(SeasonView, UrlAuthMixin):
    def view(self, secret_token=None, post=False):
        if self.persist_url_auth(secret_token):
            return redirect('by_league:by_season:edit_availability', self.league.tag, self.season.tag)
        username, player = self.get_authenticated_user()

        player_list = [player]
        include_current_round = self.league.competitor_type == 'team'
        if include_current_round:
            round_list = list(self.season.round_set.order_by('number').filter(is_completed=False))
        else:
            round_list = list(self.season.round_set.order_by('number').filter(publish_pairings=False))
        round_data = None

        if player is not None:

            # Add team members if the user is a captain
            team_member = TeamMember.objects.filter(player=player, team__season=self.season).first()
            if team_member is not None and team_member.is_captain:
                team = team_member.team
                for tm in team.teammember_set.order_by('board_number').select_related('player').nocache():
                    if tm.player not in player_list:
                        player_list.append(tm.player)

            availability_set = PlayerAvailability.objects.filter(player__in=player_list, round__in=round_list).nocache()
            is_available_dict = {(av.round_id, av.player_id): av.is_available for av in availability_set}

            if post:
                for r in round_list:
                    for p in player_list:
                        field_name = 'av_r%d_%s' % (r.number, p.lichess_username)
                        is_available = self.request.POST.get(field_name) != 'on'
                        if is_available != is_available_dict.get((r.id, p.id), True):
                            PlayerAvailability.objects.update_or_create(player=p, round=r, defaults={ 'is_available': is_available })
                return redirect('by_league:by_season:edit_availability', self.league.tag, self.season.tag)

            round_data = [(r, [(p, is_available_dict.get((r.id, p.id), True)) for p in player_list]) for r in round_list]


        context = {
            'username': username,
            'player': player,
            'player_list': player_list,
            'round_data': round_data,
        }
        return self.render('tournament/availability.html', context)

    def view_post(self):
        return self.view(post=True)

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
        assignments = AlternateAssignment.objects.filter(round=round_).order_by('date_modified').select_related('team', 'player').nocache()

        def team_member(s):
            return TeamMember.objects.filter(team=s.team, board_number=s.board_number).first()

        open_spots = [(s.board_number, s.team, team_member(s), s.date_created) for s in searches]
        filled_spots = [(aa.board_number, aa.team, aa.player, aa.date_modified) for aa in assignments]

        def with_status(alt):
            date = alt.last_contact_date if alt.status == 'contacted' else None
            status = alt.get_status_display()
            if status == 'Waiting':
                if alt.season_player.games_missed >= 2:
                    status = 'Red Card'
                elif not alt.season_player.player.is_available_for(round_):
                    status = 'Unavailable'
                elif (round_.pairings.filter(white=alt.season_player.player) | round_.pairings.filter(black=alt.season_player.player)).exists():
                    status = 'Scheduled'
            if status == 'Unresponsive':
                status = 'Unresponsive'
            return (alt, status, date)

        def alternate_board(n):
            all_alts = sorted(alternates.filter(board_number=n))
            alts_with_status = [with_status(alt) for alt in all_alts]
            eligible_alts = [(alt, status, date) for alt, status, date in alts_with_status if status in ('Waiting', 'Contacted')]
            ineligible_alts = [(alt, status, date) for alt, status, date in alts_with_status if status not in ('Waiting', 'Contacted')]
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

class AlternateAcceptView(SeasonView, UrlAuthMixin):
    def view(self, round_number, secret_token=None, post=False):
        round_number = int(round_number)
        if self.persist_url_auth(secret_token):
            return redirect('by_league:by_season:alternate_accept', self.league.tag, self.season.tag, round_number)
        username, player = self.get_authenticated_user()

        round_ = alternates_manager.current_round(self.season)

        alt = Alternate.objects.filter(season_player__season=self.season, season_player__player=player).first()
        show_button = False
        if not username:
            msg = ''
        elif alt is None:
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
                start_time = round_.start_date.strftime('%Y-%m-%d %H:%M') if not round_.publish_pairings else 'now'
                end_time = round_.end_date.strftime('%Y-%m-%d %H:%M')
                msg = 'Please confirm you can play a game for round %d. You must have multiple times you can play between %s and %s (UTC).' \
                      % (round_.number, start_time, end_time)
                show_button = True
        else:
            msg = 'Sorry, no games are currently available for round %d.' % round_.number

        context = {
            'username': username,
            'msg': msg,
            'show_button': show_button
        }
        return self.render('tournament/alternate_accept.html', context)

    def view_post(self, round_number):
        return self.view(round_number, post=True)

class AlternateDeclineView(SeasonView, UrlAuthMixin):
    def view(self, round_number, secret_token=None, post=False):
        round_number = int(round_number)
        if self.persist_url_auth(secret_token):
            return redirect('by_league:by_season:alternate_decline', self.league.tag, self.season.tag, round_number)
        username, player = self.get_authenticated_user()

        round_ = alternates_manager.current_round(self.season)

        alt = Alternate.objects.filter(season_player__season=self.season, season_player__player=player).first()
        show_button = False
        if not username:
            msg = ''
        elif alt is None:
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
                msg = 'Please confirm you do not want to play a game during round %d.' % (round_.number)
                show_button = True

        context = {
            'username': username,
            'msg': msg,
            'show_button': show_button
        }
        return self.render('tournament/alternate_decline.html', context)

    def view_post(self, round_number):
        return self.view(round_number, post=True)

class NotificationsView(SeasonView, UrlAuthMixin):
    def view(self, secret_token=None, post=False):
        if self.persist_url_auth(secret_token):
            return redirect('by_league:by_season:notifications', self.league.tag, self.season.tag)
        username, player = self.get_authenticated_user()

        if player is not None:
            if post:
                form = NotificationsForm(self.league, player, self.request.POST)
                if form.is_valid():
                    PlayerNotificationSetting.objects.filter(player=player, league=self.league).delete()
                    for type_, _ in PLAYER_NOTIFICATION_TYPES:
                        if type_ == 'alternate_needed' and self.league.competitor_type != 'team':
                            continue
                        setting = PlayerNotificationSetting(player=player, league=self.league, type=type_)
                        setting.enable_lichess_mail = form.cleaned_data[type_ + '_lichess']
                        setting.enable_slack_im = form.cleaned_data[type_ + '_slack']
                        setting.enable_slack_mpim = form.cleaned_data[type_ + '_slack_wo']
                        setting.offset = timedelta(minutes=form.cleaned_data[type_ + '_offset']) if (type_ + '_offset') in form.cleaned_data else None
                        setting.save()
            else:
                form = NotificationsForm(self.league, player)
        else:
            form = None

        context = {
            'username': username,
            'player': player,
            'form': form
        }
        return self.render('tournament/notifications.html', context)

    def view_post(self):
        return self.view(post=True)

class LoginView(LeagueView, UrlAuthMixin):
    def view(self, secret_token=None, post=False):
        slack_user_id = ''
        if secret_token:
            token = LoginToken.objects.filter(secret_token=secret_token).first()
            if token and not token.is_expired():
                if token.lichess_username:
                    # Okay, we've successfully authenticated via lichess
                    # Now we set it up so Django recognizes the user
                    user = User.objects.filter(username__iexact=token.lichess_username).first()
                    if not user:
                        # Create the user with a password no one will ever use; it can always be manually reset if needed
                        user = User.objects.create_user(username=token.lichess_username, password=create_api_token())
                    user.backend = 'django.contrib.auth.backends.ModelBackend'
                    login(self.request, user)

                    if token.slack_user_id:
                        # Oh look, we've also associated the lichess account with a slack account. How convenient.
                        SlackAccount.objects.update_or_create(lichess_username=token.lichess_username, defaults={'slack_user_id': token.slack_user_id})

                    return redirect('by_league:user_dashboard', self.league.tag)
                elif token.slack_user_id:
                    # The user has been directed here from Slack. If they complete the login their accounts will be associated
                    slack_user_id = token.slack_user_id
        if post:
            form = LoginForm(self.request.POST)
            if form.is_valid():
                username = form.cleaned_data['lichess_username']
                login_token = LoginToken.objects.create(lichess_username=username, slack_user_id=slack_user_id, expires=timezone.now() + timedelta(days=1))
                login_link = abs_url(reverse('by_league:login_with_token', args=[self.league.tag, login_token.secret_token]))
                msg = 'Click this link to complete the login process.\n\n%s' % login_link
                mail_id = lichessapi.send_mail(username, '%s - Login' % self.league, msg)
                return redirect(settings.LICHESS_DOMAIN + 'inbox/' + mail_id)
        else:
            form = LoginForm()

        context = {
            'form': form,
        }
        return self.render('tournament/login.html', context)

    def view_post(self):
        return self.view(post=True)

class TvView(LeagueView):
    def view(self):
        leagues = list((League.objects.filter(is_active=True) | League.objects.filter(pk=self.league.pk)).order_by('display_order'))
        if self.season.is_active and not self.season.is_completed:
            active_season = self.season
        else:
            active_season = _get_default_season(self.league.tag, True)

        boards = active_season.board_number_list() if active_season is not None and active_season.boards is not None else None
        teams = active_season.team_set.order_by('name') if active_season is not None else None

        filter_form = TvFilterForm(current_league=self.league, leagues=leagues, boards=boards, teams=teams)
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

def _tv_json(league, board=None, team=None):
    def export_game(game, league, board, team):
        if hasattr(game, 'teamplayerpairing'):
            game_season = game.teamplayerpairing.team_pairing.round.season
            game_league = game_season.league
            return {
                'id': game.game_id(),
                'white': str(game.white),
                'white_name': game.white.lichess_username,
                'white_rating': game.white_rating_display(league),
                'black': str(game.black),
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
                'matches_filter': (league is None and game_league.is_active or league == game_league) and
                                  (board is None or board == game.teamplayerpairing.board_number) and
                                  # TODO: Team filter can do weird things if there are multiple active seasons
                                  (team is None or team == game.teamplayerpairing.white_team().number or team == game.teamplayerpairing.black_team().number)
            }
        elif hasattr(game, 'loneplayerpairing'):
            game_season = game.loneplayerpairing.round.season
            game_league = game_season.league
            return {
                'id': game.game_id(),
                'white': str(game.white),
                'white_name': game.white.lichess_username,
                'white_rating': game.white_rating_display(league),
                'black': str(game.black),
                'black_name': game.black.lichess_username,
                'black_rating': game.black_rating_display(league),
                'time': game.scheduled_time.isoformat() if game.scheduled_time is not None else None,
                'league': game_league.tag,
                'season': game_season.tag,
                'matches_filter': (league is None and game_league.is_active or league == game_league) and board is None and team is None
            }
    current_games = PlayerPairing.objects.filter(result='', tv_state='default').exclude(game_link='').order_by('scheduled_time') \
                                         .select_related('teamplayerpairing__team_pairing__round__season__league',
                                                         'teamplayerpairing__team_pairing__black_team',
                                                         'teamplayerpairing__team_pairing__white_team',
                                                         'loneplayerpairing__round__season__league',
                                                         'white', 'black').nocache()
    scheduled_games = PlayerPairing.objects.filter(result='', game_link='', scheduled_time__gt=timezone.now() - timedelta(minutes=20)).order_by('scheduled_time') \
                                         .select_related('teamplayerpairing__team_pairing__round__season__league',
                                                         'teamplayerpairing__team_pairing__black_team',
                                                         'teamplayerpairing__team_pairing__white_team',
                                                         'loneplayerpairing__round__season__league',
                                                         'white', 'black').nocache()

    @cached_as(League, Season, Round, Team, TeamScore, Player, PlayerPairing, TeamPlayerPairing, TeamPairing, LonePlayerPairing)
    def get_games(league, board, team):
        return [export_game(g, league, board, team) for g in current_games]

    @cached_as(League, Season, Round, Team, TeamScore, Player, PlayerPairing, TeamPlayerPairing, TeamPairing, LonePlayerPairing)
    def get_schedule(league, board, team):
        return [export_game(g, league, board, team) for g in scheduled_games]

    games = get_games(league, board, team)
    schedule = get_schedule(league, board, team)
    game_ids = [g['id'] for g in games]
    return {'games': games,
            'schedule': schedule,
            'watch': lichessapi.watch_games(game_ids)}

#-------------------------------------------------------------------------------
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
    season = Season.objects.filter(league=_get_league(league_tag), is_active=True).order_by('-start_date', '-id').first()
    if not allow_none and season is None:
        raise Http404
    return season

@cached_as(NavItem)
def _get_nav_tree(league_tag, season_tag):
    league = _get_league(league_tag)
    all_items = league.navitem_set.order_by('order')
    root_items = [item for item in all_items if item.parent_id == None]

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

