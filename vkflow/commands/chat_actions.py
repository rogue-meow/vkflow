"""
Chat action events for vkflow.commands

This module provides dataclasses and handlers for chat action events like:
- Member join/invite
- Member kick/leave
- Message pin/unpin
- Chat edit (photo, title)
- Chat creation
"""

from __future__ import annotations

import dataclasses
import typing

if typing.TYPE_CHECKING:
    from vkflow.app.storages import NewMessage


__all__ = (
    "ChatActionEvent",
    "ChatActionType",
    "ChatCreateEvent",
    "ChatEditEvent",
    "ChatPhoto",
    "ChatPhotoRemoveEvent",
    "ChatPhotoUpdateEvent",
    "ChatTitleUpdateEvent",
    "MemberJoinEvent",
    "MemberRemoveEvent",
    "PinMessageEvent",
    "UnpinMessageEvent",
    "create_chat_action_event",
)


class ChatActionType:
    """Constants for chat action types"""

    CHAT_INVITE_USER = "chat_invite_user"
    CHAT_KICK_USER = "chat_kick_user"
    CHAT_INVITE_USER_BY_LINK = "chat_invite_user_by_link"
    CHAT_INVITE_USER_BY_MESSAGE_REQUEST = "chat_invite_user_by_message_request"

    CHAT_PIN_MESSAGE = "chat_pin_message"
    CHAT_UNPIN_MESSAGE = "chat_unpin_message"

    CHAT_PHOTO_UPDATE = "chat_photo_update"
    CHAT_PHOTO_REMOVE = "chat_photo_remove"
    CHAT_TITLE_UPDATE = "chat_title_update"
    CHAT_CREATE = "chat_create"

    CHAT_SCREENSHOT = "chat_screenshot"

    ALL_MEMBER_JOIN = (CHAT_INVITE_USER, CHAT_INVITE_USER_BY_LINK, CHAT_INVITE_USER_BY_MESSAGE_REQUEST)
    ALL_MEMBER_REMOVE = (CHAT_KICK_USER,)
    ALL_CHAT_EDIT = (CHAT_PHOTO_UPDATE, CHAT_PHOTO_REMOVE, CHAT_TITLE_UPDATE)
    ALL_PIN = (CHAT_PIN_MESSAGE,)
    ALL_UNPIN = (CHAT_UNPIN_MESSAGE,)


@dataclasses.dataclass
class ChatPhoto:
    """
    Chat photo object.

    Attributes:
        photo_50: URL of 50x50px image
        photo_100: URL of 100x100px image
        photo_200: URL of 200x200px image
    """

    photo_50: str | None = None
    photo_100: str | None = None
    photo_200: str | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> ChatPhoto | None:
        """Create ChatPhoto from dict"""
        if not data:
            return None
        return cls(
            photo_50=data.get("photo_50"),
            photo_100=data.get("photo_100"),
            photo_200=data.get("photo_200"),
        )


@dataclasses.dataclass
class ChatActionEvent:
    """
    Base class for chat action events.

    Attributes:
        ctx: The NewMessage context
        action_type: The type of action (chat_invite_user, chat_kick_user, etc.)
        raw: Raw action dict from VK API
        from_id: ID of the user who performed the action
        peer_id: ID of the chat where action occurred
    """

    ctx: NewMessage
    action_type: str
    raw: dict
    from_id: int
    peer_id: int

    @property
    def event(self):
        """Alias for accessing the underlying event storage"""
        return self.ctx

    @property
    def bot(self):
        """The bot instance"""
        return self.ctx.bot

    @property
    def api(self):
        """The API instance"""
        return self.ctx.api

    @property
    def payload(self) -> dict:
        """Raw payload dict"""
        return self.raw


@dataclasses.dataclass
class MemberJoinEvent(ChatActionEvent):
    """
    Event when a member joins the chat.

    Covers:
    - chat_invite_user (direct invite)
    - chat_invite_user_by_link (joined via link)
    - chat_invite_user_by_message_request (joined via message request)

    Attributes:
        member_id: ID of the user who joined
        inviter_id: ID of the user who invited (None if joined by link)
        invited: Same as member_id (alias)
        inviter: Same as inviter_id (alias)
        is_self_return: True if user returned to chat by themselves
        is_by_link: True if user joined via link
        is_by_request: True if user joined via message request
    """

    member_id: int = 0
    inviter_id: int | None = None
    email: str | None = None

    @property
    def invited(self) -> int:
        """Alias for member_id - the invited user"""
        return self.member_id

    @property
    def inviter(self) -> int | None:
        """Alias for inviter_id - the user who invited"""
        return self.inviter_id

    @property
    def is_self_return(self) -> bool:
        """True if user returned to chat themselves"""
        return self.action_type == ChatActionType.CHAT_INVITE_USER and self.member_id == self.from_id

    @property
    def is_by_link(self) -> bool:
        """True if user joined via invite link"""
        return self.action_type == ChatActionType.CHAT_INVITE_USER_BY_LINK

    @property
    def is_by_request(self) -> bool:
        """True if user joined via message request"""
        return self.action_type == ChatActionType.CHAT_INVITE_USER_BY_MESSAGE_REQUEST

    @property
    def is_direct_invite(self) -> bool:
        """True if user was directly invited by another user"""
        return self.action_type == ChatActionType.CHAT_INVITE_USER and self.member_id != self.from_id


@dataclasses.dataclass
class MemberRemoveEvent(ChatActionEvent):
    """
    Event when a member is kicked or leaves the chat.

    Covers:
    - chat_kick_user

    Attributes:
        member_id: ID of the user who was kicked/left
        kicker_id: ID of the user who kicked (None if left by themselves)
        is_self_leave: True if user left by themselves
    """

    member_id: int = 0
    kicker_id: int | None = None
    email: str | None = None

    @property
    def is_self_leave(self) -> bool:
        """True if user left by themselves"""
        return self.member_id == self.from_id

    @property
    def is_kicked(self) -> bool:
        """True if user was kicked by another user"""
        return self.member_id != self.from_id


