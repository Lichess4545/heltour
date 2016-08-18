from django.contrib import admin, messages
from django.utils import timezone
from heltour.tournament import models, lichessapi, slackapi, views, forms
from reversion.admin import VersionAdmin
from django.conf.urls import url
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import permission_required

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

# Customize which sections are visible
# admin.site.register(Comment)
admin.site.unregister(Site)

#-------------------------------------------------------------------------------
@admin.register(models.League)
class LeagueAdmin(VersionAdmin):
    actions = ['import_season']
    change_form_template = 'tournament/admin/change_form_with_comments.html'

    def get_urls(self):
        urls = super(LeagueAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/import_season/$',
                permission_required('tournament.change_league')(self.admin_site.admin_view(self.import_season_view)),
                name='import_season'),
        ]
        return my_urls + urls

    def import_season(self, request, queryset):
        return redirect('admin:import_season', object_id=queryset[0].pk)

    def import_season_view(self, request, object_id):
        league = models.League.objects.get(pk=object_id)

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

#-------------------------------------------------------------------------------
@admin.register(models.Season)
class SeasonAdmin(VersionAdmin):
    list_display = ('__unicode__', 'league',)
    list_display_links = ('__unicode__',)
    list_filter = ('league',)
    actions = ['update_board_order_by_rating', 'edit_rosters', 'round_transition']
    change_form_template = 'tournament/admin/change_form_with_comments.html'

    def get_urls(self):
        urls = super(SeasonAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/edit_rosters/$',
                permission_required('tournament.edit_rosters')(self.admin_site.admin_view(self.edit_rosters_view)),
                name='edit_rosters'),
            url(r'^(?P<object_id>[0-9]+)/player_info/(?P<player_name>[\w-]+)/$',
                permission_required('tournament.edit_rosters')(self.admin_site.admin_view(self.player_info_view)),
                name='edit_rosters_player_info'),
            url(r'^(?P<object_id>[0-9]+)/round_transition/$',
                permission_required('tournament.generate_pairings')(self.admin_site.admin_view(self.round_transition_view)),
                name='round_transition'),
        ]
        return my_urls + urls

    def round_transition(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Rounds can only be transitioned one season at a time.', messages.ERROR)
            return
        return redirect('admin:round_transition', object_id=queryset[0].pk)

    def round_transition_view(self, request, object_id):
        season = models.Season.objects.get(pk=object_id)

        round_to_close = season.round_set.filter(publish_pairings=True, is_completed=False).order_by('number').first()
        round_to_open = season.round_set.filter(publish_pairings=False, is_completed=False).order_by('number').first()

        season_to_close = season if not season.is_completed and round_to_open is None and (round_to_close is None or round_to_close.number == season.rounds) else None

        if request.method == 'POST':
            form = forms.RoundTransitionForm(round_to_close, round_to_open, season_to_close, request.POST)
            if form.is_valid():
                with transaction.atomic():
                    if 'round_to_close' in form.cleaned_data and form.cleaned_data['round_to_close'] == round_to_close.number:
                        if form.cleaned_data['complete_round']:
                            round_to_close.is_completed = True
                            round_to_close.save()
                            self.message_user(request, 'Round %d set as completed.' % round_to_close.number, messages.INFO)
                    if 'complete_season' in form.cleaned_data and season_to_close is not None and form.cleaned_data['complete_season'] \
                            and (round_to_close is None or round_to_close.is_completed):
                        season_to_close.is_completed = True
                        season_to_close.save()
                        self.message_user(request, '%s set as completed.' % season_to_close.name, messages.INFO)
                    if 'round_to_open' in form.cleaned_data and form.cleaned_data['round_to_open'] == round_to_open.number:
                        if form.cleaned_data['update_board_order']:
                            try:
                                self.do_update_board_order(season)
                                self.message_user(request, 'Board order updated.', messages.INFO)
                            except IndexError:
                                self.message_user(request, 'Error updating board order.', messages.ERROR)
                                return redirect('admin:round_transition', object_id)
                        if form.cleaned_data['generate_pairings']:
                            try:
                                pairinggen.generate_pairings(round_to_open, overwrite=False)
                                round_to_open.publish_pairings = False
                                round_to_open.save()
                                self.message_user(request, 'Pairings generated.', messages.INFO)
                                return redirect('admin:review_pairings', round_to_open.pk)
                            except pairinggen.PairingsExistException:
                                self.message_user(request, 'Unpublished pairings already exist.', messages.WARNING)
                                return redirect('admin:review_pairings', round_to_open.pk)
                            except pairinggen.PairingHasResultException:
                                self.message_user(request, 'Pairings with results can\'t be overwritten.', messages.ERROR)
                    return redirect('admin:tournament_season_changelist')
        else:
            form = forms.RoundTransitionForm(round_to_close, round_to_open, season_to_close)

        if round_to_close is not None and round_to_close.end_date is not None and round_to_close.end_date > timezone.now() + timedelta(hours=1):
            time_from_now = self._time_from_now(round_to_close.end_date - timezone.now())
            self.message_user(request, 'The round %d end date is %s from now.' % (round_to_close.number, time_from_now), messages.WARNING)
        elif round_to_open is not None and round_to_open.start_date is not None and round_to_open.start_date > timezone.now() + timedelta(hours=1):
            time_from_now = self._time_from_now(round_to_open.start_date - timezone.now())
            self.message_user(request, 'The round %d start date is %s from now.' % (round_to_open.number, time_from_now), messages.WARNING)

        if round_to_close is not None:
            incomplete_pairings = models.PlayerPairing.objects.filter(result='', teamplayerpairing__team_pairing__round=round_to_close)
            if len(incomplete_pairings) > 0:
                self.message_user(request, 'Round %d has %d pairing(s) without a result.' % (round_to_close.number, len(incomplete_pairings)), messages.WARNING)

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': season,
            'title': 'Round transition',
            'form': form
        }

        return render(request, 'tournament/admin/round_transition.html', context)

    def _time_from_now(self, delta):
        if delta.days > 0:
            if delta.days == 1:
                return '1 day'
            else:
                return '%d days' % delta.days
        else:
            hours = delta.seconds / 3600
            if hours == 1:
                return '1 hour'
            else:
                return '%d hours' % hours

    def update_board_order_by_rating(self, request, queryset):
        try:
            for season in queryset.all():
                self.do_update_board_order(season)
            self.message_user(request, 'Board order updated.', messages.INFO)
        except IndexError:
            self.message_user(request, 'Error updating board order.', messages.ERROR)

    def do_update_board_order(self, season):
        # Update board order in teams
        for team in season.team_set.all():
            members = list(team.teammember_set.all())
            members.sort(key=lambda m:-m.player.rating)
            occupied_boards = [m.board_number for m in members]
            occupied_boards.sort()
            for i, board_number in enumerate(occupied_boards):
                m = members[i]
                models.TeamMember.objects.update_or_create(team=team, board_number=board_number, \
                                                           defaults={ 'player': m.player, 'is_captain': m.is_captain,
                                                                      'is_vice_captain': m.is_vice_captain })

        # Update alternate buckets
        members_by_board = [models.TeamMember.objects.filter(team__season=season, board_number=n + 1) for n in range(season.boards)]
        ratings_by_board = [sorted([float(m.player.rating) for m in m_list]) for m_list in members_by_board]
        # Exclude highest/lowest values if possible (to avoid outliers skewing the average)
        average_by_board = [sum(r_list[1:-1]) / (len(r_list) - 2) if len(r_list) > 2 else sum(r_list) / len(r_list) if len(r_list) > 0 else None for r_list in ratings_by_board]
        boundaries = []
        for i in range(season.boards + 1):
            # The logic here is a bit complicated in order to handle cases where there are no players for a board
            left_i = i - 1
            while left_i >= 0 and average_by_board[left_i] is None:
                left_i -= 1
            left = average_by_board[left_i] if left_i >= 0 else None
            right_i = i
            while right_i < season.boards and average_by_board[right_i] is None:
                right_i += 1
            right = average_by_board[right_i] if right_i < season.boards else None
            if left is None or right is None:
                boundaries.append(None)
            else:
                boundaries.append((left + right) / 2)
        for board_num in range(1, season.boards + 1):
            models.AlternateBucket.objects.update_or_create(season=season, board_number=board_num,
                                                            defaults={ 'max_rating': boundaries[board_num - 1], 'min_rating': boundaries[board_num] })

        # Assign alternates to buckets
        for alt in models.Alternate.objects.filter(season_player__season=season):
            alt.update_board_number()

    def edit_rosters(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Rosters can only be edited one season at a time.', messages.ERROR)
            return
        return redirect('admin:edit_rosters', object_id=queryset[0].pk)

    def player_info_view(self, request, object_id, player_name):
        season = models.Season.objects.get(pk=object_id)
        season_player = models.SeasonPlayer.objects.get(season=season, player__lichess_username=player_name)

        context = {
            'season_player': season_player,
            'player': season_player.player,
            'reg': season_player.registration
        }

        return render(request, 'tournament/admin/edit_rosters_player_info.html', context)

    def edit_rosters_view(self, request, object_id):
        season = models.Season.objects.get(pk=object_id)
        teams_locked = bool(models.Round.objects.filter(season=season, publish_pairings=True).count())

        if request.method == 'POST':
            form = forms.EditRostersForm(request.POST)
            if form.is_valid():
                changes = json.loads(form.cleaned_data['changes'])
                # raise ValueError(changes)
                has_error = False
                for change in changes:
                    try:
                        if change['action'] == 'change-member':
                            team_num = change['team_number']
                            team = models.Team.objects.get(season=season, number=team_num)

                            board_num = change['board_number']
                            player_info = change['player']

                            teammember = models.TeamMember.objects.filter(team=team, board_number=board_num).first()
                            if teammember == None:
                                teammember = models.TeamMember(team=team, board_number=board_num)
                            if player_info is None:
                                teammember.delete()
                            else:
                                teammember.player = models.Player.objects.get(lichess_username=player_info['name'])
                                teammember.is_captain = player_info['is_captain']
                                teammember.is_vice_captain = player_info['is_vice_captain']
                                teammember.save()

                        if change['action'] == 'change-team' and not teams_locked:
                            team_num = change['team_number']
                            team = models.Team.objects.get(season=season, number=team_num)

                            team_name = change['team_name']
                            team.name = team_name
                            team.save()

                        if change['action'] == 'create-team' and not teams_locked:
                            model = change['model']
                            team = models.Team.objects.create(season=season, number=model['number'], name=model['name'])

                            for board_num, player_info in enumerate(model['boards'], 1):
                                if player_info is not None:
                                    player = models.Player.objects.get(lichess_username=player_info['name'])
                                    is_captain = player_info['is_captain']
                                    models.TeamMember.objects.create(team=team, player=player, board_number=board_num, is_captain=is_captain)

                        if change['action'] == 'create-alternate':
                            board_num = change['board_number']
                            season_player = models.SeasonPlayer.objects.get(season=season, player__lichess_username__iexact=change['player_name'])
                            models.Alternate.objects.update_or_create(season_player=season_player, defaults={ 'board_number': board_num })

                        if change['action'] == 'delete-alternate':
                            board_num = change['board_number']
                            season_player = models.SeasonPlayer.objects.get(season=season, player__lichess_username__iexact=change['player_name'])
                            alt = models.Alternate.objects.filter(season_player=season_player, board_number=board_num).first()
                            if alt is not None:
                                alt.delete()

                    except Exception:
                        has_error = True

                if has_error:
                    self.message_user(request, 'Some changes could not be saved.', messages.WARNING)

                if 'save_continue' in form.data:
                    return redirect('admin:edit_rosters', object_id)
                return redirect('admin:tournament_season_changelist')
        else:
            form = forms.EditRostersForm()

        board_numbers = list(range(1, season.boards + 1))
        teams = models.Team.objects.filter(season=season).order_by('number').prefetch_related(
            Prefetch('teammember_set', queryset=models.TeamMember.objects.select_related('player'))
        ).nocache()
        team_members = models.TeamMember.objects.filter(team__season=season).select_related('player').nocache()
        alternates = models.Alternate.objects.filter(season_player__season=season).select_related('season_player__player').nocache()
        alternates_by_board = [(n, sorted(
                                          alternates.filter(board_number=n).select_related('season_player__registration').nocache(),
                                          key=lambda alt: alt.priority_date()
                                         )) for n in board_numbers]

        season_players = set(sp.player for sp in models.SeasonPlayer.objects.filter(season=season, is_active=True).select_related('player').nocache())
        team_players = set(tm.player for tm in team_members)
        alternate_players = set(alt.season_player.player for alt in alternates)

        alternate_buckets = list(models.AlternateBucket.objects.filter(season=season))
        unassigned_players = list(sorted(season_players - team_players - alternate_players, key=lambda p:-p.rating))
        if len(alternate_buckets) == season.boards:
            # Sort unassigned players by alternate buckets
            unassigned_by_board = [(n, [p for p in unassigned_players if models.find(alternate_buckets, board_number=n).contains(p.rating)]) for n in board_numbers]
        else:
            # Season doesn't have buckets yet. Sort by player soup
            sorted_players = list(sorted((p for p in season_players if p.rating is not None), key=lambda p:-p.rating))
            player_count = len(sorted_players)
            unassigned_by_board = [(n, []) for n in board_numbers]
            if player_count > 0:
                max_ratings = [(n, sorted_players[len(sorted_players) * (n - 1) / season.boards].rating) for n in board_numbers]
                for p in unassigned_players:
                    board_num = 1
                    for n, max_rating in max_ratings:
                        if p.rating <= max_rating:
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

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
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
        }

        return render(request, 'tournament/admin/edit_rosters.html', context)

