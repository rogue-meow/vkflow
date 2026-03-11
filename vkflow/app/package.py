from __future__ import annotations

import asyncio
import collections
import dataclasses
import inspect
import os
import re
import sys
import typing

from vkflow.base.handler_container import HandlerMixin
from vkflow.commands.core import Command, Group
from vkflow.commands.parsing.cutters import UserID, PageID
from vkflow.exceptions import StopCurrentHandlingError
from vkflow.app.storages import (
    CallbackButtonPressed,
    NewEvent,
    NewMessage,
)
from vkflow.ui.button import (
    ButtonCallbackHandler,
    ButtonOnclickHandler,
)

unset = object()


@dataclasses.dataclass
class MessageHandler(HandlerMixin[typing.Callable[[NewMessage], typing.Awaitable]]):
    filter: BaseFilter | None = None

    async def run_handling(self, ctx: NewMessage):
        if self.filter is not None:
            try:
                await self.filter.run_making_decision(ctx)
            except StopCurrentHandlingError:
                return
        await self.handler(ctx)


class UserAddedHandler(HandlerMixin[typing.Callable[[NewMessage, PageID, UserID], typing.Awaitable]]):
    async def run_handling(self, ctx: NewMessage):
        if (
            ctx.msg.action is not None
            and ctx.msg.action["type"] == "chat_invite_user"
            and ctx.msg.from_id
            != int(invited_user := (ctx.msg.action.get("member_id") or ctx.msg.action.get("source_mid")))
        ):
            await self.handler(ctx, PageID(invited_user), UserID(ctx.msg.from_id))


class UserJoinedByLinkHandler(HandlerMixin[typing.Callable[[NewMessage, UserID], typing.Awaitable]]):
    async def run_handling(self, ctx: NewMessage):
        if ctx.msg.action is not None and ctx.msg.action["type"] == "chat_invite_user_by_link":
            await self.handler(ctx, UserID(ctx.msg.from_id))


class UserReturnedHandler(HandlerMixin[typing.Callable[[NewMessage, UserID], typing.Awaitable]]):
    async def run_handling(self, ctx: NewMessage):
        if (
            ctx.msg.action is not None
            and ctx.msg.action["type"] == "chat_invite_user"
            and ctx.msg.from_id == int(ctx.msg.action.get("member_id") or ctx.msg.action.get("source_mid"))
        ):
            await self.handler(ctx, UserID(ctx.msg.from_id))


if typing.TYPE_CHECKING:  # pragma: no cover
    from vkflow.app.bot import App, Bot
    from vkflow.app.prefixes import PrefixType
    from vkflow.base.event import EventType
    from vkflow.base.filter import BaseFilter
    from vkflow.commands.parsing.cutter import InvalidArgumentConfig


class SignalHandler(HandlerMixin[typing.Callable[["Bot"], typing.Awaitable]]):
    pass


class EventHandler(HandlerMixin[typing.Callable[[NewEvent], typing.Awaitable]]):
    pass


if typing.TYPE_CHECKING:  # pragma: no cover
    from vkflow.utils.vktypes import DecoratorFunction

    SignalHandlerTypevar = typing.TypeVar("SignalHandlerTypevar", bound=SignalHandler)
    EventHandlerTypevar = typing.TypeVar("EventHandlerTypevar", bound=EventHandler)
    MessageHandlerTypevar = typing.TypeVar("MessageHandlerTypevar", bound=MessageHandler)


def _auto_detect_package_name() -> str:
    """Определить имя пакета по имени переменной или модуля вызывающего кода."""
    import linecache

    frame = sys._getframe(1)
    while frame is not None:
        co_filename = frame.f_code.co_filename
        if "dataclasses" not in co_filename and "package.py" not in co_filename:
            break
        frame = frame.f_back

    if frame is None:
        return "package"

    line = linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip()
    match = re.match(r"(\w+)\s*=", line)
    if match:
        candidate = match.group(1)
        if candidate not in ("_", "__"):
            return candidate

    module_name = frame.f_globals.get("__name__", "")
    if module_name and module_name != "__main__":
        return module_name.rsplit(".", 1)[-1]

    basename = os.path.splitext(os.path.basename(frame.f_code.co_filename))[0]
    return basename if basename and basename != "__init__" else "package"


