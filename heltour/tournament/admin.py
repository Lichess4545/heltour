from django.contrib import admin, messages
from django.utils import timezone
from heltour.tournament import lichessapi, slackapi, views, forms, signals, simulation
from heltour.tournament.models import *
from reversion.admin import VersionAdmin
from django.conf.urls import url
from django.shortcuts import render, redirect, get_object_or_404
import reversion

import json
from . import pairinggen
from . import spreadsheet
from django.db.models import Q
from django.db.models.query import Prefetch
from django.db import transaction
from heltour import settings
from datetime import timedelta
from django_comments.models import Comment
from django.contrib.sites.models import Site
from django.urls import reverse
from django.http.response import HttpResponse
from django.utils.http import urlquote
from django.core.mail.message import EmailMultiAlternatives
from django.core import mail
from django.utils.html import format_html
from heltour.tournament.workflows import *
from django.forms.models import ModelForm
from django.core.exceptions import PermissionDenied
from django.contrib.admin.filters import FieldListFilter, RelatedFieldListFilter, \
    SimpleListFilter
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver
from django.contrib.contenttypes.models import ContentType
from heltour.tournament.team_rating_utils import team_rating_range, team_rating_variance
from heltour.tournament import teamgen
import time


# Customize which sections are visible
# admin.site.register(Comment)
# admin.site.unregister(Site)

def redirect_with_params(*args, **kwargs):
    params = kwargs.pop('params')
    response = redirect(*args, **kwargs)
    response['Location'] += params
    return response


@receiver(post_save, sender=Comment, dispatch_uid='heltour.tournament.admin')
def comment_saved(instance, created, **kwargs):
    if not created:
        return
    model = instance.content_type.model_class()
    model_admin = admin.site._registry.get(model)
    if model_admin is None or not hasattr(model_admin, 'get_league_id'):
        return
    league_id = model_admin.get_league_id(instance.content_object)
    if league_id is None:
        return
    league = League.objects.get(pk=league_id)
    signals.league_comment.send(sender=comment_saved, league=league, comment=instance)


