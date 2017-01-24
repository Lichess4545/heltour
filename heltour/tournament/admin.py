from django.contrib import admin, messages
from django.utils import timezone
from heltour.tournament import lichessapi, slackapi, views, forms, signals, simulation
from heltour.tournament.models import *
from reversion.admin import VersionAdmin
from django.conf.urls import url
from django.shortcuts import render, redirect, get_object_or_404
import reversion

import json
import pairinggen
import spreadsheet
from django.db.models.query import Prefetch
from django.db import transaction
from smtplib import SMTPException
from django.template.loader import render_to_string
from django.core.mail import send_mail
from heltour import settings
from datetime import timedelta
from django_comments.models import Comment
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.http.response import HttpResponse
from django.utils.http import urlquote
from django.core.mail.message import EmailMultiAlternatives
from django.core import mail
from django.utils.html import format_html
from heltour.tournament.workflows import RoundTransitionWorkflow, \
    UpdateBoardOrderWorkflow
from django.forms.models import ModelForm
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_permission_codename
from django.contrib.admin.filters import FieldListFilter, RelatedFieldListFilter

# Customize which sections are visible
# admin.site.register(Comment)
# admin.site.unregister(Site)

def redirect_with_params(*args, **kwargs):
    params = kwargs.pop('params')
    response = redirect(*args, **kwargs)
    response['Location'] += params
    print 'Redirect: ', response['Location']
    return response

#-------------------------------------------------------------------------------
class _BaseAdmin(VersionAdmin):
    change_form_template = 'tournament/admin/change_form_with_comments.html'
    history_latest_first = True

    league_id_field = None
    allow_all_staff = False

    def has_assigned_perm(self, user, perm_type):
        return user.has_perm(get_permission_codename(perm_type, self.opts))

    def has_league_perm(self, user, obj):
        if self.league_id_field is None:
            return False
        if obj is None:
            return len(self.authorized_leagues(user)) > 0
        else:
            return getnestedattr(obj, self.league_id_field) in self.authorized_leagues(user)

    def get_queryset(self, request):
        result = super(_BaseAdmin, self).get_queryset(request)
        if self.allow_all_staff or self.has_assigned_perm(request.user, 'change'):
            return result
        if self.league_id_field is None:
            return result.none()
        return result.filter(**{self.league_id_field + '__in': self.authorized_leagues(request.user)})

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        kwargs['queryset'] = admin.site._registry[db_field.related_model].get_queryset(request)
        return super(_BaseAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def has_add_permission(self, request):
        if self.allow_all_staff or self.has_assigned_perm(request.user, 'add'):
            return True
        return self.has_league_perm(request.user, None)

    def has_change_permission(self, request, obj=None):
        if self.allow_all_staff or self.has_assigned_perm(request.user, 'change'):
            return True
        return self.has_league_perm(request.user, obj)

    def has_delete_permission(self, request, obj=None):
        if self.allow_all_staff or self.has_assigned_perm(request.user, 'delete'):
            return True
        return self.has_league_perm(request.user, obj)

    def get_form(self, request, obj=None, **kwargs):
        form = super(_BaseAdmin, self).get_form(request, obj, **kwargs)

        def clean(form):
            super(ModelForm, form).clean()
            self.clean_form(request, form)

        form.clean = clean
        return form

    def clean_form(self, request, form):
        if self.allow_all_staff:
            return
        if form.instance.pk is None and self.has_assigned_perm(request.user, 'add'):
            return
        if form.instance.pk is not None and self.has_assigned_perm(request.user, 'change'):
            return
        if self.league_id_field is None:
            raise ValidationError('No permission to save this object')
        # Since we have cleaned_data dict instead of a model instance, we have to
        # pre-process the league id access a bit
        parts = self.league_id_field.split('__', 1)
        if len(parts) == 1:
            if parts[0] == 'id':
                league_id = form.cleaned_data['id']
            else:
                if parts[0][-3:] != '_id':
                    raise ValueError('Invalid league id field on modeladmin')
                league_id = form.cleaned_data[parts[0][:-3]].id
        else:
            league_id = getnestedattr(form.cleaned_data[parts[0]], parts[1])
        if league_id not in self.authorized_leagues(request.user):
            raise ValidationError('No permission to save objects for this league')

    def authorized_leagues(self, user):
        return [lm.league_id for lm in LeagueModerator.objects.filter(player__lichess_username__iexact=user.username)]

#-------------------------------------------------------------------------------
class LeagueRestrictedListFilter(RelatedFieldListFilter):

    def __init__(self, field, request, params, model, model_admin, field_path):
        super(LeagueRestrictedListFilter, self).__init__(field, request, params, model, model_admin, field_path)

    def field_choices(self, field, request, model_admin):
        if model_admin.has_assigned_perm(request.user, 'change'):
            return field.get_choices(include_blank=False)
        league_id_field = admin.site._registry[field.related_model].league_id_field
        league_filter = {league_id_field + '__in': model_admin.authorized_leagues(request.user)}
        return field.get_choices(include_blank=False, limit_choices_to=league_filter)

FieldListFilter.register(lambda f: f.remote_field, LeagueRestrictedListFilter, take_priority=True)

#-------------------------------------------------------------------------------
@admin.register(League)
class LeagueAdmin(_BaseAdmin):
    actions = ['import_season', 'export_forfeit_data']
    league_id_field = 'id'

    def get_urls(self):
        urls = super(LeagueAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/import_season/$',
                self.admin_site.admin_view(self.import_season_view),
                name='import_season'),
            url(r'^(?P<object_id>[0-9]+)/export_forfeit_data/$',
                self.admin_site.admin_view(self.export_forfeit_data_view),
                name='export_forfeit_data'),
        ]
        return my_urls + urls

    def import_season(self, request, queryset):
        return redirect('admin:import_season', object_id=queryset[0].pk)

    def export_forfeit_data(self, request, queryset):
        return redirect('admin:export_forfeit_data', object_id=queryset[0].pk)

    def import_season_view(self, request, object_id):
        league = get_object_or_404(League, pk=object_id)
        if not request.user.has_perm('tournament.change_league', league):
            raise PermissionDenied

        if request.method == 'POST':
            form = forms.ImportSeasonForm(request.POST)
            if form.is_valid():
                try:
                    if league.competitor_type == 'team':
                        spreadsheet.import_team_season(league, form.cleaned_data['spreadsheet_url'], form.cleaned_data['season_name'], form.cleaned_data['season_tag'],
                                                  form.cleaned_data['rosters_only'], form.cleaned_data['exclude_live_pairings'])
                        self.message_user(request, "Season imported.")
                    elif league.competitor_type == 'individual':
                        spreadsheet.import_lonewolf_season(league, form.cleaned_data['spreadsheet_url'], form.cleaned_data['season_name'], form.cleaned_data['season_tag'],
                                                           form.cleaned_data['rosters_only'], form.cleaned_data['exclude_live_pairings'])
                        self.message_user(request, "Season imported.")
                    else:
                        self.message_user(request, "League competitor type not supported for spreadsheet import")
                except spreadsheet.SpreadsheetNotFound:
                    self.message_user(request, "Spreadsheet not found. The service account may not have edit permissions.", messages.ERROR)
                return redirect('admin:tournament_league_changelist')
        else:
            form = forms.ImportSeasonForm()

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': league,
            'title': 'Import season',
            'form': form
        }

        return render(request, 'tournament/admin/import_season.html', context)

    def export_forfeit_data_view(self, request, object_id):
        league = get_object_or_404(League, pk=object_id)
        if not request.user.has_perm('tournament.change_league', league):
            raise PermissionDenied

        pairings = LonePlayerPairing.objects.exclude(result='').exclude(white=None).exclude(black=None).filter(round__season__league=league) \
                                    .order_by('round__start_date').select_related('white', 'black', 'round').nocache()
        rows = []

        for p in pairings:
            rows.append({
                'forfeit': 'BOTH' if p.result == '0F-0F' else 'SELF' if p.result == '0F-1X' else 'DRAW' if p.result == '1/2Z-1/2Z' else 'OPP' if p.result == '1X-0F' else 'NO',
                'average_rating': (p.white_rating_display(league) + p.black_rating_display(league)) / 2,
                'rating_delta': abs(p.white_rating_display(league) - p.black_rating_display(league)),
                'timezone_delta': 'TODO',
                'round_joined': 'TODO',
                'player_games_played': 'TODO',
                'player_games_forfeited': 'TODO',
                'player_byes': 'TODO',
                'player_seasons_participated': 'TODO',
                'player_team_seasons_participated': 'TODO',
                'player_games_on_lichess': p.white.games_played,
                'round_start_date': p.round.start_date
            })
            rows.append({
                'forfeit': 'BOTH' if p.result == '0F-0F' else 'SELF' if p.result == '1X-0F' else 'DRAW' if p.result == '1/2Z-1/2Z' else 'OPP' if p.result == '0F-1X' else 'NO',
                'average_rating': (p.white_rating_display(league) + p.black_rating_display(league)) / 2,
                'rating_delta': abs(p.white_rating_display(league) - p.black_rating_display(league)),
                'timezone_delta': 'TODO',
                'round_joined': 'TODO',
                'player_games_played': 'TODO',
                'player_games_forfeited': 'TODO',
                'player_byes': 'TODO',
                'player_seasons_participated': 'TODO',
                'player_team_seasons_participated': 'TODO',
                'player_games_on_lichess': p.black.games_played,
                'round_start_date': p.round.start_date
            })

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': league,
            'title': 'Export forfeit data',
            'rows': rows
        }

        return render(request, 'tournament/admin/export_forfeit_data.html', context)

