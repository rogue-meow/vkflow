from __future__ import annotations

import contextlib
import typing
import asyncio

from dataclasses import dataclass, field

if typing.TYPE_CHECKING:
    from types import TracebackType

    from vkflow.api import API


__all__ = ["Chat", "ChatMember", "ChatPermissions", "ChatSettings", "Typing"]


@dataclass
class ChatPermissions:
    can_change_info: bool = False
    can_change_invite_link: bool = False
    can_change_pin: bool = False
    can_invite: bool = False
    can_promote_users: bool = False
    can_see_invite_link: bool = False
    can_moderate: bool = False
    can_copy_chat: bool = False
    can_call: bool = False
    can_use_mass_mentions: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> ChatPermissions:
        return cls(
            can_change_info=data.get("can_change_info", False),
            can_change_invite_link=data.get("can_change_invite_link", False),
            can_change_pin=data.get("can_change_pin", False),
            can_invite=data.get("can_invite", False),
            can_promote_users=data.get("can_promote_users", False),
            can_see_invite_link=data.get("can_see_invite_link", False),
            can_moderate=data.get("can_moderate", False),
            can_copy_chat=data.get("can_copy_chat", False),
            can_call=data.get("can_call", False),
            can_use_mass_mentions=data.get("can_use_mass_mentions", False),
        )


@dataclass
class ChatMember:
    member_id: int
    invited_by: int | None = None
    is_admin: bool = False
    is_owner: bool = False
    join_date: int | None = None
    can_kick: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> ChatMember:
        return cls(
            member_id=data.get("member_id", 0),
            invited_by=data.get("invited_by"),
            is_admin=data.get("is_admin", False),
            is_owner=data.get("is_owner", False),
            join_date=data.get("join_date"),
            can_kick=data.get("can_kick", False),
        )


@dataclass
class ChatSettings:
    owner_id: int
    title: str
    state: str
    members_count: int = 0
    admin_ids: list[int] = field(default_factory=list)
    active_ids: list[int] = field(default_factory=list)
    is_group_channel: bool = False
    acl: ChatPermissions | None = None
    photo_50: str | None = None
    photo_100: str | None = None
    photo_200: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> ChatSettings:
        acl_data = data.get("acl", {})
        photo_data = data.get("photo", {})

        return cls(
            owner_id=data.get("owner_id", 0),
            title=data.get("title", ""),
            state=data.get("state", ""),
            members_count=data.get("members_count", 0),
            admin_ids=data.get("admin_ids", []),
            active_ids=data.get("active_ids", []),
            is_group_channel=data.get("is_group_channel", False),
            acl=ChatPermissions.from_dict(acl_data) if acl_data else None,
            photo_50=photo_data.get("photo_50"),
            photo_100=photo_data.get("photo_100"),
            photo_200=photo_data.get("photo_200"),
        )


class Typing:
    def __init__(
        self,
        api: API,
        peer_id: int,
        *,
        interval: float = 5.0,
        activity_type: str = "typing",
    ) -> None:
        self._api = api
        self._peer_id = peer_id
        self._interval = interval
        self._activity_type = activity_type
        self._task: asyncio.Task | None = None

    async def _send_typing(self) -> None:
        await self._api.messages.set_activity(
            peer_id=self._peer_id,
            type=self._activity_type,
        )

    async def _typing_loop(self) -> None:
        try:
            while True:
                await self._send_typing()
                await asyncio.sleep(self._interval)

        except asyncio.CancelledError:
            pass

    def __await__(self):
        return self._send_typing().__await__()

    async def __aenter__(self) -> Typing:
        await self._send_typing()
        self._task = asyncio.create_task(self._typing_loop())

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._task is not None:
            self._task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await self._task

            self._task = None


