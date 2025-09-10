import logging
from collections import namedtuple
from time import sleep

import reversion
from django.conf import settings

from heltour.tournament.slackapi import SlackUser

if settings.USE_CHATBACKEND == "slack":
    from heltour.tournament import slackapi


logger = logging.getLogger(__name__)


# helper functions for formatting text
def bold(text: str) -> str:
    if settings.USE_CHATBACKEND == "slack":
        return f"*{text}*"
    else:
        return text


def channellink(
    *, channelprefix: str = "#", channelid: str = "", channel: str, topic: str = ""
) -> str:
    if settings.USE_CHATBACKEND == "/dev/null":
        return ""
    elif settings.USE_CHATBACKEND == "log":
        return (
            f"{channelprefix}{channel}>{topic}"
            if topic
            else f"{channelprefix}{channel}"
        )
    elif settings.USE_CHATBACKEND == "slack":
        if channelid:
            return f"<{channelprefix}{channelid}|{channel}>"
        else:
            return f"{channelprefix}{channel}"
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def chatbackend() -> str:
    if settings.USE_CHATBACKEND == "/dev/null":
        return "/dev/null"
    return settings.USE_CHATBACKEND.capitalize()

def chatbackend_render() -> bool:
    return settings.USE_CHATBACKEND in ["slack", "zulip"]


def chatbackend_url() -> str:
    if settings.USE_CHATBACKEND == "/dev/null":
        return ""
    elif settings.USE_CHATBACKEND == "log":
        return "log"
    elif settings.USE_CHATBACKEND == "slack":
        return settings.SLACK_URL
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def dm_link(*, usernames: list[str], userids: list[str], add_bot: bool) -> str:
    if settings.USE_CHATBACKEND == "/dev/null" or settings.USE_CHATBACKEND == "log":
        return ""
    elif settings.USE_CHATBACKEND == "slack":
        if add_bot:
            usernames.append(settings.SLACK_LISTENING_BOT)
        users = "@" + ",@".join(usernames)
        return f"{settings.SLACK_URL}/messages/{users}"
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def inlinecode(text: str) -> str:
    # same for slack and zulip
    if settings.USE_CHATBACKEND == "slack":
        return f"`{text}`"
    else:
        return text


def italic(text: str) -> str:
    if settings.USE_CHATBACKEND == "slack":
        return f"_{text}_"
    else:
        return text


def link(*, text: str, url: str) -> str:
    if settings.USE_CHATBACKEND == "slack":
        return f"<{url}|{text}>"
    else:
        return url


def ping_mods() -> str:
    if settings.USE_CHATBACKEND == "/dev/null":
        return ""
    elif settings.USE_CHATBACKEND == "log":
        return "@mods"
    elif settings.USE_CHATBACKEND == "slack":
        return f"@{settings.SLACK_LISTENING_BOT} summon mods"
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def userlink_ping(user: str) -> str:
    if settings.USE_CHATBACKEND == "slack":
        return f"<@{user}>"
    else:
        return user


# linking someone without ping is possible on zulip, that is why this is here.
def userlink_silent(user: str) -> str:
    if settings.USE_CHATBACKEND == "slack":
        return f"<@{user}>"
    else:
        return user


# messaging functions


def channel_message(
    *, channel: str, text: str, topic: str = "(no topic)", tries: int = 0
) -> None:
    if settings.USE_CHATBACKEND == "/dev/null":
        return
    elif settings.USE_CHATBACKEND == "log":
        logger.info(f"[CBE] {channel} message:\n{text}")
        return
    elif settings.USE_CHATBACKEND == "slack":
        slackapi.send_message(channel=channel, text=text)
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def send_control_message(text: str, tries: int = 0) -> None:
    if settings.USE_CHATBACKEND == "/dev/null":
        return
    elif settings.USE_CHATBACKEND == "log":
        logger.info(f"[CBE] Control message:\n{text}")
        return
    elif settings.USE_CHATBACKEND == "slack":
        slackapi.send_control_message(text=text)
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def direct_user_message(
    *, username: str, text: str, userid: str, tries: int = 0
) -> None:
    if settings.USE_CHATBACKEND == "/dev/null":
        return
    elif settings.USE_CHATBACKEND == "log":
        logger.info(f"[CBE] Message to {username}:\n{text}")
        return
    elif settings.USE_CHATBACKEND == "slack":
        slackapi.send_message(f"@{username}", text)
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def multiple_user_message(
    *, usernames: list[str], text: str, userids: list[str], tries: int = 0
) -> None:
    if settings.USE_CHATBACKEND == "/dev/null":
        return
    elif settings.USE_CHATBACKEND == "log":
        logger.info(f"[CBE] Message to {usernames}:\n{text}")
        return
    elif settings.USE_CHATBACKEND == "slack":
        slackapi.send_message("+".join((f"@{u}" for u in usernames)), text)
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


