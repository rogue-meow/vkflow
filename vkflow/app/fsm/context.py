from __future__ import annotations

import typing
from dataclasses import dataclass, field
from enum import StrEnum

if typing.TYPE_CHECKING:
    from vkflow.app.storages import NewMessage, CallbackButtonPressed
    from vkflow.api import API
    from .state import State
    from .storage import BaseStorage


__all__ = (
    "Context",
    "FSMContext",
    "KeyStrategy",
)


class KeyStrategy(StrEnum):
    """
    Strategy for generating FSM storage keys.

    Determines how user/chat context is identified:
    - USER_CHAT: Separate state per user per chat (most common)
    - USER: Same state for user across all chats
    - CHAT: Same state for all users in chat
    """

    USER_CHAT = "user_chat"
    USER = "user"
    CHAT = "chat"


@dataclass
class FSMContext:
    """
    Context for managing FSM state and data.

    FSMContext provides methods to get/set state and store
    data between FSM steps. It's the primary interface for
    interacting with FSM in handlers.

    Attributes:
        storage: The storage backend
        key: Unique identifier for this context
        strategy: Key generation strategy used

    Examples:
        @fsm.state(OrderStates.waiting_name)
        async def handle_name(ctx: fsm.Context, msg: NewMessage):
            # Store data
            await ctx.update_data(name=msg.msg.text)

            # Move to next state
            await ctx.set_state(OrderStates.waiting_phone)

            await msg.answer("Enter your phone:")

        @fsm.state(OrderStates.waiting_phone)
        async def handle_phone(ctx: fsm.Context, msg: NewMessage):
            # Get all collected data and finish
            data = await ctx.finish()

            await msg.answer(f"Order: {data['name']}, {msg.msg.text}")
    """

    storage: BaseStorage
    key: str
    strategy: KeyStrategy = field(default=KeyStrategy.USER_CHAT)

    _message: NewMessage | CallbackButtonPressed | None = field(default=None, repr=False)

    @classmethod
    def from_message(
        cls,
        storage: BaseStorage,
        message: NewMessage | CallbackButtonPressed,
        *,
        strategy: KeyStrategy | str = KeyStrategy.USER_CHAT,
    ) -> FSMContext:
        """
        Create FSMContext from a message or callback.

        Args:
            storage: Storage backend to use
            message: NewMessage or CallbackButtonPressed context
            strategy: Key generation strategy

        Returns:
            FSMContext instance bound to this user/chat.
        """
        if isinstance(strategy, str):
            strategy = KeyStrategy(strategy)

        key = cls._make_key(message, strategy)

        return cls(
            storage=storage,
            key=key,
            strategy=strategy,
            _message=message,
        )

    @staticmethod
    def _make_key(
        message: NewMessage | CallbackButtonPressed,
        strategy: KeyStrategy,
    ) -> str:
        """
        Generate storage key based on strategy.

        Args:
            message: Message context
            strategy: Key strategy

        Returns:
            Storage key string.
        """
        from vkflow.app.storages import CallbackButtonPressed

        if isinstance(message, CallbackButtonPressed):
            user_id = message.msg.user_id
            peer_id = message.msg.peer_id
        else:
            user_id = message.msg.from_id
            peer_id = message.msg.peer_id

        if strategy == KeyStrategy.USER:
            return f"fsm:{user_id}"
        if strategy == KeyStrategy.CHAT:
            return f"fsm:{peer_id}"
        return f"fsm:{user_id}:{peer_id}"

    @property
    def api(self) -> API | None:
        """Get API instance from message context."""
        return self._message.api if self._message else None

    @property
    def message(self) -> NewMessage | CallbackButtonPressed | None:
        """Get the original message context."""
        return self._message

    async def get_state(self) -> str | None:
        """
        Get current state.

        Returns:
            Current state name or None if no state is set.
        """
        return await self.storage.get_state(self.key)

    async def set_state(self, state: State | str | None) -> None:
        """
        Set new state.

        Args:
            state: State object, state name string, or None to clear.

        Examples:
            await ctx.set_state(OrderStates.waiting_phone)
            await ctx.set_state("custom_state")
            await ctx.set_state(None)  # Clear state
        """
        if state is None:
            await self.storage.delete_state(self.key)
        else:
            state_name = state.name if hasattr(state, "name") else str(state)
            await self.storage.set_state(self.key, state_name)

    async def get_data(self) -> dict[str, typing.Any]:
        """
        Get all stored data.

        Returns:
            Dict of all stored data (empty dict if none).
        """
        return await self.storage.get_data(self.key)

    async def update_data(self, **kwargs: typing.Any) -> dict[str, typing.Any]:
        """
        Update stored data (merge with existing).

        Args:
            **kwargs: Key-value pairs to add/update.

        Returns:
            Full data dict after update.

        Examples:
            await ctx.update_data(name="John")
            await ctx.update_data(phone="+123", address="...")
        """
        return await self.storage.update_data(self.key, **kwargs)

    async def set_data(self, data: dict[str, typing.Any]) -> None:
        """
        Replace all stored data.

        Args:
            data: New data dict (replaces existing).
        """
        await self.storage.set_data(self.key, data)

    async def clear(self) -> None:
        """
        Clear both state and data.

        Use this to reset FSM for user/chat.
        """
        await self.storage.clear(self.key)

    async def finish(self) -> dict[str, typing.Any]:
        """
        Finish FSM flow: get data and clear state.

        This is a convenience method for the common pattern of
        retrieving collected data and cleaning up the FSM state.

        Returns:
            All collected data before clearing.

        Examples:
            data = await ctx.finish()
            await msg.answer(f"Order complete: {data}")
        """
        data = await self.get_data()
        await self.clear()
        return data


Context = FSMContext
