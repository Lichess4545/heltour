import logging
from collections import namedtuple
from time import sleep

import requests
import reversion
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from heltour.tournament.chat_client import ChatClient

logger = logging.getLogger(__name__)


SlackUser = namedtuple(
    "SlackUser",
    ["id", "name_deprecated", "real_name", "display_name", "email", "tz_offset"],
)
SlackGroup = namedtuple("SlackGroup", ["id", "name"])


class SlackClient(ChatClient):
    def __init__(self, api_token: str) -> None:
        self.api_token = api_token

    def _get_slack_token(self):
        if not settings.SLACK_API_TOKEN:
            raise ImproperlyConfigured("SLACK_API_TOKEN is not set")
        return settings.SLACK_API_TOKEN

    def _get_slack_webhook(self):
        return settings.SLACK_WEBHOOK_URL or None

    def _get_slack_channel_builder_token(self):
        if not settings.SLACK_CHANNEL_BUILDER_TOKEN:
            raise ImproperlyConfigured("SLACK_CHANNEL_BUILDER_TOKEN is not set")
        return settings.SLACK_CHANNEL_BUILDER_TOKEN

    def _create_group(self, group_name):
        url = "https://slack.com/api/conversations.create"
        r = requests.post(
            url,
            params={"name": group_name, "is_private": "true"},
            headers={"Authorization": self._get_slack_channel_builder_token()},
        )
        json = r.json()
        if not json["ok"]:
            if json["error"] == "name_taken":
                raise self.ChatBackendError
            raise self.ChatBackendError(json["error"])
        g = json["channel"]
        return SlackGroup(g["id"], g["name"])

    def _invite_to_group(self, group_id, user_ids):
        url = "https://slack.com/api/conversations.invite"
        r = requests.post(
            url,
            params={"channel": group_id, "users": ",".join(user_ids)},
            headers={"Authorization": self._get_slack_channel_builder_token()},
        )
        json = r.json()
        if not json["ok"]:
            raise self.ChatBackendError(json["error"])

    def _leave_group(self, group_id):
        url = "https://slack.com/api/conversations.leave"
        r = requests.get(
            url,
            params={"channel": group_id},
            headers={"Authorization": self._get_slack_channel_builder_token()},
        )
        json = r.json()
        if not json["ok"]:
            raise self.ChatBackendError(json["error"])

    def _set_group_topic(self, group_id, topic):
        url = "https://slack.com/api/conversations.setTopic"
        r = requests.post(
            url,
            params={"channel": group_id, "topic": topic},
            headers={"Authorization": self._get_slack_channel_builder_token()},
        )
        json = r.json()
        if not json["ok"]:
            raise self.ChatBackendError(json["error"])

    def bold(self, text: str) -> str:
        return f"*{text}*"

    def channellink(
        self,
        channel: str,
        channelprefix: str = "#",
        channelid: str = "",
        topic: str = "",
    ) -> str:
        if channelid:
            return f"<{channelprefix}{channelid}|{channel}>"
        else:
            return f"{channelprefix}{channel}"

    def chatbackend(self) -> str:
        return "Slack"

    def chatbackend_render(self) -> bool:
        return True

    def chatbackend_url(self) -> str:
        return settings.SLACK_URL

    def dm_link(self, usernames: list[str], userids: list[str], add_bot: bool) -> str:
        if add_bot:
            usernames.append(settings.SLACK_LISTENING_BOT)
        users = "@" + ",@".join(usernames)
        return f"{settings.SLACK_URL}/messages/{users}/"

    def inlinecode(self, text: str) -> str:
        return f"`{text}`"

    def italic(self, text: str) -> str:
        return f"_{text}_"

    def link(self, text: str, url: str) -> str:
        return f"<{url}|{text}>"

    def ping_mods(self) -> str:
        return f"@{settings.SLACK_LISTENING_BOT} summon mods"

    def userlink_ping(self, user: str) -> str:
        return f"<@{user}>"

    def userlink_silent(self, user: str) -> str:
        return self.userlink_ping(user)

    def channel_message(
        self, channel: str, text: str, topic: str = "(no topic)", tries: int = 0
    ) -> None:
        url = self._get_slack_webhook()
        if not url:
            # Not configured
            if settings.DEBUG:
                print(f"[{channel}]: {text}")
            logger.error(f"Could not send slack message to {channel}")
            return
        r = requests.post(
            url, json={"text": f"forward to {channel}", "attachments": [{"text": text}]}
        )
        if r.text == "" or r.text == "ok":
            # OK
            logger.info(f"Slack [{channel}]: {text}")
        else:
            # Unexpected error
            logger.error(f"Could not send slack message to {channel}, error {r.text}")

    def send_control_message(self, text: str, tries: int = 0) -> None:
        url = self._get_slack_webhook()
        if not url:
            # Not configured
            if settings.DEBUG:
                print("[control]: %s" % text)
            logger.error("Could not send slack control message")
            return
        r = requests.post(url, json={"text": text})
        if r.text == "" or r.text == "ok":
            # OK
            logger.info("Slack [control]: %s" % text)
        else:
            # Unexpected error
            logger.error("Could not send slack control message, error %s" % r.text)

    def direct_user_message(
        self, username: str, text: str, userid: str, tries: int = 0
    ) -> None:
        self.channel_message(channel=f"@{username}", text=text)

    def multiple_user_message(
        self, usernames: list[str], text: str, userids: list[str], tries: int = 0
    ) -> None:
        self.channel_message(channel="+".join(f"@{u}" for u in usernames), text=text)

    def cb_create_team_channel(
        self,
        team,
        channel_name: str,
        user_ids: list[str],
        topic: str,
        intro_message: str,
        tries: int = 0,
    ) -> None:
        try:
            group = self._create_group(channel_name)
            sleep(settings.SLEEP_UNIT)
        except self.ChatBackendError:
            logger.error("Could not create slack team, name taken: %s" % channel_name)
            return
        channel_ref = "#%s" % group.name
        try:
            self._invite_to_group(group.id, user_ids)
        except self.ChatBackendError:
            logger.exception("Could not invite %s to channel" % ",".join(user_ids))
            sleep(settings.SLEEP_UNIT)
        try:
            self._invite_to_group(group.id, settings.SLACK_LISTENING_BOT_ID)
            sleep(settings.SLEEP_UNIT)
        except self.ChatBackendError:
            logger.exception(
                "Could not invite the listening bot to "
                f"channel {channel_name} ({group.id})"
            )
        with reversion.create_revision():
            reversion.set_comment("Creating slack channel")
            team.slack_channel = group.id
            team.save()
        try:
            self._set_group_topic(group.id, topic)
            sleep(settings.SLEEP_UNIT)
        except self.ChatBackendError:
            logger.exception(
                f"Failed to set topic for channel {channel_name} ({group.id})"
            )
        try:
            self._leave_group(group.id)
            sleep(settings.SLEEP_UNIT)
        except self.ChatBackendError:
            logger.exception(f"Failed to leave channel {channel_name} ({group.id})")
        try:
            self.channel_message(channel_ref, intro_message)
            sleep(settings.SLEEP_UNIT)
        except self.ChatBackendError:
            logger.exception(
                f"Failed to sent intro message to channel {channel_name} ({group.id})"
            )

    def get_user(self, user_id: str, tries: int = 0) -> namedtuple:
        url = "https://slack.com/api/users.info"
        r = requests.get(
            url, params={"user": user_id, "token": self._get_slack_token()}
        )
        json = r.json()
        if not json["ok"]:
            raise self.ChatBackendError(json["error"])
        m = json["user"]
        return SlackUser(
            m["id"],
            m.get("name"),
            m["profile"].get("real_name"),
            m["profile"].get("display_name"),
            m["profile"].get("email", ""),
            m.get("tz_offset"),
        )

    def get_user_list(self, tries: int = 0) -> list[namedtuple]:
        url = "https://slack.com/api/users.list"
        r = requests.get(url, params={"token": self._get_slack_token()})
        json = r.json()
        if not json["ok"]:
            raise self.ChatBackendError(json["error"])
        return [
            SlackUser(
                m["id"],
                m.get("name"),
                m["profile"].get("real_name"),
                m["profile"].get("display_name"),
                m["profile"].get("email", ""),
                m.get("tz_offset"),
            )
            for m in json["members"]
        ]

    def invite_user(self, email: str, tries: int = 0) -> None:
        url = "https://slack.com/api/users.admin.invite"
        r = requests.get(url, params={"token": self._get_slack_token(), "email": email})
        json = r.json()
        if not json["ok"]:
            if json["error"] == "already_invited":
                raise self.InvitationFailedError
            if json["error"] == "already_in_team":
                raise self.InvitationFailedError
            raise self.InvitationFailedError(json["error"])
