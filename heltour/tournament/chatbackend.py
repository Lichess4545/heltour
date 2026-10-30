from collections import namedtuple

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from heltour.tournament.chat_client import ChatClient
from heltour.tournament.chat_notifier import Notifier


def make_chat_client(backend: str) -> ChatClient:
    if backend == "slack":
        from heltour.tournament.slackapi import SlackClient

        if not settings.SLACK_API_TOKEN:
            raise ImproperlyConfigured("SLACK_API_TOKEN is not set")
        return SlackClient(api_token=settings.SLACK_API_TOKEN)

    raise ChatBackendError(f"Unknown CHAT_BACKEND: {backend!r}")


chat = make_chat_client(settings.USE_CHATBACKEND)
notifier = Notifier(chat)


def bold(text: str) -> str:
    return notifier.bold(text)


def channellink(
    channel: str, channelprefix: str = "#", channelid: str = "", topic: str = ""
) -> str:
    return notifier.channellink(channel, channelprefix, channelid, topic)


def chatbackend() -> str:
    return notifier.chatbackend()


def chatbackend_render() -> bool:
    return notifier.chatbackend_render()


def chatbackend_url() -> str:
    return notifier.chatbackend_url()


def dm_link(*, usernames: list[str], userids: list[str], add_bot: bool) -> str:
    return notifier.dm_link(usernames, userids, add_bot)


def inlinecode(text: str) -> str:
    return notifier.inlinecode(text)


def italic(text: str) -> str:
    return notifier.italic(text)


def link(*, text: str, url: str) -> str:
    return notifier.link(text, url)


def ping_mods() -> str:
    return notifier.ping_mods()


def userlink_ping(user: str) -> str:
    return notifier.userlink_ping(user)


def userlink_silent(user: str) -> str:
    return notifier.userlink_silent(user)


def channel_message(
    *, channel: str, text: str, topic: str = "(no topic)", tries: int = 0
) -> None:
    notifier.channel_message(channel, text, topic, tries)


def send_control_message(text: str, tries: int = 0) -> None:
    notifier.send_control_message(text, tries)


def direct_user_message(
    *, username: str, text: str, userid: str, tries: int = 0
) -> None:
    notifier.direct_user_message(username, text, userid, tries)


def multiple_user_message(
    *, usernames: list[str], text: str, userids: list[str], tries: int = 0
) -> None:
    notifier.multiple_user_message(usernames, text, userids, tries)


def cb_create_team_channel(
    *,
    team,
    channel_name: str,
    user_ids: list[str],
    topic: str,
    intro_message: str,
    tries: int = 0,
) -> None:
    try:
        notifier.cb_create_team_channel(
            team, channel_name, user_ids, topic, intro_message, tries
        )
    except notifier.ChatBackendError:
        raise ChatBackendError


def get_user(user_id: str, tries: int = 0) -> namedtuple:
    try:
        return notifier.get_user(user_id, tries)
    except notifier.ChatBackendError:
        raise ChatBackendError


def get_user_list(tries: int = 0) -> list[namedtuple]:
    try:
        return notifier.get_user_list(tries)
    except notifier.ChatBackendError:
        raise ChatBackendError


def invite_user(email: str, tries: int = 0) -> None:
    try:
        return notifier.invite_user(email, tries)
    except notifier.InvitationFailedError:
        raise InvitationFailedError()


class ChatBackendError(Exception):
    pass


class InvitationFailedError(ChatBackendError):
    pass
