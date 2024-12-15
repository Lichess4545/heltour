from django.apps import AppConfig


class TournamentConfig(AppConfig):
    name = "heltour.tournament"

    def ready(self):
        # Make sure signal handlers are registered
        pass  # @UnusedImport
