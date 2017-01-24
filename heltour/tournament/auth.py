from heltour.tournament.models import LeagueModerator, League

class LeagueAuthBackend(object):
    def has_perm(self, user_obj, perm, obj=None):
        if isinstance(obj, League):
            return LeagueModerator.objects.filter(league=obj, player__lichess_username__iexact=user_obj.username).exists()
        if obj is None and perm.startswith('tournament.delete_'):
            # Have to work around a django bug preventing deletion
            # https://code.djangoproject.com/ticket/13539
            # There should be an object-specific check that will be sufficient to prevent unauthorized deletion
            return LeagueModerator.objects.filter(player__lichess_username__iexact=user_obj.username).exists()
        return False

    def has_module_perms(self, user_obj, app_label):
        if app_label != 'tournament':
            return False
        return LeagueModerator.objects.filter(player__lichess_username__iexact=user_obj.username).exists()