# -------------------------------------------------------------------------------
class _BaseAdmin(VersionAdmin):
    change_form_template = 'tournament/admin/change_form_with_comments.html'
    history_latest_first = True

    league_id_field = None
    league_competitor_type = None

    def has_assigned_perm(self, user, perm_type):
        return 'tournament.%s_%s' % (perm_type, self.opts.model_name) in user.get_all_permissions()

    def get_league_id(self, obj):
        if self.league_id_field is None:
            return None
        return getnestedattr(obj, self.league_id_field)

    def has_league_perm(self, user, action, obj):
        if self.league_id_field is None:
            return False
        authorized_leagues = self.authorized_leagues(user)
        if self.league_competitor_type is not None \
            and all(
            (League.objects.get(pk=pk).competitor_type != self.league_competitor_type for pk in
             authorized_leagues)):
            return False
        if obj is None:
            return bool(authorized_leagues)
        else:
            return self.get_league_id(obj) in authorized_leagues

    def get_queryset(self, request):
        queryset = super(_BaseAdmin, self).get_queryset(request)
        if self.has_assigned_perm(request.user, 'change'):
            return queryset
        if self.league_id_field is None:
            return queryset.none()
        return queryset.filter(
            **{self.league_id_field + '__in': self.authorized_leagues(request.user)})

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        kwargs['queryset'] = admin.site._registry[db_field.related_model].get_queryset(request)
        return super(_BaseAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def has_add_permission(self, request):
        if self.has_assigned_perm(request.user, 'add'):
            return True
        return self.has_league_perm(request.user, 'add', None)

    def has_change_permission(self, request, obj=None):
        if self.has_assigned_perm(request.user, 'change'):
            return True
        return self.has_league_perm(request.user, 'change', obj)

    def has_delete_permission(self, request, obj=None):
        if self.has_assigned_perm(request.user, 'delete'):
            return True
        return self.has_league_perm(request.user, 'delete', obj)

    def get_form(self, request, obj=None, **kwargs):
        form = super(_BaseAdmin, self).get_form(request, obj, **kwargs)

        def clean(form):
            super(ModelForm, form).clean()
            self.clean_form(request, form)

        form.clean = clean
        return form

    def clean_form(self, request, form):
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
                league = form.cleaned_data.get(parts[0][:-3])
                if league is None:
                    return
                league_id = league.id
        else:
            league_id = getnestedattr(form.cleaned_data[parts[0]], parts[1])
        if league_id not in self.authorized_leagues(request.user):
            raise ValidationError('No permission to save objects for this league')

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['related_objects_for_comments'] = self.related_objects_for_comments(request,
                                                                                          object_id)
        return super(_BaseAdmin, self).change_view(request, object_id, form_url,
                                                   extra_context=extra_context)

    def related_objects_for_comments(self, request, object_id):
        return []

    def authorized_leagues(self, user):
        return [lm['league_id'] for lm in LeagueModerator.objects.filter(
            player__lichess_username__iexact=user.username).values('league_id')]


# -------------------------------------------------------------------------------
class LeagueRestrictedListFilter(RelatedFieldListFilter):

    def field_choices(self, field, request, model_admin):
        if not isinstance(model_admin, _BaseAdmin) or model_admin.has_assigned_perm(request.user,
                                                                                    'change'):
            return field.get_choices(include_blank=False)
        league_id_field = admin.site._registry[field.related_model].league_id_field
        league_filter = {league_id_field + '__in': model_admin.authorized_leagues(request.user)}
        return field.get_choices(include_blank=False, limit_choices_to=league_filter)


FieldListFilter.register(lambda f: f.remote_field, LeagueRestrictedListFilter, take_priority=True)


# -------------------------------------------------------------------------------
@admin.register(League)
class LeagueAdmin(_BaseAdmin):
    actions = ['import_season', 'export_forfeit_data']
    league_id_field = 'id'

    def has_add_permission(self, request):
        return self.has_assigned_perm(request.user, 'add')

    def has_delete_permission(self, request, obj=None):
        return self.has_assigned_perm(request.user, 'delete')

    def get_readonly_fields(self, request, obj=None):
        if self.has_assigned_perm(request.user, 'change'):
            return ()
        return ('competitor_type', 'tag', 'theme', 'display_order', 'description', 'is_active',
                'is_default', 'enable_notifications')

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
                        spreadsheet.import_team_season(league, form.cleaned_data['spreadsheet_url'],
                                                       form.cleaned_data['season_name'],
                                                       form.cleaned_data['season_tag'],
                                                       form.cleaned_data['rosters_only'],
                                                       form.cleaned_data['exclude_live_pairings'])
                        self.message_user(request, "Season imported.")
                    elif league.competitor_type == 'individual':
                        spreadsheet.import_lonewolf_season(league,
                                                           form.cleaned_data['spreadsheet_url'],
                                                           form.cleaned_data['season_name'],
                                                           form.cleaned_data['season_tag'],
                                                           form.cleaned_data['rosters_only'],
                                                           form.cleaned_data[
                                                               'exclude_live_pairings'])
                        self.message_user(request, "Season imported.")
                    else:
                        self.message_user(request,
                                          "League competitor type not supported for spreadsheet import")
                except spreadsheet.SpreadsheetNotFound:
                    self.message_user(request,
                                      "Spreadsheet not found. The service account may not have edit permissions.",
                                      messages.ERROR)
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

        pairings = LonePlayerPairing.objects.exclude(result='').exclude(white=None).exclude(
            black=None).filter(round__season__league=league) \
            .order_by('round__start_date').select_related('white', 'black', 'round').nocache()
        rows = []

        for p in pairings:
            rows.append({
                'forfeit': 'BOTH' if p.result == '0F-0F' else 'SELF' if p.result == '0F-1X' else 'DRAW' if p.result == '1/2Z-1/2Z' else 'OPP' if p.result == '1X-0F' else 'NO',
                'average_rating': (p.white_rating_display(league) + p.black_rating_display(
                    league)) / 2,
                'rating_delta': abs(
                    p.white_rating_display(league) - p.black_rating_display(league)),
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
                'average_rating': (p.white_rating_display(league) + p.black_rating_display(
                    league)) / 2,
                'rating_delta': abs(
                    p.white_rating_display(league) - p.black_rating_display(league)),
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


# -------------------------------------------------------------------------------
@admin.register(LeagueSetting)
class LeagueSettingAdmin(_BaseAdmin):
    list_display = ('__str__',)
    league_id_field = 'league_id'


# -------------------------------------------------------------------------------
@admin.register(SectionGroup)
class SectionGroupAdmin(_BaseAdmin):
    list_display = ('__str__', 'league')
    search_fields = ('name',)
    list_filter = ('league',)
    league_id_field = 'league_id'


# -------------------------------------------------------------------------------
@admin.register(Section)
class SectionAdmin(_BaseAdmin):
    list_display = ('__str__', 'season', 'min_rating', 'max_rating')
    search_fields = ('name', 'season__name')
    list_filter = ('season__league',)
    league_id_field = 'season__league_id'


# -------------------------------------------------------------------------------
@admin.register(Season)
class SeasonAdmin(_BaseAdmin):
    list_display = ('__str__', 'league',)
    list_display_links = ('__str__',)
    list_filter = ('league',)
    actions = ['update_board_order_by_rating', 'force_alternate_board_update', 'recalculate_scores',
               'verify_data', 'review_nominated_games', 'bulk_email', 'team_spam', 'mod_report',
               'manage_players', 'round_transition', 'simulate_tournament']
    league_id_field = 'league_id'

    def get_urls(self):
        urls = super(SeasonAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/manage_players/$',
                self.admin_site.admin_view(self.manage_players_view),
                name='manage_players'),
            url(r'^(?P<object_id>[0-9]+)/create_teams/$',
                self.admin_site.admin_view(self.create_teams_view),
                name='create_teams'),
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
            url(r'^(?P<object_id>[0-9]+)/team_spam/$',
                self.admin_site.admin_view(self.team_spam_view),
                name='team_spam'),
            url(r'^(?P<object_id>[0-9]+)/mod_report/$',
                self.admin_site.admin_view(self.mod_report_view),
                name='mod_report'),
            url(r'^(?P<object_id>[0-9]+)/pre_round_report/$',
                self.admin_site.admin_view(self.pre_round_report_view),
                name='pre_round_report'),
            url(r'^(?P<object_id>[0-9]+)/export_players/$',
                self.admin_site.admin_view(self.export_players_view),
                name='export_players'),
        ]
        return my_urls + urls

    def simulate_tournament(self, request, queryset):
        if not request.user.is_superuser:
            raise PermissionDenied
        if not settings.DEBUG and not settings.STAGING:
            self.message_user(request, 'Results can\'t be simulated in a live environment',
                              messages.ERROR)
            return
        if queryset.count() > 1:
            self.message_user(request, 'Results can only be simulated one season at a time',
                              messages.ERROR)
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
                self.message_user(request,
                                  '%d bad gamelinks for %s.' % (bad_gamelinks, season.name),
                                  messages.WARNING)
        self.message_user(request, 'Data verified.', messages.INFO)

    def review_nominated_games(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Nominated games can only be reviewed one season at a time.',
                              messages.ERROR)
            return
        return redirect('admin:review_nominated_games', object_id=queryset[0].pk)

    def review_nominated_games_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.review_nominated_games', season.league):
            raise PermissionDenied

        selections = GameSelection.objects.filter(season=season).order_by(
            'pairing__teamplayerpairing__board_number')
        nominations = GameNomination.objects.filter(season=season).order_by(
            'pairing__teamplayerpairing__board_number', 'date_created')

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

        selections = [(link_counts.get(s.game_link, 0), s, link_to_nom.get(s.game_link, None)) for s
                      in selections]
        nominations = [(link_counts.get(n.game_link, 0), n) for n in first_nominations if
                       n.game_link not in selected_links]

        if season.nominations_open:
            self.message_user(request,
                              'Nominations are still open. You should edit the season and close nominations before reviewing.',
                              messages.WARNING)

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

        GameSelection.objects.get_or_create(season=season, game_link=nom.game_link,
                                            defaults={'pairing': nom.pairing})

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
            self.message_user(request, 'Rounds can only be transitioned one season at a time.',
                              messages.ERROR)
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
            form = forms.RoundTransitionForm(season.league.competitor_type == 'team',
                                             round_to_close, round_to_open, season_to_close,
                                             request.POST)
            if form.is_valid():
                complete_round = 'round_to_close' in form.cleaned_data and form.cleaned_data[
                    'round_to_close'] == round_to_close.number \
                                 and form.cleaned_data['complete_round']
                complete_season = 'complete_season' in form.cleaned_data and form.cleaned_data[
                    'complete_season']
                update_board_order = 'round_to_open' in form.cleaned_data and form.cleaned_data[
                    'round_to_open'] == round_to_open.number \
                                     and 'update_board_order' in form.cleaned_data and \
                                     form.cleaned_data['update_board_order']
                generate_pairings = 'round_to_open' in form.cleaned_data and form.cleaned_data[
                    'round_to_open'] == round_to_open.number \
                                    and form.cleaned_data['generate_pairings']

                msg_list = workflow.run(complete_round=complete_round,
                                        complete_season=complete_season,
                                        update_board_order=update_board_order,
                                        generate_pairings=generate_pairings)

                for text, level in msg_list:
                    self.message_user(request, text, level)

                if generate_pairings:
                    return redirect('admin:review_pairings', round_to_open.pk)
                else:
                    return redirect('admin:tournament_season_changelist')
        else:
            form = forms.RoundTransitionForm(season.league.competitor_type == 'team',
                                             round_to_close, round_to_open, season_to_close)

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
            self.message_user(request, 'Emails can only be sent one season at a time.',
                              messages.ERROR)
            return
        return redirect('admin:bulk_email', object_id=queryset[0].pk)

    def bulk_email_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.bulk_email', season.league):
            raise PermissionDenied

        if request.method == 'POST':
            form = forms.BulkEmailForm(season.seasonplayer_set.count(), request.POST)
            if form.is_valid() and form.cleaned_data['confirm_send']:
                season_players = season.seasonplayer_set.all()
                email_addresses = {sp.player.email for sp in season_players if
                                   sp.player.email != ''}
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
                self.message_user(request, 'Emails sent to %d players.' % len(season_players),
                                  messages.INFO)
                return redirect('admin:tournament_season_changelist')
        else:
            form = forms.BulkEmailForm(season.seasonplayer_set.count())

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': season,
            'title': 'Bulk email',
            'form': form
        }

        return render(request, 'tournament/admin/bulk_email.html', context)

    def team_spam(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Team spam can only be sent one season at a time.',
                              messages.ERROR)
            return
        return redirect('admin:team_spam', object_id=queryset[0].pk)

    def team_spam_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.bulk_email', season.league):
            raise PermissionDenied

        if request.method == 'POST':
            form = forms.TeamSpamForm(season, request.POST)
            if form.is_valid() and form.cleaned_data['confirm_send']:
                teams = season.team_set.all()
                for t in teams:
                    if t.slack_channel:
                        slackapi.send_message(t.slack_channel, form.cleaned_data['text'])
                        time.sleep(1)
                self.message_user(request, 'Spam sent to %d teams.' % len(teams), messages.INFO)
                return redirect('admin:tournament_season_changelist')
        else:
            form = forms.TeamSpamForm(season)

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': season,
            'title': 'Team spam',
            'form': form
        }

        return render(request, 'tournament/admin/team_spam.html', context)

    def mod_report(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Can only generate mod report one season at a time.',
                              messages.ERROR)
            return
        return redirect('admin:mod_report', object_id=queryset[0].pk)

    def mod_report_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.change_season', season.league):
            raise PermissionDenied

        season_players = season.seasonplayer_set.select_related('player').nocache()
        players = []
        for sp in season_players:
            games = (PlayerPairing.objects.filter(white=sp.player) | PlayerPairing.objects.filter(
                black=sp.player)).nocache()
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

    def pre_round_report(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Can only generate pre-round report one season at a time.',
                              messages.ERROR)
            return
        return redirect('admin:pre_round_report', object_id=queryset[0].pk)

    def pre_round_report_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.change_season', season.league):
            raise PermissionDenied

        last_round = Round.objects.filter(season=season, publish_pairings=True,
                                          is_completed=False).order_by('number').first()
        next_round = Round.objects.filter(season=season, publish_pairings=False,
                                          is_completed=False).order_by('number').first()

        season_players = season.seasonplayer_set.select_related('player').nocache()
        active_players = {sp.player for sp in season_players if sp.is_active}
        withdrawn_players = {wd.player for wd in PlayerWithdrawal.objects.filter(round=next_round)}
        continuation_players = {mr.requester for mr in ModRequest.objects.filter(round=next_round,
                                                                                 type='request_continuation',
                                                                                 status='approved')}
        red_cards = {sp.player for sp in season_players if
                     sp.is_active and sp.games_missed >= 2} - withdrawn_players

        missing_withdrawals = None
        pairings_wo_results = None

        pending_regs = [(reg.lichess_username, reg) for reg in
                        Registration.objects.filter(season=season, status='pending')]

        bad_player_status = [p for p in (active_players - withdrawn_players) if
                             p.account_status != 'normal']

        latereg_list = PlayerLateRegistration.objects.filter(round=next_round)
        not_on_slack = [(lr.player, lr, (timezone.now() - lr.date_created).days) for lr in
                        latereg_list if not lr.player.slack_user_id]
        not_on_slack += [(p, None, None) for p in active_players if not p.slack_user_id]

        pending_mod_reqs = ModRequest.objects.filter(season=season, status='pending')

        if last_round is not None:
            players_with_0f = set()
            for p in last_round.pairings:
                if p.result != '' and not p.game_played():
                    if p.black_score() == 0:
                        players_with_0f.add(p.black)
                    if p.white_score() == 0:
                        players_with_0f.add(p.white)
            missing_withdrawals = sorted(
                (players_with_0f & active_players) - withdrawn_players - continuation_players)

            def text_class(p):
                if p.game_link != '':
                    return 'text-approved'
                if p.scheduled_time and p.scheduled_time < timezone.now() - timedelta(hours=1):
                    return 'text-rejected'
                return ''

            pairings_wo_results = [(p, text_class(p)) for p in last_round.pairings.order_by(
                'loneplayerpairing__pairing_order').filter(result='')]

        ct_pairing = ContentType.objects.get_for_model(PlayerPairing)
        ct_season_player = ContentType.objects.get_for_model(SeasonPlayer)

        def with_round_info(player_list):
            """Annotates a player record with their pairing and comments
            """
            if not player_list:
                return None
            retval = []

            for player in player_list:
                pairing = LonePlayerPairing.objects.filter(Q(white=player) | Q(black=player),
                                                        round=last_round).first()
                season_player = SeasonPlayer.objects.get(player=player, season=season)
                comments = list(Comment.objects.filter(
                    (Q(content_type=ct_pairing) & Q(object_pk=pairing.pk)) |
                    (Q(content_type=ct_season_player) & Q(object_pk=season_player.pk))
                ))
                retval.append((player, pairing, comments))
            return retval

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': season,
            'title': 'Pre-round report',
            'last_round': last_round,
            'next_round': next_round,
            'missing_withdrawals': with_round_info(missing_withdrawals),
            'red_cards': with_round_info(sorted(red_cards)),
            'bad_player_status': sorted(
                bad_player_status) if bad_player_status is not None else None,
            'not_on_slack': sorted(not_on_slack) if not_on_slack is not None else None,
            'pending_mod_reqs': pending_mod_reqs,
            'pending_regs': sorted(pending_regs, key=lambda x: x[
                0].lower()) if pending_regs is not None else None,
            'pairings_wo_results': pairings_wo_results
        }

        return render(request, 'tournament/admin/pre_round_report.html', context)

    def export_players_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.change_season', season.league):
            raise PermissionDenied

        players = season.export_players()
        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': season,
            'title': 'Export players',
            'players': json.dumps(players)
        }

        return render(request, 'tournament/admin/export_players.html', context)

    def update_board_order_by_rating(self, request, queryset):
        try:
            for season in queryset.all():
                if not request.user.has_perm('tournament.manage_players', season.league):
                    raise PermissionDenied
                UpdateBoardOrderWorkflow(season).run(alternates_only=False)
            self.message_user(request, 'Board order updated.', messages.INFO)
        except IndexError:
            self.message_user(request, 'Error updating board order.', messages.ERROR)

    def force_alternate_board_update(self, request, queryset):
        try:
            for season in queryset.all():
                if not request.user.has_perm('tournament.manage_players', season.league):
                    raise PermissionDenied
                UpdateBoardOrderWorkflow(season).run(alternates_only=True)
            self.message_user(request, 'Alternate order updated.', messages.INFO)
        except IndexError:
            self.message_user(request, 'Error updating alternate order.', messages.ERROR)

    def manage_players(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Players can only be managed one season at a time.',
                              messages.ERROR)
            return
        return redirect('admin:manage_players', object_id=queryset[0].pk)

    def player_info_view(self, request, object_id, player_name):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm('tournament.manage_players', season.league):
            raise PermissionDenied
        season_player = get_object_or_404(SeasonPlayer, season=season,
                                          player__lichess_username=player_name)
        player = season_player.player

        reg = season_player.registration
        if player.games_played is not None:
            has_played_20_games = not player.provisional_for(season.league)
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

    def create_teams_view(self, request, object_id):
        def insert_teams(teams):
            for team_number, team in enumerate(teams, 1):
                team_instance = Team.objects.create(season=season,
                                                    number=team_number,
                                                    name=f'Team {team_number}')
                for board_number, board in enumerate(team.boards, 1):
                    player = Player.objects.get(lichess_username=board.name)
                    TeamMember.objects.create(team=team_instance,
                                              player=player,
                                              board_number=board_number)

        def insert_alternates(alts_split):
            for board_number, board in enumerate(alts_split, 1):
                for player in board:
                    season_player = (SeasonPlayer.objects
                                     .get(season=season,
                                          player__lichess_username__iexact=player.name))
                    Alternate.objects.create(season_player=season_player,
                                             board_number=board_number)

        season = get_object_or_404(Season, pk=object_id)
        season_started = Round.objects.filter(season=season, publish_pairings=True).exists()
        if season_started:
            return HttpResponse(status=400)
        team_count = Team.objects.filter(season=season).count()
        if request.method == 'POST':
            form = forms.CreateTeamsForm(team_count, request.POST)
            if form.is_valid():
                player_data = [p for p in season.export_players() if p['date_created']]
                league = teamgen.get_best_league(player_data,
                                                 season.boards,
                                                 form.cleaned_data['balance'],
                                                 form.cleaned_data['count'])

                with reversion.create_revision():
                    reversion.set_user(request.user)
                    reversion.set_comment('Create teams')

                    Team.objects.filter(season=season).delete()
                    insert_teams(league['teams'])

                    Alternate.objects.filter(season_player__season=season).delete()
                    insert_alternates(league['alts_split'])

                return redirect('admin:manage_players', object_id)

        else:
            form = forms.CreateTeamsForm(team_count)

        context = {
            'opts': self.model._meta,
            'season': season,
            'form': form,
            'season_started': season_started
        }
        return render(request, 'tournament/admin/create_teams.html', context)

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
        teams_locked = Round.objects.filter(season=season, publish_pairings=True).exists()

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

                for _, team_changes in list(changes_by_team_number.items()):
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

                                    teammember = TeamMember.objects.filter(team=team,
                                                                           board_number=board_num).first()
                                    original_teammember = str(teammember)
                                    if teammember == None:
                                        teammember = TeamMember(team=team, board_number=board_num)
                                    if player_info is None:
                                        teammember.delete()
                                        teammember = None
                                    else:
                                        teammember.player = Player.objects.get(
                                            lichess_username=player_info['name'])
                                        teammember.is_captain = player_info['is_captain']
                                        teammember.is_vice_captain = player_info['is_vice_captain']
                                        teammember.save()

                                    change_descriptions.append(
                                        'changed board %d from "%s" to "%s"' % (
                                        board_num, original_teammember, teammember))

                                if change['action'] == 'change-team' and not teams_locked:
                                    team_num = change['team_number']
                                    team = Team.objects.get(season=season, number=team_num)

                                    team_name = change['team_name']
                                    team.name = team_name
                                    team.save()

                                    change_descriptions.append(
                                        'changed team name to "%s"' % team_name)

                                if change['action'] == 'create-team' and not teams_locked:
                                    model = change['model']
                                    team = Team.objects.create(season=season,
                                                               number=model['number'],
                                                               name=model['name'])

                                    for board_num, player_info in enumerate(model['boards'], 1):
                                        if player_info is not None:
                                            player = Player.objects.get(
                                                lichess_username=player_info['name'])
                                            is_captain = player_info['is_captain']
                                            with reversion.create_revision():
                                                TeamMember.objects.create(team=team, player=player,
                                                                          board_number=board_num,
                                                                          is_captain=is_captain)

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
                                season_player = (SeasonPlayer.objects
                                                 .get(season=season,
                                                      player__lichess_username__iexact=change[
                                                          'player_name']))
                                (Alternate.objects
                                 .update_or_create(season_player=season_player,
                                                   defaults={'board_number': board_num}))

                        if change['action'] == 'delete-alternate':
                            with reversion.create_revision():
                                reversion.set_user(request.user)
                                reversion.set_comment('Edit rosters - deleted alternate.')

                                board_num = change['board_number']
                                season_player = (SeasonPlayer.objects
                                                 .get(season=season,
                                                      player__lichess_username__iexact=change[
                                                          'player_name']))
                                alt = (Alternate.objects
                                       .filter(season_player=season_player, board_number=board_num)
                                       .first())
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
            self.message_user(request, 'Number of boards must be specified for %s' % season.name,
                              messages.ERROR)
            return redirect('admin:tournament_season_changelist')
        board_numbers = list(range(1, season.boards + 1))
        teams = list(Team.objects.filter(season=season).order_by('number').prefetch_related(
            Prefetch('teammember_set',
                     queryset=TeamMember.objects.select_related('player').nocache())
        ).nocache())
        team_members = TeamMember.objects.filter(team__season=season).select_related(
            'player').nocache()
        alternates = Alternate.objects.filter(season_player__season=season).select_related(
            'season_player__player').nocache()
        alternates_by_board = [(n, sorted(
            alternates.filter(board_number=n).select_related(
                'season_player__registration').nocache(),
            key=lambda alt: alt.priority_date()
        )) for n in board_numbers]

        season_player_objs = SeasonPlayer.objects.filter(season=season,
                                                         is_active=True).select_related('player',
                                                                                        'registration').nocache()
        season_players = set(sp.player for sp in season_player_objs)
        team_players = set(tm.player for tm in team_members)
        alternate_players = set(alt.season_player.player for alt in alternates)
        old_alternates = season.last_season_alternates()

        alternate_buckets = list(AlternateBucket.objects.filter(season=season))
        unassigned_players = list(sorted(season_players - team_players - alternate_players,
                                         key=lambda p: p.rating_for(league), reverse=True))
        if len(alternate_buckets) == season.boards:
            # Sort unassigned players by alternate buckets
            unassigned_by_board = [(n, [p for p in unassigned_players if
                                        find(alternate_buckets, board_number=n).contains(
                                            p.rating_for(league))]) for n in board_numbers]
        else:
            # Season doesn't have buckets yet. Sort by player soup
            sorted_players = list(
                sorted((p for p in season_players if p.rating_for(league) is not None),
                       key=lambda p: p.rating_for(league), reverse=True))
            player_count = len(sorted_players)
            unassigned_by_board = [(n, []) for n in board_numbers]
            if player_count > 0:
                max_ratings = [(n, sorted_players[
                    len(sorted_players) * (n - 1) // season.boards].rating_for(league)) for n in
                               board_numbers]
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
            if sp.player.provisional_for(league):
                red_players.add(sp.player)
            if not sp.player.slack_user_id:
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
        season_started = Round.objects.filter(season=season, publish_pairings=True).exists()

        context = {
            'season_started': season_started,
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
        if teams:
            context.update({
                'team_rating_variance': team_rating_variance(teams, False),
                'team_rating_range': team_rating_range(teams, False),
                'team_expected_rating_variance': team_rating_variance(teams, True),
                'team_expected_rating_range': team_rating_range(teams, True),
            })
        return render(request, 'tournament/admin/edit_rosters.html', context)

    def lone_manage_players_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)

        active_players = SeasonPlayer.objects.filter(season=season, is_active=True).order_by(
            'player__lichess_username')
        inactive_players = SeasonPlayer.objects.filter(season=season, is_active=False).order_by(
            'player__lichess_username')

        projected_active = {sp.player for sp in active_players}

        def get_data(r):
            regs = r.playerlateregistration_set.order_by('player__lichess_username')
            wds = r.playerwithdrawal_set.order_by('player__lichess_username')

            if not r.publish_pairings:
                for reg in regs:
                    projected_active.add(reg.player)
                for wd in wds:
                    try:
                        projected_active.remove(wd.player)
                    except KeyError:
                        pass

            byes = r.playerbye_set.order_by('player__lichess_username')
            players_with_byes = {b.player for b in byes}

            def show(avail):
                return avail.player in projected_active and avail.player not in players_with_byes

            unavailables = [avail for avail in
                            r.playeravailability_set.filter(is_available=False).order_by(
                                'player__lichess_username') if show(avail)]

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
            self.message_user(request, 'Pairings can only be generated one round at a time',
                              messages.ERROR)
            return
        return redirect('admin:generate_pairings', object_id=queryset[0].pk)

    def simulate_results(self, request, queryset):
        if not settings.DEBUG and not settings.STAGING:
            self.message_user(request, 'Results can\'t be simulated in a live environment',
                              messages.ERROR)
            return
        if queryset.count() > 1:
            self.message_user(request, 'Results can only be simulated one round at a time',
                              messages.ERROR)
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
                        signals.do_generate_pairings.send(sender=self.__class__, round_id=round_.pk,
                                                          overwrite=form.cleaned_data[
                                                              'overwrite_existing'])
                        self.message_user(request, 'Generating pairings in background.',
                                          messages.INFO)
                        return redirect('admin:review_pairings', object_id)
                    else:
                        pairinggen.generate_pairings(round_, overwrite=form.cleaned_data[
                            'overwrite_existing'])
                        with reversion.create_revision():
                            reversion.set_user(request.user)
                            reversion.set_comment('Generated pairings.')
                            round_.publish_pairings = False
                            round_.save()

                        self.message_user(request, 'Pairings generated.', messages.INFO)
                        return redirect('admin:review_pairings', object_id)
                except pairinggen.PairingsExistException:
                    if not round_.publish_pairings:
                        self.message_user(request, 'Unpublished pairings already exist.',
                                          messages.WARNING)
                        return redirect('admin:review_pairings', object_id)
                    self.message_user(request, 'Pairings already exist for the selected round.',
                                      messages.ERROR)
                except pairinggen.PairingHasResultException:
                    self.message_user(request, 'Pairings with results can\'t be overwritten.',
                                      messages.ERROR)
                except pairinggen.PairingGenerationException as e:
                    self.message_user(request, 'Error generating pairings. %s' % e.message,
                                      messages.ERROR)
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
                    signals.do_schedule_publish.send(sender=self, round_id=round_.id,
                                                     eta=timezone.now())
                    self.message_user(request, 'Pairings published.', messages.INFO)
                elif 'schedule' in form.data:
                    publish_time = max(round_.start_date, timezone.now())
                    signals.do_schedule_publish.send(sender=self, round_id=round_.id,
                                                     eta=publish_time)
                    self.message_user(request,
                                      'Pairings scheduled to be published in %d minutes.' % (
                                              (publish_time - timezone.now()).total_seconds() / 60),
                                      messages.INFO)
                elif 'delete' in form.data:
                    try:
                        # Note: no reversion required for deleting things
                        pairinggen.delete_pairings(round_)
                        self.message_user(request, 'Pairings deleted.', messages.INFO)
                    except pairinggen.PairingHasResultException:
                        self.message_user(request, 'Pairings with results can\'t be deleted.',
                                          messages.ERROR)
                return redirect('admin:tournament_round_changelist')
        else:
            form = forms.ReviewPairingsForm()

        if round_.season.league.competitor_type == 'team':
            team_pairings = round_.teampairing_set.order_by('pairing_order')
            pairing_lists = [team_pairing.teamplayerpairing_set.order_by('board_number').nocache()
                             for team_pairing in team_pairings]
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
            duplicate_players = {k for k, v in list(player_refcounts.items()) if v > 1}

            active_players = {sp.player for sp in
                              SeasonPlayer.objects.filter(season=round_.season, is_active=True)}

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


# -------------------------------------------------------------------------------
@admin.register(PlayerLateRegistration)
class PlayerLateRegistrationAdmin(_BaseAdmin):
    list_display = ('__str__', 'retroactive_byes', 'late_join_points')
    search_fields = ('player__lichess_username',)
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('round', 'player')
    actions = ['refresh_fields', 'move_to_next_round']
    league_id_field = 'round__season__league_id'
    league_competitor_type = 'individual'

    def get_urls(self):
        urls = super(PlayerLateRegistrationAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/move_latereg/$',
                self.admin_site.admin_view(self.move_latereg_view),
                name='move_latereg'),
        ]
        return my_urls + urls

    def refresh_fields(self, request, queryset):
        for reg in queryset.all():
            wf = RefreshLateRegWorkflow(reg)
            wf.run()
        self.message_user(request, 'Fields updated.', messages.INFO)
        return redirect('admin:tournament_playerlateregistration_changelist')

    def move_to_next_round(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Late registrations can only be moved one at a time.',
                              messages.ERROR)
            return
        return redirect('admin:move_latereg', object_id=queryset[0].pk)

    def move_latereg_view(self, request, object_id):
        reg = get_object_or_404(PlayerLateRegistration, pk=object_id)
        if not request.user.has_perm('tournament.change_playerlateregistration',
                                     reg.round.season.league):
            raise PermissionDenied

        workflow = MoveLateRegWorkflow(reg)

        if request.method == 'POST':
            form = forms.MoveLateRegForm(request.POST, reg=reg)
            if form.is_valid():
                update_fields = form.cleaned_data['update_fields']
                prev_round = form.cleaned_data['prev_round']
                if prev_round == reg.round.number:
                    workflow.run(update_fields)
                    reg.refresh_from_db()
                    self.message_user(request, 'Late reg moved to round %d.' % (reg.round.number),
                                      messages.INFO)
                return redirect('admin:tournament_playerlateregistration_changelist')
        else:
            form = forms.MoveLateRegForm(reg=reg)

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': reg,
            'title': 'Move late registration',
            'form': form,
            'next_round': workflow.next_round
        }

        return render(request, 'tournament/admin/move_latereg.html', context)