@admin.register(models.Round)
class RoundAdmin(VersionAdmin):
    list_filter = ('season',)
    actions = ['generate_pairings']
    change_form_template = 'tournament/admin/change_form_with_comments.html'

    def get_urls(self):
        urls = super(RoundAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/generate_pairings/$',
                permission_required('tournament.generate_pairings')(self.admin_site.admin_view(self.generate_pairings_view)),
                name='generate_pairings'),
            url(r'^(?P<object_id>[0-9]+)/review_pairings/$',
                permission_required('tournament.generate_pairings')(self.admin_site.admin_view(self.review_pairings_view)),
                name='review_pairings'),
        ]
        return my_urls + urls

    def generate_pairings(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Pairings can only be generated one round at a time', messages.ERROR)
            return
        return redirect('admin:generate_pairings', object_id=queryset[0].pk)

    def generate_pairings_view(self, request, object_id):
        round_ = models.Round.objects.get(pk=object_id)

        if request.method == 'POST':
            form = forms.GeneratePairingsForm(request.POST)
            if form.is_valid():
                try:
                    pairinggen.generate_pairings(round_, overwrite=form.cleaned_data['overwrite_existing'])
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
        round_ = models.Round.objects.get(pk=object_id)

        if request.method == 'POST':
            form = forms.ReviewPairingsForm(request.POST)
            if form.is_valid():
                if 'publish' in form.data:
                    round_.publish_pairings = True
                    round_.save()
                    self.message_user(request, 'Pairings published.', messages.INFO)
                elif 'delete' in form.data:
                    try:
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
            pairings = round_.loneplayerpairing_set.order_by('pairing_order')
            byes = round_.playerbye_set.order_by('type', 'player_rank', 'player__lichess_username')
            next_pairing_order = 0
            for p in pairings:
                next_pairing_order = max(next_pairing_order, p.pairing_order + 1)
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
                'next_pairing_order': next_pairing_order,
            }
            return render(request, 'tournament/admin/review_lone_pairings.html', context)


