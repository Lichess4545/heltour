import logging
from collections import namedtuple

import requests

from django.conf import settings


logger = logging.getLogger(__name__)


def _get_slack_token():
    with open(settings.SLACK_API_TOKEN_FILE_PATH) as fin:
        return fin.read().strip()

def _get_slack_channel_builder_token():
    with open(settings.SLACK_CHANNEL_BUILDER_TOKEN_FILE_PATH) as fin:
        return fin.read().strip()

def _get_slack_webhook():
    try:
        with open(settings.SLACK_WEBHOOK_FILE_PATH) as fin:
            return fin.read().strip()
    except (IOError, IndexError):
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


SlackUser = namedtuple('SlackUser',
                       ['id', 'name_deprecated', 'real_name', 'display_name', 'email', 'tz_offset'])
SlackGroup = namedtuple('SlackGroup', ['id', 'name'])


def get_user_list():
    url = 'https://slack.com/api/users.list'
    r = requests.get(url, params={'token': _get_slack_token()})
    json = r.json()
    if not json['ok']:
        raise SlackError(json['error'])
    return [SlackUser(m['id'], m.get('name'), m['profile'].get('real_name'),
                      m['profile'].get('display_name'), m['profile'].get('email', ''),
                      m.get('tz_offset')) for m in json['members']]


def get_user(user_id):
    url = 'https://slack.com/api/users.info'
    r = requests.get(url, params={'user': user_id, 'token': _get_slack_token()})
    json = r.json()
    if not json['ok']:
        raise SlackError(json['error'])
    m = json['user']
    return SlackUser(m['id'], m.get('name'), m['profile'].get('real_name'),
                     m['profile'].get('display_name'), m['profile'].get('email', ''),
                     m.get('tz_offset'))


def send_message(channel, text):
    url = _get_slack_webhook()
    if not url:
        # Not configured
        if settings.DEBUG:
            print('[%s]: %s' % (channel, text))
        logger.error('Could not send slack message to %s' % channel)
        return
    r = requests.post(url,
                      json={'text': 'forward to %s' % channel, 'attachments': [{'text': text}]})
    if r.text == '' or r.text == 'ok':
        # OK
        logger.info('Slack [%s]: %s' % (channel, text))
    else:
        # Unexpected error
        logger.error('Could not send slack message to %s, error %s' % (channel, r.text))


def send_control_message(text):
    url = _get_slack_webhook()
    if not url:
        # Not configured
        if settings.DEBUG:
            print('[control]: %s' % text)
        logger.error('Could not send slack control message')
        return
    r = requests.post(url, json={'text': text})
    if r.text == '' or r.text == 'ok':
        # OK
        logger.info('Slack [control]: %s' % text)
    else:
        # Unexpected error
        logger.error('Could not send slack control message, error %s' % r.text)


def create_group(group_name):
    url = 'https://slack.com/api/conversations.create'
    r = requests.post(url, params={'name': group_name, 'is_private':'true'},
                      headers={'Authorization': _get_slack_channel_builder_token()})
    json = r.json()
    if not json['ok']:
        if json['error'] == 'name_taken':
            raise NameTaken
        raise SlackError(json['error'])
    g = json['channel']
    return SlackGroup(g['id'], g['name'])


def invite_to_group(group_id, user_ids):
    url = 'https://slack.com/api/conversations.invite'
    r = requests.post(url,
                     params={'channel': group_id, 'users': ",".join(user_ids)},
                     headers={'Authorization': _get_slack_channel_builder_token()})
    json = r.json()
    if not json['ok']:
        raise SlackError(json['error'])


def set_group_topic(group_id, topic):
    url = 'https://slack.com/api/conversations.setTopic'
    r = requests.post(url, params={'channel': group_id, 'topic': topic},
                     headers={'Authorization': _get_slack_channel_builder_token()})
    json = r.json()
    if not json['ok']:
        raise SlackError(json['error'])


def leave_group(group_id):
    url = 'https://slack.com/api/conversations.leave'
    r = requests.get(url, params={'channel': group_id},
                     headers={'Authorization': _get_slack_channel_builder_token()})
    json = r.json()
    if not json['ok']:
        raise SlackError(json['error'])


class SlackError(Exception):
    pass


class AlreadyInvited(SlackError):
    pass


class AlreadyInTeam(SlackError):
    pass


class NameTaken(SlackError):
    pass
