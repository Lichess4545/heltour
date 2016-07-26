from django.contrib import admin, messages
from heltour.tournament import models, lichessapi, views, forms
from reversion.admin import VersionAdmin
from django.conf.urls import url
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import permission_required
from datetime import datetime

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
    # TODO: when rounds are set or the season is 'started' create 
    #       all of the round records for this season, and don't let
    #       the number of rounds to change after that.

# TODO: flesh out the rest of these admin classes based on the workflows of
#       The moderators
#-------------------------------------------------------------------------------
@admin.register(models.Round)
class RoundAdmin(VersionAdmin):
    list_filter = ('season',)
    actions = ['generate_pairings']
    
    def generate_pairings(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(request, 'Pairings can only be generated one round at a time', messages.ERROR)
            return
        try:
            pairinggen.generate_pairings(queryset.first())
            self.message_user(request, 'Pairings created', messages.INFO)
        except ValueError:
            self.message_user(request, 'Pairings already exist for the selected round', messages.ERROR)

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
@admin.register(models.Pairing)
class PairingAdmin(VersionAdmin):
    list_display = ('__unicode__', 'season_name', 'round_number', 'white_team_name', 'black_team_name', 'board_number')
    search_fields = ('white_team__name', 'black_team__name', 'white__lichess_username', 'black__lichess_username')
    list_filter = ('team_pairing__round',)
    
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
                    reg.status_changed_date = datetime.now()
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
                    reg.status_changed_date = datetime.now()
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
    list_display = ('tag', 'league', 'type', 'document',)
    search_fields = ('league__name', 'tag', 'document__name')
