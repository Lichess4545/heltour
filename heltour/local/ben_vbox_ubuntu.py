from datetime import timedelta
DEBUG = True
GOOGLE_SERVICE_ACCOUNT_KEYFILE_PATH = '/home/ben/gspread-creds.json'
SLACK_API_TOKEN_FILE_PATH = '/home/ben/slack-token'
SLACK_WEBHOOK_FILE_PATH = '/home/ben/slack-webhook'
LICHESS_CREDS_FILE_PATH = '/home/ben/lichess-creds'
FCM_API_KEY_FILE_PATH = '/home/ben/fcm-key'
LICHESS_DOMAIN = 'https://en.stage.lichess.org/'
JAVAFO_COMMAND = 'java -jar /home/ben/javafo.jar'

INTERNAL_IPS = ['127.0.0.1', '192.168.56.100']

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

CELERYBEAT_SCHEDULE = {
    'alternates_manager_tick': {
        'task': 'heltour.tournament.tasks.alternates_manager_tick',
        'schedule': timedelta(seconds=10),
        'args': ()
    },
}
