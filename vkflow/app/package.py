from __future__ import annotations

import asyncio
import collections
import dataclasses
import re
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
    from vkflow.app.bot import Bot
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


@dataclasses.dataclass
class Package:
    prefixes: PrefixType = dataclasses.field(default_factory=list)
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

            command = Command(
                func,
                name=cmd_name,
                aliases=cmd_aliases or None,
                **cmd_kwargs,
            )
            self.commands.append(command)

            return command

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
            self.commands.append(grp)

            return grp

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

    def on_event(
        self, *event_types: EventType
    ) -> typing.Callable[[EventHandlerTypevar], EventHandlerTypevar]:
        def wrapper(func):
            for event_type in event_types:
                handler = EventHandler(func)

                self.event_handlers[event_type].append(handler)

            return func

        return wrapper

    def listener(self, name: str | None = None) -> typing.Callable:
        """
        Декоратор для регистрации слушателя события напрямую в приложении.

        Создаёт объект Listener и регистрирует его в event_handlers.

        Args:
            name: Имя события. Если не указано, определяется по имени функции
                  (префикс ``on_`` убирается автоматически).

        Returns:
            Декоратор, оборачивающий функцию в Listener

        Example:
            app = vf.App()

            @app.listener()
            async def on_message_new(payload):
                print(f"Новое сообщение: {payload}")

            @app.listener("message_reply")
            async def handle_reply(user_id, text):
                print(f"Ответ от {user_id}: {text}")
        """
        from vkflow.commands.listener import Listener

        def decorator(func):
            lst = Listener(func, event_name=name)
            event_key = lst.event_name

            if lst.is_chat_action:
                event_key = "message_new"

            if event_key not in self.event_handlers:
                self.event_handlers[event_key] = []
            self.event_handlers[event_key].append(lst)

            return lst

        return decorator

    def on_message(
        self, filter: BaseFilter | None = None
    ) -> typing.Callable[[MessageHandlerTypevar], MessageHandlerTypevar]:
        def wrapper(func):
            handler = MessageHandler(handler=func, filter=filter)
            self.message_handlers.append(handler)

            return func

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
