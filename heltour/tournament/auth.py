from heltour.tournament.models import LeagueModerator

class LeagueAuthBackend(object):
    def has_module_perms(self, user_obj, app_label):
        if app_label != 'tournament':
            return False
        return LeagueModerator.objects.filter(player__lichess_username__iexact=user_obj.username).exists()