#-------------------------------------------------------------------------------
@admin.register(Season)
class SeasonAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'league',)
    list_display_links = ('__unicode__',)
    list_filter = ('league',)
    actions = ['update_board_order_by_rating', 'recalculate_scores', 'verify_data', 'review_nominated_games', 'bulk_email', 'mod_report', 'manage_players', 'round_transition', 'simulate_tournament']
    league_id_field = 'league_id'

    def get_urls(self):
        urls = super(SeasonAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/manage_players/$',
                self.admin_site.admin_view(self.manage_players_view),
                name='manage_players'),
            url(r'^(?P<object_id>[0-9]+)/player_info/(?P<player_name>[\w-]+)/$',
                self.admin_site.admin_view(self.player_info_view),
                name='edit_rosters_player_info'),
            url(r'^(?P<object_id>[0-9]+)/round_transition/$',
                self.admin_site.admin_view(self.round_transition_view),
                name='round_transition'),
            url(r'^(?P<object_id>[0-9]+)/review_nominated_games/$',
                self.admin_site.admin_view(self.review_nominated_games_view),
                name='review_nominated_games'),
            url(r'^(?P<object_id>[0-9]+)/review_nominated_games/select/(?P<nom_id>[0-9]+)/$',
                self.admin_site.admin_view(self.review_nominated_games_select_view),
                name='review_nominated_games_select'),
            url(r'^(?P<object_id>[0-9]+)/review_nominated_games/deselect/(?P<sel_id>[0-9]+)/$',
                self.admin_site.admin_view(self.review_nominated_games_deselect_view),
                name='review_nominated_games_deselect'),
            url(r'^(?P<object_id>[0-9]+)/review_nominated_games/pgn/$',
                self.admin_site.admin_view(self.review_nominated_games_pgn_view),
                name='review_nominated_games_pgn'),
            url(r'^(?P<object_id>[0-9]+)/bulk_email/$',
                self.admin_site.admin_view(self.bulk_email_view),
                name='bulk_email'),
            url(r'^(?P<object_id>[0-9]+)/mod_report/$',
                self.admin_site.admin_view(self.mod_report_view),
                name='mod_report'),
        ]
        return my_urls + urls


    def simulate_tournament(self, request, queryset):
        if not request.user.is_superuser:
            raise PermissionDenied
        if not settings.DEBUG and not settings.STAGING:
            self.message_user(request, 'Results can\'t be simulated in a live environment', messages.ERROR)
            return
        if queryset.count() > 1:
            self.message_user(request, 'Results can only be simulated one season at a time', messages.ERROR)
            return
        season = queryset[0]
        simulation.simulate_season(season)
        self.message_user(request, 'Simulation complete.', messages.INFO)
        return redirect('admin:tournament_season_changelist')

    def recalculate_scores(self, request, queryset):
        for season in queryset:
            if season.league.competitor_type == 'team':
                for team_pairing in TeamPairing.objects.filter(round__season=season):
                    team_pairing.refresh_points()
                    team_pairing.save()
            season.calculate_scores()
        self.message_user(request, 'Scores recalculated.', messages.INFO)

    def verify_data(self, request, queryset):
        for season in queryset:
            # Ensure SeasonPlayer objects exist for all paired players
            if season.league.competitor_type == 'team':
                pairings = TeamPlayerPairing.objects.filter(team_pairing__round__season=season)
            else:
                pairings = LonePlayerPairing.objects.filter(round__season=season)
            for p in pairings:
                SeasonPlayer.objects.get_or_create(season=season, player=p.white)
                SeasonPlayer.objects.get_or_create(season=season, player=p.black)
            # Normalize all gamelinks
            bad_gamelinks = 0
            for p in pairings:
                old = p.game_link
                p.game_link, ok = normalize_gamelink(old)
                if not ok:
                    bad_gamelinks += 1
                if p.game_link != old:
                    p.save()
            if bad_gamelinks > 0:
                self.message_user(request, '%d bad gamelinks for %s.' % (bad_gamelinks, season.name), messages.WARNING)
        self.message_user(request, 'Data verified.', messages.INFO)

    def review_nominated_games(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Nominated games can only be reviewed one season at a time.', messages.ERROR)
            return
        return redirect('admin:review_nominated_games', object_id=queryset[0].pk)

    def review_nominated_games_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.review_nominated_games', season.league):
            raise PermissionDenied

        selections = GameSelection.objects.filter(season=season).order_by('pairing__teamplayerpairing__board_number')
        nominations = GameNomination.objects.filter(season=season).order_by('pairing__teamplayerpairing__board_number', 'date_created')

        selected_links = set((s.game_link for s in selections))

        link_counts = {}
        link_to_nom = {}
        first_nominations = []
        for n in nominations:
            value = link_counts.get(n.game_link, 0)
            if value == 0:
                first_nominations.append(n)
                link_to_nom[n.game_link] = n
            link_counts[n.game_link] = value + 1

        selections = [(link_counts.get(s.game_link, 0), s, link_to_nom.get(s.game_link, None)) for s in selections]
        nominations = [(link_counts.get(n.game_link, 0), n) for n in first_nominations if n.game_link not in selected_links]

        if season.nominations_open:
            self.message_user(request, 'Nominations are still open. You should edit the season and close nominations before reviewing.', messages.WARNING)

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': season,
            'title': 'Review nominated games',
            'selections': selections,
            'nominations': nominations,
            'is_team': season.league.competitor_type == 'team',
        }

        return render(request, 'tournament/admin/review_nominated_games.html', context)

    def review_nominated_games_select_view(self, request, object_id, nom_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.review_nominated_games', season.league):
            raise PermissionDenied
        nom = get_object_or_404(GameNomination, pk=nom_id)

        GameSelection.objects.get_or_create(season=season, game_link=nom.game_link, defaults={'pairing': nom.pairing})

        return redirect('admin:review_nominated_games', object_id=object_id)

    def review_nominated_games_deselect_view(self, request, object_id, sel_id):
        gs = GameSelection.objects.filter(pk=sel_id).first()
        if gs is not None:
            if not request.user.has_perm('tournament.review_nominated_games', gs.season.league):
                raise PermissionDenied
            gs.delete()

        return redirect('admin:review_nominated_games', object_id=object_id)

    def review_nominated_games_pgn_view(self, request, object_id):
        gamelink = request.GET.get('gamelink')
        gameid = get_gameid_from_gamelink(gamelink)
        pgn = lichessapi.get_pgn_with_cache(gameid, priority=10)

        # Strip most tags for "blind" review
        pgn = re.sub('\[[^R]\w+ ".*"\]\n', '', pgn)

        return HttpResponse(pgn)

    def round_transition(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Rounds can only be transitioned one season at a time.', messages.ERROR)
            return
        return redirect('admin:round_transition', object_id=queryset[0].pk)

    def round_transition_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.generate_pairings', season.league):
            raise PermissionDenied

        workflow = RoundTransitionWorkflow(season)

        round_to_close = workflow.round_to_close
        round_to_open = workflow.round_to_open
        season_to_close = workflow.season_to_close

        if request.method == 'POST':
            form = forms.RoundTransitionForm(season.league.competitor_type == 'team', round_to_close, round_to_open, season_to_close, request.POST)
            if form.is_valid():
                complete_round = 'round_to_close' in form.cleaned_data and form.cleaned_data['round_to_close'] == round_to_close.number \
                                 and form.cleaned_data['complete_round']
                complete_season = 'complete_season' in form.cleaned_data and form.cleaned_data['complete_season']
                update_board_order = 'round_to_open' in form.cleaned_data and form.cleaned_data['round_to_open'] == round_to_open.number \
                                     and 'update_board_order' in form.cleaned_data and form.cleaned_data['update_board_order']
                generate_pairings = 'round_to_open' in form.cleaned_data and form.cleaned_data['round_to_open'] == round_to_open.number \
                                    and form.cleaned_data['generate_pairings']

                msg_list = workflow.run(complete_round=complete_round, complete_season=complete_season, update_board_order=update_board_order, generate_pairings=generate_pairings)

                for text, level in msg_list:
                    self.message_user(request, text, level)

                if generate_pairings:
                    return redirect('admin:review_pairings', round_to_open.pk)
                else:
                    return redirect('admin:tournament_season_changelist')
        else:
            form = forms.RoundTransitionForm(season.league.competitor_type == 'team', round_to_close, round_to_open, season_to_close)

        for text, level in workflow.warnings:
            self.message_user(request, text, level)

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': season,
            'title': 'Round transition',
            'form': form
        }

        return render(request, 'tournament/admin/round_transition.html', context)

    def bulk_email(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Emails can only be sent one season at a time.', messages.ERROR)
            return
        return redirect('admin:bulk_email', object_id=queryset[0].pk)

    def bulk_email_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.bulk_email', season.league):
            raise PermissionDenied

        if request.method == 'POST':
            form = forms.BulkEmailForm(season, request.POST)
            if form.is_valid() and form.cleaned_data['confirm_send']:
                season_players = season.seasonplayer_set.all()
                email_addresses = {sp.player.email for sp in season_players if sp.player.email != ''}
                email_messages = []
                for addr in email_addresses:
                    message = EmailMultiAlternatives(
                        form.cleaned_data['subject'],
                        form.cleaned_data['text_content'],
                        settings.DEFAULT_FROM_EMAIL,
                        [addr]
                    )
                    message.attach_alternative(form.cleaned_data['html_content'], 'text/html')
                    email_messages.append(message)
                conn = mail.get_connection()
                conn.open()
                conn.send_messages(email_messages)
                conn.close()
                self.message_user(request, 'Emails sent to %d players.' % len(season_players), messages.INFO)
                return redirect('admin:tournament_season_changelist')
        else:
            form = forms.BulkEmailForm(season)

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': season,
            'title': 'Bulk email',
            'form': form
        }

        return render(request, 'tournament/admin/bulk_email.html', context)

    def mod_report(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Can only generate mod report one season at a time.', messages.ERROR)
            return
        return redirect('admin:mod_report', object_id=queryset[0].pk)

    def mod_report_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.change_season', season.league):
            raise PermissionDenied

        season_players = season.seasonplayer_set.select_related('player').nocache()
        players = []
        for sp in season_players:
            games = (PlayerPairing.objects.filter(white=sp.player) | PlayerPairing.objects.filter(black=sp.player)).nocache()
            game_count = games.count()
            players.append((game_count, sp.player.games_played, sp.player.lichess_username))

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': season,
            'title': 'Mod report',
            'players': sorted(players)
        }

        return render(request, 'tournament/admin/mod_report.html', context)

    def update_board_order_by_rating(self, request, queryset):
        try:
            for season in queryset.all():
                if not request.user.has_perm('tournament.manage_players', season.league):
                    raise PermissionDenied
                UpdateBoardOrderWorkflow(season).run(alternates_only=False)
            self.message_user(request, 'Board order updated.', messages.INFO)
        except IndexError:
            self.message_user(request, 'Error updating board order.', messages.ERROR)

    def manage_players(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Players can only be managed one season at a time.', messages.ERROR)
            return
        return redirect('admin:manage_players', object_id=queryset[0].pk)

    def player_info_view(self, request, object_id, player_name):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.manage_players', season.league):
            raise PermissionDenied
        season_player = get_object_or_404(SeasonPlayer, season=season, player__lichess_username=player_name)
        player = season_player.player

        reg = season_player.registration
        if player.games_played is not None:
            has_played_20_games = player.games_played >= 20
        else:
            has_played_20_games = reg is not None and reg.has_played_20_games

        context = {
            'season_player': season_player,
            'league': season.league,
            'player': season_player.player,
            'reg': reg,
            'has_played_20_games': has_played_20_games
        }

        return render(request, 'tournament/admin/edit_rosters_player_info.html', context)

    def manage_players_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.manage_players', season.league):
            raise PermissionDenied
        if season.league.competitor_type == 'team':
            return self.team_manage_players_view(request, object_id)
        else:
            return self.lone_manage_players_view(request, object_id)

    def team_manage_players_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        league = season.league
        teams_locked = bool(Round.objects.filter(season=season, publish_pairings=True).count())

        if request.method == 'POST':
            form = forms.EditRostersForm(request.POST)
            if form.is_valid():
                changes = json.loads(form.cleaned_data['changes'])
                has_error = False

                # Group changes by team
                changes_by_team_number = defaultdict(list)
                nonteam_changes = []
                for change in changes:
                    if 'team_number' in change:
                        changes_by_team_number[change['team_number']].append(change)
                    else:
                        nonteam_changes.append(change)

                for _, team_changes in changes_by_team_number.items():
                    with reversion.create_revision():
                        reversion.set_user(request.user)
                        change_descriptions = []
                        for change in team_changes:
                            try:
                                if change['action'] == 'change-member':
                                    team_num = change['team_number']
                                    team = Team.objects.get(season=season, number=team_num)

                                    board_num = change['board_number']
                                    player_info = change['player']

                                    teammember = TeamMember.objects.filter(team=team, board_number=board_num).first()
                                    original_teammember = str(teammember)
                                    if teammember == None:
                                        teammember = TeamMember(team=team, board_number=board_num)
                                    if player_info is None:
                                        teammember.delete()
                                        teammember = None
                                    else:
                                        teammember.player = Player.objects.get(lichess_username=player_info['name'])
                                        teammember.is_captain = player_info['is_captain']
                                        teammember.is_vice_captain = player_info['is_vice_captain']
                                        teammember.save()

                                    change_descriptions.append('changed board %d from "%s" to "%s"' % (board_num, original_teammember, teammember))

                                if change['action'] == 'change-team' and not teams_locked:
                                    team_num = change['team_number']
                                    team = Team.objects.get(season=season, number=team_num)

                                    team_name = change['team_name']
                                    team.name = team_name
                                    team.save()

                                    change_descriptions.append('changed team name to "%s"' % team_name)

                                if change['action'] == 'create-team' and not teams_locked:
                                    model = change['model']
                                    team = Team.objects.create(season=season, number=model['number'], name=model['name'])

                                    for board_num, player_info in enumerate(model['boards'], 1):
                                        if player_info is not None:
                                            player = Player.objects.get(lichess_username=player_info['name'])
                                            is_captain = player_info['is_captain']
                                            with reversion.create_revision():
                                                TeamMember.objects.create(team=team, player=player, board_number=board_num, is_captain=is_captain)

                                    change_descriptions.append('created team "%s"' % model['name'])
                            except Exception:
                                has_error = True
                        reversion.set_comment('Edit rosters - %s.' % ', '.join(change_descriptions))

                for change in nonteam_changes:
                    try:
                        if change['action'] == 'create-alternate':
                            with reversion.create_revision():
                                reversion.set_user(request.user)
                                reversion.set_comment('Edit rosters - created alternate.')

                                board_num = change['board_number']
                                season_player = SeasonPlayer.objects.get(season=season, player__lichess_username__iexact=change['player_name'])
                                Alternate.objects.update_or_create(season_player=season_player, defaults={ 'board_number': board_num })

                        if change['action'] == 'delete-alternate':
                            with reversion.create_revision():
                                reversion.set_user(request.user)
                                reversion.set_comment('Edit rosters - deleted alternate.')

                                board_num = change['board_number']
                                season_player = SeasonPlayer.objects.get(season=season, player__lichess_username__iexact=change['player_name'])
                                alt = Alternate.objects.filter(season_player=season_player, board_number=board_num).first()
                                if alt is not None:
                                    alt.delete()

                    except Exception:
                        has_error = True

                if has_error:
                    self.message_user(request, 'Some changes could not be saved.', messages.WARNING)

                if 'save_continue' in form.data:
                    return redirect('admin:manage_players', object_id)
                return redirect('admin:tournament_season_changelist')
        else:
            form = forms.EditRostersForm()

        if not season.boards:
            self.message_user(request, 'Number of boards must be specified for %s' % season.name, messages.ERROR)
            return redirect('admin:tournament_season_changelist')
        board_numbers = list(range(1, season.boards + 1))
        teams = list(Team.objects.filter(season=season).order_by('number').prefetch_related(
            Prefetch('teammember_set', queryset=TeamMember.objects.select_related('player').nocache())
        ).nocache())
        team_members = TeamMember.objects.filter(team__season=season).select_related('player').nocache()
        alternates = Alternate.objects.filter(season_player__season=season).select_related('season_player__player').nocache()
        alternates_by_board = [(n, sorted(
                                          alternates.filter(board_number=n).select_related('season_player__registration').nocache(),
                                          key=lambda alt: alt.priority_date()
                                         )) for n in board_numbers]

        season_player_objs = SeasonPlayer.objects.filter(season=season, is_active=True).select_related('player', 'registration').nocache()
        season_players = set(sp.player for sp in season_player_objs)
        team_players = set(tm.player for tm in team_members)
        alternate_players = set(alt.season_player.player for alt in alternates)
        last_season = Season.objects.filter(league=league, start_date__lt=season.start_date).order_by('-start_date').first()
        old_alternates = {alt.season_player.player for alt in Alternate.objects.filter(season_player__season=last_season) \
                                                                               .select_related('season_player__player').nocache()}

        alternate_buckets = list(AlternateBucket.objects.filter(season=season))
        unassigned_players = list(sorted(season_players - team_players - alternate_players, key=lambda p: p.rating_for(league), reverse=True))
        if len(alternate_buckets) == season.boards:
            # Sort unassigned players by alternate buckets
            unassigned_by_board = [(n, [p for p in unassigned_players if find(alternate_buckets, board_number=n).contains(p.rating_for(league))]) for n in board_numbers]
        else:
            # Season doesn't have buckets yet. Sort by player soup
            sorted_players = list(sorted((p for p in season_players if p.rating_for(league) is not None), key=lambda p: p.rating_for(league), reverse=True))
            player_count = len(sorted_players)
            unassigned_by_board = [(n, []) for n in board_numbers]
            if player_count > 0:
                max_ratings = [(n, sorted_players[len(sorted_players) * (n - 1) / season.boards].rating_for(league)) for n in board_numbers]
                for p in unassigned_players:
                    board_num = 1
                    for n, max_rating in max_ratings:
                        if p.rating_for(league) <= max_rating:
                            board_num = n
                        else:
                            break
                    unassigned_by_board[board_num - 1][1].append(p)

        if teams_locked:
            new_team_number = None
        elif len(teams) == 0:
            new_team_number = 1
        else:
            new_team_number = teams[-1].number + 1

        # Player highlights
        red_players = set()
        blue_players = set()
        purple_players = set()
        for sp in season_player_objs:
            reg = sp.registration
            if sp.player.games_played is not None:
                if sp.player.games_played < 20:
                    red_players.add(sp.player)
            elif reg is None or not reg.has_played_20_games:
                red_players.add(sp.player)
            if not sp.player.in_slack_group:
                red_players.add(sp.player)
            if sp.games_missed >= 2:
                red_players.add(sp.player)
            if sp.player.account_status != 'normal':
                red_players.add(sp.player)
            if reg is not None and reg.alternate_preference == 'alternate':
                blue_players.add(sp.player)
            if sp.player in old_alternates:
                purple_players.add(sp.player)

        expected_ratings = {sp.player: sp.expected_rating(league) for sp in season_player_objs}

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'league': league,
            'original': season,
            'title': 'Edit rosters',
            'form': form,
            'teams': teams,
            'teams_locked': teams_locked,
            'new_team_number': new_team_number,
            'alternates_by_board': alternates_by_board,
            'unassigned_by_board': unassigned_by_board,
            'board_numbers': board_numbers,
            'board_count': season.boards,
            'red_players': red_players,
            'blue_players': blue_players,
            'purple_players': purple_players,
            'expected_ratings': expected_ratings,
        }

        return render(request, 'tournament/admin/edit_rosters.html', context)

    def lone_manage_players_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)

        active_players = SeasonPlayer.objects.filter(season=season, is_active=True).order_by('player__lichess_username')
        inactive_players = SeasonPlayer.objects.filter(season=season, is_active=False).order_by('player__lichess_username')

        def get_data(r):
            regs = r.playerlateregistration_set.order_by('player__lichess_username')
            wds = r.playerwithdrawal_set.order_by('player__lichess_username')
            byes = r.playerbye_set.order_by('player__lichess_username')
            unavailables = r.playeravailability_set.filter(is_available=False).order_by('player__lichess_username')

            # Don't show "unavailable" for players that already have a bye
            players_with_byes = {b.player for b in byes}
            unavailables = [u for u in unavailables if u.player not in players_with_byes]

            return r, regs, wds, byes, unavailables

        rounds = Round.objects.filter(season=season, is_completed=False).order_by('number')
        round_data = [get_data(r) for r in rounds]

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': season,
            'title': '',
            'active_players': active_players,
            'inactive_players': inactive_players,
            'round_data': round_data,
            'league': season.league,
        }

        return render(request, 'tournament/admin/manage_lone_players.html', context)