#-------------------------------------------------------------------------------
@admin.register(models.PlayerLateRegistration)
class PlayerLateRegistrationAdmin(VersionAdmin):
    list_display = ('__unicode__', 'retroactive_byes', 'late_join_points')
    search_fields = ('player__lichess_username',)
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('round', 'player')
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.PlayerWithdrawl)
class PlayerWithdrawlAdmin(VersionAdmin):
    list_display = ('__unicode__',)
    search_fields = ('player__lichess_username',)
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('round', 'player')
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.PlayerBye)
class PlayerByeAdmin(VersionAdmin):
    list_display = ('__unicode__', 'type')
    search_fields = ('player__lichess_username',)
    list_filter = ('round__season', 'round__number', 'type')
    raw_id_fields = ('round', 'player')
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.Player)
class PlayerAdmin(VersionAdmin):
    search_fields = ('lichess_username',)
    list_filter = ('is_active',)
    actions = ['update_selected_player_ratings']
    change_form_template = 'tournament/admin/change_form_with_comments.html'

    def update_selected_player_ratings(self, request, queryset):
        try:
            for player in queryset.all():
                rating, games_played = lichessapi.get_user_classical_rating_and_games_played(player.lichess_username, priority=1)
                player.rating = rating
                player.games_played = games_played
                player.save()
            self.message_user(request, 'Rating(s) updated', messages.INFO)
        except:
            self.message_user(request, 'Error updating rating(s) from lichess API', messages.ERROR)


