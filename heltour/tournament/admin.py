from django.contrib import admin, messages
from heltour.tournament import models, lichessapi
from reversion.admin import VersionAdmin

import pairinggen

#-------------------------------------------------------------------------------
@admin.register(models.League)
class LeagueAdmin(VersionAdmin):
    pass

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

def generate_pairings(modeladmin, request, queryset):
    if queryset.count() > 1:
        modeladmin.message_user(request, 'Pairings can only be generated one round at a time', messages.ERROR)
        return
    try:
        pairinggen.generate_pairings(queryset.first())
        modeladmin.message_user(request, 'Pairings created', messages.INFO)
    except ValueError:
        modeladmin.message_user(request, 'Pairings already exist for the selected round', messages.ERROR)

# TODO: flesh out the rest of these admin classes based on the workflows of
#       The moderators
#-------------------------------------------------------------------------------
@admin.register(models.Round)
class RoundAdmin(VersionAdmin):
    list_filter = ('season',)
    actions = [generate_pairings]

#-------------------------------------------------------------------------------
@admin.register(models.RoundChange)
class RoundChangeAdmin(VersionAdmin):
    pass

def update_selected_player_ratings(modeladmin, request, queryset):
    try:
        for player in queryset.all():
            rating, games_played = lichessapi.get_user_classical_rating_and_games_played(player.lichess_username)
            player.rating = rating
            player.games_played = games_played
            player.save()
        modeladmin.message_user(request, 'Rating(s) updated', messages.INFO)
    except:
        modeladmin.message_user(request, 'Error updating rating(s) from lichess API', messages.ERROR)

#-------------------------------------------------------------------------------
@admin.register(models.Player)
class PlayerAdmin(VersionAdmin):
    search_fields = ('lichess_username',)
    list_filter = ('is_active',)
    actions = [update_selected_player_ratings]

def update_board_order_by_rating(modeladmin, request, queryset):
    for team in queryset.all():
        members = team.teammember_set.order_by('-player__rating')
        for i in range(len(members)):
            members[i].board_number = i + 1
            members[i].save()
    modeladmin.message_user(request, 'Board order updated', messages.INFO)

#-------------------------------------------------------------------------------
@admin.register(models.Team)
class TeamAdmin(VersionAdmin):
    list_display = ('name', 'season')
    search_fields = ('name',)
    list_filter = ('season',)
    actions = [update_board_order_by_rating]

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

