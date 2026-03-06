from __future__ import annotations

import typing
import inspect
from dataclasses import dataclass

from loguru import logger

from .context import FSMContext, KeyStrategy

if typing.TYPE_CHECKING:
    from vkflow.app.storages import NewMessage, CallbackButtonPressed
    from .state import State
    from .storage import BaseStorage

    Handler = typing.Callable[..., typing.Awaitable[typing.Any]]


__all__ = (
    "FSMRouter",
    "Router",
    "StateHandler",
)


@dataclass
class StateHandler:
    """
    Wrapper for a state handler function.

    Handles argument injection for FSM handlers, automatically
    providing fsm context, message, data, etc.
    """

    handler: Handler
    state: State | str

    async def invoke(
        self,
        fsm_ctx: FSMContext,
        message: NewMessage | CallbackButtonPressed,
    ) -> typing.Any:
        """
        Invoke the handler with automatic argument injection.

        Supported parameter names:
        - ctx, fsm: FSMContext instance
        - msg, message: NewMessage/CallbackButtonPressed
        - data: Current FSM data dict
        - state: Current state name string

        Args:
            fsm_ctx: FSM context
            message: Message context

        Returns:
            Handler return value
        """
        sig = inspect.signature(self.handler)
        kwargs: dict[str, typing.Any] = {}

        for param_name in sig.parameters:
            if param_name in ("self", "cls"):
                continue
            if param_name in ("ctx", "fsm"):
                kwargs[param_name] = fsm_ctx
            elif param_name in ("msg", "message"):
                kwargs[param_name] = message
            elif param_name == "data":
                kwargs[param_name] = await fsm_ctx.get_data()
            elif param_name == "state":
                kwargs[param_name] = await fsm_ctx.get_state()

        return await self.handler(**kwargs)


class FSMRouter:
    """
    Router for FSM state handlers.

    FSMRouter provides a standalone way to register and dispatch
    FSM state handlers, independent of the Cog system.

    Features:
    - Register handlers with @router.state() decorator
    - Before/after state hooks
    - Automatic argument injection
    - Process messages through registered handlers

    Examples:
        from vkflow.app.fsm import FSMRouter, MemoryStorage, StateGroup, State

        class OrderStates(StateGroup):
            waiting_name = State()
            waiting_phone = State()

        storage = MemoryStorage()
        router = FSMRouter(storage)

        @router.state(OrderStates.waiting_name)
        async def handle_name(ctx, msg):
            await ctx.update_data(name=msg.msg.text)
            await ctx.set_state(OrderStates.waiting_phone)
            await msg.answer("Enter phone:")

        @router.state(OrderStates.waiting_phone)
        async def handle_phone(ctx, msg):
            data = await ctx.finish()
            await msg.answer(f"Order: {data['name']}, {msg.msg.text}")

        # Register in app
        app.include_fsm_router(router)
    """

    def __init__(
        self,
        storage: BaseStorage,
        *,
        strategy: KeyStrategy | str = KeyStrategy.USER_CHAT,
        name: str | None = None,
    ):
        """
        Initialize FSMRouter.

        Args:
            storage: FSM storage backend
            strategy: Key generation strategy
            name: Optional router name for debugging
        """
        self.storage = storage
        self.strategy = KeyStrategy(strategy) if isinstance(strategy, str) else strategy
        self.name = name or self.__class__.__name__

        self._handlers: dict[str, StateHandler] = {}
        self._before_hooks: list[Handler] = []
        self._after_hooks: list[Handler] = []

    def state(
        self,
        state: State | str,
    ) -> typing.Callable[[Handler], Handler]:
        """
        Decorator to register a state handler.

        Args:
            state: State object or state name string

        Returns:
            Decorator function

        Examples:
            @router.state(OrderStates.waiting_name)
            async def handle_name(ctx: fsm.Context, msg: NewMessage):
                await ctx.update_data(name=msg.msg.text)
                await ctx.set_state(OrderStates.waiting_phone)
        """

        def decorator(func: Handler) -> Handler:
            state_name = state.name if hasattr(state, "name") else str(state)
            self._handlers[state_name] = StateHandler(
                handler=func,
                state=state,
            )
            return func

        return decorator

    def before_state(self) -> typing.Callable[[Handler], Handler]:
        """
        Decorator for before-state hook.

        Hook is called before any state handler. If it returns False,
        the state handler will be skipped.

        Examples:
            @router.before_state()
            async def log_before(ctx, msg):
                logger.info(f"Processing state for {msg.msg.from_id}")
        """

        def decorator(func: Handler) -> Handler:
            self._before_hooks.append(func)
            return func

        return decorator

    def after_state(self) -> typing.Callable[[Handler], Handler]:
        """
        Decorator for after-state hook.

        Hook is called after state handler completes (success or failure).

        Examples:
            @router.after_state()
            async def log_after(ctx, msg):
                logger.info(f"Finished processing for {msg.msg.from_id}")
        """

        def decorator(func: Handler) -> Handler:
            self._after_hooks.append(func)
            return func

        return decorator

    def get_handler(self, state: str) -> StateHandler | None:
        """
        Get handler for a state.

        Args:
            state: State name

        Returns:
            StateHandler or None if not found
        """
        return self._handlers.get(state)

    def get_states(self) -> list[str]:
        """
        Get all registered state names.

        Returns:
            List of state name strings
        """
        return list(self._handlers.keys())

    async def process(
        self,
        message: NewMessage | CallbackButtonPressed,
    ) -> bool:
        """
        Process a message through FSM handlers.

        Checks if user is in a registered state and invokes
        the corresponding handler.

        Args:
            message: Message to process

        Returns:
            True if a handler was invoked, False otherwise
        """
        fsm_ctx = FSMContext.from_message(self.storage, message, strategy=self.strategy)

        current_state = await fsm_ctx.get_state()
        if current_state is None:
            return False

        handler = self._handlers.get(current_state)
        if handler is None:
            return False

        for hook in self._before_hooks:
            try:
                result = await self._invoke_hook(hook, fsm_ctx, message)
                if result is False:
                    return False
            except Exception:
                logger.exception("Error in before_state hook")
                raise

        try:
            await handler.invoke(fsm_ctx, message)
        except Exception:
            logger.exception(f"Error in FSM handler for state {current_state}")
            raise
        finally:
            for hook in self._after_hooks:
                try:
                    await self._invoke_hook(hook, fsm_ctx, message)
                except Exception:
                    logger.exception("Error in after_state hook")

        return True

    async def _invoke_hook(
        self,
        hook: Handler,
        fsm_ctx: FSMContext,
        message: NewMessage | CallbackButtonPressed,
    ) -> typing.Any:
        """Invoke a hook with argument injection."""
        sig = inspect.signature(hook)
        kwargs: dict[str, typing.Any] = {}

        for param_name in sig.parameters:
            if param_name in ("self", "cls"):
                continue
            if param_name in ("ctx", "fsm"):
                kwargs[param_name] = fsm_ctx
            elif param_name in ("msg", "message"):
                kwargs[param_name] = message

        return await hook(**kwargs)

    def include_router(self, router: FSMRouter) -> None:
        """
        Include another router's handlers.

        Args:
            router: Router to include
        """
        self._handlers.update(router._handlers)
        self._before_hooks.extend(router._before_hooks)
        self._after_hooks.extend(router._after_hooks)

    def __repr__(self) -> str:
        return f"<FSMRouter {self.name!r} states={len(self._handlers)}>"


Router = FSMRouter
