"""
Event listener system for vkflow.commands

Supports VK events and custom chat action events.

Chat action events (from message_new with action field):
- chat_invite_user, chat_invite_user_by_link -> member_join
- chat_kick_user -> member_remove
- chat_pin_message -> pin_message
- chat_unpin_message -> unpin_message
- chat_photo_update, chat_photo_remove, chat_title_update -> chat_edit
- chat_create -> chat_create
"""

from __future__ import annotations

import contextlib
import copy
import typing
import inspect

if typing.TYPE_CHECKING:
    from vkflow.app.storages import NewEvent
    from .chat_actions import ChatActionEvent

    Handler = typing.Callable[..., typing.Awaitable]


__all__ = (
    "CHAT_ACTION_ALIASES",
    "CHAT_ACTION_EVENTS",
    "Listener",
    "listener",
)


EVENT_ALIASES = {
    "callback": "message_event",
    "message": "message_new",
    "on_message": "message_new",
    "typing": "message_typing_state",
    "on_typing": "message_typing_state",
    "connect": "connect",
    "disconnect": "disconnect",
    "on_ready": "ready",
    "command": "command",
    "command_complete": "command_complete",
    "command_error": "command_error",
}


CHAT_ACTION_EVENTS = {
    "chat_invite_user",
    "chat_invite_user_by_link",
    "chat_invite_user_by_message_request",
    "chat_kick_user",
    "chat_pin_message",
    "chat_unpin_message",
    "chat_photo_update",
    "chat_photo_remove",
    "chat_title_update",
    "chat_create",
    "chat_screenshot",
    "member_join",
    "member_remove",
    "pin_message",
    "unpin_message",
    "chat_edit",
}


CHAT_ACTION_ALIASES = {
    "member_join": ["chat_invite_user", "chat_invite_user_by_link", "chat_invite_user_by_message_request"],
    "user_join": ["chat_invite_user", "chat_invite_user_by_link", "chat_invite_user_by_message_request"],
    "invite_user": ["chat_invite_user"],
    "invite_by_link": ["chat_invite_user_by_link"],
    "member_remove": ["chat_kick_user"],
    "member_kick": ["chat_kick_user"],
    "user_kick": ["chat_kick_user"],
    "kick_user": ["chat_kick_user"],
    "pin_message": ["chat_pin_message"],
    "unpin_message": ["chat_unpin_message"],
    "message_pin": ["chat_pin_message"],
    "message_unpin": ["chat_unpin_message"],
    "chat_edit": ["chat_photo_update", "chat_photo_remove", "chat_title_update"],
    "photo_update": ["chat_photo_update"],
    "photo_remove": ["chat_photo_remove"],
    "title_update": ["chat_title_update"],
    "chat_invite_user": ["chat_invite_user"],
    "chat_invite_user_by_link": ["chat_invite_user_by_link"],
    "chat_invite_user_by_message_request": ["chat_invite_user_by_message_request"],
    "chat_kick_user": ["chat_kick_user"],
    "chat_pin_message": ["chat_pin_message"],
    "chat_unpin_message": ["chat_unpin_message"],
    "chat_photo_update": ["chat_photo_update"],
    "chat_photo_remove": ["chat_photo_remove"],
    "chat_title_update": ["chat_title_update"],
    "chat_create": ["chat_create"],
    "chat_screenshot": ["chat_screenshot"],
}


def normalize_event_name(name: str) -> tuple[str, bool]:
    """
    Normalize event name by removing 'on_' prefix and applying aliases

    Args:
        name: Event name (e.g., "on_message_new", "message_new", "callback", "on_raw_message_new",
              "on_member_join", "on_raw_chat_invite_user")

    Returns:
        Tuple of (normalized_event_name, is_raw)
        is_raw indicates if this is a raw event (on_raw_*)
    """
    is_raw = False

    if name.startswith("on_raw_"):
        name = name[7:]
        is_raw = True

    elif name.startswith("raw_"):
        name = name[4:]
        is_raw = True

    elif name.startswith("on_"):
        name = name[3:]

    normalized = EVENT_ALIASES.get(name, name)

    return normalized, is_raw