# -------------------------------------------------------------------------------
@admin.register(PlayerWithdrawal)
class PlayerWithdrawalAdmin(_BaseAdmin):
    list_display = ('__str__',)
    search_fields = ('player__lichess_username',)
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('round', 'player')
    league_id_field = 'round__season__league_id'
    league_competitor_type = 'individual'


# -------------------------------------------------------------------------------
@admin.register(PlayerBye)
class PlayerByeAdmin(_BaseAdmin):
    list_display = ('__str__', 'type')
    search_fields = ('player__lichess_username',)
    list_filter = ('round__season', 'round__number', 'type')
    raw_id_fields = ('round', 'player')
    exclude = ('player_rating',)
    league_id_field = 'round__season__league_id'
    league_competitor_type = 'individual'


# -------------------------------------------------------------------------------
@admin.register(PlayerWarning)
class PlayerWarningAdmin(_BaseAdmin):
    list_display = ('__str__', 'type')
    search_fields = ('player__lichess_username',)
    list_filter = ('round__season', 'round__number', 'type')
    raw_id_fields = ('round', 'player')
    league_id_field = 'round__season__league_id'
    league_competitor_type = 'individual'


# -------------------------------------------------------------------------------
@admin.register(Player)
class PlayerAdmin(_BaseAdmin):
    search_fields = ('lichess_username', 'email', 'slack_user_id')
    list_filter = ('is_active',)
    readonly_fields = (
    'rating', 'games_played', 'slack_user_id', 'timezone_offset', 'account_status')
    exclude = ('profile', 'oauth_token')
    actions = ['update_selected_player_ratings']

    def has_delete_permission(self, request, obj=None):
        # Don't let unprivileged users delete players
        return self.has_assigned_perm(request.user, 'delete')

    def get_readonly_fields(self, request, obj=None):
        fields = []
        if not request.user.has_perm('tournament.change_player_details'):
            fields += ('lichess_username', 'email', 'is_active')
        fields += ['rating', 'games_played']
        if not request.user.has_perm('tournament.link_slack'):
            fields += ['slack_user_id']
        fields += ['timezone_offset', 'account_status']
        return fields

    def update_selected_player_ratings(self, request, queryset):
        #         try:
        usernames = [p.lichess_username for p in queryset.all()]
        for user_meta in lichessapi.enumerate_user_metas(usernames, priority=1):
            p = Player.objects.get(lichess_username__iexact=user_meta['id'])
            p.update_profile(user_meta)
        self.message_user(request, 'Rating(s) updated', messages.INFO)

    #         except:
    #             self.message_user(request, 'Error updating rating(s) from lichess API', messages.ERROR)

    def related_objects_for_comments(self, request, object_id):
        sps = SeasonPlayer.objects.filter(player_id=object_id,
                                          season__league_id__in=self.authorized_leagues(
                                              request.user)) \
            .select_related('season').nocache()
        return [(sp.season.name, sp) for sp in sps]