@admin.register(Round)
class RoundAdmin(_BaseAdmin):
    list_filter = ('season',)
    actions = ['generate_pairings', 'simulate_results']
    league_id_field = 'season__league_id'

    def get_urls(self):
        urls = super(RoundAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/generate_pairings/$',
                self.admin_site.admin_view(self.generate_pairings_view),
                name='generate_pairings'),
            url(r'^(?P<object_id>[0-9]+)/review_pairings/$',
                self.admin_site.admin_view(self.review_pairings_view),
                name='review_pairings'),
        ]
        return my_urls + urls

    def generate_pairings(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Pairings can only be generated one round at a time', messages.ERROR)
            return
        return redirect('admin:generate_pairings', object_id=queryset[0].pk)

    def simulate_results(self, request, queryset):
        if not settings.DEBUG and not settings.STAGING:
            self.message_user(request, 'Results can\'t be simulated in a live environment', messages.ERROR)
            return
        if queryset.count() > 1:
            self.message_user(request, 'Results can only be simulated one round at a time', messages.ERROR)
            return
        round_ = queryset[0]
        simulation.simulate_round(round_)
        self.message_user(request, 'Simulation complete.', messages.INFO)
        return redirect('admin:tournament_round_changelist')

    def generate_pairings_view(self, request, object_id):
        round_ = get_object_or_404(Round, pk=object_id)
        if not request.user.has_perm('tournament.generate_pairings', round_.season.league):
            raise PermissionDenied

        if request.method == 'POST':
            form = forms.GeneratePairingsForm(request.POST)
            if form.is_valid():
                try:
                    if form.cleaned_data['run_in_background']:
                        signals.do_generate_pairings.send(sender=self.__class__, round_id=round_.pk, overwrite=form.cleaned_data['overwrite_existing'])
                        self.message_user(request, 'Generating pairings in background.', messages.INFO)
                        return redirect('admin:review_pairings', object_id)
                    else:
                        pairinggen.generate_pairings(round_, overwrite=form.cleaned_data['overwrite_existing'])
                        with reversion.create_revision():
                            reversion.set_user(request.user)
                            reversion.set_comment('Generated pairings.')
                            round_.publish_pairings = False
                            round_.save()

                        self.message_user(request, 'Pairings generated.', messages.INFO)
                        return redirect('admin:review_pairings', object_id)
                except pairinggen.PairingsExistException:
                    if not round_.publish_pairings:
                        self.message_user(request, 'Unpublished pairings already exist.', messages.WARNING)
                        return redirect('admin:review_pairings', object_id)
                    self.message_user(request, 'Pairings already exist for the selected round.', messages.ERROR)
                except pairinggen.PairingHasResultException:
                    self.message_user(request, 'Pairings with results can\'t be overwritten.', messages.ERROR)
                except pairinggen.PairingGenerationException as e:
                    self.message_user(request, 'Error generating pairings. %s' % e.message, messages.ERROR)
                return redirect('admin:generate_pairings', object_id=round_.pk)
        else:
            form = forms.GeneratePairingsForm()

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': round_,
            'title': 'Generate pairings',
            'form': form
        }

        return render(request, 'tournament/admin/generate_pairings.html', context)

    def review_pairings_view(self, request, object_id):
        round_ = get_object_or_404(Round, pk=object_id)
        if not request.user.has_perm('tournament.generate_pairings', round_.season.league):
            raise PermissionDenied

        if request.method == 'POST':
            form = forms.ReviewPairingsForm(request.POST)
            if form.is_valid():
                if 'publish' in form.data:
                    round_.publish_pairings = True
                    round_.save()
                    # Update ranks in case of manual edits
                    rank_dict = lone_player_pairing_rank_dict(round_.season)
                    for lpp in round_.loneplayerpairing_set.all().nocache():
                        lpp.refresh_ranks(rank_dict)
                        with reversion.create_revision():
                            reversion.set_user(request.user)
                            reversion.set_comment('Published pairings.')
                            lpp.save()
                    for bye in round_.playerbye_set.all():
                        bye.refresh_rank(rank_dict)
                        with reversion.create_revision():
                            reversion.set_user(request.user)
                            reversion.set_comment('Published pairings.')
                            bye.save()
                    self.message_user(request, 'Pairings published.', messages.INFO)
                elif 'delete' in form.data:
                    try:
                        # Note: no reversion required for deleting things
                        pairinggen.delete_pairings(round_)
                        self.message_user(request, 'Pairings deleted.', messages.INFO)
                    except pairinggen.PairingHasResultException:
                        self.message_user(request, 'Pairings with results can\'t be deleted.', messages.ERROR)
                return redirect('admin:tournament_round_changelist')
        else:
            form = forms.ReviewPairingsForm()

        if round_.season.league.competitor_type == 'team':
            team_pairings = round_.teampairing_set.order_by('pairing_order')
            pairing_lists = [team_pairing.teamplayerpairing_set.order_by('board_number').nocache() for team_pairing in team_pairings]
            context = {
                'has_permission': True,
                'opts': self.model._meta,
                'site_url': '/',
                'original': round_,
                'title': 'Review pairings',
                'form': form,
                'pairing_lists': pairing_lists
            }
            return render(request, 'tournament/admin/review_team_pairings.html', context)
        else:
            pairings = round_.loneplayerpairing_set.order_by('pairing_order').nocache()
            byes = round_.playerbye_set.order_by('type', 'player_rank', 'player__lichess_username')
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

            active_players = {sp.player for sp in SeasonPlayer.objects.filter(season=round_.season, is_active=True)}

            def pairing_error(pairing):
                if not request.user.is_staff:
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
                if not request.user.is_staff:
                    return None
                if bye.player in duplicate_players:
                    return 'Duplicate player: %s' % bye.player.lichess_username
                if not round_.is_completed and bye.player not in active_players:
                    return 'Inactive player: %s' % bye.player.lichess_username
                return None

            # Add errors
            pairings = [(p, pairing_error(p)) for p in pairings]
            byes = [(b, bye_error(b)) for b in byes]

            context = {
                'has_permission': True,
                'opts': self.model._meta,
                'site_url': '/',
                'original': round_,
                'title': 'Review pairings',
                'form': form,
                'pairings': pairings,
                'byes': byes,
                'round_': round_,
                'league': round_.season.league,
                'next_pairing_order': next_pairing_order,
            }
            return render(request, 'tournament/admin/review_lone_pairings.html', context)