def is_chat_action_event(event_name: str) -> bool:
    """Check if the event name is a chat action event"""
    return event_name in CHAT_ACTION_EVENTS or event_name in CHAT_ACTION_ALIASES


def get_action_types_for_event(event_name: str) -> list[str]:
    """
    Get the list of VK action types for a given event name.

    Args:
        event_name: The normalized event name (e.g., "member_join", "chat_invite_user")

    Returns:
        List of VK action types that match this event
    """
    return CHAT_ACTION_ALIASES.get(event_name, [])


class Listener:
    """
    A class that represents an event listener.

    This allows you to listen to VK events, custom library events, and chat action events.

    Attributes:
        callback: The coroutine that is executed when the event is received
        event_name: The name of the event to listen to
        is_raw: Whether this is a raw event listener
        is_chat_action: Whether this listens to chat action events

    Examples:
        # Standard VK events
        @commands.listener()
        async def on_message_new(payload):
            print(f"New message: {payload}")

        # Chat action events (with wrapper class)
        @commands.listener()
        async def on_member_join(event: MemberJoinEvent):
            print(f"User {event.member_id} joined")

        # Raw chat action events (with raw dict)
        @commands.listener()
        async def on_raw_member_join(payload, member_id):
            print(f"User {member_id} joined")

        # Specific action type
        @commands.listener()
        async def on_chat_invite_user(event: MemberJoinEvent, inviter_id):
            print(f"User invited by {inviter_id}")

        # Pin/unpin without chat_ prefix
        @commands.listener()
        async def on_pin_message(event: PinMessageEvent, conversation_message_id):
            print(f"Message {conversation_message_id} pinned")
    """

    def __init__(
        self,
        callback: Handler,
        event_name: str | None = None,
    ):
        self.callback = callback
        self.event_name, self.is_raw = self._determine_event_name(callback, event_name)

        self.is_chat_action = is_chat_action_event(self.event_name)
        self.action_types = get_action_types_for_event(self.event_name) if self.is_chat_action else []

        self.__cog_listener__ = True
        self.__cog_listener_name__ = self.event_name

        self._parse_signature()

    def __set_name__(self, owner, name):
        """Вызывается при назначении Listener атрибуту класса"""
        self._cog_class = owner
        self._method_name = name

    def __get__(self, instance, owner):
        """Протокол дескриптора -привязка callback при доступе через экземпляр"""
        if instance is None:
            return self

        bound_listener = copy.copy(self)

        if hasattr(self.callback, "__get__") and not hasattr(self.callback, "__self__"):
            with contextlib.suppress(TypeError, AttributeError):
                bound_listener.callback = self.callback.__get__(instance, owner)

        return bound_listener

    def _determine_event_name(self, callback: Handler, event_name: str | None) -> tuple[str, bool]:
        """
        Determine the event name from the decorator argument or function name.

        Args:
            callback: The callback function
            event_name: Optional event name from decorator argument

        Returns:
            Tuple of (event_name, is_raw)
        """
        if event_name is not None:
            return normalize_event_name(event_name)

        func_name = callback.__name__
        return normalize_event_name(func_name)

    def _parse_signature(self):
        """Разбор сигнатуры callback для определения инжектируемых параметров"""
        sig = inspect.signature(self.callback)
        self._params = {}

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            self._params[param_name] = {
                "name": param_name,
                "annotation": param.annotation,
                "has_default": param.default != inspect.Parameter.empty,
            }

    async def invoke(self, event_storage: NewEvent):
        """
        Invoke the listener with the event data.

        Args:
            event_storage: The NewEvent storage containing event data
        """
        kwargs = {}

        payload = event_storage.event.object

        if self.is_raw:
            for param_name in self._params:
                if param_name == "payload":
                    kwargs["payload"] = payload
                elif param_name == "event":
                    kwargs["event"] = event_storage
                elif param_name == "bot":
                    kwargs["bot"] = event_storage.bot
                elif isinstance(payload, dict) and param_name in payload:
                    kwargs[param_name] = payload[param_name]
        else:
            for param_name, param_info in self._params.items():
                if param_name == "payload":
                    kwargs["payload"] = payload
                elif param_name == "event":
                    kwargs["event"] = event_storage
                elif param_name == "bot":
                    kwargs["bot"] = event_storage.bot
                elif isinstance(payload, dict) and param_name in payload:
                    kwargs[param_name] = payload[param_name]
                elif not param_info["has_default"]:
                    pass

        result = self.callback(**kwargs)

        if inspect.iscoroutine(result):
            await result

    async def invoke_chat_action(
        self,
        action_event: ChatActionEvent,
        raw_action: dict,
    ):
        """
        Invoke the listener with chat action event data.

        Args:
            action_event: The ChatActionEvent wrapper instance
            raw_action: The raw action dict from VK API
        """
        kwargs = {}

        for param_name in self._params:
            if self.is_raw:
                if param_name == "payload":
                    kwargs["payload"] = raw_action
                elif param_name == "raw":
                    kwargs["raw"] = raw_action
                elif param_name == "event":
                    kwargs["event"] = action_event
                elif param_name == "ctx":
                    kwargs["ctx"] = action_event.ctx
                elif param_name == "bot":
                    kwargs["bot"] = action_event.bot
                elif param_name == "api":
                    kwargs["api"] = action_event.api
                elif param_name in raw_action:
                    kwargs[param_name] = raw_action[param_name]
                elif hasattr(action_event, param_name):
                    kwargs[param_name] = getattr(action_event, param_name)
            else:
                if param_name == "event":
                    kwargs["event"] = action_event
                elif param_name == "payload":
                    kwargs["payload"] = raw_action
                elif param_name == "raw":
                    kwargs["raw"] = raw_action
                elif param_name == "ctx":
                    kwargs["ctx"] = action_event.ctx
                elif param_name == "bot":
                    kwargs["bot"] = action_event.bot
                elif param_name == "api":
                    kwargs["api"] = action_event.api
                elif hasattr(action_event, param_name):
                    kwargs[param_name] = getattr(action_event, param_name)
                elif param_name in raw_action:
                    kwargs[param_name] = raw_action[param_name]

        result = self.callback(**kwargs)

        if inspect.iscoroutine(result):
            await result

    def matches_action_type(self, action_type: str) -> bool:
        """
        Check if this listener should handle the given action type.

        Args:
            action_type: The VK action type (e.g., "chat_invite_user")

        Returns:
            True if this listener handles this action type
        """
        if not self.is_chat_action:
            return False
        return action_type in self.action_types

    def __repr__(self):
        if self.is_chat_action:
            return f"<Listener event={self.event_name!r} actions={self.action_types!r} callback={self.callback.__name__}>"
        return f"<Listener event={self.event_name!r} callback={self.callback.__name__}>"


def listener(name: str | None = None):
    """
    A decorator to mark a function as an event listener.

    This can be used both inside and outside of Cogs.

    Args:
        name: Optional event name. If not provided, uses the function name
              (with 'on_' prefix removed if present)

    Returns:
        The decorated function as a Listener instance

    Example:
        # Inside a Cog
        class MyCog(commands.Cog):
            @commands.listener()
            async def on_message_new(self, payload):
                print(f"New message: {payload}")

            @commands.listener("message_reply")
            async def handle_reply(self, user_id, text):
                print(f"Reply from {user_id}: {text}")
    """

    def decorator(func: Handler) -> Listener:
        return Listener(func, event_name=name)

    return decorator
