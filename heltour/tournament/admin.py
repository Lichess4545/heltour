from django.contrib import admin, messages
from django.utils import timezone
from heltour.tournament import models, lichessapi, views, forms
from reversion.admin import VersionAdmin
from django.conf.urls import url
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import permission_required

import json
import pairinggen
import spreadsheet

#-------------------------------------------------------------------------------
@admin.register(models.League)
class LeagueAdmin(VersionAdmin):
    actions = ['import_season']
    
    def get_urls(self):
        urls = super(LeagueAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/import_season/$', permission_required('tournament.change_league')(self.admin_site.admin_view(self.import_season_view)), name='import_season'),
        ]
        return my_urls + urls
    
    def import_season(self, request, queryset):
        return redirect('admin:import_season', object_id=queryset[0].pk)
    
    def import_season_view(self, request, object_id):
        league = models.League.objects.get(pk=object_id)
        
        if request.method == 'POST':
            form = forms.ImportSeasonForm(request.POST)
            if form.is_valid():
                spreadsheet.import_season(league, form.cleaned_data['spreadsheet_url'], form.cleaned_data['season_name'], form.cleaned_data['rosters_only'], form.cleaned_data['exclude_live_pairings'])
                self.message_user(request, "Season imported.")
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
    list_display = (
            '__unicode__',
            'league',
        )
    list_display_links = (
            '__unicode__',
        )
    list_filter = (
        'league',
    )
    actions = ['edit_rosters']
    # TODO: when rounds are set or the season is 'started' create 
    #       all of the round records for this season, and don't let
    #       the number of rounds to change after that.
    
    def edit_rosters(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Rosters can only be edited one season at a time', messages.ERROR)
            return
        return redirect('admin:edit_rosters', object_id=queryset[0].pk)
    
    def get_urls(self):
        urls = super(SeasonAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/edit_rosters/$', permission_required('tournament.edit_rosters')(self.admin_site.admin_view(self.edit_rosters_view)), name='edit_rosters'),
        ]
        return my_urls + urls
    
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
                            player = models.Player.objects.get(lichess_username=change['player_name'])
                            
                            models.Alternate.objects.update_or_create(season=season, player=player, defaults={ 'board_number': board_num })
                            
                        if change['action'] == 'delete-alternate':
                            board_num = change['board_number']
                            player = models.Player.objects.get(lichess_username=change['player_name'])
                            alt = models.Alternate.objects.filter(season=season, player=player, board_number=board_num).first()
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
        teams = list(models.Team.objects.filter(season=season).order_by('number')) 
        team_members = models.TeamMember.objects.filter(team__season=season)
        alternates = models.Alternate.objects.filter(season=season)
        alternates_by_board = [(n, alternates.filter(board_number=n).order_by('-player__rating')) for n in board_numbers]
        
        season_players = set(sp.player for sp in models.SeasonPlayer.objects.filter(season=season, is_active=True))
        team_players = set(tm.player for tm in team_members)
        alternate_players = set(alt.player for alt in alternates)
        
        alternate_buckets = models.AlternateBucket.objects.filter(season=season)
        unassigned_players = list(sorted(season_players - team_players - alternate_players, key=lambda p: -p.rating))
        if len(alternate_buckets) == season.boards:
            # Sort unassigned players by alternate buckets
            unassigned_by_board = [(n, [p for p in unassigned_players if alternate_buckets.get(board_number=n).contains(p.rating)]) for n in board_numbers]
        else:
            # Season doesn't have buckets yet. Sort by player soup
            sorted_players = list(sorted((p for p in season_players if p.rating is not None), key=lambda p: -p.rating))
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
    
    def get_urls(self):
        urls = super(RoundAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/generate_pairings/$', permission_required('tournament.generate_pairings')(self.admin_site.admin_view(self.generate_pairings_view)), name='generate_pairings'),
            url(r'^(?P<object_id>[0-9]+)/review_pairings/$', permission_required('tournament.generate_pairings')(self.admin_site.admin_view(self.review_pairings_view)), name='review_pairings'),
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
                    return redirect('admin:review_pairings', object_id) 
                except pairinggen.PairingsExistException:
                    self.message_user(request, 'Pairings already exist for the selected round.', messages.ERROR)
                except pairinggen.PairingHasResultException:
                    self.message_user(request, 'Pairings with results can\'t be overwritten.', messages.ERROR)
                return redirect('admin:tournament_round_changelist')
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
        
        team_pairings = round_.teampairing_set.order_by('pairing_order')
        pairing_lists = [team_pairing.teamplayerpairing_set.order_by('board_number') for team_pairing in team_pairings]
        
        context = {
            'has_permission': True,
            'opts': self.model._meta,
            'site_url': '/',
            'original': round_,
            'title': 'Review pairings',
            'form': form,
            'pairing_lists': pairing_lists
        }
        
        return render(request, 'tournament/admin/review_pairings.html', context)

#-------------------------------------------------------------------------------
@admin.register(models.RoundChange)
class RoundChangeAdmin(VersionAdmin):
    pass

#-------------------------------------------------------------------------------
@admin.register(models.Player)
class PlayerAdmin(VersionAdmin):
    search_fields = ('lichess_username',)
    list_filter = ('is_active',)
    actions = ['update_selected_player_ratings']
    
    def update_selected_player_ratings(self, request, queryset):
        try:
            for player in queryset.all():
                rating, games_played = lichessapi.get_user_classical_rating_and_games_played(player.lichess_username)
                player.rating = rating
                player.games_played = games_played
                player.save()
            self.message_user(request, 'Rating(s) updated', messages.INFO)
        except:
            self.message_user(request, 'Error updating rating(s) from lichess API', messages.ERROR)

#-------------------------------------------------------------------------------
@admin.register(models.Team)
class TeamAdmin(VersionAdmin):
    list_display = ('name', 'season')
    search_fields = ('name',)
    list_filter = ('season',)
    actions = ['update_board_order_by_rating']
    
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
    list_filter = ('team',)
    pass

#-------------------------------------------------------------------------------
@admin.register(models.TeamScore)
class TeamScoreAdmin(VersionAdmin):
    list_display = ('team', 'match_points', 'game_points')
    search_fields = ('team__name',)
    list_filter = ('team__season',)
    pass

#-------------------------------------------------------------------------------
@admin.register(models.TeamPairing)
class TeamPairingAdmin(VersionAdmin):
    list_display = ('white_team_name', 'black_team_name', 'season_name', 'round_number')
    search_fields = ('white_team__name', 'black_team__name')
    list_filter = ('round',)

#-------------------------------------------------------------------------------
@admin.register(models.PlayerPairing)
class PlayerPairingAdmin(VersionAdmin):
    list_display = ('__unicode__', 'scheduled_time')
    search_fields = ('white__lichess_username', 'black__lichess_username')

#-------------------------------------------------------------------------------
@admin.register(models.TeamPlayerPairing)
class TeamPlayerPairingAdmin(VersionAdmin):
    list_display = ('player_pairing', 'team_pairing', 'board_number')
    search_fields = ('player_pairing__white__lichess_username', 'player_pairing__black__lichess_username', 'team_pairing__white_team__name', 'team_pairing__black_team__name')
    list_filter = ('team_pairing__round',)

#-------------------------------------------------------------------------------
@admin.register(models.LonePlayerPairing)
class LonePlayerPairingAdmin(VersionAdmin):
    list_display = ('player_pairing', 'round')
    search_fields = ('white__lichess_username', 'black__lichess_username')
    list_filter = ('round',)

#-------------------------------------------------------------------------------
@admin.register(models.Registration)
class RegistrationAdmin(VersionAdmin):
    list_display = ('lichess_username', 'email', 'status', 'season')
    search_fields = ('lichess_username', 'season')
    list_filter = ('status', 'season',)
    
    def get_urls(self):
        urls = super(RegistrationAdmin, self).get_urls()
        my_urls = [
            url(r'^(?P<object_id>[0-9]+)/approve/$', permission_required('tournament.change_registration')(self.admin_site.admin_view(self.approve_registration)), name='approve_registration'),
            url(r'^(?P<object_id>[0-9]+)/reject/$', permission_required('tournament.change_registration')(self.admin_site.admin_view(self.reject_registration)), name='reject_registration')
        ]
        return my_urls + urls
    
    def review_registration(self, request, object_id):
        reg = models.Registration.objects.get(pk=object_id)
        
        if request.method == 'POST':
            form = forms.ReviewRegistrationForm(request.POST, registration=reg)
            if form.is_valid():
                reg.moderator_notes = form.cleaned_data['moderator_notes']
                reg.save()
                if 'approve' in form.data and reg.status == 'pending':
                    return redirect('admin:approve_registration', object_id=object_id)
                elif 'reject' in form.data and reg.status == 'pending':
                    return redirect('admin:reject_registration', object_id=object_id)
                else:
                    return redirect('admin:tournament_registration_changelist')
        else:
            form = forms.ReviewRegistrationForm(registration=reg)
        
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
                    # TODO: Update model to associate players with seasons and create the association here
                    # TODO: Invite to slack, send confirmation email, etc. based on form input
                    reg.status = 'approved'
                    reg.status_changed_by = request.user.username
                    reg.status_changed_date = timezone.now()
                    reg.save()
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

#-------------------------------------------------------------------------------
@admin.register(models.ApiKey)
class ApiKeyAdmin(VersionAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    
#-------------------------------------------------------------------------------
@admin.register(models.Document)
class DocumentAdmin(VersionAdmin):
    list_display = ('name',)
    search_fields = ('name',)

#-------------------------------------------------------------------------------
@admin.register(models.LeagueDocument)
class LeagueDocumentAdmin(VersionAdmin):
    list_display = ('document', 'league', 'tag', 'type')
    search_fields = ('league__name', 'tag', 'document__name')