# -------------------------------------------------------------------------------
@admin.register(LeagueModerator)
class LeagueModeratorAdmin(_BaseAdmin):
    list_display = ('__str__', 'is_active', 'send_contact_emails')
    search_fields = ('player__lichess_username',)
    list_filter = ('league',)
    raw_id_fields = ('player',)
    league_id_field = 'league_id'


# -------------------------------------------------------------------------------
class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 0
    ordering = ('board_number',)
    raw_id_fields = ('player',)
    exclude = ('player_rating',)


# -------------------------------------------------------------------------------
@admin.register(Team)
class TeamAdmin(_BaseAdmin):
    list_display = ('name', 'season')
    search_fields = ('name',)
    list_filter = ('season',)
    inlines = [TeamMemberInline]
    actions = ['update_board_order_by_rating', 'create_slack_channels']
    league_id_field = 'season__league_id'
    league_competitor_type = 'team'

    def update_board_order_by_rating(self, request, queryset):
        for team in queryset.all():
            if not request.user.has_perm('tournament.manage_players', team.season.league):
                raise PermissionDenied
            members = team.teammember_set.order_by('-player__rating')
            for i in range(len(members)):
                members[i].board_number = i + 1
                members[i].save()
        self.message_user(request, 'Board order updated', messages.INFO)

    def create_slack_channels(self, request, queryset):
        team_ids = []
        skipped = 0
        for team in queryset.select_related('season').nocache():
            if not team.season.is_active or team.season.is_completed:
                self.message_user(request,
                                  'The team season must be active and not completed in order to create channels.',
                                  messages.ERROR)
                return
            if len(team.season.tag) > 3:
                self.message_user(request, 'The team season tag is too long to create a channel.',
                                  messages.ERROR)
                return
            if team.slack_channel == '':
                team_ids.append(team.pk)
            else:
                skipped += 1
        signals.do_create_team_channel.send(sender=self, team_ids=team_ids)
        self.message_user(request, 'Creating %d channels. %d skipped.' % (len(team_ids), skipped),
                          messages.INFO)