# other functions


def create_team_channel(
    *,
    team,
    channel_name: str,
    user_ids: list[str],
    topic: str,
    intro_message: str,
    tries: int = 0,
) -> None:
    if settings.USE_CHATBACKEND == "/dev/null":
        return
    elif settings.USE_CHATBACKEND == "log":
        logger.info(f"[CBE] Team Channel creation '{team}': {user_ids}")
        return
    elif settings.USE_CHATBACKEND == "slack":
        try:
            group = slackapi.create_group(channel_name)
            sleep(settings.SLEEP_UNIT)
        except slackapi.NameTaken:
            logger.error("Could not create slack team, name taken: %s" % channel_name)
            return
        channel_ref = "#%s" % group.name
        try:
            slackapi.invite_to_group(group.id, user_ids)
        except slackapi.SlackError:
            logger.exception("Could not invite %s to channel" % ",".join(user_ids))
            sleep(settings.SLEEP_UNIT)
        try:
            slackapi.invite_to_group(group.id, settings.SLACK_LISTENING_BOT_ID)
            sleep(settings.SLEEP_UNIT)
        except slackapi.SlackError:
            logger.exception(
                "Could not invite the listening bot to "
                f"channel {channel_name} ({group.id})"
            )
        with reversion.create_revision():
            reversion.set_comment("Creating slack channel")
            team.slack_channel = group.id
            team.save()
        try:
            slackapi.set_group_topic(group.id, topic)
            sleep(settings.SLEEP_UNIT)
        except slackapi.SlackError:
            logger.exception(
                f"Failed to set topic for channel {channel_name} ({group.id})"
            )
        try:
            slackapi.leave_group(group.id)
            sleep(settings.SLEEP_UNIT)
        except slackapi.SlackError:
            logger.exception(f"Failed to leave channel {channel_name} ({group.id})")
        try:
            slackapi.send_message(channel_ref, intro_message)
            sleep(settings.SLEEP_UNIT)
        except slackapi.SlackError:
            logger.exception(
                f"Failed to sent intro message to channel {channel_name} ({group.id})"
            )
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def get_user(user_id: str, tries: int = 0) -> namedtuple:
    if settings.USE_CHATBACKEND == "/dev/null":
        return SlackUser(
            id="",
            display_name="",
            email="",
            tz_offset=0,
            real_name="",
            name_deprecated="",
        )
    elif settings.USE_CHATBACKEND == "log":
        logger.info(f"[CBE] Logging request for id: {user_id}")
        return SlackUser(
            id="",
            display_name="",
            email="",
            tz_offset=0,
            real_name="",
            name_deprecated="",
        )
    elif settings.USE_CHATBACKEND == "slack":
        return slackapi.get_user(user_id=user_id)
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def get_user_list(tries: int = 0) -> list[namedtuple]:
    if settings.USE_CHATBACKEND == "/dev/null":
        return []
    elif settings.USE_CHATBACKEND == "log":
        logger.info("[CBE] Logging request to list all users.")
        return []
    elif settings.USE_CHATBACKEND == "slack":
        return slackapi.get_user_list()
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def invite_user(email: str, tries: int = 0) -> None:
    if settings.USE_CHATBACKEND == "/dev/null":
        return
    elif settings.USE_CHATBACKEND == "log":
        logger.info(f"[CBE] Logging request to invite {email}.")
        return
    elif settings.USE_CHATBACKEND == "slack":
        try:
            slackapi.invite_user(email)
        except slackapi.SlackError as e:
            raise InvitationFailedError(repr(e))
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


class ChatBackendError(Exception):
    pass


class InvitationFailedError(ChatBackendError):
    pass
