from collections import namedtuple


class ChatClient:
    class ChatBackendError(Exception):
        pass

    class InvitationFailedError(ChatBackendError):
        pass

    def bold(self, text: str) -> str:
        raise NotImplementedError

    def channellink(
        self,
        channel: str,
        channelprefix: str = "#",
        channelid: str = "",
        topic: str = "",
    ) -> str:
        raise NotImplementedError

    def chatbackend(self) -> str:
        raise NotImplementedError

    def chatbackend_render(self) -> str:
        raise NotImplementedError

    def chatbackend_url(self) -> str:
        raise NotImplementedError

    def dm_link(self, usernames: list[str], userids: list[str], add_bot: bool) -> str:
        raise NotImplementedError

    def inlinecode(self, text: str) -> str:
        raise NotImplementedError

    def italic(self, text: str) -> str:
        raise NotImplementedError

    def link(self, text: str, url: str) -> str:
        raise NotImplementedError

    def ping_mods(self) -> str:
        raise NotImplementedError

    def userlink_ping(self, user: str) -> str:
        raise NotImplementedError

    def userlink_silent(self, user: str) -> str:
        raise NotImplementedError

    def channel_message(
        self, channel: str, text: str, topic: str = "(no topic)", tries: int = 0
    ) -> None:
        raise NotImplementedError

    def send_control_message(self, text: str, tries: int = 0) -> None:
        raise NotImplementedError

    def direct_user_message(
        self, username: str, text: str, userid: str, tries: int = 0
    ) -> None:
        raise NotImplementedError

    def multiple_user_message(
        self, usernames: list[str], text: str, userids: list[str], tries: int = 0
    ) -> None:
        raise NotImplementedError

    def cb_create_team_channel(
        self,
        team,
        channel_name: str,
        user_ids: list[str],
        topic: str,
        intro_message: str,
        tries: int = 0,
    ) -> None:
        raise NotImplementedError

    def get_user(self, user_id: str, tries: int = 0) -> namedtuple:
        raise NotImplementedError

    def get_user_list(self, tries: int = 0) -> list[namedtuple]:
        raise NotImplementedError

    def invite_user(self, email: str, tries: int = 0) -> None:
        raise NotImplementedError
