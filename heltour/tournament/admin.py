from django.contrib import admin
from heltour.tournament import models
from reversion.admin import VersionAdmin

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
    # TODO: when rounds are set or the season is "started" create 
    #       all of the round records for this season, and don't let
    #       the number of rounds to change after that.



# TODO: flesh out the rest of these admin classes based on the workflows of
#       The moderators
#-------------------------------------------------------------------------------
@admin.register(models.Round)
class RoundAdmin(VersionAdmin):
    list_filter = ('season',)

#-------------------------------------------------------------------------------
@admin.register(models.RoundChange)
class RoundChangeAdmin(VersionAdmin):
    pass

#-------------------------------------------------------------------------------
@admin.register(models.Player)
class PlayerAdmin(VersionAdmin):
    search_fields = ('lichess_username',)

#-------------------------------------------------------------------------------
@admin.register(models.Team)
class TeamAdmin(VersionAdmin):
    list_display = ('name', 'season')
    search_fields = ('name',)
    list_filter = ('season',)

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