# -------------------------------------------------------------------------------
@admin.register(TeamMember)
class TeamMemberAdmin(_BaseAdmin):
    list_display = ('__str__', 'team')
    search_fields = ('team__name', 'player__lichess_username')
    list_filter = ('team__season',)
    raw_id_fields = ('player',)
    exclude = ('player_rating',)
    league_id_field = 'team__season__league_id'
    league_competitor_type = 'team'


# -------------------------------------------------------------------------------
@admin.register(TeamScore)
class TeamScoreAdmin(_BaseAdmin):
    list_display = ('team', 'match_points', 'game_points')
    search_fields = ('team__name',)
    list_filter = ('team__season',)
    raw_id_fields = ('team',)
    league_id_field = 'team__season__league_id'
    league_competitor_type = 'team'


# -------------------------------------------------------------------------------
@admin.register(Alternate)
class AlternateAdmin(_BaseAdmin):
    list_display = ('__str__', 'board_number', 'status')
    search_fields = ('season_player__player__lichess_username',)
    list_filter = ('season_player__season', 'board_number', 'status')
    raw_id_fields = ('season_player',)
    exclude = ('player_rating',)
    league_id_field = 'season_player__season__league_id'
    league_competitor_type = 'team'


# -------------------------------------------------------------------------------
@admin.register(AlternateAssignment)
class AlternateAssignmentAdmin(_BaseAdmin):
    list_display = ('__str__', 'player')
    search_fields = ('team__name', 'player__lichess_username')
    list_filter = ('round__season', 'round__number', 'board_number')
    raw_id_fields = ('round', 'team', 'player', 'replaced_player')
    league_id_field = 'round__season__league_id'
    league_competitor_type = 'team'


# -------------------------------------------------------------------------------
@admin.register(AlternateBucket)
class AlternateBucketAdmin(_BaseAdmin):
    list_display = ('__str__', 'season')
    search_fields = ()
    list_filter = ('season', 'board_number')
    league_id_field = 'season__league_id'
    league_competitor_type = 'team'