class Chat:
    PEER_ID_OFFSET = 2000000000

    def __init__(
        self,
        api: API,
        peer_id: int,
        *,
        settings: ChatSettings | None = None,
    ) -> None:
        self._api = api
        self._peer_id = peer_id
        self._settings = settings

    @classmethod
    def from_id(cls, api: API, id: int) -> Chat:
        return cls(api, peer_id=cls.PEER_ID_OFFSET + id)

    @property
    def peer_id(self) -> int:
        return self._peer_id

    @property
    def id(self) -> int:
        return self._peer_id - self.PEER_ID_OFFSET

    @property
    def api(self) -> API:
        return self._api

    @property
    def settings(self) -> ChatSettings | None:
        return self._settings

    @property
    def name(self) -> str | None:
        if self._settings is not None:
            return self._settings.title
        return None

    @property
    def title(self) -> str | None:
        return self.name

    async def fetch_name(self) -> str:
        settings = await self.fetch_settings()
        return settings.title

    async def fetch_title(self) -> str:
        return await self.fetch_name()

    def is_chat(self) -> bool:
        return self._peer_id > self.PEER_ID_OFFSET

    async def fetch_settings(self, *, extended: bool = False) -> ChatSettings:
        response = await self._api.messages.get_conversations_by_id(
            peer_ids=self._peer_id,
            extended=extended,
        )

        if response.get("items"):
            conversation = response["items"][0]
            chat_settings_data = conversation.get("chat_settings", {})

            self._settings = ChatSettings.from_dict(chat_settings_data)
            return self._settings

        raise ValueError(f"Chat {self._peer_id} not found")

    async def get_info(self, *, fields: list[str] | None = None) -> dict:
        return await self._api.messages.get_chat(
            chat_id=self.id,
            fields=fields,
        )

    async def get_members(
        self,
        *,
        offset: int = 0,
        count: int = 200,
        extended: bool = True,
        fields: list[str] | None = None,
    ) -> dict:
        return await self._api.messages.get_conversation_members(
            peer_id=self._peer_id,
            offset=offset,
            count=count,
            extended=extended,
            fields=fields or ["first_name", "last_name", "photo_100"],
        )

    async def get_member_ids(self) -> list[int]:
        result = await self.get_members(extended=False)
        return [item["member_id"] for item in result.get("items", [])]

    async def get_admins(self) -> list[ChatMember]:
        result = await self.get_members(extended=False)

        return [
            ChatMember.from_dict(item)
            for item in result.get("items", [])
            if item.get("is_admin") or item.get("is_owner")
        ]

    async def get_admin_ids(self) -> list[int]:
        admins = await self.get_admins()
        return [admin.member_id for admin in admins]

    async def get_owner(self) -> int:
        result = await self.get_members(extended=False)

        for item in result.get("items", []):
            if item.get("is_owner"):
                return item["member_id"]

        settings = await self.fetch_settings()
        return settings.owner_id

    async def get_creator(self) -> int:
        return await self.get_owner()

    async def is_member(self, user_id: int) -> bool:
        member_ids = await self.get_member_ids()
        return user_id in member_ids

    async def is_admin(self, user_id: int) -> bool:
        admin_ids = await self.get_admin_ids()
        return user_id in admin_ids

    async def kick(
        self,
        user_id: int | None = None,
        *,
        member_id: int | None = None,
    ) -> bool:
        await self._api.messages.remove_chat_user(
            chat_id=self.id,
            user_id=user_id,
            member_id=member_id,
        )

        return True

    async def invite(
        self,
        user_id: int,
        *,
        visible_messages_count: int | None = None,
    ) -> bool:
        await self._api.messages.add_chat_user(
            chat_id=self.id,
            user_id=user_id,
            visible_messages_count=visible_messages_count,
        )

        return True

    async def leave(self) -> bool:
        _, owner = await self._api.define_token_owner()
        return await self.kick(member_id=owner.id)

    async def edit_title(self, title: str) -> bool:
        await self._api.messages.edit_chat(
            chat_id=self.id,
            title=title,
        )

        return True

    async def set_title(self, title: str) -> bool:
        return await self.edit_title(title)

    async def delete_photo(self) -> dict:
        return await self._api.messages.delete_chat_photo(
            chat_id=self.id,
        )

    async def set_photo(self, file: str) -> dict:
        return await self._api.messages.set_chat_photo(file=file)

    async def get_invite_link(self, *, reset: bool = False) -> str:
        response = await self._api.messages.get_invite_link(
            peer_id=self._peer_id,
            reset=reset,
        )

        return response.get("link", "")

    async def reset_invite_link(self) -> str:
        return await self.get_invite_link(reset=True)

    async def get_history(
        self,
        *,
        offset: int = 0,
        count: int = 20,
        start_message_id: int | None = None,
        rev: int = 0,
        extended: bool = False,
        fields: list[str] | None = None,
    ) -> dict:
        return await self._api.messages.get_history(
            peer_id=self._peer_id,
            offset=offset,
            count=count,
            start_message_id=start_message_id,
            rev=rev,
            extended=extended,
            fields=fields,
        )

    async def get_history_attachments(
        self,
        media_type: str = "photo",
        *,
        count: int = 30,
        offset: int = 0,
        extended: bool = False,
        fields: list[str] | None = None,
    ) -> dict:
        return await self._api.messages.get_history_attachments(
            peer_id=self._peer_id,
            media_type=media_type,
            count=count,
            offset=offset,
            extended=extended,
            fields=fields,
        )

    async def search(
        self,
        q: str,
        *,
        offset: int = 0,
        count: int = 20,
        extended: bool = False,
        fields: list[str] | None = None,
    ) -> dict:
        return await self._api.messages.search(
            q=q,
            peer_id=self._peer_id,
            offset=offset,
            count=count,
            extended=extended,
            fields=fields,
        )

    async def pin(
        self,
        *,
        message_id: int | None = None,
        cmid: int | None = None,
    ) -> dict:
        return await self._api.messages.pin(
            peer_id=self._peer_id,
            message_id=message_id,
            cmid=cmid,
        )

    async def unpin(self) -> bool:
        await self._api.messages.unpin(peer_id=self._peer_id)
        return True

    async def mark_as_read(self, *, start_message_id: int | None = None) -> bool:
        await self._api.messages.mark_as_read(
            peer_id=self._peer_id,
            start_message_id=start_message_id,
        )

        return True

    async def set_activity(
        self,
        type: str = "typing",
    ) -> bool:
        await self._api.messages.set_activity(
            peer_id=self._peer_id,
            type=type,
        )

        return True

    def typing(self, *, interval: float = 5.0) -> Typing:
        return Typing(self._api, self._peer_id, interval=interval)

    async def delete_conversation(self) -> dict:
        return await self._api.messages.delete_conversation(
            peer_id=self._peer_id,
        )

    def __repr__(self) -> str:
        return f"<Chat peer_id={self._peer_id} id={self.id}>"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Chat):
            return self._peer_id == other._peer_id
        return False

    def __hash__(self) -> int:
        return hash(self._peer_id)