#-------------------------------------------------------------------------------
@admin.register(PlayerLateRegistration)
class PlayerLateRegistrationAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'retroactive_byes', 'late_join_points')
    search_fields = ('player__lichess_username',)
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('round', 'player')
    league_id_field = 'round__season__league_id'

#-------------------------------------------------------------------------------
@admin.register(PlayerWithdrawal)
class PlayerWithdrawalAdmin(_BaseAdmin):
    list_display = ('__unicode__',)
    search_fields = ('player__lichess_username',)
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('round', 'player')
    league_id_field = 'round__season__league_id'

#-------------------------------------------------------------------------------
@admin.register(PlayerBye)
class PlayerByeAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'type')
    search_fields = ('player__lichess_username',)
    list_filter = ('round__season', 'round__number', 'type')
    raw_id_fields = ('round', 'player')
    exclude = ('player_rating',)
    league_id_field = 'round__season__league_id'

#-------------------------------------------------------------------------------
@admin.register(Player)
class PlayerAdmin(_BaseAdmin):
    search_fields = ('lichess_username', 'email')
    list_filter = ('is_active',)
    readonly_fields = ('rating', 'games_played', 'in_slack_group', 'account_status')
    exclude = ('profile',)
    actions = ['update_selected_player_ratings']
    allow_all_staff = True

    def has_delete_permission(self, request, obj=None):
        # Don't let unprivileged users delete players
        return self.has_assigned_perm(request.user, 'delete')

    def clean_form(self, request, form):
        # Restrict what can be edited manually
        if self.has_assigned_perm(request.user, 'change'):
            return
        if form.instance.pk is None:
            return
        old_username = form.instance.lichess_username.lower()
        if old_username != form.cleaned_data['lichess_username'].lower():
            raise ValidationError('No permission to change a player\'s username')
        if old_username != request.user.username.lower() and LeagueModerator.objects.filter(player__lichess_username__iexact=old_username).exists():
            raise ValidationError('No permission to change a mod\'s info')

    def update_selected_player_ratings(self, request, queryset):
