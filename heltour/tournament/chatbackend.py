import logging
from time import sleep

import reversion
from django.conf import settings

if settings.USE_CHATBACKEND == "zulip":
    from heltour.tournament import zulipapi
if settings.USE_CHATBACKEND == "slack":
    from heltour.tournament import slackapi


logger = logging.getLogger(__name__)


# helper functions for formatting text
def bold(text):
    if settings.USE_CHATBACKEND == "zulip":
        return f"**{text}**"
    elif settings.USE_CHATBACKEND == "slack":
        return f"*{text}*"
    else:
        return text


def channellink(*, channelprefix="#", channelid="", channel, topic=""):
    if settings.USE_CHATBACKEND == "zulip":
        if topic:
            return f"{channelprefix}**{channel}>{topic}**"
        else:
            return f"{channelprefix}**{channel}**"
    elif settings.USE_CHATBACKEND == "slack":
        if channelid:
            return f"<{channelprefix}{channelid}|{channel}>"
        else:
            return f"{channelprefix}{channel}"
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def chatbackend():
    return settings.USE_CHATBACKEND.capitalize()


def chatbackend_url():
    if settings.USE_CHATBACKEND == "zulip":
        return settings.ZULIP_URL
    elif settings.USE_CHATBACKEND == "slack":
        return settings.SLACK_URL
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def dm_link(*, usernames, userids, add_bot):
    if settings.USE_CHATBACKEND == "zulip":
        if add_bot:
            userids.append(settings.ZULIP_LISTENING_BOT)
        users = ",".join(str(u) for u in userids)
        return f"{settings.ZULIP_URL}/#narrow/dm/{users}-group"
    elif settings.USE_CHATBACKEND == "slack":
        if add_bot:
            usernames.append(settings.SLACK_LISTENING_BOT)
        users = "@" + ",@".join(usernames)
        return f"{settings.SLACK_URL}/messages/{users}"
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def inlinecode(text):
    # same for slack and zulip
    return f"`{text}`"


def italic(text):
    if settings.USE_CHATBACKEND == "zulip":
        return f"*{text}*"
    elif settings.USE_CHATBACKEND == "slack":
        return f"_{text}_"
    else:
        return text


def link(*, text, url):
    if settings.USE_CHATBACKEND == "zulip":
        return f"[{text}]({url})"
    elif settings.USE_CHATBACKEND == "slack":
        return f"<{url}|{text}>"
    else:
        return url


def ping_mods():
    if settings.USE_CHATBACKEND == "zulip":
        return "@*mods4545*"
    elif settings.USE_CHATBACKEND == "slack":
        return f"@{settings.SLACK_LISTENING_BOT} summon mods"
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def userlink_ping(user):
    if settings.USE_CHATBACKEND == "zulip":
        return f"@**{user}**"
    elif settings.USE_CHATBACKEND == "slack":
        return f"<@{user}>"
    else:
        return user


def userlink_silent(user):
    if settings.USE_CHATBACKEND == "zulip":
        return f"@_**{user}**"
    elif settings.USE_CHATBACKEND == "slack":
        return f"<@{user}>"
    else:
        return user


# messaging functions


