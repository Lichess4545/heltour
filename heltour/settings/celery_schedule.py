from datetime import timedelta

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "update-ratings": {
        "task": "heltour.tournament.tasks.update_player_ratings",
        "schedule": timedelta(minutes=60),
        "args": (),
    },
    "update-tv-state": {
        "task": "heltour.tournament.tasks.update_tv_state",
        "schedule": timedelta(minutes=5),
        "args": (),
    },
    "update-slack-users": {
        "task": "heltour.tournament.tasks.update_slack_users",
        "schedule": timedelta(minutes=30),
        "args": (),
    },
    "populate-historical-ratings": {
        "task": "heltour.tournament.tasks.populate_historical_ratings",
        "schedule": timedelta(minutes=60),
        "args": (),
    },
    "run_scheduled_events": {
        "task": "heltour.tournament.tasks.run_scheduled_events",
        "schedule": timedelta(minutes=10),
        "args": (),
    },
    "alternates_manager_tick": {
        "task": "heltour.tournament.tasks.alternates_manager_tick",
        "schedule": timedelta(minutes=2),
        "args": (),
    },
    "update_lichess_presence": {
        "task": "heltour.tournament.tasks.update_lichess_presence",
        "schedule": timedelta(minutes=1),
        "args": (),
    },
    "celery_is_up": {
        "task": "heltour.tournament.tasks.celery_is_up",
        "schedule": timedelta(minutes=5),
        "args": (),
    },
    "start_games": {
        "task": "heltour.tournament.tasks.start_games",
        "schedule": crontab(minute="*/5"),
        "args": (),
    },
}