#         try:
        usernames = [p.lichess_username for p in queryset.all()]
        for user_meta in lichessapi.enumerate_user_metas(usernames, priority=1):
            p = Player.objects.get(lichess_username__iexact=user_meta['id'])
            p.update_profile(user_meta)
        self.message_user(request, 'Rating(s) updated', messages.INFO)
#         except:
#             self.message_user(request, 'Error updating rating(s) from lichess API', messages.ERROR)

#-------------------------------------------------------------------------------
@admin.register(LeagueModerator)
class LeagueModeratorAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'is_active', 'send_contact_emails')
    search_fields = ('player__lichess_username',)
    list_filter = ('league',)
    raw_id_fields = ('player',)
    league_id_field = 'league_id'

#-------------------------------------------------------------------------------
class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 0
    ordering = ('board_number',)
    raw_id_fields = ('player',)
    exclude = ('player_rating',)

#-------------------------------------------------------------------------------
@admin.register(Team)
class TeamAdmin(_BaseAdmin):
    list_display = ('name', 'season')
    search_fields = ('name',)
    list_filter = ('season',)
    inlines = [TeamMemberInline]
    actions = ['update_board_order_by_rating']
    league_id_field = 'season__league_id'

    def update_board_order_by_rating(self, request, queryset):
        for team in queryset.all():
            if not request.user.has_perm('tournament.manage_players', team.season.league):
                raise PermissionDenied
            members = team.teammember_set.order_by('-player__rating')
            for i in range(len(members)):
                members[i].board_number = i + 1
                members[i].save()
        self.message_user(request, 'Board order updated', messages.INFO)

