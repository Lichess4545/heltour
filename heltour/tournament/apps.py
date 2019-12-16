from django.apps import AppConfig


class TournamentConfig(AppConfig):
    name = 'heltour.tournament'

    def ready(self):
        from . import uptime  # @UnusedImport
        # Make sure signal handlers are registered
        from . import notify  # @UnusedImport
        from . import automod  # @UnusedImport
        from . import tasks  # @UnusedImport