#-------------------------------------------------------------------------------
class TeamMemberInline(admin.TabularInline):
    model = models.TeamMember
    extra = 0
    ordering = ('board_number',)
    raw_id_fields = ('player',)

#-------------------------------------------------------------------------------
@admin.register(models.Team)
class TeamAdmin(VersionAdmin):
    list_display = ('name', 'season')
    search_fields = ('name',)
    list_filter = ('season',)
    inlines = [TeamMemberInline]
    actions = ['update_board_order_by_rating']
    change_form_template = 'tournament/admin/change_form_with_comments.html'

    def update_board_order_by_rating(self, request, queryset):
        for team in queryset.all():
            members = team.teammember_set.order_by('-player__rating')
            for i in range(len(members)):
                members[i].board_number = i + 1
                members[i].save()
        self.message_user(request, 'Board order updated', messages.INFO)

#-------------------------------------------------------------------------------
@admin.register(models.TeamMember)
class TeamMemberAdmin(VersionAdmin):
    list_display = ('__unicode__', 'team')
    search_fields = ('team__name', 'player__lichess_username')
    list_filter = ('team__season',)
    raw_id_fields = ('player',)
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.TeamScore)
class TeamScoreAdmin(VersionAdmin):
    list_display = ('team', 'match_points', 'game_points')
    search_fields = ('team__name',)
    list_filter = ('team__season',)
    raw_id_fields = ('team',)
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.Alternate)
class AlternateAdmin(VersionAdmin):
    list_display = ('__unicode__', 'board_number')
    search_fields = ('season_player__player__lichess_username',)
    list_filter = ('season_player__season', 'board_number')
    raw_id_fields = ('season_player',)
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.AlternateAssignment)
class AlternateAssignmentAdmin(VersionAdmin):
    list_display = ('__unicode__', 'player')
    search_fields = ('team__name', 'player__lichess_username')
    list_filter = ('round__season', 'round__number', 'board_number')
    raw_id_fields = ('round', 'team', 'player')
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.AlternateBucket)
class AlternateBucketAdmin(VersionAdmin):
    list_display = ('__unicode__', 'season')
    search_fields = ()
    list_filter = ('season', 'board_number')
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.TeamPairing)
class TeamPairingAdmin(VersionAdmin):
    list_display = ('white_team_name', 'black_team_name', 'season_name', 'round_number')
    search_fields = ('white_team__name', 'black_team__name')
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('white_team', 'black_team', 'round')
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.PlayerPairing)
class PlayerPairingAdmin(VersionAdmin):
    list_display = ('__unicode__', 'scheduled_time')
    search_fields = ('white__lichess_username', 'black__lichess_username')
    raw_id_fields = ('white', 'black')
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.TeamPlayerPairing)
class TeamPlayerPairingAdmin(VersionAdmin):
    list_display = ('__unicode__', 'team_pairing', 'board_number')
    search_fields = ('white__lichess_username', 'black__lichess_username',
                     'team_pairing__white_team__name', 'team_pairing__black_team__name')
    list_filter = ('team_pairing__round__season', 'team_pairing__round__number',)
    raw_id_fields = ('white', 'black', 'team_pairing')
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.LonePlayerPairing)
class LonePlayerPairingAdmin(VersionAdmin):
    list_display = ('__unicode__', 'round')
    search_fields = ('white__lichess_username', 'black__lichess_username')
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('white', 'black', 'round')
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.Registration)
class RegistrationAdmin(VersionAdmin):
    list_display = ('lichess_username', 'email', 'status', 'season')
    search_fields = ('lichess_username', 'season')
    list_filter = ('status', 'season',)

    def get_urls(self):
        urls = super(RegistrationAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/approve/$',
                permission_required('tournament.change_registration')(self.admin_site.admin_view(self.approve_registration)),
                name='approve_registration'),
            url(r'^(?P<object_id>[0-9]+)/reject/$',
                permission_required('tournament.change_registration')(self.admin_site.admin_view(self.reject_registration)),
                name='reject_registration')
        ]
        return my_urls + urls

    def review_registration(self, request, object_id):
        reg = models.Registration.objects.get(pk=object_id)

        if request.method == 'POST':
            form = forms.ReviewRegistrationForm(request.POST)
            if form.is_valid():
                if 'approve' in form.data and reg.status == 'pending':
                    return redirect('admin:approve_registration', object_id=object_id)
                elif 'reject' in form.data and reg.status == 'pending':
                    return redirect('admin:reject_registration', object_id=object_id)
                else:
                    return redirect('admin:tournament_registration_changelist')
        else:
            form = forms.ReviewRegistrationForm()

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': reg,
            'title': 'Review registration',
            'form': form
        }

        return render(request, 'tournament/admin/review_registration.html', context)

    def approve_registration(self, request, object_id):
        reg = models.Registration.objects.get(pk=object_id)

        if reg.status != 'pending':
            return redirect('admin:tournament_registration_change', object_id)

        if request.method == 'POST':
            form = forms.ApproveRegistrationForm(request.POST, registration=reg)
            if form.is_valid():
                if 'confirm' in form.data:
                    with transaction.atomic():
                        # Add or update the player in the DB
                        player, _ = models.Player.objects.update_or_create(
                            lichess_username__iexact=reg.lichess_username,
                            defaults={'lichess_username': reg.lichess_username, 'rating': reg.classical_rating, 'email': reg.email, 'is_active': True}
                        )
                        models.SeasonPlayer.objects.update_or_create(
                            player=player,
                            season=reg.season,
                            defaults={'registration': reg, 'is_active': True}
                        )
                        if form.cleaned_data['send_confirm_email']:
                            try:
                                subject = render_to_string('tournament/emails/registration_approved_subject.txt', {'reg': reg})
                                msg_plain = render_to_string('tournament/emails/registration_approved.txt', {'reg': reg})
                                msg_html = render_to_string('tournament/emails/registration_approved.html', {'reg': reg})
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

                        reg.status = 'approved'
                        reg.status_changed_by = request.user.username
                        reg.status_changed_date = timezone.now()
                        reg.save()

                        for week_number in reg.weeks_unavailable.split(','):
                            if week_number != '':
                                round_ = models.Round.objects.filter(season=reg.season, number=int(week_number)).first()
                                if round_ is not None:
                                    models.PlayerAvailability.objects.update_or_create(player=player, round=round_, defaults={'is_available': False})

                    self.message_user(request, 'Registration for "%s" approved.' % reg.lichess_username, messages.INFO)
                    return redirect('admin:tournament_registration_changelist')
                else:
                    return redirect('admin:tournament_registration_change', object_id)
        else:
            form = forms.ApproveRegistrationForm(registration=reg)

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': reg,
            'title': 'Confirm approval',
            'form': form
        }

        return render(request, 'tournament/admin/approve_registration.html', context)

    def reject_registration(self, request, object_id):
        reg = models.Registration.objects.get(pk=object_id)

        if reg.status != 'pending':
            return redirect('admin:tournament_registration_change', object_id)

        if request.method == 'POST':
            form = forms.RejectRegistrationForm(request.POST, registration=reg)
            if form.is_valid():
                if 'confirm' in form.data:
                    reg.status = 'rejected'
                    reg.status_changed_by = request.user.username
                    reg.status_changed_date = timezone.now()
                    reg.save()
                    self.message_user(request, 'Registration for "%s" rejected.' % reg.lichess_username, messages.INFO)
                    return redirect('admin:tournament_registration_changelist')
                else:
                    return redirect('admin:tournament_registration_change', object_id)
        else:
            form = forms.RejectRegistrationForm(registration=reg)

        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': reg,
            'title': 'Confirm rejection',
            'form': form
        }

        return render(request, 'tournament/admin/reject_registration.html', context)

    change_view = review_registration