def channel_message(*, channel, text, topic="(no topic)", tries=0):
    if settings.USE_CHATBACKEND == "zulip":
        try:
            zulipapi.send_message(channel=channel, text=text, topic=topic)
        except zulipapi.ZulipRateLimitHit as e:
            if tries < 1:
                logger.error(
                    "Error: Hit Rate Limit. "
                    f"Waiting for {2*e.wait} seconds before retrying once."
                )
                sleep(2 * e.wait)
                zulipapi.send_message(channel=channel, text=text, topic=topic, tries=1)
            else:
                logger.error(f"Error: Hit Rate Limit twice. Giving up.\n{e.message}")
        except zulipapi.ZulipError as e:
            logger.error(f"Error sending Zulip message:\n{e}")
    elif settings.USE_CHATBACKEND == "slack":
        slackapi.send_message(channel=channel, text=text)
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def send_control_message(text):
    if settings.USE_CHATBACKEND == "zulip":
        try:
            zulipapi.send_control_message(text=text)
        except zulipapi.ZulipRateLimitHit as e:
            if tries < 0:
                logger.error(
                    "Error: Hit Rate Limit. "
                    f"Waiting for {2*e.wait} seconds before retrying once."
                )
                sleep(2 * e.wait)
                zulipapi.send_direct_message(users=[int(userid)], text=text, tries=1)
            else:
                logger.error(f"Error: Hit Rate Limit twice. Giving up.\n{e.message}")
        except zulipapi.ZulipError as e:
            logger.error(f"Error sending Zulip message:\n{e}")
    elif settings.USE_CHATBACKEND == "slack":
        slackapi.send_control_message(text=text)
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def direct_user_message(*, username, text, userid, tries=0):
    if settings.USE_CHATBACKEND == "zulip":
        try:
            zulipapi.send_direct_message(users=[int(userid)], text=text)
        except zulipapi.ZulipRateLimitHit as e:
            if tries < 0:
                logger.error(
                    "Error: Hit Rate Limit. "
                    f"Waiting for {2*e.wait} seconds before retrying once."
                )
                sleep(2 * e.wait)
                zulipapi.send_direct_message(users=[int(userid)], text=text, tries=1)
            else:
                logger.error(f"Error: Hit Rate Limit twice. Giving up.\n{e.message}")
        except zulipapi.ZulipError as e:
            logger.error(f"Error sending Zulip message:\n{e}")

    elif settings.USE_CHATBACKEND == "slack":
        slackapi.send_message(f"@{username}", text)
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def multiple_user_message(*, usernames, text, userids, tries=0):
    if settings.USE_CHATBACKEND == "zulip":
        userids_int = list(map(int, userids))
        userids_int.append(settings.ZULIP_LISTENING_BOT)
        try:
            zulipapi.send_direct_message(users=userids_int, text=text)
        except zulipapi.ZulipRateLimitHit as e:
            if tries < 0:
                logger.error(
                    "Error: Hit Rate Limit. "
                    f"Waiting for {2*e.wait} seconds before retrying once."
                )
                sleep(2 * e.wait)
                zulipapi.send_direct_message(users=userids_int, text=text, tries=1)
            else:
                logger.error(f"Error: Hit Rate Limit twice. Giving up.\n{e.message}")
        except zulipapi.ZulipError as e:
            logger.error(f"Error sending Zulip message:\n{e}")
            return
    elif settings.USE_CHATBACKEND == "slack":
        slackapi.send_message("+".join((f"@{u}" for u in usernames)), text)
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


# other functions