#-------------------------------------------------------------------------------
@admin.register(TeamMember)
class TeamMemberAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'team')
    search_fields = ('team__name', 'player__lichess_username')
    list_filter = ('team__season',)
    raw_id_fields = ('player',)
    exclude = ('player_rating',)
    league_id_field = 'team__season__league_id'

#-------------------------------------------------------------------------------
@admin.register(TeamScore)
class TeamScoreAdmin(_BaseAdmin):
    list_display = ('team', 'match_points', 'game_points')
    search_fields = ('team__name',)
    list_filter = ('team__season',)
    raw_id_fields = ('team',)
    league_id_field = 'team__season__league_id'

#-------------------------------------------------------------------------------
@admin.register(Alternate)
class AlternateAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'board_number', 'status')
    search_fields = ('season_player__player__lichess_username',)
    list_filter = ('season_player__season', 'board_number', 'status')
    raw_id_fields = ('season_player',)
    exclude = ('player_rating',)
    league_id_field = 'season_player__season__league_id'

#-------------------------------------------------------------------------------
@admin.register(AlternateAssignment)
class AlternateAssignmentAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'player')
    search_fields = ('team__name', 'player__lichess_username')
    list_filter = ('round__season', 'round__number', 'board_number')
    raw_id_fields = ('round', 'team', 'player', 'replaced_player')
    league_id_field = 'round__season__league_id'

#-------------------------------------------------------------------------------
@admin.register(AlternateBucket)
class AlternateBucketAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'season')
    search_fields = ()
    list_filter = ('season', 'board_number')
    league_id_field = 'season__league_id'

#-------------------------------------------------------------------------------
@admin.register(AlternateSearch)
class AlternateSearchAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'status')
    search_fields = ('team__name',)
    list_filter = ('round__season', 'round__number', 'board_number', 'status')
    league_id_field = 'round__season__league_id'

#-------------------------------------------------------------------------------
@admin.register(AlternatesManagerSetting)
class AlternatesManagerSettingAdmin(_BaseAdmin):
    list_display = ('__unicode__',)
    league_id_field = 'season__league_id'

#-------------------------------------------------------------------------------
@admin.register(TeamPairing)
class TeamPairingAdmin(_BaseAdmin):
    list_display = ('white_team_name', 'black_team_name', 'season_name', 'round_number')
    search_fields = ('white_team__name', 'black_team__name')
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('white_team', 'black_team', 'round')
    league_id_field = 'round__season__league_id'

#-------------------------------------------------------------------------------
@admin.register(PlayerPairing)
class PlayerPairingAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'scheduled_time', 'game_link_url')
    search_fields = ('white__lichess_username', 'black__lichess_username', 'game_link')
    raw_id_fields = ('white', 'black')
    exclude = ('white_rating', 'black_rating', 'tv_state')

    def get_queryset(self, request):
        result = super(_BaseAdmin, self).get_queryset(request)
        if self.has_assigned_perm(request.user, 'change'):
            return result
        return result.filter(teamplayerpairing__team_pairing__round__season__league_id__in=self.authorized_leagues(request.user)) \
             | result.filter(loneplayerpairing__round__season__league_id__in=self.authorized_leagues(request.user))

    def get_league_id(self, obj):
        if hasattr(obj, 'teamplayerpairing'):
            return obj.teamplayerpairing.team_pairing.round.season.league_id
        elif hasattr(obj, 'loneplayerpairing'):
            return obj.loneplayerpairing.round.season.league_id
        else:
            return None

    def has_league_perm(self, user, obj=None):
        if obj is None:
            return len(self.authorized_leagues(user)) > 0
        else:
            return self.get_league_id(obj) in self.authorized_leagues(user)

    def clean_form(self, request, form):
        if form.instance.pk is None or self.has_assigned_perm(request.user, 'change'):
            return
        if self.get_league_id(form.instance) not in self.authorized_leagues(request.user):
            raise ValidationError('No permission to save objects for this league')

    def game_link_url(self, obj):
        if not obj.game_link:
            return ''
        return format_html("<a href='{url}'>{url}</a>", url=obj.game_link)

#-------------------------------------------------------------------------------
@admin.register(TeamPlayerPairing)
class TeamPlayerPairingAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'team_pairing', 'board_number', 'game_link_url')
    search_fields = ('white__lichess_username', 'black__lichess_username',
                     'team_pairing__white_team__name', 'team_pairing__black_team__name', 'game_link')
    list_filter = ('team_pairing__round__season', 'team_pairing__round__number',)
    raw_id_fields = ('white', 'black', 'team_pairing')
    league_id_field = 'team_pairing__round__season__league_id'

    def game_link_url(self, obj):
        if not obj.game_link:
            return ''
        return format_html("<a href='{url}'>{url}</a>", url=obj.game_link)

#-------------------------------------------------------------------------------
@admin.register(LonePlayerPairing)
class LonePlayerPairingAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'round', 'game_link_url')
    search_fields = ('white__lichess_username', 'black__lichess_username', 'game_link')
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('white', 'black', 'round')
    league_id_field = 'round__season__league_id'

    def game_link_url(self, obj):
        if not obj.game_link:
            return ''
        return format_html("<a href='{url}'>{url}</a>", url=obj.game_link)

