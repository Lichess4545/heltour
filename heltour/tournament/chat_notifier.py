from collections import namedtuple

from heltour.tournament.chat_client import ChatClient


class Notifier:
    def __init__(self, chat: ChatClient) -> None:
        self.chat: ChatClient = chat

    def bold(self, text: str) -> str:
        return self.chat.bold(text)

    def channellink(
        self,
        channel: str,
        channelprefix: str = "#",
        channelid: str = "",
        topic: str = "",
    ) -> str:
        return self.chat.channellink(channel, channelprefix, channelid, topic)

    def chatbackend(self) -> str:
        return self.chat.chatbackend()

    def chatbackend_render(self) -> bool:
        return self.chat.chatbackend_render()

    def chatbackend_url(self) -> str:
        return self.chat.chatbackend_url()

    def dm_link(self, usernames: list[str], userids: list[str], add_bot: bool) -> str:
        return self.chat.dm_link(usernames, userids, add_bot)

    def inlinecode(self, text: str) -> str:
        return self.chat.inlinecode(text)

    def italic(self, text: str) -> str:
        return self.chat.italic(text)

    def link(self, text: str, url: str) -> str:
        return self.chat.link(text, url)

    def ping_mods(self) -> str:
        return self.chat.ping_mods()

    def userlink_ping(self, user: str) -> str:
        return self.chat.userlink_ping(user)

    def userlink_silent(self, user: str) -> str:
        return self.chat.userlink_silent(user)

    def channel_message(
        self, channel: str, text: str, topic: str = "(no topic)"
    ) -> None:
        self.chat.channel_message(channel, text, topic)

    def send_control_message(self, text: str) -> None:
        self.chat.send_control_message(text)

    def direct_user_message(
        self, username: str, text: str, userid: str
    ) -> None:
        self.chat.direct_user_message(username, text, userid)

    def multiple_user_message(
        self, usernames: list[str], text: str, userids: list[str]
    ) -> None:
        self.chat.multiple_user_message(usernames, text, userids)

    def cb_create_team_channel(
        self,
        team,
        channel_name: str,
        user_ids: list[str],
        topic: str,
        intro_message: str,
    ) -> None:
        self.chat.cb_create_team_channel(
            team, channel_name, user_ids, topic, intro_message
        )

    def get_user(self, user_id: str) -> namedtuple:
        return self.chat.get_user(user_id)

    def get_user_list(self) -> list[namedtuple]:
        return self.chat.get_user_list()

    def invite_user(self, email: str) -> None:
        return self.chat.invite_user(email)
