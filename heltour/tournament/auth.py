from heltour.tournament.models import LeagueModerator, League

class LeagueAuthBackend(object):
    def has_perm(self, user_obj, perm, obj=None):
        if isinstance(obj, League):
            return LeagueModerator.objects.filter(league=obj, player__lichess_username__iexact=user_obj.username).exists()
        return False

    def has_module_perms(self, user_obj, app_label):
        if app_label != 'tournament':
            return False
        return LeagueModerator.objects.filter(player__lichess_username__iexact=user_obj.username).exists()
