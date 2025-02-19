from heltour.settings import ZULIP_CONFIG, ZULIP_CONFIG_NOBOT, ZULIP_ERROR_LOGGING, ZULIP_ERROR_LOG
from collections import namedtuple
from datetime import datetime
from zulip import Client
import logging
import pytz


logger = logging.getLogger(__name__)

SlackUser = namedtuple('SlackUser',
        ['id', 'display_name', 'email', 'tz_offset'])
SlackGroup = namedtuple('SlackGroup', ['id', 'name'])


def _initial_connection():
    try:
        client = Client(config_file=ZULIP_CONFIG, client='ZulipHeltour') 
        register = client.register(event_types=['realm'])
        if not register['result'] == 'success':
            raise ZulipError(f'ERROR in getting client register: {register["msg"]}')
        else:
            try:
                max_topic_length = register['max_topic_length']
                max_message_length = register['max_message_length']
                max_stream_name_length = register['max_stream_name_length']
                max_stream_description_length = register['max_stream_description_length']
            except KeyError:
                logger.error('ERROR: Realm response does not contain zulip server setting for max lengths of topics/message/stream_name/stream_description')
                return
    except:
        logger.error('ERROR: Could not connect to zulip')
        return
    return max_topic_length, max_message_length, max_stream_name_length, max_stream_description_length, client


_max_topic_length, _max_message_length, _max_stream_name_length, _max_stream_description_length, _client = _initial_connection()


def invite_user(email, *args, **kwargs):
    params = {
        'invitee_emails': email,
        'invite_expires_in_minutes': 60*24*7*4, # 4 weeks
        'invite_as': 600, # 600: guest, 400: member
        'stream_ids': [], # none, because we can modify default_subscriptions easily, and we do not have any special invitees
        'include_realm_default_subscriptions': 'true',
        'notify_referrer_on_join': 'false',
        }
    try:
        human_client = Client(config_file=ZULIP_CONFIG_NOBOT, client='ZulipHeltour')
    except:
        raise ZulipError('ERROR connecting human client for user invitations.')
        return
    r = human_client.call_endpoint(url="/invites", method="POST", request=params)
    if not r['result'] == 'success':
        if ZULIP_ERROR_LOGGING:
            send_message(channel=ZULIP_ERROR_LOG, text=f'Could not invite {email}\nError Code: {r["code"]}\nError msg: {r["msg"]}')
        if r['code'] == 'INVITATION_FAILED':
            raise AlreadyInTeamError(r['msg'])
        elif r['code'] == 'BAD_REQUEST':
            raise BadRequestError(r['msg'])
        elif r['code'] == 'RATE_LIMIT_HIT':
            raise ZulipRateLimitHit(message=r['msg'], wait=r['retry-after'])
        else:
            raise ZulipError(r['msg'])
    else:
        logger.info(f'Zulip: invited {email} to zulip')


def get_user_list():
    r = _client.get_users()
    if not r['result'] == 'success':
        if ZULIP_ERROR_LOGGING:
            send_message(channel=ZULIP_ERROR_LOG, text=f'Could not retrieve user list.\nError Code: {r["code"]}\nError msg: {r["msg"]}')
        if r['code'] == 'RATE_LIMIT_HIT':
            raise ZulipRateLimitHit(message=r['msg'], wait=r['retry-after'])
        else:
            raise ZulipError(r['msg'])
    result = []
    for m in r['members']:
        tz = m.get('timezone')
        if tz:
            tzseconds = pytz.timezone(tz).localize(datetime.now()).utcoffset().total_seconds()
        else:
            tzseconds = 0.0
        result.append(SlackUser(str(m.get('user_id')), m.get('full_name'), m.get('delivery_email'), tzseconds))
    return result


def get_user(user_id):
    r = _client.get_user_by_id(user_id)
    if not r['result'] == 'success':
        if ZULIP_ERROR_LOGGING:
            send_message(channel=ZULIP_ERROR_LOG, text=f'Could not retrieve user {user_id}.\nError Code: {r["code"]}\nError msg: {r["msg"]}')
        if r['code'] == 'RATE_LIMIT_HIT':
            raise ZulipRateLimitHit(message=r['msg'], wait=r['retry-after'])
        else:
            raise ZulipError(r['msg'])
    m = r['user']
    tz = m.get('timezone')
    if tz:
        tzseconds = pytz.timezone(m.get('timezone')).localize(datetime.now()).utcoffset().total_seconds()
    else:
        tzseconds = 0.0
    return SlackUser(str(m.get('user_id')), m.get('full_name'), m.get('email'), tzseconds)