@dataclasses.dataclass
class Package:
    """Функциональный контейнер для команд, обработчиков и хуков."""

    prefixes: PrefixType = dataclasses.field(default_factory=list)
    name: str | None = None
    filter: BaseFilter | None = None
    commands: list[Command] = dataclasses.field(default_factory=list)
    event_handlers: dict[EventType, list[EventHandler]] = dataclasses.field(
        default_factory=lambda: collections.defaultdict(list)
    )
    message_handlers: list[MessageHandler] = dataclasses.field(default_factory=list)
    startup_handlers: list[SignalHandler] = dataclasses.field(default_factory=list)
    shutdown_handlers: list[SignalHandler] = dataclasses.field(default_factory=list)
    button_onclick_handlers: dict[str, ButtonOnclickHandler] = dataclasses.field(default_factory=dict)
    button_callback_handlers: dict[str, ButtonCallbackHandler] = dataclasses.field(default_factory=dict)
    inviting_handlers: list[UserReturnedHandler | UserJoinedByLinkHandler | UserAddedHandler] = (
        dataclasses.field(default_factory=list)
    )

    fsm_storage: typing.Any = dataclasses.field(default=None, repr=False)
    fsm_strategy: str = dataclasses.field(default="user_chat", repr=False)

    _app: App | None = dataclasses.field(default=None, init=False, repr=False)
    _before_invoke_handler: typing.Any = dataclasses.field(default=None, init=False, repr=False)
    _after_invoke_handler: typing.Any = dataclasses.field(default=None, init=False, repr=False)
    _error_handler_func: typing.Any = dataclasses.field(default=None, init=False, repr=False)
    _error_fallback_func: typing.Any = dataclasses.field(default=None, init=False, repr=False)
    _fsm_handlers: dict = dataclasses.field(default_factory=dict, init=False, repr=False)
    _before_command_hooks: list = dataclasses.field(default_factory=list, init=False, repr=False)
    _after_command_hooks: list = dataclasses.field(default_factory=list, init=False, repr=False)

    def __post_init__(self):
        if self.name is None:
            self.name = _auto_detect_package_name()
        for cmd in self.commands:
            cmd._package = self

    def command(
        self,
        *names: str,
        prefixes: PrefixType | None = None,
        aliases: list[str] | None = None,
        routing_re_flags: re.RegexFlag | int = re.IGNORECASE,
        exclude_from_autodoc: bool = False,
        filter: BaseFilter | None = None,
        description: str | None = None,
        help: str | None = None,
        brief: str | None = None,
        usage: str | None = None,
        enabled: bool = True,
        hidden: bool = False,
        invalid_argument_config: InvalidArgumentConfig | None = unset,
        **kwargs,
    ) -> typing.Callable[[DecoratorFunction], Command[DecoratorFunction]]:
        def wrapper(func):
            cmd_name = names[0] if names else func.__name__
            cmd_aliases = list(names[1:]) if len(names) > 1 else []
            if aliases:
                cmd_aliases.extend(aliases)

            cmd_kwargs = {
                "prefixes": prefixes or self.prefixes,
                "routing_re_flags": routing_re_flags,
                "exclude_from_autodoc": exclude_from_autodoc or hidden,
                "filter": filter,
                "description": description,
                "help": help,
                "brief": brief,
                "usage": usage,
                "enabled": enabled,
                "hidden": hidden,
            }

            if invalid_argument_config != unset:
                cmd_kwargs["invalid_argument_config"] = invalid_argument_config

            cmd_kwargs.update(kwargs)

            if hasattr(func, "__vkflow_checks__"):
                checks = func.__vkflow_checks__
                if checks:
                    combined_filter = cmd_kwargs["filter"]
                    for check in checks:
                        combined_filter = check if combined_filter is None else combined_filter & check
                    cmd_kwargs["filter"] = combined_filter

            cmd = Command(
                func,
                name=cmd_name,
                aliases=cmd_aliases or None,
                **cmd_kwargs,
            )
            cmd._package = self
            self.commands.append(cmd)

            return cmd

        return wrapper

    def group(
        self,
        *names: str,
        prefixes: PrefixType | None = None,
        aliases: list[str] | None = None,
        routing_re_flags: re.RegexFlag | int = re.IGNORECASE,
        exclude_from_autodoc: bool = False,
        filter: BaseFilter | None = None,
        description: str | None = None,
        help: str | None = None,
        brief: str | None = None,
        usage: str | None = None,
        enabled: bool = True,
        hidden: bool = False,
        invoke_without_command: bool = False,
        invalid_argument_config: InvalidArgumentConfig | None = unset,
        **kwargs,
    ) -> typing.Callable[[DecoratorFunction], Group[DecoratorFunction]]:
        """Декоратор для регистрации группы команд в пакете."""

        def wrapper(func):
            grp_name = names[0] if names else func.__name__
            grp_aliases = list(names[1:]) if len(names) > 1 else []
            if aliases:
                grp_aliases.extend(aliases)

            grp_kwargs = {
                "prefixes": prefixes or self.prefixes,
                "routing_re_flags": routing_re_flags,
                "exclude_from_autodoc": exclude_from_autodoc or hidden,
                "filter": filter,
                "description": description,
                "help": help,
                "brief": brief,
                "usage": usage,
                "enabled": enabled,
                "hidden": hidden,
                "invoke_without_command": invoke_without_command,
            }

            if invalid_argument_config != unset:
                grp_kwargs["invalid_argument_config"] = invalid_argument_config

            grp_kwargs.update(kwargs)

            if hasattr(func, "__vkflow_checks__"):
                checks = func.__vkflow_checks__
                if checks:
                    combined_filter = grp_kwargs["filter"]
                    for check in checks:
                        combined_filter = check if combined_filter is None else combined_filter & check
                    grp_kwargs["filter"] = combined_filter

            grp = Group(
                func,
                name=grp_name,
                aliases=grp_aliases or None,
                **grp_kwargs,
            )
            grp._package = self
            self.commands.append(grp)

            return grp

        return wrapper

    def listener(self, *names: str) -> typing.Callable:
        """
        Декоратор для регистрации слушателя событий.

        Создаёт объект Listener и регистрирует его в event_handlers.
        Поддерживает несколько имён событий одновременно.

        Args:
            *names: Имена событий. Если не указаны, определяется по имени функции
                    (префикс ``on_`` убирается автоматически).

        Returns:
            Декоратор, оборачивающий функцию в Listener

        Example:
            @package.listener()
            async def on_message_new(payload):
                print(f"Новое сообщение: {payload}")

            @package.listener("message_reply")
            async def handle_reply(user_id, text):
                print(f"Ответ от {user_id}: {text}")

            @package.listener("message_typing_state", "message_event")
            async def handle_multiple(event):
                print(f"Событие: {event}")
        """
        from vkflow.commands.listener import Listener

        def decorator(func):
            event_names = names if names else (None,)
            first_listener = None

            for event_name in event_names:
                lst = Listener(func, event_name=event_name)
                event_key = lst.event_name

                if lst.is_chat_action:
                    event_key = "message_new"

                if event_key not in self.event_handlers:
                    self.event_handlers[event_key] = []
                self.event_handlers[event_key].append(lst)

                if first_listener is None:
                    first_listener = lst

            return first_listener

        return decorator

    def on_event(
        self, *event_types: EventType
    ) -> typing.Callable[[EventHandlerTypevar], EventHandlerTypevar]:
        """
        .. deprecated::
            Используйте :meth:`listener` вместо ``on_event``.
        """
        import warnings

        warnings.warn(
            "on_event() устарел, используйте listener() вместо него",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.listener(*event_types)

    def on_message(
        self, filter: BaseFilter | None = None
    ) -> typing.Callable[[MessageHandlerTypevar], MessageHandlerTypevar]:
        def wrapper(func):
            handler = MessageHandler(handler=func, filter=filter)
            self.message_handlers.append(handler)

            return func

        return wrapper

    def on_returned_user(self) -> typing.Callable[[DecoratorFunction], Command[DecoratorFunction]]:
        def wrapper(func):
            self.inviting_handlers.append(UserReturnedHandler(func))

            return func

        return wrapper

    def on_user_joined_by_link(self) -> typing.Callable[[DecoratorFunction], Command[DecoratorFunction]]:
        def wrapper(func):
            self.inviting_handlers.append(UserJoinedByLinkHandler(func))

            return func

        return wrapper

    def on_added_page(self) -> typing.Callable[[DecoratorFunction], Command[DecoratorFunction]]:
        def wrapper(func):
            self.inviting_handlers.append(UserAddedHandler(func))

            return func

        return wrapper

    def on_clicked_button(
        self,
    ) -> typing.Callable[[DecoratorFunction], ButtonOnclickHandler]:
        def wrapper(func):
            if isinstance(func, Command):
                func = func.handler
            handler = ButtonOnclickHandler(func)

            self.button_onclick_handlers[func.__name__] = handler

            return handler

        return wrapper

    def on_called_button(
        self,
    ) -> typing.Callable[[DecoratorFunction], ButtonCallbackHandler]:
        def wrapper(func):
            if isinstance(func, Command):
                func = func.handler
            handler = ButtonCallbackHandler(func)

            self.button_callback_handlers[func.__name__] = handler

            return handler

        return wrapper

    def on_startup(
        self,
    ) -> typing.Callable[[SignalHandlerTypevar], SignalHandlerTypevar]:
        def wrapper(func):
            handler = SignalHandler(func)
            self.startup_handlers.append(handler)

            return func

        return wrapper

    def on_shutdown(
        self,
    ) -> typing.Callable[[SignalHandlerTypevar], SignalHandlerTypevar]:
        def wrapper(func):
            handler = SignalHandler(func)
            self.shutdown_handlers.append(handler)

            return func

        return wrapper

    def before_invoke(self) -> typing.Callable:
        """
        Декоратор для хука, вызываемого перед каждой командой пакета.

        Если хук вернёт False, выполнение команды будет отменено.

        Example:
            @package.before_invoke()
            async def before(ctx):
                print(f"Запускаю {ctx.command.name}")
        """

        def decorator(func):
            if self._before_invoke_handler is not None:
                raise ValueError(f"Пакет '{self.name}' уже имеет обработчик before_invoke.")
            self._before_invoke_handler = func
            return func

        return decorator

    def after_invoke(self) -> typing.Callable:
        """
        Декоратор для хука, вызываемого после каждой команды пакета.

        Вызывается всегда, независимо от результата выполнения.

        Example:
            @package.after_invoke()
            async def after(ctx, result=None, error=None):
                if error:
                    print(f"Ошибка: {error}")
        """

        def decorator(func):
            if self._after_invoke_handler is not None:
                raise ValueError(f"Пакет '{self.name}' уже имеет обработчик after_invoke.")
            self._after_invoke_handler = func
            return func

        return decorator

    def error_handler(self) -> typing.Callable:
        """
        Декоратор для информационного обработчика ошибок пакета.

        Вызывается при любой ошибке команды (не влияет на поток ошибок).

        Example:
            @package.error_handler()
            async def on_error(ctx, error):
                print(f"Ошибка в {ctx.command.name}: {error}")
        """

        def decorator(func):
            if self._error_handler_func is not None:
                raise ValueError(f"Пакет '{self.name}' уже имеет error_handler.")
            self._error_handler_func = func
            return func

        return decorator

    def error_fallback(self) -> typing.Callable:
        """
        Декоратор для fallback-обработчика ошибок пакета.

        Вызывается, когда ошибка не обработана локальными обработчиками.
        Если завершится без исключения, ошибка считается обработанной.

        Example:
            @package.error_fallback()
            async def fallback(ctx, error):
                await ctx.send(f"Произошла ошибка: {error}")
        """

        def decorator(func):
            if self._error_fallback_func is not None:
                raise ValueError(f"Пакет '{self.name}' уже имеет error_fallback.")
            self._error_fallback_func = func
            return func

        return decorator

    def before_command(self) -> typing.Callable:
        """
        Декоратор для middleware-хука, вызываемого перед командой пакета.

        Можно зарегистрировать несколько обработчиков.
        Если любой вернёт False, выполнение команды будет отменено.

        Example:
            @package.before_command()
            async def log_cmd(ctx):
                print(f"Команда: {ctx.command.name}")
        """

        def decorator(func):
            self._before_command_hooks.append(func)
            return func

        return decorator

    def after_command(self) -> typing.Callable:
        """
        Декоратор для middleware-хука, вызываемого после команды пакета.

        Можно зарегистрировать несколько обработчиков.

        Example:
            @package.after_command()
            async def track(ctx, result=None, error=None):
                print(f"Команда {ctx.command.name} завершена")
        """

        def decorator(func):
            self._after_command_hooks.append(func)
            return func

        return decorator

    def state(
        self,
        state_obj: typing.Any,
        *,
        strategy: str | None = None,
    ) -> typing.Callable:
        """
        Декоратор для регистрации обработчика FSM-состояния.

        Требует установки fsm_storage при создании пакета.

        Args:
            state_obj: Объект State или строка с именем состояния
            strategy: Опциональное переопределение стратегии ключа

        Example:
            package = Package(prefixes=["/"], fsm_storage=MemoryStorage())

            @package.state(OrderStates.waiting_name)
            async def handle_name(ctx, msg):
                await ctx.update_data(name=msg.msg.text)
                await ctx.set_state(OrderStates.waiting_phone)
        """

        def decorator(func):
            state_name = state_obj.name if hasattr(state_obj, "name") else str(state_obj)
            self._fsm_handlers[state_name] = func
            if strategy is not None:
                self.fsm_strategy = strategy
            return func

        return decorator

    def get_fsm(
        self,
        ctx: NewMessage | CallbackButtonPressed,
        *,
        strategy: str | None = None,
    ) -> typing.Any:
        """
        Получить FSMContext для данного контекста.

        Args:
            ctx: NewMessage или CallbackButtonPressed
            strategy: Опциональное переопределение стратегии ключа

        Raises:
            ValueError: Если fsm_storage не настроен
        """
        if self.fsm_storage is None:
            raise ValueError(
                f"FSM-хранилище не настроено для пакета '{self.name}'. "
                "Установите fsm_storage при создании пакета."
            )

        from vkflow.app.fsm import Context as FSMContext

        message = ctx._message if hasattr(ctx, "_message") else ctx
        return FSMContext.from_message(
            self.fsm_storage,
            message,
            strategy=strategy or self.fsm_strategy,
        )

    async def process_fsm(self, message: NewMessage) -> bool:
        """
        Обработать сообщение через FSM-обработчики пакета.

        Returns:
            True если обработчик был вызван, False иначе
        """
        if self.fsm_storage is None or not self._fsm_handlers:
            return False

        from vkflow.app.fsm import Context as FSMContext

        fsm_ctx = FSMContext.from_message(
            self.fsm_storage,
            message,
            strategy=self.fsm_strategy,
        )

        current_state = await fsm_ctx.get_state()
        if current_state is None:
            return False

        handler = self._fsm_handlers.get(current_state)
        if handler is None:
            return False

        sig = inspect.signature(handler)
        kwargs = {}

        for param_name in sig.parameters:
            if param_name in ("ctx", "fsm"):
                kwargs[param_name] = fsm_ctx
            elif param_name in ("msg", "message"):
                kwargs[param_name] = message
            elif param_name == "data":
                kwargs[param_name] = await fsm_ctx.get_data()
            elif param_name == "state":
                kwargs[param_name] = current_state

        await handler(**kwargs)
        return True

    def get_fsm_states(self) -> list[str]:
        """Получить все FSM-состояния, обрабатываемые этим пакетом."""
        return list(self._fsm_handlers.keys())

    def get_commands(self) -> list[Command]:
        """Получить все команды в этом пакете."""
        return self.commands.copy()

    def walk_commands(self) -> typing.Generator[Command, None, None]:
        """Итерация по всем командам, включая подкоманды групп."""
        for command in self.commands:
            yield command
            if hasattr(command, "all_commands"):
                yield from set(command.all_commands.values())

    async def handle_event(self, new_event_storage: NewEvent) -> None:
        handlers = self.event_handlers[new_event_storage.event.type]
        handle_coroutines = []

        for handler in handlers:
            if hasattr(handler, "invoke") and callable(handler.invoke):
                handle_coroutines.append(handler.invoke(new_event_storage))

            elif hasattr(handler, "handler"):
                handle_coroutines.append(handler.handler(new_event_storage))

            else:
                handle_coroutines.append(handler(new_event_storage))

        async with asyncio.TaskGroup() as tg:
            for coro in handle_coroutines:
                tg.create_task(coro)

    async def handle_message(self, ctx: NewMessage):
        if self.filter is not None:
            try:
                await self.filter.run_making_decision(ctx)
            except StopCurrentHandlingError:
                return

        command_coroutines = [command.handle_message(ctx) for command in self.commands]

        message_handler_coroutines = [
            message_handler.run_handling(ctx) for message_handler in self.message_handlers
        ]

        inviting_handler_coroutines = [
            inviting_handler.run_handling(ctx) for inviting_handler in self.inviting_handlers
        ]

        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.routing_payload(ctx))
            for coro in command_coroutines:
                tg.create_task(coro)
            for coro in message_handler_coroutines:
                tg.create_task(coro)
            for coro in inviting_handler_coroutines:
                tg.create_task(coro)

    async def routing_payload(self, ctx: NewMessage):
        if (
            isinstance(ctx.msg.payload, dict)
            and ctx.msg.payload.get("command") in self.button_onclick_handlers
        ):
            handler_name = ctx.msg.payload.get("command")
            extra_arguments = {}

            if "args" in ctx.msg.payload:
                extra_arguments = ctx.msg.payload.get("args")

                if isinstance(extra_arguments, list):
                    extra_arguments = {}

            handler = self.button_onclick_handlers[handler_name]

            if NewMessage in handler.handler.__annotations__.values():
                response = await handler.handler(ctx, **extra_arguments)
            else:
                response = await handler.handler(**extra_arguments)

            if response is not None:
                await ctx.reply(str(response))

    async def handle_callback_button_pressing(self, ctx: CallbackButtonPressed):
        if ctx.msg.payload is not None and ctx.msg.payload.get("command") in self.button_callback_handlers:
            handler_name = ctx.msg.payload.get("command")
            extra_arguments = {}

            if "args" in ctx.msg.payload:
                extra_arguments = ctx.msg.payload.get("args")

                if isinstance(extra_arguments, list):
                    extra_arguments = {}

            handler = self.button_callback_handlers[handler_name]

            if CallbackButtonPressed in handler.handler.__annotations__.values():
                response = await handler.handler(ctx, **extra_arguments)

            else:
                response = await handler.handler(**extra_arguments)

            if response is not None:
                await ctx.show_snackbar(str(response))

    def __repr__(self) -> str:
        return f"<Package {self.name!r}>"