# -------------------------------------------------------------------------------
@admin.register(AlternateSearch)
class AlternateSearchAdmin(_BaseAdmin):
    list_display = ('__str__', 'status')
    search_fields = ('team__name',)
    list_filter = ('round__season', 'round__number', 'board_number', 'status')
    league_id_field = 'round__season__league_id'
    league_competitor_type = 'team'


# -------------------------------------------------------------------------------
@admin.register(AlternatesManagerSetting)
class AlternatesManagerSettingAdmin(_BaseAdmin):
    list_display = ('__str__',)
    league_id_field = 'league_id'
    league_competitor_type = 'team'


# -------------------------------------------------------------------------------
@admin.register(TeamPairing)
class TeamPairingAdmin(_BaseAdmin):
    list_display = ('white_team_name', 'black_team_name', 'season_name', 'round_number')
    search_fields = ('white_team__name', 'black_team__name')
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('white_team', 'black_team', 'round')
    league_id_field = 'round__season__league_id'
    league_competitor_type = 'team'


# -------------------------------------------------------------------------------
class PlayerPresenceInline(admin.TabularInline):
    model = PlayerPresence
    extra = 0
    exclude = ('round', 'player')
    readonly_fields = ('first_msg_time', 'last_msg_time', 'online_for_game')
    can_delete = False
    max_num = 0


# -------------------------------------------------------------------------------
@admin.register(PlayerPairing)
class PlayerPairingAdmin(_BaseAdmin):
    list_display = ('__str__', 'scheduled_time', 'game_link_url')
    search_fields = ('white__lichess_username', 'black__lichess_username', 'game_link')
    raw_id_fields = ('white', 'black')
    inlines = [PlayerPresenceInline]
    exclude = ('white_rating', 'black_rating', 'tv_state')
    actions = ['send_pairing_notification']

    def send_pairing_notification(self, request, queryset):
        count = 0
        for pairing in queryset.all():
            round_ = pairing.get_round()
            if round_ is not None:
                signals.notify_players_late_pairing.send(sender=self, round_=round_,
                                                         pairing=pairing)
                count += 1
        self.message_user(request, 'Notifications sent for %d pairings.' % count, messages.INFO)

    def get_queryset(self, request):
        queryset = super(_BaseAdmin, self).get_queryset(request)
        if self.has_assigned_perm(request.user, 'change'):
            return queryset
        return queryset.filter(
            teamplayerpairing__team_pairing__round__season__league_id__in=self.authorized_leagues(
                request.user)) \
               | queryset.filter(
            loneplayerpairing__round__season__league_id__in=self.authorized_leagues(request.user))

    def has_add_permission(self, request):
        return self.has_assigned_perm(request.user, 'add')

    def get_league_id(self, obj):
        if hasattr(obj, 'teamplayerpairing'):
            return obj.teamplayerpairing.team_pairing.round.season.league_id
        elif hasattr(obj, 'loneplayerpairing'):
            return obj.loneplayerpairing.round.season.league_id
        else:
            return None

    def has_league_perm(self, user, action, obj):
        if obj is None:
            return bool(self.authorized_leagues(user))
        else:
            return self.get_league_id(obj) in self.authorized_leagues(user)

    def clean_form(self, request, form):
        pass

    def game_link_url(self, obj):
        if not obj.game_link:
            return ''
        return format_html("<a href='{url}'>{url}</a>", url=obj.game_link)

    def related_objects_for_comments(self, request, object_id):
        related_objects = []
        related_objects += list(TeamPlayerPairing.objects.filter(id=object_id).nocache())
        related_objects += list(LonePlayerPairing.objects.filter(id=object_id).nocache())
        return related_objects


# -------------------------------------------------------------------------------
@admin.register(TeamPlayerPairing)
class TeamPlayerPairingAdmin(_BaseAdmin):
    list_display = ('__str__', 'team_pairing', 'board_number', 'game_link_url')
    search_fields = ('white__lichess_username', 'black__lichess_username',
                     'team_pairing__white_team__name', 'team_pairing__black_team__name',
                     'game_link')
    list_filter = ('team_pairing__round__season', 'team_pairing__round__number',)
    raw_id_fields = ('white', 'black', 'team_pairing')
    league_id_field = 'team_pairing__round__season__league_id'
    league_competitor_type = 'team'

    def game_link_url(self, obj):
        if not obj.game_link:
            return ''
        return format_html("<a href='{url}'>{url}</a>", url=obj.game_link)

    def related_objects_for_comments(self, request, object_id):
        return list(PlayerPairing.objects.filter(id=object_id).nocache())


# -------------------------------------------------------------------------------
@admin.register(LonePlayerPairing)
class LonePlayerPairingAdmin(_BaseAdmin):
    list_display = ('__str__', 'round', 'game_link_url')
    search_fields = ('white__lichess_username', 'black__lichess_username', 'game_link')
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('white', 'black', 'round')
    league_id_field = 'round__season__league_id'
    league_competitor_type = 'individual'

    def game_link_url(self, obj):
        if not obj.game_link:
            return ''
        return format_html("<a href='{url}'>{url}</a>", url=obj.game_link)

    def related_objects_for_comments(self, request, object_id):
        return list(PlayerPairing.objects.filter(id=object_id).nocache())


# -------------------------------------------------------------------------------
@admin.register(Registration)
class RegistrationAdmin(_BaseAdmin):
    list_display = (
    'review', 'email', 'status', 'valid', 'season', 'section', 'classical_rating', 'date_created')
    list_display_links = ()
    search_fields = ('lichess_username', 'email', 'season__name')
    list_filter = ('status', 'season', 'section_preference__name')
    actions = ('validate', 'approve')
    league_id_field = 'season__league_id'

    def changelist_view(self, request, extra_context=None):
        self.request = request
        return super(RegistrationAdmin, self).changelist_view(request, extra_context=extra_context)

    def section(self, obj):
        return obj.section_preference.name if obj.section_preference else ''

    def review(self, obj):
        _url = reverse('admin:review_registration',
                       args=[obj.pk]) + "?" + self.get_preserved_filters(self.request)
        return '<a href="%s"><b>%s</b></a>' % (_url, obj.lichess_username)

    review.allow_tags = True

    def edit(self, obj):
        return 'Edit'

    edit.allow_tags = True

    def valid(self, obj):
        if obj.validation_warning == True:
            return '<img src="%s">' % static('admin/img/icon-alert.svg')
        elif obj.validation_ok == True:
            return '<img src="%s">' % static('admin/img/icon-yes.svg')
        elif obj.validation_ok == False:
            return '<img src="%s">' % static('admin/img/icon-no.svg')
        return ''

    valid.allow_tags = True

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
            signals.do_validate_registration.send(sender=RegistrationAdmin, reg_id=reg.pk)
        self.message_user(request, 'Validation started.', messages.INFO)
        return redirect('admin:tournament_registration_changelist')

    def approve(self, request, queryset):
        if not request.user.has_perm('tournament.invite_to_slack'):
            self.message_user(request, 'You don\'t have permissions to invite users to slack.',
                              messages.ERROR)
            return redirect('admin:tournament_registration_changelist')
        count = 0
        for reg in queryset:
            if reg.status == 'pending' and reg.validation_ok and not reg.validation_warning:
                workflow = ApproveRegistrationWorkflow(reg)

                send_confirm_email = workflow.default_send_confirm_email
                invite_to_slack = workflow.default_invite_to_slack
                default_section = workflow.default_section
                if workflow.is_late:
                    retroactive_byes = workflow.default_byes
                    late_join_points = workflow.default_ljp
                else:
                    retroactive_byes = None
                    late_join_points = None

                workflow.approve_reg(request, None, send_confirm_email, invite_to_slack,
                                     default_section, retroactive_byes, late_join_points)
                count += 1

        self.message_user(request, '%d approved.' % count, messages.INFO)
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
                    return redirect_with_params('admin:approve_registration', object_id=object_id,
                                                params=params)
                elif 'reject' in form.data and reg.status == 'pending':
                    return redirect_with_params('admin:reject_registration', object_id=object_id,
                                                params=params)
                elif 'edit' in form.data:
                    return redirect_with_params('admin:tournament_registration_change', object_id,
                                                params=params)
                else:
                    return redirect_with_params('admin:tournament_registration_changelist',
                                                params=params)
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
                    workflow = ApproveRegistrationWorkflow(reg)
                    workflow.approve_reg(
                        request,
                        self,
                        form.cleaned_data['send_confirm_email'],
                        form.cleaned_data['invite_to_slack'],
                        form.cleaned_data.get('section', reg.season),
                        form.cleaned_data.get('retroactive_byes'),
                        form.cleaned_data.get('late_join_points'))
                    return redirect_with_params('admin:tournament_registration_changelist',
                                                params='?' + changelist_filters)
                else:
                    return redirect_with_params('admin:review_registration', object_id,
                                                params='?_changelist_filters=' + urlquote(
                                                    changelist_filters))
        else:
            changelist_filters = request.GET.get('_changelist_filters', '')
            form = forms.ApproveRegistrationForm(registration=reg)

        next_round = Round.objects.filter(season=reg.season, publish_pairings=False).order_by(
            'number').first()

        mod = LeagueModerator.objects.filter(
            player__lichess_username__iexact=reg.lichess_username).first()
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

                    self.message_user(request,
                                      'Registration for "%s" rejected.' % reg.lichess_username,
                                      messages.INFO)
                    return redirect_with_params('admin:tournament_registration_changelist',
                                                params='?' + changelist_filters)
                else:
                    return redirect('admin:review_registration', object_id)
                    return redirect_with_params('admin:review_registration', object_id,
                                                params='?_changelist_filters=' + urlquote(
                                                    changelist_filters))
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