#-------------------------------------------------------------------------------
@admin.register(models.SeasonPlayer)
class SeasonPlayerAdmin(VersionAdmin):
    list_display = ('player', 'season')
    search_fields = ('season__name', 'player__lichess_username')
    list_filter = ('season',)
    raw_id_fields = ('player',)
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.LonePlayerScore)
class LonePlayerScoreAdmin(VersionAdmin):
    list_display = ('season_player', 'points', 'late_join_points')
    search_fields = ('season_player__season__name', 'season_player__player__lichess_username')
    list_filter = ('season_player__season',)
    raw_id_fields = ('season_player',)
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.PlayerAvailability)
class PlayerAvailabilityAdmin(VersionAdmin):
    list_display = ('player', 'round', 'is_available')
    search_fields = ('player__lichess_username',)
    list_filter = ('round__season', 'round__number')
    raw_id_fields = ('player', 'round')
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.SeasonPrize)
class SeasonPrizeAdmin(VersionAdmin):
    list_display = ('season', 'rank', 'max_rating')
    search_fields = ('season__name',)
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.SeasonPrizeWinner)
class SeasonPrizeWinnerAdmin(VersionAdmin):
    list_display = ('season_prize', 'player',)
    search_fields = ('season_prize__name', 'player__lichess_username')
    raw_id_fields = ('season_prize', 'player')
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.ApiKey)
class ApiKeyAdmin(VersionAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.Document)
class DocumentAdmin(VersionAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    change_form_template = 'tournament/admin/change_form_with_comments.html'

#-------------------------------------------------------------------------------
@admin.register(models.LeagueDocument)
class LeagueDocumentAdmin(VersionAdmin):
    list_display = ('document', 'league', 'tag', 'type')
    search_fields = ('league__name', 'tag', 'document__name')
    change_form_template = 'tournament/admin/change_form_with_comments.html'