#-------------------------------------------------------------------------------
@admin.register(Registration)
class RegistrationAdmin(_BaseAdmin):
    list_display = ('review', 'email', 'status', 'season', 'date_created')
    list_display_links = ()
    search_fields = ('lichess_username', 'email', 'season__name')
    list_filter = ('status', 'season',)
    actions = ('validate',)
    league_id_field = 'season__league_id'

    def changelist_view(self, request, extra_context=None):
        self.request = request
        return super(RegistrationAdmin, self).changelist_view(request, extra_context=extra_context)

    def review(self, obj):
        _url = reverse('admin:review_registration', args=[obj.pk]) + "?" + self.get_preserved_filters(self.request)
        return '<a href="%s"><b>%s</b></a>' % (_url, obj.lichess_username)
    review.allow_tags = True

    def edit(self, obj):
        return 'Edit'
    edit.allow_tags = True

    def get_urls(self):
        urls = super(RegistrationAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/review/$',
                self.admin_site.admin_view(self.review_registration),
                name='review_registration'),
            url(r'^(?P<object_id>[0-9]+)/approve/$',
                self.admin_site.admin_view(self.approve_registration),
                name='approve_registration'),
            url(r'^(?P<object_id>[0-9]+)/reject/$',
                self.admin_site.admin_view(self.reject_registration),
                name='reject_registration')
        ]
        return my_urls + urls

    def validate(self, request, queryset):
        for reg in queryset:
            if not request.user.has_perm('tournament.change_registration', reg.season.league):
                raise PermissionDenied
            signals.do_validate_registration.send(sender=RegistrationAdmin, reg_id=reg.pk)
        self.message_user(request, 'Validation started.', messages.INFO)
        return redirect('admin:tournament_registration_changelist')

    def review_registration(self, request, object_id):
        reg = get_object_or_404(Registration, pk=object_id)
        if not request.user.has_perm('tournament.change_registration', reg.season.league):
            raise PermissionDenied

        if request.method == 'POST':
            changelist_filters = request.POST.get('_changelist_filters', '')
            form = forms.ReviewRegistrationForm(request.POST)
            if form.is_valid():
                params = '?_changelist_filters=' + urlquote(changelist_filters)
                if 'approve' in form.data and reg.status == 'pending':
                    return redirect_with_params('admin:approve_registration', object_id=object_id, params=params)
                elif 'reject' in form.data and reg.status == 'pending':
                    return redirect_with_params('admin:reject_registration', object_id=object_id, params=params)
                elif 'edit' in form.data:
                    return redirect_with_params('admin:tournament_registration_change', object_id, params=params)
                else:
                    return redirect_with_params('admin:tournament_registration_changelist', params=params)
        else:
            changelist_filters = request.GET.get('_changelist_filters', '')
            form = forms.ReviewRegistrationForm()

        is_team = reg.season.league.competitor_type == 'team'

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': reg,
            'title': 'Review registration',
            'form': form,
            'is_team': is_team,
            'changelist_filters': changelist_filters
        }

        return render(request, 'tournament/admin/review_registration.html', context)

    def approve_registration(self, request, object_id):
        reg = get_object_or_404(Registration, pk=object_id)
        if not request.user.has_perm('tournament.change_registration', reg.season.league):
            raise PermissionDenied

        if reg.status != 'pending':
            return redirect('admin:review_registration', object_id)

        if request.method == 'POST':
            changelist_filters = request.POST.get('_changelist_filters', '')
            form = forms.ApproveRegistrationForm(request.POST, registration=reg)
            if form.is_valid():
                if 'confirm' in form.data:
                    # Limit changes to moderators
                    mod = LeagueModerator.objects.filter(player__lichess_username__iexact=reg.lichess_username).first()
                    if mod is not None and mod.player.email and mod.player.email != reg.email:
                        reg.email = mod.player.email

                    # Add or update the player in the DB
                    with reversion.create_revision():
                        reversion.set_user(request.user)
                        reversion.set_comment('Approved registration.')

                        player, created = Player.objects.update_or_create(
                            lichess_username__iexact=reg.lichess_username,
                            defaults={'lichess_username': reg.lichess_username, 'email': reg.email, 'is_active': True}
                        )
                        if player.rating is None:
                            # This is automatically set, so don't change it if we already have a rating
                            player.rating = reg.classical_rating
                            player.save()
                        if created and reg.already_in_slack_group:
                            # This is automatically set, so don't change it if the player already exists
                            player.in_slack_group = True
                            player.save()

                    with reversion.create_revision():
                        reversion.set_user(request.user)
                        reversion.set_comment('Approved registration.')

                        SeasonPlayer.objects.update_or_create(
                            player=player,
                            season=reg.season,
                            defaults={'registration': reg, 'is_active': True}
                        )

                    # Set availability
                    for week_number in reg.weeks_unavailable.split(','):
                        if week_number != '':
                            round_ = Round.objects.filter(season=reg.season, number=int(week_number)).first()
                            if round_ is not None:
                                with reversion.create_revision():
                                    reversion.set_user(request.user)
                                    reversion.set_comment('Approved registration.')
                                    PlayerAvailability.objects.update_or_create(player=player, round=round_, defaults={'is_available': False})

                    if reg.season.league.competitor_type == 'team':
                        subject = render_to_string('tournament/emails/team_registration_approved_subject.txt', {'reg': reg})
                        msg_plain = render_to_string('tournament/emails/team_registration_approved.txt', {'reg': reg})
                        msg_html = render_to_string('tournament/emails/team_registration_approved.html', {'reg': reg})
                    else:
                        if Round.objects.filter(season=reg.season, publish_pairings=True).count() > 0:
                            # Late registration
                            next_round = Round.objects.filter(season=reg.season, publish_pairings=False).order_by('number').first()
                            if next_round is not None:
                                with reversion.create_revision():
                                    reversion.set_user(request.user)
                                    reversion.set_comment('Approved registration.')
                                    PlayerLateRegistration.objects.update_or_create(round=next_round, player=player,
                                                                      defaults={'retroactive_byes': form.cleaned_data['retroactive_byes'],
                                                                      'late_join_points': form.cleaned_data['late_join_points']})

                        subject = render_to_string('tournament/emails/lone_registration_approved_subject.txt', {'reg': reg})
                        msg_plain = render_to_string('tournament/emails/lone_registration_approved.txt', {'reg': reg})
                        msg_html = render_to_string('tournament/emails/lone_registration_approved.html', {'reg': reg})

                    if form.cleaned_data['send_confirm_email']:
                        try:
                            send_mail(
                                subject,
                                msg_plain,
                                settings.DEFAULT_FROM_EMAIL,
                                [reg.email],
                                html_message=msg_html,
                            )
                            self.message_user(request, 'Confirmation email sent to "%s".' % reg.email, messages.INFO)
                        except SMTPException:
                            self.message_user(request, 'A confirmation email could not be sent.', messages.ERROR)

                    if form.cleaned_data['invite_to_slack']:
                        try:
                            slackapi.invite_user(reg.email)
                            self.message_user(request, 'Slack invitation sent to "%s".' % reg.email, messages.INFO)
                        except slackapi.AlreadyInTeam:
                            self.message_user(request, 'The player is already in the slack group.', messages.WARNING)
                        except slackapi.AlreadyInvited:
                            self.message_user(request, 'The player has already been invited to the slack group.', messages.WARNING)

                    with reversion.create_revision():
                        reversion.set_user(request.user)
                        reversion.set_comment('Approved registration.')
                        reg.status = 'approved'
                        reg.status_changed_by = request.user.username
                        reg.status_changed_date = timezone.now()
                        reg.save()

                    self.message_user(request, 'Registration for "%s" approved.' % reg.lichess_username, messages.INFO)
                    return redirect_with_params('admin:tournament_registration_changelist', params='?' + changelist_filters)
                else:
                    return redirect_with_params('admin:review_registration', object_id, params='?_changelist_filters=' + urlquote(changelist_filters))
        else:
            changelist_filters = request.GET.get('_changelist_filters', '')
            form = forms.ApproveRegistrationForm(registration=reg)

        next_round = Round.objects.filter(season=reg.season, publish_pairings=False).order_by('number').first()

        mod = LeagueModerator.objects.filter(player__lichess_username__iexact=reg.lichess_username).first()
        no_email_change = mod is not None and mod.player.email and mod.player.email != reg.email
        confirm_email = mod.player.email if no_email_change else reg.email

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': reg,
            'title': 'Confirm approval',
            'form': form,
            'next_round': next_round,
            'confirm_email': confirm_email,
            'no_email_change': no_email_change,
            'changelist_filters': changelist_filters
        }

        return render(request, 'tournament/admin/approve_registration.html', context)

    def reject_registration(self, request, object_id):
        reg = get_object_or_404(Registration, pk=object_id)
        if not request.user.has_perm('tournament.change_registration', reg.season.league):
            raise PermissionDenied

        if reg.status != 'pending':
            return redirect('admin:review_registration', object_id)

        if request.method == 'POST':
            changelist_filters = request.POST.get('_changelist_filters', '')
            form = forms.RejectRegistrationForm(request.POST, registration=reg)
            if form.is_valid():
                if 'confirm' in form.data:
                    with reversion.create_revision():
                        reversion.set_user(request.user)
                        reversion.set_comment('Rejected registration.')

                        reg.status = 'rejected'
                        reg.status_changed_by = request.user.username
                        reg.status_changed_date = timezone.now()
                        reg.save()

                    self.message_user(request, 'Registration for "%s" rejected.' % reg.lichess_username, messages.INFO)
                    return redirect_with_params('admin:tournament_registration_changelist', params='?' + changelist_filters)
                else:
                    return redirect('admin:review_registration', object_id)
                    return redirect_with_params('admin:review_registration', object_id, params='?_changelist_filters=' + urlquote(changelist_filters))
        else:
            changelist_filters = request.GET.get('_changelist_filters', '')
            form = forms.RejectRegistrationForm(registration=reg)

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': reg,
            'title': 'Confirm rejection',
            'form': form,
            'changelist_filters': changelist_filters
        }

        return render(request, 'tournament/admin/reject_registration.html', context)