class InSlackFilter(SimpleListFilter):
    title = 'is in slack'
    parameter_name = 'player__slack_user_id'

    def lookups(self, request, model_admin):
        return (
            ('1', 'Yes',),
            ('0', 'No',),
        )

    def queryset(self, request, queryset):
        if self.value() == '0':
            return queryset.filter(player__slack_user_id='')
        if self.value() == '1':
            return queryset.exclude(player__slack_user_id='')
        return queryset


# -------------------------------------------------------------------------------
@admin.register(SeasonPlayer)
class SeasonPlayerAdmin(_BaseAdmin):
    list_display = ('player', 'season', 'is_active', 'in_slack')
    search_fields = ('season__name', 'player__lichess_username')
    list_filter = ('season__league', 'season', 'is_active', InSlackFilter)
    raw_id_fields = ('player', 'registration')
    league_id_field = 'season__league_id'
    actions = ['bulk_email', 'link_reminder']

    def in_slack(self, sp):
        return bool(sp.player.slack_user_id)

    in_slack.boolean = True

    def get_urls(self):
        urls = super(SeasonPlayerAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_ids>[0-9,]+)/bulk_email/$',
                self.admin_site.admin_view(self.bulk_email_view),
                name='bulk_email_by_players'),
        ]
        return my_urls + urls

    def link_reminder(self, request, queryset):
        slack_users = slackapi.get_user_list()
        by_email = {u.email: u.id for u in slack_users}

        for sp in queryset.filter(is_active=True, player__slack_user_id='').select_related(
            'player').nocache():
            uid = by_email.get(sp.player.email)
            if uid:
                token = LoginToken.objects.create(slack_user_id=uid,
                                                  username_hint=sp.player.lichess_username,
                                                  expires=timezone.now() + timedelta(days=30))
                url = reverse('by_league:login_with_token',
                              args=[sp.season.league.tag, token.secret_token])
                url = request.build_absolute_uri(url)
                text = 'Reminder: You need to link your Slack and Lichess accounts. <%s|Click here> to do that now. Contact a mod if you need help.' % url
                slackapi.send_message(uid, text)

        return redirect('admin:tournament_seasonplayer_changelist')

    def bulk_email(self, request, queryset):
        return redirect('admin:bulk_email_by_players',
                        object_ids=','.join((str(sp.id) for sp in queryset)))

    def bulk_email_view(self, request, object_ids):
        season_players = SeasonPlayer.objects.filter(
            id__in=[int(i) for i in object_ids.split(',')]).select_related('season',
                                                                           'player').nocache()
        seasons = {sp.season for sp in season_players}
        for season in seasons:
            if not request.user.has_perm('tournament.bulk_email', season.league):
                raise PermissionDenied

        if request.method == 'POST':
            form = forms.BulkEmailForm(len(season_players), request.POST)
            if form.is_valid() and form.cleaned_data['confirm_send']:
                email_addresses = {sp.player.email for sp in season_players if
                                   sp.player.email != ''}
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
                self.message_user(request, 'Emails sent to %d players.' % len(season_players),
                                  messages.INFO)
                return redirect('admin:tournament_seasonplayer_changelist')
        else:
            form = forms.BulkEmailForm(len(season_players))

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': 'Bulk email',
            'title': 'Bulk email',
            'form': form
        }

        return render(request, 'tournament/admin/bulk_email.html', context)


# -------------------------------------------------------------------------------
@admin.register(LonePlayerScore)
class LonePlayerScoreAdmin(_BaseAdmin):
    list_display = ('season_player', 'points', 'late_join_points')
    search_fields = ('season_player__season__name', 'season_player__player__lichess_username')
    list_filter = ('season_player__season',)
    raw_id_fields = ('season_player',)
    league_id_field = 'season_player__season__league_id'
    league_competitor_type = 'individual'


# -------------------------------------------------------------------------------
@admin.register(PlayerAvailability)
class PlayerAvailabilityAdmin(_BaseAdmin):
    list_display = ('player', 'round', 'is_available')
    search_fields = ('player__lichess_username',)
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('player', 'round')
    league_id_field = 'round__season__league_id'


# -------------------------------------------------------------------------------
@admin.register(SeasonPrize)
class SeasonPrizeAdmin(_BaseAdmin):
    list_display = ('season', 'rank', 'max_rating')
    search_fields = ('season__name',)
    league_id_field = 'season__league_id'


# -------------------------------------------------------------------------------
@admin.register(SeasonPrizeWinner)
class SeasonPrizeWinnerAdmin(_BaseAdmin):
    list_display = ('season_prize', 'player',)
    search_fields = ('season_prize__name', 'player__lichess_username')
    raw_id_fields = ('season_prize', 'player')
    league_id_field = 'season_prize__season__league_id'


# -------------------------------------------------------------------------------
@admin.register(GameNomination)
class GameNominationAdmin(_BaseAdmin):
    list_display = ('__str__',)
    search_fields = ('season__name', 'nominating_player__lichess_username')
    raw_id_fields = ('nominating_player', 'pairing')
    league_id_field = 'season__league_id'


# -------------------------------------------------------------------------------
@admin.register(GameSelection)
class GameSelectionAdmin(_BaseAdmin):
    list_display = ('__str__',)
    search_fields = ('season__name',)
    raw_id_fields = ('pairing',)
    league_id_field = 'season__league_id'


# -------------------------------------------------------------------------------
@admin.register(AvailableTime)
class AvailableTimeAdmin(_BaseAdmin):
    list_display = ('player', 'time', 'league')
    search_fields = ('player__lichess_username',)
    league_id_field = 'league_id'


# -------------------------------------------------------------------------------
@admin.register(NavItem)
class NavItemAdmin(_BaseAdmin):
    list_display = ('__str__', 'parent')
    search_fields = ('text',)
    league_id_field = 'league_id'


# -------------------------------------------------------------------------------
@admin.register(ApiKey)
class ApiKeyAdmin(_BaseAdmin):
    list_display = ('name',)
    search_fields = ('name',)


# -------------------------------------------------------------------------------
@admin.register(PrivateUrlAuth)
class PrivateUrlAuthAdmin(_BaseAdmin):
    list_display = ('__str__', 'expires')
    search_fields = ('authenticated_user',)


