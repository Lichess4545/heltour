from datetime import timedelta

DEBUG = True
GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH = '/home/ben/gspread-creds.json'
SLACK_API_TOKEN_FILE_PATH = '/home/ben/slack-token'
SLACK_WEBHOOK_FILE_PATH = '/home/ben/slack-webhook'
FCM_API_KEY_FILE_PATH = '/home/ben/fcm-key'
LICHESS_DOMAIN = 'https://listage.ovh/'
JAVAFO_COMMAND = 'java -jar /home/ben/javafo.jar'
LINK_PROTOCOL = 'http'

INTERNAL_IPS = ['127.0.0.1', '192.168.56.101', 'localhost']
ALLOWED_HOSTS = INTERNAL_IPS

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

CELERYBEAT_SCHEDULE = {
    # 'alternates_manager_tick': {
    #     'task': 'heltour.tournament.tasks.alternates_manager_tick',
    #     'schedule': timedelta(seconds=5),
    #     'args': ()
    # },
    # 'update_tv_state': {
    #     'task': 'heltour.tournament.tasks.update_tv_state',
    #     'schedule': timedelta(seconds=20),
    #     'args': ()
    # },
    'run_scheduled_events': {
        'task': 'heltour.tournament.tasks.run_scheduled_events',
        'schedule': timedelta(seconds=5),
        'args': ()
    },
}
