from __future__ import annotations

import typing
import dataclasses

from vkflow.base.filter import BaseFilter
from vkflow.exceptions import StopCurrentHandlingError

from .context import FSMContext, KeyStrategy

if typing.TYPE_CHECKING:
    from vkflow.app.storages import NewMessage
    from .state import State
    from .storage import BaseStorage


__all__ = ("StateFilter",)


@dataclasses.dataclass
class StateFilter(BaseFilter):
    """
    Filter for checking FSM state before command execution.

    StateFilter integrates FSM with the existing command system.
    It checks if user is in a specific state before allowing
    the command to execute.

    Examples:
        # Filter for specific state
        @app.command("next", filter=StateFilter(OrderStates.waiting_name, storage))
        async def handle_name(ctx: NewMessage):
            ...

        # Filter for any state in group
        @app.command("cancel", filter=StateFilter.any(OrderStates, storage))
        async def cancel(ctx: NewMessage):
            ...

        # Filter for no active state
        @app.command("start", filter=StateFilter.none(storage))
        async def start(ctx: NewMessage):
            ...

        # Combine with other filters
        combined = StateFilter(MyStates.waiting, storage) & SomeOtherFilter()
    """

    states: list[State | str]
    storage: BaseStorage
    strategy: KeyStrategy | str = KeyStrategy.USER_CHAT
    _check_none: bool = dataclasses.field(default=False, repr=False)

    def __init__(
        self,
        state: State | str | list[State | str],
        storage: BaseStorage,
        *,
        strategy: KeyStrategy | str = KeyStrategy.USER_CHAT,
    ):
        """
        Create a StateFilter for specific state(s).

        Args:
            state: Single state or list of states to match
            storage: FSM storage backend
            strategy: Key generation strategy
        """
        states = list(state) if isinstance(state, (list, tuple)) else [state]

        object.__setattr__(self, "states", states)
        object.__setattr__(self, "storage", storage)
        object.__setattr__(self, "strategy", strategy)
        object.__setattr__(self, "_check_none", False)

        self.__post_init__()

    @classmethod
    def any(
        cls,
        group: type,  # StateGroup
        storage: BaseStorage,
        *,
        strategy: KeyStrategy | str = KeyStrategy.USER_CHAT,
    ) -> StateFilter:
        """
        Create filter that matches ANY state in a StateGroup.

        Args:
            group: StateGroup class
            storage: FSM storage backend
            strategy: Key generation strategy

        Returns:
            StateFilter that passes if user is in any state of the group.

        Examples:
            @app.command("cancel", filter=StateFilter.any(OrderStates, storage))
            async def cancel(ctx: NewMessage):
                # Works when user is in ANY OrderStates state
                ...
        """
        return cls(
            state=list(group.__states__.values()),
            storage=storage,
            strategy=strategy,
        )

    @classmethod
    def none(
        cls,
        storage: BaseStorage,
        *,
        strategy: KeyStrategy | str = KeyStrategy.USER_CHAT,
    ) -> StateFilter:
        """
        Create filter that matches when NO state is active.

        Args:
            storage: FSM storage backend
            strategy: Key generation strategy

        Returns:
            StateFilter that passes only if user has no active state.

        Examples:
            @app.command("start", filter=StateFilter.none(storage))
            async def start(ctx: NewMessage):
                # Only works when user is NOT in any state
                ...
        """
        filter_obj = cls(
            state=[],
            storage=storage,
            strategy=strategy,
        )
        object.__setattr__(filter_obj, "_check_none", True)
        return filter_obj

    async def make_decision(self, ctx: NewMessage, **kwargs) -> None:
        """
        Check if the current state matches filter criteria.

        Raises:
            StopCurrentHandlingError: If state doesn't match
        """
        fsm_ctx = FSMContext.from_message(self.storage, ctx, strategy=self.strategy)

        current_state = await fsm_ctx.get_state()

        if self._check_none:
            if current_state is not None:
                raise StopCurrentHandlingError()
            return

        if current_state is None:
            raise StopCurrentHandlingError()

        for state in self.states:
            state_name = state.name if hasattr(state, "name") else str(state)
            if current_state == state_name:
                return

        raise StopCurrentHandlingError()


@dataclasses.dataclass
class NotStateFilter(BaseFilter):
    """
    Filter that passes when user is NOT in specified state(s).

    Inverse of StateFilter - useful for preventing certain commands
    while user is in an FSM flow.

    Examples:
        @app.command("help", filter=NotStateFilter(OrderStates.confirm, storage))
        async def help_cmd(ctx: NewMessage):
            # Works when user is NOT in confirm state
            ...
    """

    states: list[State | str]
    storage: BaseStorage
    strategy: KeyStrategy | str = KeyStrategy.USER_CHAT

    def __init__(
        self,
        state: State | str | list[State | str],
        storage: BaseStorage,
        *,
        strategy: KeyStrategy | str = KeyStrategy.USER_CHAT,
    ):
        states = list(state) if isinstance(state, (list, tuple)) else [state]

        object.__setattr__(self, "states", states)
        object.__setattr__(self, "storage", storage)
        object.__setattr__(self, "strategy", strategy)

        self.__post_init__()

    async def make_decision(self, ctx: NewMessage, **kwargs) -> None:
        """
        Check if the current state does NOT match filter criteria.

        Raises:
            StopCurrentHandlingError: If state DOES match (inverse logic)
        """
        fsm_ctx = FSMContext.from_message(self.storage, ctx, strategy=self.strategy)

        current_state = await fsm_ctx.get_state()

        if current_state is None:
            return

        for state in self.states:
            state_name = state.name if hasattr(state, "name") else str(state)
            if current_state == state_name:
                raise StopCurrentHandlingError()