def _message(*, channel, channel_type, text, topic='(no topic)'):
    if len(topic) > _max_topic_length:
        logger.warning(f'topic length exceeds max_topic_length {_max_topic_length}, cutting it.')
        topic = topic[:_max_topic_length]
    if len(text) > _max_message_length:
        logger.warning(f'message length exceeds max_message_length {_max_message_length}, cutting it.')
        text = text[:_max_message_length]

    if channel_type == 'channel':
        params = {
                'type': channel_type,
                'to': channel[1:] if not isinstance(channel, int) and '#' in channel else channel,
                'content': text,
                'topic': topic,
                }
    elif channel_type == 'direct':
        params = {
                'type': channel_type,
                'to': channel,
                'content': text,
                }
    else:
        raise ZulipError(f'Unkown channel_type "{channel_type}"')
    r = _client.send_message(params)
    if r['result']!='success':
        if ZULIP_ERROR_LOGGING and not f'{channel}>{topic}' == ZULIP_ERROR_LOG: # prevent trying to send errors about failed error messages to prevent infinite recursion when zulip is down or something
            send_message(channel=ZULIP_ERROR_LOG, text=(f'Could not send message to {channel}>{topic}.\nError Code: {r["code"]}\nError msg: {r["msg"]}'))
        logger.error(f'Could not send message to {channel}>{topic}, error:\n{r["msg"]}')
        if r['code'] == 'RATE_LIMIT_HIT':
            raise ZulipRateLimitHit(message=r['msg'], wait=r['retry-after'])
        else:
            raise ZulipError(r['msg'])
    else:
        logger.info(f'Zulip [{channel} > {topic}]: {text}')


def send_forward_message(*, channel, text):
    _message(channel='msg-forward', channel_type='channel', text=f'forward to {channel}\n>{text}', topic='logging')


def send_message(*, channel, text, topic='(no topic)'):
    if not isinstance(channel, int) and '>' in channel:
        channel_split = channel.partition('>')
        _message(channel=channel_split[0], channel_type='channel', text=text, topic=channel_split[2])
    else:
        _message(channel=channel, channel_type='channel', text=text, topic=topic)


def send_direct_message(*, users, text):
    _message(channel=users, channel_type='direct', text=text, topic='')


def send_control_message(text):
    _message(channel='msg-forward', channel_type='channel', text=text, topic='control')


def _get_channel_id(channel_name):
    r = _client.get_stream_id(channel_name)
    if r['result']!='success':
        if r['code'] == 'RATE_LIMIT_HIT':
            raise ZulipRateLimitHit(message=r['msg'], wait=r['retry-after'])
        else:
            raise ZulipError(r['msg'])
    return(r['stream_id'])


def create_channel(channel_name, user_ids, topic="", invite_only=True, history_public=False,
                   can_add_subscribers_ids=[], can_add_subscribers_groups=[],
                   can_remove_subscribers_ids=[], can_remove_subscribers_groups=[],
                   can_admin_channel_ids=[], can_admin_channel_groups=[],
                   ):
    if len(channel_name) > _max_stream_name_length:
        logger.warning(f'channel name length exceeds max_stream_name_length {_max_stream_name_length}, cutting it.')
        channel_name = channel_name[:_max_stream_name_length]
    if len(topic) > _max_stream_description_length:
        logger.warning(f'channel description length exceeds max_stream_description_length {_max_stream_description_length}, cutting it.')
        topic = topic[:_max_stream_description_length]
    if topic:
        stream=[{
            'name': channel_name,
            'description': topic,
            'invite_only': invite_only,
            'history_public_to_subscribers': history_public,
            }]
    else: 
        stream=[{
            'name': channel_name,
            'invite_only': invite_only,
            'history_public_to_subscribers': history_public,
            }]
    r = _client.add_subscriptions(streams=stream, principals=user_ids, invite_only=invite_only,
                                  history_public_to_subscribers=history_public,
                                  can_add_subscribers_group={'direct_members': can_add_subscribers_ids,
                                                             'direct_subgroups': can_add_subscribers_groups},
                                  can_remove_subscribers_group={'direct_members': can_remove_subscribers_ids,
                                                             'direct_subgroups': can_remove_subscribers_groups},
                                  can_administer_channel_group={'direct_members': can_admin_channel_ids,
                                                           'direct_subgroups': can_admin_channel_groups})
    if r['result']!='success':
        if ZULIP_ERROR_LOGGING:
            send_message(channel=ZULIP_ERROR_LOG, text=(f'Could not create channel {channel_name} for user ids {user_ids}.\nError Code: {r["code"]}\nError msg: {r["msg"]}'))
        if r['code'] == 'RATE_LIMIT_HIT':
            raise ZulipRateLimitHit(message=r['msg'], wait=r['retry-after'])
        else:
            raise ZulipError(r['msg'])
    channel_id = _get_channel_id(channel_name)
    return SlackGroup(channel_id, channel_name)


def invite_to_group(channel_name, user_ids):
    create_channel(channel_name=channel_name, user_ids=user_ids)


class ZulipError(Exception):
    pass


class AlreadyInTeamError(ZulipError):
    pass


class BadRequestError(ZulipError):
    pass


class ZulipRateLimitHit(ZulipError):
    def __init__(self, message, wait, *args):
        self.message = message 
        self.wait = wait
        super(ZulipRateLimitHit, self).__init__(message, wait, *args)
