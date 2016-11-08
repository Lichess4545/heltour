import requests
from heltour import settings
from collections import namedtuple

def _get_slack_token():
    with open(settings.SLACK_API_TOKEN_FILE_PATH) as fin:
        return fin.read().strip()

def _get_slack_webhook():
    try:
        with open(settings.SLACK_WEBHOOK_FILE_PATH) as fin:
            return fin.read().strip()
    except IOError:
        return None

def invite_user(email):
    url = 'https://slack.com/api/users.admin.invite'
    r = requests.get(url, params={'token': _get_slack_token(), 'email': email})
    json = r.json()
    if not json['ok']:
        if json['error'] == 'already_invited':
            raise AlreadyInvited
        if json['error'] == 'already_in_team':
            raise AlreadyInTeam
        raise SlackError(json['error'])

SlackUser = namedtuple('SlackUser', ['name', 'email'])

def get_user_list():
    url = 'https://slack.com/api/users.list'
    r = requests.get(url, params={'token': _get_slack_token()})
    json = r.json()
    if not json['ok']:
        raise SlackError(json['error'])
    return [SlackUser(m['name'], m['profile'].get('email', '')) for m in json['members']]

def send_message(channel, text):
    url = _get_slack_webhook()
    if not url:
        # Not configured
        if settings.DEBUG:
            print 'Sending slack notification: ', text
        return
    requests.post(url, json={'channel': channel, 'text': text})

class SlackError(Exception):
    pass

class AlreadyInvited(SlackError):
    pass

class AlreadyInTeam(SlackError):
    pass
