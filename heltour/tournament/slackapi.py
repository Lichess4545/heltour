import requests
from heltour import settings

def _get_slack_token():
    with open(settings.SLACK_API_TOKEN_FILE_PATH) as fin:
        return fin.read().strip()

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

class SlackError(Exception):
    pass

class AlreadyInvited(SlackError):
    pass

class AlreadyInTeam(SlackError):
    pass