# -------------------------------------------------------------------------------
@admin.register(Document)
class DocumentAdmin(_BaseAdmin):
    list_display = ('name',)
    search_fields = ('name',)

    def get_queryset(self, request):
        queryset = super(_BaseAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return queryset
        filtered_queryset = queryset.filter(
            leaguedocument__league_id__in=self.authorized_leagues(request.user)) \
                            | queryset.filter(
            seasondocument__season__league_id__in=self.authorized_leagues(request.user)) \
                            | queryset.filter(owner=request.user)
        if self.has_assigned_perm(request.user, 'change'):
            filtered_queryset |= queryset.filter(allow_editors=True)
        return filtered_queryset

    def get_league_id(self, obj):
        if hasattr(obj, 'leaguedocument'):
            return obj.leaguedocument.league_id
        elif hasattr(obj, 'seasondocument'):
            return obj.seasondocument.season.league_id
        else:
            return None

    def has_league_perm(self, user, action, obj):
        if obj is None:
            return bool(self.authorized_leagues(user)) or Document.objects.filter(
                owner=user).exists()
        else:
            return user.is_superuser or obj.owned_by(user) \
                   or self.get_league_id(obj) in self.authorized_leagues(user) \
                   or action == 'change' and obj.allow_editors and self.has_assigned_perm(user,
                                                                                          'change')

    def has_change_permission(self, request, obj=None):
        return self.has_league_perm(request.user, 'change', obj)

    def get_changeform_initial_data(self, request):
        get_data = super(DocumentAdmin, self).get_changeform_initial_data(request)
        get_data['owner'] = request.user.pk
        return get_data

    def clean_form(self, request, form):
        pass

    def get_readonly_fields(self, request, obj=None):
        if obj is None or request.user.is_superuser or obj.owned_by(request.user):
            return ()
        return ('allow_editors', 'owner')


# -------------------------------------------------------------------------------
@admin.register(LeagueDocument)
class LeagueDocumentAdmin(_BaseAdmin):
    list_display = ('document', 'league', 'tag', 'type', 'url')
    search_fields = ('league__name', 'tag', 'document__name')
    league_id_field = 'league_id'

    def url(self, obj):
        _url = reverse('by_league:document', args=[obj.league.tag, obj.tag])
        return '<a href="%s">%s</a>' % (_url, _url)

    url.allow_tags = True


# -------------------------------------------------------------------------------
@admin.register(SeasonDocument)
class SeasonDocumentAdmin(_BaseAdmin):
    list_display = ('document', 'season', 'tag', 'type', 'url')
    search_fields = ('season__name', 'tag', 'document__name')
    league_id_field = 'season__league_id'

    def url(self, obj):
        _url = reverse('by_league:by_season:document',
                       args=[obj.season.league.tag, obj.season.tag, obj.tag])
        return '<a href="%s">%s</a>' % (_url, _url)

    url.allow_tags = True


# -------------------------------------------------------------------------------
@admin.register(LeagueChannel)
class LeagueChannelAdmin(_BaseAdmin):
    list_display = ('league', 'type', 'slack_channel')
    search_fields = ('league__name', 'slack_channel')
    league_id_field = 'league_id'


# -------------------------------------------------------------------------------
@admin.register(ScheduledEvent)
class ScheduledEventAdmin(_BaseAdmin):
    list_display = ('type', 'offset', 'relative_to', 'league', 'season')
    search_fields = ('league__name', 'season__name')
    league_id_field = 'league_id'


# -------------------------------------------------------------------------------
@admin.register(PlayerNotificationSetting)
class PlayerNotificationSettingAdmin(_BaseAdmin):
    list_display = ('player', 'type', 'league', 'offset', 'enable_lichess_mail', 'enable_slack_im',
                    'enable_slack_mpim')
    list_filter = ('league', 'type')
    search_fields = ('player__lichess_username',)
    raw_id_fields = ('player',)
    league_id_field = 'league_id'


# -------------------------------------------------------------------------------
@admin.register(ScheduledNotification)
class ScheduledNotificationAdmin(_BaseAdmin):
    list_display = ('setting', 'pairing', 'notification_time')
    list_filter = ('setting__type',)
    search_fields = ('player__lichess_username',)
    raw_id_fields = ('setting', 'pairing')
    league_id_field = 'setting__league_id'


# -------------------------------------------------------------------------------
@admin.register(ModRequest)
class ModRequestAdmin(_BaseAdmin):
    list_display = ('review', 'type', 'status', 'season', 'date_created')
    list_display_links = ()
    list_filter = ('status', 'type', 'season')
    search_fields = ('requester__lichess_username',)
    raw_id_fields = ('round', 'requester', 'pairing')
    league_id_field = 'season__league_id'

    def changelist_view(self, request, extra_context=None):
        self.request = request
        return super(ModRequestAdmin, self).changelist_view(request, extra_context=extra_context)

    def review(self, obj):
        _url = reverse('admin:tournament_modrequest_review',
                       args=[obj.pk]) + "?" + self.get_preserved_filters(self.request)
        return '<a href="%s"><b>%s</b></a>' % (_url, obj.requester.lichess_username)

    review.allow_tags = True

    def edit(self, obj):
        return 'Edit'

    edit.allow_tags = True

    def get_urls(self):
        urls = super(ModRequestAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/review/$',
                self.admin_site.admin_view(self.review_request),
                name='tournament_modrequest_review'),
            url(r'^(?P<object_id>[0-9]+)/approve/$',
                self.admin_site.admin_view(self.approve_request),
                name='tournament_modrequest_approve'),
            url(r'^(?P<object_id>[0-9]+)/reject/$',
                self.admin_site.admin_view(self.reject_request),
                name='tournament_modrequest_reject')
        ]
        return my_urls + urls

    def review_request(self, request, object_id):
        obj = get_object_or_404(ModRequest, pk=object_id)
        if not request.user.has_perm('tournament.change_modrequest', obj.season.league):
            raise PermissionDenied

        if request.method == 'POST':
            changelist_filters = request.POST.get('_changelist_filters', '')
            form = forms.ReviewModRequestForm(request.POST)
            if form.is_valid():
                params = '?_changelist_filters=' + urlquote(changelist_filters)
                if 'approve' in form.data and obj.status == 'pending':
                    return redirect_with_params('admin:tournament_modrequest_approve',
                                                object_id=object_id, params=params)
                elif 'reject' in form.data and obj.status == 'pending':
                    return redirect_with_params('admin:tournament_modrequest_reject',
                                                object_id=object_id, params=params)
                elif 'edit' in form.data:
                    return redirect_with_params('admin:tournament_modrequest_change', object_id,
                                                params=params)
                else:
                    return redirect_with_params('admin:tournament_modrequest_changelist',
                                                params=params)
        else:
            changelist_filters = request.GET.get('_changelist_filters', '')
            form = forms.ReviewModRequestForm()

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': obj,
            'title': 'Review mod request',
            'form': form,
            'changelist_filters': changelist_filters
        }

        return render(request, 'tournament/admin/review_modrequest.html', context)

    def approve_request(self, request, object_id):
        obj = get_object_or_404(ModRequest, pk=object_id)
        if not request.user.has_perm('tournament.change_modrequest', obj.season.league):
            raise PermissionDenied

        if obj.status != 'pending':
            return redirect('admin:tournament_modrequest_review', object_id)

        if request.method == 'POST':
            changelist_filters = request.POST.get('_changelist_filters', '')
            form = forms.ApproveModRequestForm(request.POST)
            if form.is_valid():
                if 'confirm' in form.data:
                    obj.approve(request.user.username, form.cleaned_data['response'])
                    self.message_user(request, 'Request approved.', messages.INFO)
                    return redirect_with_params('admin:tournament_modrequest_changelist',
                                                params='?' + changelist_filters)
                else:
                    return redirect_with_params('admin:tournament_modrequest_review', object_id,
                                                params='?_changelist_filters=' + urlquote(
                                                    changelist_filters))
        else:
            changelist_filters = request.GET.get('_changelist_filters', '')
            form = forms.ApproveModRequestForm()

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': obj,
            'title': 'Confirm approval',
            'form': form,
            'changelist_filters': changelist_filters
        }

        return render(request, 'tournament/admin/approve_modrequest.html', context)

    def reject_request(self, request, object_id):
        obj = get_object_or_404(ModRequest, pk=object_id)
        if not request.user.has_perm('tournament.change_modrequest', obj.season.league):
            raise PermissionDenied

        if obj.status != 'pending':
            return redirect('admin:tournament_modrequest_review', object_id)

        if request.method == 'POST':
            changelist_filters = request.POST.get('_changelist_filters', '')
            form = forms.RejectModRequestForm(request.POST)
            if form.is_valid():
                if 'confirm' in form.data:
                    obj.reject(request.user.username, form.cleaned_data['response'])
                    self.message_user(request, 'Request rejected.', messages.INFO)
                    return redirect_with_params('admin:tournament_registration_changelist',
                                                params='?' + changelist_filters)
                else:
                    return redirect_with_params('admin:tournament_modrequest_review', object_id,
                                                params='?_changelist_filters=' + urlquote(
                                                    changelist_filters))
        else:
            changelist_filters = request.GET.get('_changelist_filters', '')
            form = forms.RejectModRequestForm()

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': obj,
            'title': 'Confirm rejection',
            'form': form,
            'changelist_filters': changelist_filters
        }

        return render(request, 'tournament/admin/reject_modrequest.html', context)
