from __future__ import annotations

import asyncio
import dataclasses
import functools
import importlib
import inspect
import signal
import sys
import typing

from loguru import logger

from vkflow.api import API, TokenOwner
from vkflow.exceptions import StopCurrentHandlingError, StopStateHandlingError
from vkflow.app.package import Package
from vkflow.app.storages import (
    CallbackButtonPressed,
    NewEvent,
    NewMessage,
)
from vkflow.ui.view import ViewStore
from vkflow.event import GroupEvent
from vkflow.logger import update_logging_level
from vkflow.longpoll import GroupLongPoll, UserLongPoll

if typing.TYPE_CHECKING:
    from vkflow.base.event_factories import BaseEventFactory
    from vkflow.commands import Command, Group, Cog

AppPayloadFieldTypevar = typing.TypeVar("AppPayloadFieldTypevar")


@dataclasses.dataclass
class App(Package, typing.Generic[AppPayloadFieldTypevar]):
    packages: list[Package] = dataclasses.field(default_factory=list)
    debug: bool = False
    strict_mode: bool = False
    name: str = "VK Quick Бот"
    description: str = "Чат-бот для ВКонтакте, написанный на Python с использованием VK Quick"
    addons: list = dataclasses.field(default_factory=list)
    payload_factory: type[AppPayloadFieldTypevar] = dataclasses.field(default=None)

    def __post_init__(self):
        if self.debug:
            update_logging_level("DEBUG")

        self._extensions: dict[str, typing.Any] = {}
        self._cogs: dict[str, typing.Any] = {}

        from vkflow.commands.middleware import MiddlewareManager

        self.middleware_manager = MiddlewareManager()

        self.view_store = ViewStore()

        self._bots: list[Bot] = []
        self._polling_tasks: list[asyncio.Task] = []
        self._is_ready = False
        self._is_closed = False

        self._ready_event: asyncio.Event | None = None
        self._ready_callbacks: list[typing.Callable] = []
        self._ready_bots: set = set()
        self._background_tasks: set = set()

        self._fsm_routers: list = []
        self._fsm_storage = None
        self._app_fsm_router = None

        self._addons: dict[str, typing.Any] = {}
        for addon in self.addons:
            self._register_addon(addon)

        packages_gen = self.packages.copy()

        for package in packages_gen:
            for command in package.commands:
                if isinstance(self.prefixes, list):
                    command.update_prefix(*self.prefixes)
                else:
                    command.update_prefix(self.prefixes)

        self.packages.append(self)

    @functools.cached_property
    def payload(self) -> AppPayloadFieldTypevar:
        return self.payload_factory()

    async def get_context(
        self,
        message: NewMessage,
        *,
        cls: type | None = None,
        command: typing.Any = None,
        prefix: str | None = None,
        invoked_with: str | None = None,
    ) -> typing.Any:
        """
        Create a Context for the given message.

        Override this method in a subclass to use a custom Context class
        or to add custom attributes/initialization to the context.

        Args:
            message: The NewMessage that triggered the command
            cls: The Context class to use. Defaults to Context from ext.commands.
            command: The Command being invoked
            prefix: The prefix used to invoke the command
            invoked_with: The name/alias used to invoke the command

        Returns:
            Context instance

        Example:
            class MyContext(commands.Context):
                @property
                def db(self):
                    return self.app.database

            class MyApp(App):
                async def get_context(self, message, *, cls=MyContext, **kwargs):
                    return await super().get_context(message, cls=cls, **kwargs)
        """
        from vkflow.commands.context import Context

        if cls is None:
            cls = Context

        return cls.from_message(
            message,
            command=command,
            prefix=prefix,
            invoked_with=invoked_with,
        )

    async def route_event(self, new_event_storage) -> None:
        async with asyncio.TaskGroup() as tg:
            for package in self.packages:
                tg.create_task(package.handle_event(new_event_storage))

    async def wait_for(
        self,
        event_name: str,
        *,
        timeout: float | None = None,
        check: typing.Callable[..., bool] | None = None,
    ) -> NewEvent | tuple:
        from vkflow.exceptions import EventTimeoutError
        from vkflow.commands.listener import normalize_event_name

        event_name, _ = normalize_event_name(event_name)
        future = asyncio.Future()

        async def temp_listener(event=None, **kwargs):
            raw = event.event.object if event and hasattr(event, "event") else {}

            if check is not None:
                try:
                    sig = inspect.signature(check)
                    params = sig.parameters

                    check_args = {}

                    for param_name, param in params.items():
                        if param_name in ("self", "cls"):
                            continue
                        if param_name == "event":
                            check_args["event"] = event
                        elif param_name == "raw":
                            check_args["raw"] = raw
                        elif param_name in kwargs:
                            check_args[param_name] = kwargs[param_name]
                        elif param.kind == inspect.Parameter.VAR_KEYWORD:
                            check_args.update(kwargs)
                            break

                    if inspect.iscoroutinefunction(check):
                        result = await check(**check_args)
                    else:
                        result = check(**check_args)

                    if not result:
                        return
                except Exception:
                    import traceback

                    traceback.print_exc()

                    return

            if not future.done():
                if kwargs:
                    future.set_result((event, kwargs))
                else:
                    future.set_result(event)

        from vkflow.app.package import EventHandler

        handler = EventHandler(temp_listener)

        if event_name not in self.event_handlers:
            self.event_handlers[event_name] = []
        self.event_handlers[event_name].insert(0, handler)

        try:
            if timeout is not None:
                result = await asyncio.wait_for(future, timeout=timeout)
            else:
                result = await future

            return result

        except TimeoutError:
            raise EventTimeoutError(event_name, timeout) from None

        finally:
            if handler in self.event_handlers[event_name]:
                self.event_handlers[event_name].remove(handler)

    async def dispatch_event(self, event_name: str, *args, **kwargs) -> None:
        from vkflow.app.storages import NewEvent

        event_data = kwargs.copy()

        class FakeEvent:
            def __init__(self, obj, event_type):
                self.object = obj
                self.type = event_type
                self.content = obj

        fake_event = FakeEvent(event_data, event_name)

        bot = None

        if "context" in kwargs and hasattr(kwargs["context"], "bot"):
            bot = kwargs["context"].bot
        elif "bot" in kwargs:
            bot = kwargs["bot"]

        fake_new_event = (
            NewEvent(event=fake_event, bot=bot)
            if bot
            else type("FakeNewEvent", (), {"event": fake_event, "bot": None})()
        )

        handler_coroutines = []

        for package in self.packages:
            handlers = package.event_handlers.get(event_name, [])

            for handler in handlers:
                if hasattr(handler, "invoke") and callable(handler.invoke):
                    handler_coroutines.append(handler.invoke(fake_new_event))
                elif hasattr(handler, "handler"):
                    handler_coroutines.append(handler.handler(event=fake_new_event, **event_data))
                else:
                    handler_coroutines.append(handler(**event_data))

        if handler_coroutines:
            await asyncio.gather(*handler_coroutines, return_exceptions=True)

        if event_name == "ready" and bot is not None:
            await self._on_bot_ready(bot)

    async def dispatch(self, event_name: str, *args, **kwargs) -> None:
        await self.dispatch_event(event_name, *args, **kwargs)

    async def route_message(self, ctx: NewMessage):
        try:
            if self.filter is not None:
                await self.filter.run_making_decision(ctx)

        except StopCurrentHandlingError:
            return

        else:
            for router in self._fsm_routers:
                if await router.process(ctx):
                    return

            for cog in self._cogs.values():
                if hasattr(cog, "process_fsm") and await cog.process_fsm(ctx):
                    return

            async with asyncio.TaskGroup() as tg:
                for package in self.packages:
                    tg.create_task(package.handle_message(ctx))

    async def route_callback_button_pressing(self, ctx: CallbackButtonPressed):
        handled = await self.view_store.process_interaction(ctx)

        if not handled:
            async with asyncio.TaskGroup() as tg:
                for package in self.packages:
                    tg.create_task(package.handle_callback_button_pressing(ctx))

    def set_fsm_storage(self, storage: typing.Any) -> None:
        """
        Set global FSM storage for App-level state decorators.

        Args:
            storage: BaseStorage instance (e.g., MemoryStorage)

        Example:
            from vkflow.app.fsm import MemoryStorage

            app = App(prefixes=["/"])
            app.set_fsm_storage(MemoryStorage())

            @app.state(OrderStates.waiting_name)
            async def handle_name(ctx, msg):
                ...
        """
        self._fsm_storage = storage

    def include_fsm_router(self, router: typing.Any) -> None:
        """
        Include an FSM router for state handling.

        FSM routers are checked before regular command routing.
        If a router handles a message, command routing is skipped.

        Args:
            router: FSMRouter instance

        Example:
            from vkflow.app.fsm import FSMRouter, MemoryStorage

            storage = MemoryStorage()
            router = FSMRouter(storage)

            @router.state(OrderStates.waiting_name)
            async def handle_name(ctx, msg):
                ...

            app.include_fsm_router(router)
        """
        self._fsm_routers.append(router)

    def state(
        self,
        state_obj: typing.Any,
        *,
        strategy: str = "user_chat",
    ) -> typing.Callable:
        """
        Decorator to register an FSM state handler at App level.

        Requires set_fsm_storage() to be called first.

        Args:
            state_obj: State object or state name string
            strategy: Key generation strategy

        Returns:
            Decorator function

        Example:
            app.set_fsm_storage(MemoryStorage())

            @app.state(OrderStates.waiting_name)
            async def handle_name(ctx, msg):
                await ctx.update_data(name=msg.msg.text)
                await ctx.set_state(OrderStates.waiting_phone)
                await msg.answer("Enter phone:")
        """
        if self._fsm_storage is None:
            raise ValueError("FSM storage not configured. Call app.set_fsm_storage() first.")

        def decorator(func: typing.Callable) -> typing.Callable:
            from vkflow.app.fsm import Router as FSMRouter

            if self._app_fsm_router is None:
                self._app_fsm_router = FSMRouter(self._fsm_storage, strategy=strategy)
                self.include_fsm_router(self._app_fsm_router)

            self._app_fsm_router.state(state_obj)(func)
            return func

        return decorator

    def get_fsm(
        self, ctx: NewMessage | CallbackButtonPressed, *, strategy: str = "user_chat"
    ) -> typing.Any:
        """
        Get FSMContext for a message context.

        Args:
            ctx: NewMessage or CallbackButtonPressed
            strategy: Key generation strategy

        Returns:
            FSMContext instance

        Raises:
            ValueError: If FSM storage is not configured

        Example:
            @app.command("start_order")
            async def start_order(ctx: NewMessage):
                fsm = app.get_fsm(ctx)
                await fsm.set_state(OrderStates.waiting_name)
                await ctx.reply("Enter your name:")
        """
        if self._fsm_storage is None:
            raise ValueError("FSM storage not configured. Call app.set_fsm_storage() first.")

        from vkflow.app.fsm import Context as FSMContext

        return FSMContext.from_message(
            self._fsm_storage,
            ctx,
            strategy=strategy,
        )

    async def dispatch_chat_action(self, ctx: NewMessage) -> None:
        """
        Dispatch chat action events from message_new with action field.

        This creates the appropriate ChatActionEvent wrapper and invokes
        all matching listeners.

        Args:
            ctx: The NewMessage context containing the action
        """
        action = ctx.msg.action
        if action is None:
            return

        action_type = action.get("type")
        if not action_type:
            return

        try:
            from vkflow.commands.chat_actions import create_chat_action_event
            from vkflow.commands.listener import Listener
        except ImportError:
            return

        action_event = create_chat_action_event(ctx, action)
        if action_event is None:
            return

        logger.opt(colors=True).debug(
            "Chat action: <y>{action_type}</y> in peer <c>{peer_id}</c>",
            action_type=action_type,
            peer_id=ctx.msg.peer_id,
        )

        handler_coroutines = []

        for package in self.packages:
            for handlers in package.event_handlers.values():
                for handler in handlers:
                    if isinstance(handler, Listener) and handler.is_chat_action:  # noqa: SIM102
                        if handler.matches_action_type(action_type):
                            handler_coroutines.append(handler.invoke_chat_action(action_event, action))

        if handler_coroutines:
            await asyncio.gather(*handler_coroutines, return_exceptions=True)

    def add_package(self, package: Package) -> None:
        self.packages.append(package)

        for command in package.commands:
            if isinstance(self.prefixes, list):
                command.update_prefix(*self.prefixes)
            else:
                command.update_prefix(self.prefixes)

    def _register_addon(self, addon: typing.Any) -> None:
        from vkflow.addons.base import BaseAddon, AddonConflictError

        if not isinstance(addon, BaseAddon):
            raise TypeError(f"Expected BaseAddon instance, got {type(addon)}")

        name = addon.meta.name
        if name in self._addons:
            raise AddonConflictError(name, self._addons[name], addon)

        addon.check_dependencies()
        addon.setup(self)
        self._addons[name] = addon

    def add_addon(self, addon: typing.Any) -> None:
        self._register_addon(addon)

    def get_addon(self, name: str) -> typing.Any | None:
        return self._addons.get(name)

    async def on_command_error(self, ctx: NewMessage | CallbackButtonPressed, error: Exception) -> None:
        """
        Called when any command raises an error, regardless of other handlers.

        This is informational and does NOT affect the error handling flow.
        Override this method to add global logging, metrics, or notifications.

        Args:
            ctx: The command context (NewMessage or Context)
            error: The exception that was raised

        Example:
            class MyApp(App):
                async def on_command_error(self, ctx, error):
                    print(f"Error: {error}")
                    await self.send_error_to_admin(error)
        """

    async def on_command_error_fallback(
        self, ctx: NewMessage | CallbackButtonPressed, error: Exception
    ) -> None:
        """
        Called when a command error is not handled by any error handler.

        This is the last fallback before the error is re-raised.
        Override this method to handle all otherwise unhandled errors.
        If this method completes without raising, the error is considered handled.

        Args:
            ctx: The command context (NewMessage or Context)
            error: The exception that was raised

        Example:
            class MyApp(App):
                async def on_command_error_fallback(self, ctx, error):
                    await ctx.reply(f"Произошла ошибка: {error}")
        """
        raise error

    async def startup(self, bot: Bot | None = None) -> None:
        pass

    async def shutdown(self, bot: Bot | None = None) -> None:
        pass

    async def wait_until_ready(self) -> None:
        if self._is_closed:
            raise asyncio.CancelledError("App is closed")

        if self._ready_event is None:
            self._ready_event = asyncio.Event()

        if self._is_ready:
            return

        await self._ready_event.wait()

        if self._is_closed:
            raise asyncio.CancelledError("App is closed")

    def run_when_ready(self, callback: typing.Callable[[], typing.Awaitable[None]]) -> None:
        if self._is_ready:
            task = asyncio.create_task(callback(), name="ready_callback")
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        else:
            self._ready_callbacks.append(callback)

    async def _on_bot_ready(self, bot: Bot) -> None:
        self._ready_bots.add(id(bot))

        if self._bots and len(self._ready_bots) >= len(self._bots):
            logger.opt(colors=True).success("All bots are ready")
            self._is_ready = True

            if self._ready_event is not None:
                self._ready_event.set()

            if self._ready_callbacks:
                logger.debug(f"Executing {len(self._ready_callbacks)} ready callbacks")
                for callback in self._ready_callbacks:
                    task = asyncio.create_task(callback(), name="ready_callback")
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)
                self._ready_callbacks.clear()

    async def add_cog(self, cog: typing.Any) -> None:
        try:
            from vkflow.commands.cog import Cog
        except ImportError:
            Cog = None  # noqa: N806

        if Cog is None:
            raise ImportError("vkflow.commands.cog is required for add_cog()")

        if not isinstance(cog, Cog):
            raise TypeError(f"Expected Cog instance, got {type(cog)}")

        cog_name = type(cog).__name__

        if cog_name in self._cogs:
            raise ValueError(f"Cog {cog_name} is already loaded")

        cog._inject_app(self)

        if hasattr(cog, "_cog_commands"):
            for command in cog._cog_commands:
                command._cog = cog

                if isinstance(self.prefixes, list):
                    command.update_prefix(*self.prefixes)
                else:
                    command.update_prefix(self.prefixes)

                self.commands.append(command)

        if hasattr(cog, "_cog_event_handlers"):
            for event_type, handlers in cog._cog_event_handlers.items():
                for handler in handlers:
                    try:
                        from vkflow.commands.listener import Listener
                    except ImportError:
                        Listener = None  # noqa: N806

                    if Listener is not None and isinstance(handler, Listener):
                        pass

                    elif hasattr(handler, "handler") and hasattr(handler.handler, "__name__"):  # noqa: SIM102
                        if not hasattr(handler.handler, "__self__"):
                            bound_method = getattr(cog, handler.handler.__name__)
                            handler.handler = bound_method

                    if event_type not in self.event_handlers:
                        self.event_handlers[event_type] = []
                    self.event_handlers[event_type].append(handler)

        if hasattr(cog, "_cog_message_handlers"):
            for handler in cog._cog_message_handlers:
                if hasattr(handler.handler, "__name__"):
                    bound_method = getattr(cog, handler.handler.__name__)
                    handler.handler = bound_method
                self.message_handlers.append(handler)

        if hasattr(cog, "_cog_startup_handlers"):
            for handler in cog._cog_startup_handlers:
                if hasattr(handler.handler, "__name__"):
                    bound_method = getattr(cog, handler.handler.__name__)
                    handler.handler = bound_method
                self.startup_handlers.append(handler)

        if hasattr(cog, "_cog_shutdown_handlers"):
            for handler in cog._cog_shutdown_handlers:
                if hasattr(handler.handler, "__name__"):
                    bound_method = getattr(cog, handler.handler.__name__)
                    handler.handler = bound_method
                self.shutdown_handlers.append(handler)

        self._cogs[cog_name] = cog

        logger.opt(colors=True).success(
            "Loaded cog: <c>{cog_name}</c>",
            cog_name=cog_name,
        )

        try:
            await cog.cog_load()
        except Exception:
            await self.remove_cog(cog_name)
            raise

    async def remove_cog(self, cog_name: str) -> None:
        if cog_name not in self._cogs:
            raise ValueError(f"Cog {cog_name} is not loaded")

        cog = self._cogs[cog_name]

        try:
            await cog.cog_unload()
        except Exception as e:
            logger.opt(colors=True).warning(
                "Error in cog_unload for <c>{cog_name}</c>: {error}",
                cog_name=cog_name,
                error=e,
            )

        if hasattr(cog, "_cog_commands"):
            for command in cog._cog_commands:
                if command in self.commands:
                    self.commands.remove(command)

        if hasattr(cog, "_cog_event_handlers"):
            for event_type, handlers in cog._cog_event_handlers.items():
                for handler in handlers:
                    if event_type in self.event_handlers and handler in self.event_handlers[event_type]:
                        self.event_handlers[event_type].remove(handler)

        if hasattr(cog, "_cog_message_handlers"):
            for handler in cog._cog_message_handlers:
                if handler in self.message_handlers:
                    self.message_handlers.remove(handler)

        if hasattr(cog, "_cog_startup_handlers"):
            for handler in cog._cog_startup_handlers:
                if handler in self.startup_handlers:
                    self.startup_handlers.remove(handler)

        if hasattr(cog, "_cog_shutdown_handlers"):
            for handler in cog._cog_shutdown_handlers:
                if handler in self.shutdown_handlers:
                    self.shutdown_handlers.remove(handler)

        del self._cogs[cog_name]
        cog.app = None

        logger.opt(colors=True).success(
            "Removed cog: <c>{cog_name}</c>",
            cog_name=cog_name,
        )

    def get_command(self, name: str) -> Command | Group | None:
        for package in self.packages:
            if hasattr(package, "commands"):
                for command in package.commands:
                    if hasattr(command, "names"):
                        if name in command.names:
                            return command

                    elif hasattr(command, "name") and command.name == name:
                        return command

        for package in self.packages:
            if hasattr(package, "commands"):
                for command in package.commands:
                    if hasattr(command, "commands") and isinstance(command.commands, dict):
                        for subcmd_name, subcmd in command.commands.items():
                            if hasattr(subcmd, "names"):
                                if name in subcmd.names:
                                    return subcmd

                            elif subcmd_name == name:
                                return subcmd

        return None

    def get_cog(self, name: str) -> Cog | None:
        return self._cogs.get(name)

    async def load_extension(self, name: str) -> None:
        if name in self._extensions:
            raise ValueError(f"Extension {name} is already loaded")

        try:
            module = importlib.import_module(name)
        except ImportError as e:
            raise ImportError(f"Failed to import extension {name}: {e}") from e

        if not hasattr(module, "setup"):
            raise ValueError(
                f"Extension {name} does not have a setup function. "
                f"Please add: async def setup(app: App): ..."
            )

        try:
            if inspect.iscoroutinefunction(module.setup):
                await module.setup(self)
            else:
                module.setup(self)

            self._extensions[name] = module
            logger.opt(colors=True).success(
                "Loaded extension: <c>{name}</c>",
                name=name,
            )

        except Exception as e:
            raise RuntimeError(f"Failed to setup extension {name}: {e}") from e

    async def unload_extension(self, name: str) -> None:
        if name not in self._extensions:
            raise ValueError(f"Extension {name} is not loaded")

        module = self._extensions[name]

        if hasattr(module, "teardown"):
            try:
                if inspect.iscoroutinefunction(module.teardown):
                    await module.teardown(self)
                else:
                    module.teardown(self)
            except Exception as e:
                logger.opt(colors=True).warning(
                    "Failed to teardown extension <c>{name}</c>: {error}",
                    name=name,
                    error=e,
                )

        if name in sys.modules:
            del sys.modules[name]

        del self._extensions[name]

        logger.opt(colors=True).success(
            "Unloaded extension: <c>{name}</c>",
            name=name,
        )

    async def reload_extension(self, name: str) -> None:
        if name not in self._extensions:
            raise ValueError(f"Extension {name} is not loaded")

        await self.unload_extension(name)
        await self.load_extension(name)

        logger.opt(colors=True).success(
            "Reloaded extension: <c>{name}</c>",
            name=name,
        )

    def run(
        self,
        *tokens: str | API,
        bot_payload_factory: type[BotPayloadFieldTypevar] | None = None,
    ) -> asyncio.Task | None:
        coro = self.start(
            *tokens,
            bot_payload_factory=bot_payload_factory,
        )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._run_sync(coro)
            return None
        else:
            return loop.create_task(coro, name="vkflow_app")

    def _run_sync(self, coro: typing.Coroutine) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        if self.debug:
            loop.set_debug(True)

        try:
            loop.run_until_complete(coro)

        except KeyboardInterrupt:
            pass

        finally:
            try:
                pending = asyncio.all_tasks(loop)

                for task in pending:
                    task.cancel()

                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

                loop.run_until_complete(loop.shutdown_asyncgens())

            except Exception:
                pass

            finally:
                asyncio.set_event_loop(None)
                loop.close()

    async def start(
        self,
        *tokens: str | API,
        bot_payload_factory: type[BotPayloadFieldTypevar] | None = None,
    ) -> None:
        logger.opt(colors=True).success(
            "Run app (<b>{count}</b> bot{postfix})",
            count=len(tokens),
            postfix="s" if len(tokens) > 1 else "",
        )

        bots_init_coroutines = [
            Bot.via_token(token=token, app=self, payload_factory=bot_payload_factory) for token in tokens
        ]

        async with asyncio.TaskGroup() as tg:
            bot_tasks = [tg.create_task(coro) for coro in bots_init_coroutines]
        bots = [t.result() for t in bot_tasks]
        self._bots = list(bots)

        if self._ready_event is None:
            self._ready_event = asyncio.Event()

        await self._call_startup(*bots)

        self._polling_tasks = [
            asyncio.create_task(bot.run_polling(), name=f"bot_polling_{i}") for i, bot in enumerate(bots)
        ]

        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()

        def signal_handler(sig):
            logger.opt(colors=True).warning(
                f"Received signal <r>{signal.Signals(sig).name}</r>, shutting down..."
            )

            loop.call_soon_threadsafe(shutdown_event.set)

        if sys.platform == "win32":
            signal.signal(signal.SIGINT, lambda s, f: signal_handler(s))
            signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s))
        else:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

        try:
            _, pending = await asyncio.wait(
                [*self._polling_tasks, asyncio.create_task(shutdown_event.wait())],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if shutdown_event.is_set():
                for task in pending:
                    task.cancel()

                await asyncio.gather(*pending, return_exceptions=True)

        except KeyboardInterrupt:
            logger.opt(colors=True).warning("Received <r>KeyboardInterrupt</r>, shutting down...")

        except asyncio.CancelledError:
            logger.opt(colors=True).warning("Tasks cancelled, shutting down...")

        finally:
            await self.close()

            if sys.platform == "win32":
                signal.signal(signal.SIGINT, signal.default_int_handler)
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
            else:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.remove_signal_handler(sig)

            executor = getattr(loop, "_default_executor", None)

            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)

            _prevent_shutdown_hang()

    async def close(self) -> None:
        self._is_closed = True

        if self._ready_event is not None:
            self._ready_event.set()

        for task in self._polling_tasks:
            if not task.done():
                task.cancel()

        await asyncio.gather(*self._polling_tasks, return_exceptions=True)
        self._polling_tasks = []

        if self._bots:
            await self._call_shutdown(*self._bots)

            for bot in self._bots:
                await bot.close_sessions()

    async def _call_startup(self, *bots: Bot) -> None:
        for addon in self._addons.values():
            await addon.on_startup(self, list(bots))

        startup_coroutines = []

        sig = inspect.signature(self.startup)

        params = list(sig.parameters.values())
        params = [p for p in params if p.name != "self"]

        for bot in bots:
            if len(params) > 0:
                startup_coroutines.append(self.startup(bot))
            else:
                startup_coroutines.append(self.startup())

        for pkg in self.packages:
            for startup_handler in pkg.startup_handlers:
                startup_coroutines.extend(startup_handler.handler(bot) for bot in bots)

        async with asyncio.TaskGroup() as tg:
            for coro in startup_coroutines:
                tg.create_task(coro)

    async def _call_shutdown(self, *bots: Bot) -> None:
        shutdown_coroutines = []

        sig = inspect.signature(self.shutdown)

        params = list(sig.parameters.values())
        params = [p for p in params if p.name != "self"]

        for bot in bots:
            if len(params) > 0:
                shutdown_coroutines.append(self.shutdown(bot))
            else:
                shutdown_coroutines.append(self.shutdown())

        for pkg in self.packages:
            for shutdown_handler in pkg.shutdown_handlers:
                shutdown_coroutines.extend(shutdown_handler.handler(bot) for bot in bots)

        async with asyncio.TaskGroup() as tg:
            for coro in shutdown_coroutines:
                tg.create_task(coro)

        for addon in self._addons.values():
            await addon.on_shutdown(self, list(bots))