def create_team_channel(*, team, channel_name, user_ids, topic, intro_message, tries=0):
    if settings.USE_CHATBACKEND == "zulip":
        user_ids_ext = list(map(int, user_ids))
        user_ids_ext.extend([settings.ZULIP_LISTENING_BOT, settings.ZULIP_HELTOUR_BOT])
        try:
            channel = zulipapi.create_channel(
                channel_name=channel_name,
                user_ids=user_ids_ext,
                topic=topic,
                invite_only=True,
                history_public=False,
                can_add_subscribers_ids=user_ids_ext,
                can_remove_subscribers_ids=user_ids_ext,
                can_admin_channel_ids=user_ids_ext,
            )
        except zulipapi.ZulipRateLimitHit as e:
            if tries < 1:
                logger.error(
                    "Error: Hit Rate Limit. "
                    f"Waiting for {e.wait + 10} seconds before retrying once."
                )
                sleep(e.wait + 10)
                channel = zulipapi.create_channel(
                    channel_name=channel_name,
                    user_ids=user_ids_ext,
                    topic=topic,
                    invite_only=True,
                    history_public=False,
                    can_add_subscribers_ids=user_ids_ext,
                    can_remove_subscribers_ids=user_ids_ext,
                    can_admin_channel_ids=user_ids_ext,
                    tries=1,
                )
            else:
                logger.error(f"Error: Hit Rate limit twice. Giving up.\n{e.message}")
                return
        except zulipapi.ZulipError as e:
            logger.error(
                "Could not create slack team, name probably taken: "
                f"{channel_name}\nError msg: {e.message}"
            )
            return
        with reversion.create_revision():
            reversion.set_comment("Creating zulip channel")
            team.slack_channel = channel.id
            team.save()
        channel_message(channel=int(channel.id), text=intro_message, topic="Welcome!")
        sleep(1)
    elif settings.USE_CHATBACKEND == "slack":
        try:
            group = slackapi.create_group(channel_name)
            sleep(1)
        except slackapi.NameTaken:
            logger.error("Could not create slack team, name taken: %s" % channel_name)
            return
        channel_ref = "#%s" % group.name
        try:
            slackapi.invite_to_group(group.id, user_ids)
        except slackapi.SlackError:
            logger.exception("Could not invite %s to channel" % ",".join(user_ids))
            sleep(1)
        slackapi.invite_to_group(group.id, settings.SLACK_LISTENING_BOT_ID)
        sleep(1)
        with reversion.create_revision():
            reversion.set_comment("Creating slack channel")
            team.slack_channel = group.id
            team.save()
        slackapi.set_group_topic(group.id, topic)
        sleep(1)
        slackapi.leave_group(group.id)
        sleep(1)
        slackapi.send_message(channel_ref, intro_message)
        sleep(1)
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def get_user(user_id, tries=0):
    if settings.USE_CHATBACKEND == "zulip":
        try:
            return zulipapi.get_user(user_id=int(user_id))
        except zulipapi.ZulipRateLimitHit as e:
            if tries < 1:
                logger.error(
                    f"Error: Hit Rate Limit. Waiting for {2*e.wait} seconds before retrying once."
                )
                sleep(2 * e.wait)
                zulipapi.get_user(user_id, tries=1)
            else:
                logger.error(f"Error: Hit Rate Limit twice. Giving up.\n{e.message}")
        except zulipapi.ZulipError as e:
            logger.error(f"Could not get user {user_id}.\nError msg: {e.message}")
            raise InvitationFailedError(repr(e))
    elif settings.USE_CHATBACKEND == "slack":
        return slackapi.get_user(user_id=user_id)
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def get_user_list(tries=0):
    if settings.USE_CHATBACKEND == "zulip":
        try:
            return zulipapi.get_user_list()
        except zulipapi.ZulipRateLimitHit as e:
            if tries < 1:
                logger.error(
                    "Error: Hit Rate Limit. "
                    f"Waiting for {2*e.wait} seconds before retrying once."
                )
                sleep(2 * e.wait)
                zulipapi.get_user_list(tries=1)
            else:
                logger.error(f"Error: Hit Rate Limit twice. Giving up.\n{e.message}")
        except zulipapi.ZulipError as e:
            logger.error(f"Could get user list.\nError msg: {e.message}")
            raise InvitationFailedError(repr(e))
    elif settings.USE_CHATBACKEND == "slack":
        return slackapi.get_user_list()
    else:
        raise ChatBackendError(
            "ERROR: Unknown chat backend in settings.USE_CHATBACKEND"
        )


def invite_user(email, tries=0):
    if settings.USE_CHATBACKEND == "zulip":
        try:
            zulipapi.invite_user(email)
        except zulipapi.ZulipRateLimitHit as e:
            if tries < 1:
                logger.error(
                    "Error: Hit Rate Limit. "
                    f"Waiting for {2*e.wait} seconds before retrying once."
                )
                sleep(2 * e.wait)
                zulipapi.invite_user(email, tries=1)
            else:
                logger.error(f"Error: Hit Rate Limit twice. Giving up.\n{e.message}")
        except zulipapi.ZulipError as e:
            logger.error(f"Could invite user {email}.\nError msg: {e.message}")
            raise InvitationFailedError(repr(e))
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
