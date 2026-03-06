from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from .state import State
    from .storage import BaseStorage

    Handler = typing.Callable[..., typing.Awaitable[typing.Any]]


__all__ = (
    "on_state",
    "state",
)


def state(
    state_obj: State | str,
    *,
    storage: BaseStorage | None = None,
) -> typing.Callable[[Handler], Handler]:
    """
    Decorator to mark a function as FSM state handler.

    When used in a Cog, the handler will be automatically collected
    and invoked when user is in the specified state.

    Args:
        state_obj: State object or state name string
        storage: Optional storage override (uses Cog's storage by default)

    Returns:
        Decorated function with FSM metadata

    Examples:
        from vkflow import fsm

        class OrderStates(fsm.StateGroup):
            waiting_name = fsm.State()
            waiting_phone = fsm.State()

        class OrderCog(Cog):
            def __init__(self):
                self.fsm_storage = fsm.MemoryStorage()

            @commands.command()
            async def order(self, ctx):
                fsm_ctx = fsm.Context.from_message(self.fsm_storage, ctx._message)
                await fsm_ctx.set_state(OrderStates.waiting_name)
                await ctx.send("Enter your name:")

            @fsm.state(OrderStates.waiting_name)
            async def handle_name(self, ctx: fsm.Context, msg):
                await ctx.update_data(name=msg.msg.text)
                await ctx.set_state(OrderStates.waiting_phone)
                await msg.answer("Enter phone:")

            @fsm.state(OrderStates.waiting_phone)
            async def handle_phone(self, ctx: fsm.Context, msg):
                data = await ctx.finish()
                await msg.answer(f"Order: {data['name']}, tel: {msg.msg.text}")
    """

    def decorator(func: Handler) -> Handler:
        func.__fsm_state__ = state_obj
        func.__fsm_storage__ = storage
        return func

    return decorator


def on_state(
    state_obj: State | str,
    *,
    storage: BaseStorage | None = None,
) -> typing.Callable[[Handler], Handler]:
    """
    Alternative syntax for @state decorator.

    Functionally identical to @state, provided for users who prefer
    a more explicit naming convention.

    Args:
        state_obj: State object or state name string
        storage: Optional storage override

    Returns:
        Decorated function with FSM metadata

    Examples:
        @fsm.on_state(OrderStates.waiting_name)
        async def process_name(ctx: fsm.Context, msg):
            ...
    """
    return state(state_obj, storage=storage)
