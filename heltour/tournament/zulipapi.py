import logging
from datetime import datetime
from time import sleep

import pytz
import reversion
from django.conf import settings
from zulip import Client, ZulipError

from heltour.tournament.chat_client import ChatClient
from heltour.tournament.slackapi import SlackGroup, SlackUser

logger = logging.getLogger(__name__)


class ZulipClient(ChatClient):
    def __init__(self, zulip_env: str):
        self.client = Client(config_file=zulip_env, client="ZulipHeltour")
        register = self.client.register(event_types=["realm"])
        if not register["result"] == "success":
            raise ZulipError(f"ERROR in getting client register: {register['msg']}")
        else:
            try:
                self.max_topic_length = register["max_topic_length"]
                self.max_message_length = register["max_message_length"]
                self.max_stream_name_length = register["max_stream_name_length"]
                self.max_stream_description_length = register[
                    "max_stream_description_length"
                ]
            except KeyError as e:
                logger.error(
                    "ERROR: Realm response does not contain zulip server setting for "
                    "max lengths of topics/message/stream_name/stream_description"
                )
                raise ZulipError("Realm settings missing") from e
            try:
                self.lichess_custom_field_id = next(
                    x["id"]
                    for x in register["custom_profile_fields"]
                    if x["name"] == "lichess account"
                )
            except KeyError as e:
                logger.error(
                    "ERROR: Registration response does not contain zulip settings for "
                    "custom profile fields."
                )
                raise ZulipError("Custom profile fields settings missing") from e
            except IndexError as e:
                logger.error(
                    "ERROR: Custom profile field 'lichess account' does not exist."
                )
                raise ZulipError(
                    "Custom profile field 'lichess account' missing"
                ) from e
            try:
                self.captains_group_id = next(
                    x["id"]
                    for x in register["realm_user_groups"]
                    if "aptain" in x["name"] # should be improved once the name is fixed
                )
            except KeyError as e:
                logger.error(
                    "ERROR: Registration response does not contain zulip settings for "
                    "user groups."
                )
                raise ZulipError("User group settings missing") from e
            except IndexError as e:
                logger.error(
                    "ERROR: User group 'Captains' [or similar] does not exist."
                )
                raise ZulipError("User Group 'Captains' missing") from e

    def _message(
        self,
        channel: str | list[int] | int,
        channel_type: str,
        text: str,
        topic: str = "(no topic)",
        tries: int = 0,
    ) -> None:
        if len(topic) > self.max_topic_length:
            logger.warning(
                f"topic length exceeds max_topic_length {self.max_topic_length}, "
                "cutting it."
            )
            topic = topic[: self.max_topic_length]
        if len(text) > self.max_message_length:
            logger.warning(
                "message length exceeds max_message_length "
                f"{self.max_message_length}, cutting it."
            )
            text = text[: self.max_message_length]
        if channel_type == "channel":
            params = {
                "type": channel_type,
                "to": channel[1:]
                if not isinstance(channel, int) and "#" in channel
                else channel,
                "content": text,
                "topic": topic,
            }
        elif channel_type == "direct":
            params = {
                "type": channel_type,
                "to": channel,
                "content": text,
            }
        else:
            raise ZulipError(f'Unkown channel_type "{channel_type}"')
        r = self.client.send_message(params)
        if r["result"] != "success":
            if (
                settings.ZULIP_ERROR_LOGGING
                and r["code"] != "RATE_LIMIT_HIT"
                and f"{channel}>{topic}" != settings.ZULIP_ERROR_LOG
            ):  # prevent trying to send errors about failed error messages to prevent infinite recursion when zulip is down or something
                self._send_message(
                    channel=settings.ZULIP_ERROR_LOG,
                    text=(
                        f"Could not send message to {channel}>{topic}.\n"
                        f"Error Code: {r['code']}\nError msg: {r['msg']}"
                    ),
                )
            logger.error(
                f"Could not send message to {channel}>{topic}, error:\n{r['msg']}"
            )
            if r["code"] == "RATE_LIMIT_HIT" and tries < settings.ZULIP_RETRIES:
                sleep(
                    settings.SLEEP_UNIT * r["retry-after"] * 1.05
                )  # add 5 percent, just to be sure.
                self._message(
                    channel=channel,
                    channel_type=channel_type,
                    text=text,
                    topic=topic,
                    tries=tries + 1,
                )
            elif r["code"] == "RATE_LIMIT_HIT":
                logger.error(
                    f"Hit Rate Limit twice, giving up.\n"
                    f"msg: {r['msg']}\n"
                    f"retry: {r['retry-after']}"
                )
                raise ZulipRateLimitHit(message=r["msg"], wait=r["retry-after"])
            else:
                raise ZulipError(r["msg"])
        else:
            logger.info(f"Zulip [{channel} > {topic}]: {text}")

    def _send_message(self, channel: str, text: str, topic: str = "(no topic)") -> None:
        if ">" in channel:
            channel_split = channel.partition(">")
            self._message(
                channel=channel_split[0],
                channel_type="channel",
                text=text,
                topic=channel_split[2],
            )
        else:
            self._message(
                channel=channel, channel_type="channel", text=text, topic=topic
            )

    def _send_direct_message(self, users: list[int], text: str) -> None:
        self._message(channel=users, channel_type="direct", text=text, topic="")

    def _send_forward_message(self, channel: str, text: str) -> None:
        self._message(
            channel="msg-forward",
            channel_type="channel",
            text=f"forward to {channel}\n>{text}",
            topic="logging",
        )

    def _get_channel_id(self, channel_name: str) -> int:
        r = self.client.get_stream_id(channel_name)
        if r["result"] != "success":
            if r["code"] == "RATE_LIMIT_HIT":
                raise ZulipRateLimitHit(message=r["msg"], wait=r["retry-after"])
            else:
                raise ZulipError(r["msg"])
        return int(r["stream_id"])

    def _invite_to_group(self, channel_name: str, user_ids: list[int]) -> None:
        self._create_channel(channel_name=channel_name, user_ids=user_ids)

    def _create_channel(
        self,
        channel_name: str,
        user_ids: list[int],
        topic: str = "",
        invite_only: bool = True,
        history_public: bool = False,
        can_add_subscribers_ids: list[int] | None = None,
        can_add_subscribers_groups: list[int] | None = None,
        can_remove_subscribers_ids: list[int] | None = None,
        can_remove_subscribers_groups: list[int] | None = None,
        can_admin_channel_ids: list[int] | None = None,
        can_admin_channel_groups: list[int] | None = None,
        tries: int = 0,
    ) -> SlackGroup:
        # don't really see how this could bite us, but avoid mutable defaults anyway
        if can_add_subscribers_ids is None:
            can_add_subscribers_ids = []
        if can_add_subscribers_groups is None:
            can_add_subscribers_groups = []
        if can_remove_subscribers_ids is None:
            can_remove_subscribers_ids = []
        if can_remove_subscribers_groups is None:
            can_remove_subscribers_groups = []
        if can_admin_channel_ids is None:
            can_admin_channel_ids = []
        if can_admin_channel_groups is None:
            can_admin_channel_groups = []

        if len(channel_name) > self.max_stream_name_length:
            logger.warning(
                "channel name length exceeds max_stream_name_length "
                f"{self.max_stream_name_length}, cutting it."
            )
            channel_name = channel_name[: self.max_stream_name_length]
        if len(topic) > self.max_stream_description_length:
            logger.warning(
                "channel description length exceeds max_stream_description_length "
                f"{self.max_stream_description_length}, cutting it."
            )
            topic = topic[: self.max_stream_description_length]
        if topic:
            stream = [
                {
                    "name": channel_name,
                    "description": topic,
                }
            ]
        else:
            stream = [
                {
                    "name": channel_name,
                }
            ]
        r = self.client.add_subscriptions(
            streams=stream,
            principals=user_ids,
            invite_only=invite_only,
            history_public_to_subscribers=history_public,
            can_add_subscribers_group={
                "direct_members": can_add_subscribers_ids,
                "direct_subgroups": can_add_subscribers_groups,
            },
            can_remove_subscribers_group={
                "direct_members": can_remove_subscribers_ids,
                "direct_subgroups": can_remove_subscribers_groups,
            },
            can_administer_channel_group={
                "direct_members": can_admin_channel_ids,
                "direct_subgroups": can_admin_channel_groups,
            },
        )
        if r["result"] != "success":
            if settings.ZULIP_ERROR_LOGGING:
                self._send_message(
                    channel=settings.ZULIP_ERROR_LOG,
                    text=(
                        f"Could not create channel {channel_name} "
                        f"for user ids {user_ids}.\n"
                        f"Error Code: {r['code']}\n"
                        f"Error msg: {r['msg']}"
                    ),
                )
            if r["code"] == "RATE_LIMIT_HIT" and tries < settings.ZULIP_RETRIES:
                sleep(
                    settings.SLEEP_UNIT * r["retry-after"] * 1.05
                )  # add 5 percent to be sure
                self._create_channel(
                    channel_name=channel_name,
                    user_ids=user_ids,
                    topic=topic,
                    invite_only=invite_only,
                    history_public=history_public,
                    can_add_subscribers_ids=can_add_subscribers_ids,
                    can_add_subscribers_groups=can_add_subscribers_groups,
                    can_remove_subscribers_ids=can_remove_subscribers_ids,
                    can_remove_subscribers_groups=can_remove_subscribers_groups,
                    can_admin_channel_ids=can_admin_channel_ids,
                    can_admin_channel_groups=can_admin_channel_groups,
                    tries=tries + 1,
                )
            elif r["code"] == "RATE_LIMIT_HIT":
                logger.error(
                    "Hit Rate Limit twice, giving up.\n"
                    f"msg: {r['msg']}\nretry: {r['retry-after']}"
                )
                raise ZulipRateLimitHit(message=r["msg"], wait=r["retry-after"])
            else:
                raise ZulipError(r["msg"])
        channel_id = self._get_channel_id(channel_name)
        return SlackGroup(channel_id, channel_name)

    def _get_lichess_username_from_profile(self, profile: dict[str, str]) -> str:
        try:
            return profile["profile_data"][self.lichess_custom_field_id]["value"]
        except KeyError:
            return ""

    def _get_tz_from_profile(self, profile: dict) -> float:
        tz = profile.get("timezone")
        if tz:
            offset = pytz.timezone(tz).localize(datetime.now()).utcoffset()
            if offset:
                return offset.total_seconds()
        return 0.0

    def bold(self, text: str) -> str:
        return f"**{text}**"

    def channellink(
        self,
        channel: str,
        channelprefix: str = "#",
        channelid: str = "",
        topic: str = "",
    ) -> str:
        if topic:
            return f"{channelprefix}**{channel}>{topic}**"
        else:
            return f"{channelprefix}**{channel}**"

    def chatbackend(self) -> str:
        return "Zulip"

    def chatbackend_render(self) -> bool:
        return True

    def chatbackend_url(self) -> str:
        return settings.ZULIP_URL

    def dm_link(self, usernames: list[str], userids: list[str], add_bot: bool) -> str:
        if add_bot:
            userids.append(settings.ZULIP_LISTENING_BOT)
        users = ",".join(str(u) for u in userids)
        return f"{settings.ZULIP_URL}/#narrow/dm/{users}-group"

    def inlinecode(self, text: str) -> str:
        return f"`{text}`"

    def italic(self, text: str) -> str:
        return f"*{text}*"

    def link(self, text: str, url: str) -> str:
        return f"[{text}]({url})"

    def ping_mods(self) -> str:
        return "@*mods4545*"

    def userlink_ping(self, user: str) -> str:
        return f"@**{user}**"

    def userlink_silent(self, user: str) -> str:
        return f"@_**{user}**"

    def channel_message(
        self, channel: str, text: str, topic: str = "(no topic)"
    ) -> None:
        self._send_message(channel=channel, text=text, topic=topic)

    def send_control_message(self, text: str) -> None:
        self._message(
            channel="msg-forward", channel_type="channel", text=text, topic="control"
        )

    def direct_user_message(self, username: str, text: str, userid: str) -> None:
        self._send_direct_message(users=[int(userid)], text=text)

    def multiple_user_message(
        self, usernames: list[str], text: str, userids: list[str]
    ) -> None:
        userids_int = list(map(int, userids))
        userids_int.append(settings.ZULIP_LISTENING_BOT)
        self._send_direct_message(users=userids_int, text=text)

    def cb_create_team_channel(
        self,
        team,
        channel_name: str,
        user_ids: list[str],
        topic: str,
        intro_message: str,
    ) -> None:
        user_ids_ext = list(map(int, user_ids))
        user_ids_ext.extend([settings.ZULIP_LISTENING_BOT, settings.ZULIP_HELTOUR_BOT])
        channel = self._create_channel(
            channel_name=channel_name,
            user_ids=user_ids_ext,
            topic=topic,
            invite_only=True,
            history_public=False,
            can_add_subscribers_ids=user_ids_ext,
            can_admin_channel_groups=[self.captains_group_id],
        )
        with reversion.create_revision():
            reversion.set_comment("Creating zulip channel")
            team.slack_channel = channel.id
            team.save()
        self.channel_message(channel=channel_name, text=intro_message, topic="Welcome!")
        sleep(settings.SLEEP_UNIT)

    def get_user(self, user_id: str) -> SlackUser:
        r = self.client.get_user_by_id(int(user_id), include_custom_profile_fields=True)
        if r["result"] != "success":
            if settings.ZULIP_ERROR_LOGGING:
                self.channel_message(
                    channel=settings.ZULIP_ERROR_LOG,
                    text=(
                        f"Could not retrieve user {user_id}.\n"
                        f"Error Code: {r['code']}\nError msg: {r['msg']}"
                    ),
                )
            if r["code"] == "RATE_LIMIT_HIT":
                raise ZulipRateLimitHit(message=r["msg"], wait=r["retry-after"])
            else:
                raise ZulipError(r["msg"])
        m = r["user"]
        tzseconds = self._get_tz_from_profile(m)
        lichess_account = self._get_lichess_username_from_profile(m)
        return SlackUser(
            id=str(m.get("user_id")),
            display_name=m.get("full_name"),
            email=m.get("email"),
            tz_offset=tzseconds,
            name_deprecated="",
            real_name="",
            lichess_username=lichess_account,
        )

    def get_user_list(self) -> list[SlackUser]:
        r = self.client.get_members({"include_custom_profile_fields": True})
        if r["result"] != "success":
            if settings.ZULIP_ERROR_LOGGING:
                self.channel_message(
                    channel=settings.ZULIP_ERROR_LOG,
                    text=(
                        "Could not retrieve user list.\n"
                        f"Error Code: {r['code']}\nError msg: {r['msg']}"
                    ),
                )
            if r["code"] == "RATE_LIMIT_HIT":
                raise ZulipRateLimitHit(message=r["msg"], wait=r["retry-after"])
            else:
                raise ZulipError(r["msg"])
        result = []
        for m in r["members"]:
            tzseconds = self._get_tz_from_profile(m)
            lichess_account = self._get_lichess_username_from_profile(m)
            result.append(
                SlackUser(
                    id=str(m.get("user_id")),
                    display_name=m.get("full_name"),
                    email=m.get("delivery_email"),
                    tz_offset=tzseconds,
                    name_deprecated="",
                    real_name="",
                    lichess_username=lichess_account,
                )
            )
        return result

    def set_user(self, user_id: str, lichess_username: str) -> None:
        r = self.client.update_user_by_id(
            int(user_id),
            profile_data=[
                {
                    "id": self.lichess_custom_field_id,
                    "value": lichess_username,
                }
            ],
        )
        if r["result"] != "success" and settings.ZULIP_ERROR_LOGGING:
            self._send_message(
                channel=settings.ZULIP_ERROR_LOG,
                text=(
                    f"Could not update user {user_id}\n"
                    f"Error Code: {r['code']}\n"
                    f"Error msg: {r['msg']}\n"
                ),
            )

    def invite_user(self, email: str) -> None:
        params = {
            "invitee_emails": email,
            "invite_expires_in_minutes": 60 * 24 * 7 * 4,  # 4 weeks
            "invite_as": 600,  # 600: guest, 400: member
            "stream_ids": [],  # none, because we can modify default_subscriptions easily, and we do not have any special invitees
            "include_realm_default_subscriptions": "true",
            "notify_referrer_on_join": "false",
        }
        try:
            human_client = Client(
                config_file=settings.ZULIP_CONFIG_NOBOT, client="ZulipHeltour"
            )
        except ZulipError as e:
            raise ZulipError(
                f"ERROR connecting human client for user invitations: {e}"
            ) from e
        r = human_client.call_endpoint(url="/invites", method="POST", request=params)
        if r["result"] != "success":
            if settings.ZULIP_ERROR_LOGGING:
                self.channel_message(
                    channel=settings.ZULIP_ERROR_LOG,
                    text=(
                        f"Could not invite {email}\nError Code: "
                        f"{r['code']}\nError msg: {r['msg']}"
                    ),
                )
            if r["code"] == "INVITATION_FAILED":
                raise AlreadyInTeamError(r["msg"])
            elif r["code"] == "BAD_REQUEST":
                raise BadRequestError(r["msg"])
            elif r["code"] == "RATE_LIMIT_HIT":
                raise ZulipRateLimitHit(message=r["msg"], wait=r["retry-after"])
            else:
                raise ZulipError(r["msg"])
        else:
            logger.info(f"Zulip: invited {email} to zulip")


class AlreadyInTeamError(ZulipError):
    pass


class BadRequestError(ZulipError):
    pass


class ZulipRateLimitHit(ZulipError):
    def __init__(self, message, wait, *args):
        self.message = message
        self.wait = wait
        super().__init__(message, wait, *args)
