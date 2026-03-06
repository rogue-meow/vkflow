"""
FSM (Finite State Machine) module for vkflow.

This module provides tools for building conversational flows with state management.
It integrates seamlessly with existing Cog and View systems.

Quick Start:
    from vkflow import fsm

    # Define states
    class OrderStates(fsm.StateGroup):
        waiting_name = fsm.State()
        waiting_phone = fsm.State()

    # Create storage
    storage = fsm.MemoryStorage()

    # Use with FSMRouter (standalone)
    router = fsm.Router(storage)

    @router.state(OrderStates.waiting_name)
    async def handle_name(ctx: fsm.Context, msg):
        await ctx.update_data(name=msg.msg.text)
        await ctx.set_state(OrderStates.waiting_phone)
        await msg.answer("Enter phone:")

    app.include_fsm_router(router)

    # Or use with Cog
    class OrderCog(Cog):
        def __init__(self):
            self.fsm_storage = fsm.MemoryStorage()

        @fsm.state(OrderStates.waiting_name)
        async def handle_name(self, ctx: fsm.Context, msg):
            ...

    # Or use with App directly
    app.set_fsm_storage(fsm.MemoryStorage())

    @app.state(OrderStates.waiting_name)
    async def handle_name(ctx, msg):
        ...

Key Components:
    - State: Represents a single state
    - StateGroup: Groups related states together
    - Context: Provides methods to get/set state and data
    - MemoryStorage: In-memory storage (for development)
    - BaseStorage: Abstract base for custom storage backends
    - Router: Standalone FSM router
    - StateFilter: Filter for commands based on state
    - state/on_state: Decorators for Cog state handlers
"""

from .state import State, StateGroup
from .context import Context, FSMContext, KeyStrategy
from .storage import BaseStorage
from .storage.memory import MemoryStorage
from .filter import StateFilter, NotStateFilter
from .router import Router, FSMRouter, StateHandler
from .decorators import state, on_state


__all__ = [
    "BaseStorage",
    "Context",
    "FSMContext",
    "FSMRouter",
    "KeyStrategy",
    "MemoryStorage",
    "NotStateFilter",
    "Router",
    "State",
    "StateFilter",
    "StateGroup",
    "StateHandler",
    "on_state",
    "state",
]
