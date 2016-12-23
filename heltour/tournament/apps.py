from __future__ import unicode_literals

from django.apps import AppConfig

class TournamentConfig(AppConfig):
    name = 'heltour.tournament'

    def ready(self):
        import uptime # @UnusedImport
        # Make sure signal handlers are registered
        import notify # @UnusedImport
        import tasks # @UnusedImport
