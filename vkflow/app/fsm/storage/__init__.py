from __future__ import annotations

import typing
from abc import ABC, abstractmethod


__all__ = ("BaseStorage",)


class BaseStorage(ABC):
    """
    Abstract base class for FSM storage backends.

    Storage is responsible for persisting FSM state and data
    between message handlers. Implementations can use various
    backends like memory, Redis, databases, etc.

    Key concepts:
    - State: Current FSM state name (string)
    - Data: Arbitrary dict of data collected during FSM flow
    - Key: Unique identifier for user/chat combination

    Examples:
        # Create custom storage
        class RedisStorage(BaseStorage):
            def __init__(self, redis_client):
                self.redis = redis_client

            async def get_state(self, key: str) -> str | None:
                return await self.redis.get(f"fsm:state:{key}")

            # ... implement other methods
    """

    @abstractmethod
    async def get_state(self, key: str) -> str | None:
        """
        Get current state for the key.

        Args:
            key: Unique identifier (e.g., "fsm:user_id:peer_id")

        Returns:
            Current state name or None if no state is set.
        """

    @abstractmethod
    async def set_state(self, key: str, state: str) -> None:
        """
        Set state for the key.

        Args:
            key: Unique identifier
            state: State name to set
        """

    @abstractmethod
    async def delete_state(self, key: str) -> None:
        """
        Delete state for the key.

        Args:
            key: Unique identifier
        """

    @abstractmethod
    async def get_data(self, key: str) -> dict[str, typing.Any]:
        """
        Get all stored data for the key.

        Args:
            key: Unique identifier

        Returns:
            Dict of stored data (empty dict if no data).
        """

    @abstractmethod
    async def set_data(self, key: str, data: dict[str, typing.Any]) -> None:
        """
        Replace all data for the key.

        Args:
            key: Unique identifier
            data: New data dict (replaces existing)
        """

    @abstractmethod
    async def update_data(self, key: str, **kwargs: typing.Any) -> dict[str, typing.Any]:
        """
        Update data for the key (merge with existing).

        Args:
            key: Unique identifier
            **kwargs: Key-value pairs to add/update

        Returns:
            Full data dict after update.
        """

    @abstractmethod
    async def delete_data(self, key: str) -> None:
        """
        Delete all data for the key.

        Args:
            key: Unique identifier
        """

    async def close(self) -> None:  # noqa: B027
        """
        Close storage connection (if applicable).

        Override this method if your storage needs cleanup
        (e.g., closing database connections).
        """

    async def clear(self, key: str) -> None:
        """
        Clear both state and data for the key.

        Args:
            key: Unique identifier
        """
        await self.delete_state(key)
        await self.delete_data(key)