@dataclasses.dataclass
class PinMessageEvent(ChatActionEvent):
    """
    Event when a message is pinned.

    Attributes:
        member_id: ID of the user who pinned the message
        conversation_message_id: ID of the pinned message in conversation
        message: Text of the pinned message (if available)
    """

    member_id: int = 0
    conversation_message_id: int | None = None
    message: str | None = None


@dataclasses.dataclass
class UnpinMessageEvent(ChatActionEvent):
    """
    Event when a message is unpinned.

    Attributes:
        member_id: ID of the user who unpinned the message
        conversation_message_id: ID of the unpinned message in conversation
    """

    member_id: int = 0
    conversation_message_id: int | None = None


@dataclasses.dataclass
class ChatEditEvent(ChatActionEvent):
    """
    Base event for chat edit actions (photo, title updates).

    Covers:
    - chat_photo_update
    - chat_photo_remove
    - chat_title_update

    Attributes:
        text: New chat title (for title_update)
        photo: New chat photo (for photo_update)
        edit_type: Type of edit ('photo_update', 'photo_remove', 'title_update')
    """

    text: str | None = None
    photo: ChatPhoto | None = None

    @property
    def edit_type(self) -> str:
        """Get the edit type without 'chat_' prefix"""
        return self.action_type.replace("chat_", "")

    @property
    def is_photo_update(self) -> bool:
        """True if chat photo was updated"""
        return self.action_type == ChatActionType.CHAT_PHOTO_UPDATE

    @property
    def is_photo_remove(self) -> bool:
        """True if chat photo was removed"""
        return self.action_type == ChatActionType.CHAT_PHOTO_REMOVE

    @property
    def is_title_update(self) -> bool:
        """True if chat title was updated"""
        return self.action_type == ChatActionType.CHAT_TITLE_UPDATE

    @property
    def new_title(self) -> str | None:
        """Alias for text - the new chat title"""
        return self.text


@dataclasses.dataclass
class ChatPhotoUpdateEvent(ChatEditEvent):
    """Event when chat photo is updated"""


@dataclasses.dataclass
class ChatPhotoRemoveEvent(ChatEditEvent):
    """Event when chat photo is removed"""


@dataclasses.dataclass
class ChatTitleUpdateEvent(ChatEditEvent):
    """Event when chat title is updated"""


@dataclasses.dataclass
class ChatCreateEvent(ChatActionEvent):
    """
    Event when a chat is created.

    Attributes:
        text: The name of the created chat
    """

    text: str | None = None

    @property
    def chat_title(self) -> str | None:
        """Alias for text - the chat title"""
        return self.text


def create_chat_action_event(
    ctx: NewMessage,
    action: dict,
) -> ChatActionEvent | None:
    """
    Factory function to create the appropriate ChatActionEvent subclass.

    Args:
        ctx: The NewMessage context
        action: The action dict from the message

    Returns:
        The appropriate ChatActionEvent subclass instance, or None if unknown action
    """
    action_type = action.get("type")
    if not action_type:
        return None

    from_id = ctx.msg.from_id
    peer_id = ctx.msg.peer_id

    base_kwargs = {
        "ctx": ctx,
        "action_type": action_type,
        "raw": action,
        "from_id": from_id,
        "peer_id": peer_id,
    }

    member_id = action.get("member_id")
    if member_id is not None:
        member_id = int(member_id)

    text = action.get("text")
    email = action.get("email")
    message = action.get("message")
    conversation_message_id = action.get("conversation_message_id")
    photo = ChatPhoto.from_dict(action.get("photo"))

    if action_type in ChatActionType.ALL_MEMBER_JOIN:
        inviter_id = from_id if action_type == ChatActionType.CHAT_INVITE_USER else None
        if action_type == ChatActionType.CHAT_INVITE_USER and member_id == from_id:
            inviter_id = None

        return MemberJoinEvent(
            **base_kwargs,
            member_id=member_id or from_id,
            inviter_id=inviter_id,
            email=email,
        )

    if action_type in ChatActionType.ALL_MEMBER_REMOVE:
        kicker_id = from_id if member_id != from_id else None
        return MemberRemoveEvent(
            **base_kwargs,
            member_id=member_id or from_id,
            kicker_id=kicker_id,
            email=email,
        )

    if action_type == ChatActionType.CHAT_PIN_MESSAGE:
        return PinMessageEvent(
            **base_kwargs,
            member_id=member_id or from_id,
            conversation_message_id=conversation_message_id,
            message=message,
        )

    if action_type == ChatActionType.CHAT_UNPIN_MESSAGE:
        return UnpinMessageEvent(
            **base_kwargs,
            member_id=member_id or from_id,
            conversation_message_id=conversation_message_id,
        )

    if action_type == ChatActionType.CHAT_PHOTO_UPDATE:
        return ChatPhotoUpdateEvent(
            **base_kwargs,
            text=text,
            photo=photo,
        )

    if action_type == ChatActionType.CHAT_PHOTO_REMOVE:
        return ChatPhotoRemoveEvent(
            **base_kwargs,
            text=text,
            photo=None,
        )

    if action_type == ChatActionType.CHAT_TITLE_UPDATE:
        return ChatTitleUpdateEvent(
            **base_kwargs,
            text=text,
            photo=photo,
        )

    if action_type == ChatActionType.CHAT_CREATE:
        return ChatCreateEvent(
            **base_kwargs,
            text=text,
        )

    return ChatActionEvent(**base_kwargs)