BotPayloadFieldTypevar = typing.TypeVar("BotPayloadFieldTypevar")


@dataclasses.dataclass
class Bot(typing.Generic[AppPayloadFieldTypevar, BotPayloadFieldTypevar]):
    app: App[AppPayloadFieldTypevar]
    api: API
    events_factory: BaseEventFactory
    payload_factory: type[BotPayloadFieldTypevar] = dataclasses.field(default=None)
    _background_tasks: set = dataclasses.field(default_factory=set, init=False, repr=False)

    @property
    def token_owner(self) -> TokenOwner:
        return self.api.token_owner

    @property
    def owner(self):
        return self.api.owner

    @functools.cached_property
    def payload(self) -> BotPayloadFieldTypevar:
        return self.payload_factory()

    @classmethod
    async def via_token(
        cls, *, token: str | API, app: App, payload_factory: type[BotPayloadFieldTypevar] | None = None
    ) -> Bot:
        api = token if isinstance(token, API) else API(token)

        token_owner, _ = await api.define_token_owner()
        events_factory: BaseEventFactory

        events_factory = UserLongPoll(api) if token_owner == TokenOwner.USER else GroupLongPoll(api)

        return cls(
            app=app,
            api=api,
            events_factory=events_factory,
            payload_factory=payload_factory,
        )

    async def run_polling(self):
        async def dispatch_ready_when_ready():
            await self.events_factory.wait_until_ready()
            logger.opt(colors=True).success("Bot is ready, dispatching on_ready event")
            await self.app.dispatch_event("ready", bot=self)

        task = asyncio.create_task(dispatch_ready_when_ready(), name="dispatch_ready")
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        async for event in self.events_factory.listen():
            logger.opt(colors=True).info(
                "New event: <y>{event_type}</y>",
                event_type=event.type,
            )

            new_event_storage = NewEvent(event=event, bot=self)

            task = asyncio.create_task(
                self.handle_event(new_event_storage), name=f"handle_event_{event.type}"
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    @logger.catch(exclude=StopStateHandlingError)
    async def handle_event(self, new_event_storage: NewEvent, wrap_to_task: bool = True):
        route_event_coroutine = self.app.route_event(new_event_storage)

        if wrap_to_task:
            task = asyncio.create_task(
                route_event_coroutine, name=f"route_event_{new_event_storage.event.type}"
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        else:
            await route_event_coroutine

        if new_event_storage.event.type in {
            "message_new",
            "message_reply",
            4,
        } and (len(new_event_storage.event.content) > 3 or isinstance(new_event_storage.event, GroupEvent)):
            ctx = await NewMessage.from_event(
                event=new_event_storage.event,
                bot=new_event_storage.bot,
                payload_factory=new_event_storage.payload_factory,
            )

            if ctx.msg.action is not None:
                chat_action_coroutine = self.app.dispatch_chat_action(ctx)

                if wrap_to_task:
                    task = asyncio.create_task(
                        chat_action_coroutine, name=f"route_chat_action_{ctx.msg.peer_id}"
                    )
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)
                else:
                    await chat_action_coroutine

            route_message_coroutine = self.app.route_message(ctx)

            if wrap_to_task:
                task = asyncio.create_task(route_message_coroutine, name=f"route_message_{ctx.msg.peer_id}")
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            else:
                await route_message_coroutine

        elif new_event_storage.event.type == "message_event":
            context = await CallbackButtonPressed.from_event(
                event=new_event_storage.event, bot=new_event_storage.bot
            )

            route_callback_button_pressing_coroutine = self.app.route_callback_button_pressing(context)

            if wrap_to_task:
                task = asyncio.create_task(
                    route_callback_button_pressing_coroutine, name=f"route_callback_{context.msg.peer_id}"
                )
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

            else:
                await route_callback_button_pressing_coroutine

    async def close_sessions(self):
        await self.events_factory.close_session()
        await self.api.close_session()

    async def mention(self, alias: str | None = None) -> str:
        if self.api.owner is None:
            await self.api.define_token_owner()

        return self.api.owner.mention(alias)


def _prevent_shutdown_hang() -> None:
    """Prevent interpreter from hanging on non-daemon thread join.

    Python 3.12+ uses non-daemon executor threads and
    ``threading._shutdown`` joins them via ``_thread._shutdown``.
    If any thread is blocked (e.g. DNS resolution in
    ``socket.getaddrinfo``), the interpreter hangs on exit.

    This function gives remaining threads a brief window to
    finish, and if any are still alive, calls ``os._exit(0)``
    to skip ``_thread._shutdown`` entirely.  All application-level
    cleanup (sessions, server, loop) has already been done
    by this point.
    """
    import os
    import threading

    alive = [
        t
        for t in threading.enumerate()
        if t is not threading.main_thread() and not t.daemon and t.is_alive()
    ]

    if not alive:
        return

    for t in alive:
        t.join(timeout=1.5)

    if any(t.is_alive() for t in alive):
        sys.stdout.flush()
        sys.stderr.flush()

        os._exit(0)