#-------------------------------------------------------------------------------
@admin.register(SeasonPlayer)
class SeasonPlayerAdmin(_BaseAdmin):
    list_display = ('player', 'season', 'is_active', 'in_slack')
    search_fields = ('season__name', 'player__lichess_username')
    list_filter = ('season', 'is_active', 'player__in_slack_group')
    raw_id_fields = ('player', 'registration')
    league_id_field = 'season__league_id'

    def in_slack(self, sp):
        return sp.player.in_slack_group
    in_slack.boolean = True

#-------------------------------------------------------------------------------
@admin.register(LonePlayerScore)
class LonePlayerScoreAdmin(_BaseAdmin):
    list_display = ('season_player', 'points', 'late_join_points')
    search_fields = ('season_player__season__name', 'season_player__player__lichess_username')
    list_filter = ('season_player__season',)
    raw_id_fields = ('season_player',)
    league_id_field = 'season_player__season__league_id'

#-------------------------------------------------------------------------------
@admin.register(PlayerAvailability)
class PlayerAvailabilityAdmin(_BaseAdmin):
    list_display = ('player', 'round', 'is_available')
    search_fields = ('player__lichess_username',)
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('player', 'round')
    league_id_field = 'round__season__league_id'

#-------------------------------------------------------------------------------
@admin.register(SeasonPrize)
class SeasonPrizeAdmin(_BaseAdmin):
    list_display = ('season', 'rank', 'max_rating')
    search_fields = ('season__name',)
    league_id_field = 'season__league_id'

#-------------------------------------------------------------------------------
@admin.register(SeasonPrizeWinner)
class SeasonPrizeWinnerAdmin(_BaseAdmin):
    list_display = ('season_prize', 'player',)
    search_fields = ('season_prize__name', 'player__lichess_username')
    raw_id_fields = ('season_prize', 'player')
    league_id_field = 'season_prize__season__league_id'

#-------------------------------------------------------------------------------
@admin.register(GameNomination)
class GameNominationAdmin(_BaseAdmin):
    list_display = ('__unicode__',)
    search_fields = ('season__name', 'nominating_player__lichess_username')
    raw_id_fields = ('nominating_player',)
    league_id_field = 'season__league_id'

#-------------------------------------------------------------------------------
@admin.register(GameSelection)
class GameSelectionAdmin(_BaseAdmin):
    list_display = ('__unicode__',)
    search_fields = ('season__name',)
    league_id_field = 'season__league_id'

#-------------------------------------------------------------------------------
@admin.register(AvailableTime)
class AvailableTimeAdmin(_BaseAdmin):
    list_display = ('player', 'time', 'league')
    search_fields = ('player__lichess_username',)
    league_id_field = 'league_id'

#-------------------------------------------------------------------------------
@admin.register(NavItem)
class NavItemAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'parent')
    search_fields = ('text',)
    league_id_field = 'league_id'

#-------------------------------------------------------------------------------
@admin.register(ApiKey)
class ApiKeyAdmin(_BaseAdmin):
    list_display = ('name',)
    search_fields = ('name',)

#-------------------------------------------------------------------------------
@admin.register(PrivateUrlAuth)
class PrivateUrlAuthAdmin(_BaseAdmin):
    list_display = ('__unicode__', 'expires')
    search_fields = ('authenticated_user',)

#-------------------------------------------------------------------------------
@admin.register(Document)
class DocumentAdmin(_BaseAdmin):
    list_display = ('name',)
    search_fields = ('name',)

    def get_queryset(self, request):
        result = super(_BaseAdmin, self).get_queryset(request)
        if self.has_assigned_perm(request.user, 'change'):
            return result
        return result.filter(leaguedocument__league_id__in=self.authorized_leagues(request.user)) \
             | result.filter(seasondocument__season__league_id__in=self.authorized_leagues(request.user)) \
             | result.filter(leaguedocument=None, seasondocument=None)

    def get_league_id(self, obj):
        if hasattr(obj, 'leaguedocument'):
            return obj.leaguedocument.league_id
        elif hasattr(obj, 'seasondocument'):
            return obj.seasondocument.season.league_id
        else:
            return None

    def has_league_perm(self, user, obj=None):
        if obj is None:
            return len(self.authorized_leagues(user)) > 0
        else:
            league_id = self.get_league_id(obj)
            return league_id is None or league_id in self.authorized_leagues(user)

    def clean_form(self, request, form):
        if form.instance.pk is None or self.has_assigned_perm(request.user, 'change'):
            return
        league_id = self.get_league_id(form.instance)
        if league_id is not None and league_id not in self.authorized_leagues(request.user):
            raise ValidationError('No permission to save objects for this league')

#-------------------------------------------------------------------------------
@admin.register(LeagueDocument)
class LeagueDocumentAdmin(_BaseAdmin):
    list_display = ('document', 'league', 'tag', 'type', 'url')
    search_fields = ('league__name', 'tag', 'document__name')
    league_id_field = 'league_id'

    def url(self, obj):
        _url = reverse('by_league:document', args=[obj.league.tag, obj.tag])
        return '<a href="%s">%s</a>' % (_url, _url)
    url.allow_tags = True

#-------------------------------------------------------------------------------
@admin.register(SeasonDocument)
class SeasonDocumentAdmin(_BaseAdmin):
    list_display = ('document', 'season', 'tag', 'type', 'url')
    search_fields = ('season__name', 'tag', 'document__name')
    league_id_field = 'season__league_id'

    def url(self, obj):
        _url = reverse('by_league:by_season:document', args=[obj.season.league.tag, obj.season.tag, obj.tag])
        return '<a href="%s">%s</a>' % (_url, _url)
    url.allow_tags = True

#-------------------------------------------------------------------------------
@admin.register(LeagueChannel)
class LeagueChannelAdmin(_BaseAdmin):
    list_display = ('league', 'type', 'slack_channel')
    search_fields = ('league__name', 'slack_channel')
    league_id_field = 'league_id'

#-------------------------------------------------------------------------------
@admin.register(ScheduledEvent)
class ScheduledEventAdmin(_BaseAdmin):
    list_display = ('type', 'offset', 'relative_to', 'league', 'season')
    search_fields = ('league__name', 'season__name')
    league_id_field = 'league_id'

#-------------------------------------------------------------------------------
@admin.register(PlayerNotificationSetting)
class PlayerNotificationSettingAdmin(_BaseAdmin):
    list_display = ('player', 'type', 'league', 'offset', 'enable_lichess_mail', 'enable_slack_im', 'enable_slack_mpim')
    list_filter = ('league', 'type')
    search_fields = ('player__lichess_username',)
    raw_id_fields = ('player',)
    league_id_field = 'league_id'

#-------------------------------------------------------------------------------
@admin.register(ScheduledNotification)
class ScheduledNotificationAdmin(_BaseAdmin):
    list_display = ('setting', 'pairing', 'notification_time')
    list_filter = ('setting__type',)
    search_fields = ('player__lichess_username',)
    raw_id_fields = ('setting', 'pairing')
    league_id_field = 'setting__league_id'
