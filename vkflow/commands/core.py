"""
Основные decorator-ы и классы команд для vkflow.commands
"""

from __future__ import annotations

import contextlib
import re

import copy
import typing

from loguru import logger

from vkflow.commands.command import Command as BaseCommand

from vkflow.utils.inject import inject_and_call

from .cooldowns import OnCooldownError

from .context import Context

if typing.TYPE_CHECKING:
    from vkflow.app.storages import NewMessage
    from vkflow.base.filter import BaseFilter
    from vkflow.commands.parsing.cutter import InvalidArgumentConfig
    from .cooldowns import BucketType

    Handler = typing.Callable[..., typing.Awaitable]
    ArgumentsDict: typing.TypeAlias = dict[str, typing.Any]


__all__ = (
    "Command",
    "Group",
    "GroupMixin",
    "command",
    "group",
)


def _bind_if_descriptor(handler, instance, owner):
    """Привязать handler к instance через descriptor protocol, если возможно."""
    if handler is None:
        return None
    if hasattr(handler, "__get__") and not hasattr(handler, "__self__"):
        return handler.__get__(instance, owner)
    return handler


class Command(BaseCommand):
    """
    Класс, представляющий команду в фреймворке ext.commands.

    Атрибуты:
        callback: Корутина, выполняемая при вызове команды
        name: Имя команды
        aliases: Псевдонимы команды
        help: Текст справки команды
        brief: Краткое описание команды
        enabled: Включена ли команда
        hidden: Скрыта ли команда из справки
        usage: Примеры использования команды
        parent: Родительская Group, если команда является подкомандой
    """

    def __init__(
        self, callback: Handler, name: str | None = None, aliases: list[str] | None = None, **kwargs
    ):
        if name is None:
            name = callback.__name__

        names = [name]
        if aliases:
            names.extend(aliases)

        self.callback = callback
        self.help = kwargs.pop("help", None)
        self.brief = kwargs.pop("brief", None)
        self.enabled = kwargs.pop("enabled", True)
        self.hidden = kwargs.pop("hidden", False)
        self.usage: str | None = kwargs.pop("usage", None)

        self.parent: Group | None = None

        self.__doc__ = callback.__doc__ if callback.__doc__ else ""

        self._cooldown_handler: typing.Callable[..., typing.Awaitable] | None = None
        self._cooldown_mappings: list[typing.Any] = []

        self._max_concurrency_mapping: typing.Any = None
        self._max_concurrency_handler: typing.Callable[..., typing.Awaitable] | None = None

        self._before_invoke: typing.Callable[..., typing.Awaitable] | None = None
        self._after_invoke: typing.Callable[..., typing.Awaitable] | None = None

        if hasattr(callback, "__max_concurrency__"):
            self._max_concurrency_mapping = callback.__max_concurrency__

        if hasattr(callback, "__vkflow_checks__"):
            for check in callback.__vkflow_checks__:
                if hasattr(check, "_cooldown_mapping"):
                    self._cooldown_mappings.append(check._cooldown_mapping)

        super().__init__(handler=callback, names=names, **kwargs)

    @property
    def name(self) -> str:
        """Имя команды"""
        return self.names[0] if self.names else ""

    @property
    def aliases(self) -> list[str]:
        """Псевдонимы команды"""
        return self.names[1:] if len(self.names) > 1 else []

    @property
    def parents(self) -> list[Group]:
        """
        Список всех родительских групп от ближайшей к корневой.

        Возвращает:
            list[Group]: Список групп от ближайшего родителя к корню

        Пример:
            # Для команды: config settings show
            # show.parents = [settings, config]
        """
        result = []
        current = self.parent
        while current is not None:
            result.append(current)
            current = current.parent
        return result

    def __hash__(self) -> int:
        """Хеширование по идентификатору объекта"""
        return id(self)

    def __eq__(self, other: object) -> bool:
        """Сравнение команд по идентификатору"""
        return self is other

    def __get__(self, instance, owner):
        """Привязка обработчиков кулдауна и хуков к экземпляру"""
        if instance is None:
            return self

        bound_command = super().__get__(instance, owner)

        bound_command._cooldown_handler = _bind_if_descriptor(self._cooldown_handler, instance, owner)
        bound_command._max_concurrency_handler = _bind_if_descriptor(
            self._max_concurrency_handler, instance, owner
        )
        bound_command._before_invoke = _bind_if_descriptor(self._before_invoke, instance, owner)
        bound_command._after_invoke = _bind_if_descriptor(self._after_invoke, instance, owner)

        bound_command.parent = self.parent
        bound_command.usage = self.usage
        bound_command._package = self._package

        return bound_command

    def on_cooldown(
        self,
    ) -> typing.Callable[[typing.Callable[..., typing.Awaitable]], typing.Callable[..., typing.Awaitable]]:
        """
        Decorator для регистрации обработчика cooldown для этой команды.

        Этот обработчик вызывается, когда команда находится на cooldown.

        Обработчик может принимать следующие необязательные параметры:
        - ctx (Context): Контекст команды
        - error (OnCooldownError): Исключение OnCooldownError
        - remaining (float): Секунды до окончания cooldown (то же, что error.retry_after)

        Возвращает:
            Функцию-decorator

        Пример:
            @commands.command()
            @commands.cooldown(rate=3, per=60, type=BucketType.USER)
            async def test(ctx: Context):
                await ctx.send("Command executed!")

            # С параметром error
            @test.on_cooldown()
            async def on_test_cooldown(ctx: Context, error: OnCooldownError):
                await ctx.send(f"Try again in {error.retry_after:.1f} seconds")

            # С параметром remaining (удобнее)
            @test.on_cooldown()
            async def on_test_cooldown(ctx: Context, remaining: float):
                await ctx.send(f"Wait {remaining:.1f}s")

            # Минимальный вариант -только ctx
            @test.on_cooldown()
            async def on_test_cooldown(ctx: Context):
                await ctx.send("On cooldown!")
        """

        def decorator(
            func: typing.Callable[..., typing.Awaitable],
        ) -> typing.Callable[..., typing.Awaitable]:
            if self._cooldown_handler is not None:
                raise ValueError(
                    f"Команда '{self.name}' уже имеет обработчик cooldown. "
                    "Допускается только один decorator @.on_cooldown()."
                )
            self._cooldown_handler = func
            return func

        return decorator

    def on_max_concurrency(
        self,
    ) -> typing.Callable[[typing.Callable[..., typing.Awaitable]], typing.Callable[..., typing.Awaitable]]:
        """
        Decorator для регистрации обработчика max concurrency для этой команды.

        Этот обработчик вызывается при достижении лимита одновременных выполнений.

        Обработчик может принимать следующие необязательные параметры:
        - ctx (Context): Контекст команды
        - error (MaxConcurrencyReachedError): Исключение MaxConcurrencyReachedError
        - limit (int): Максимально допустимое количество одновременных выполнений
        - current (int): Текущее количество активных выполнений

        Возвращает:
            Функцию-decorator

        Пример:
            @commands.command()
            @commands.max_concurrency(2, BucketType.CHAT)
            async def heavy(ctx: Context):
                await asyncio.sleep(10)
                await ctx.send("Done!")

            # С параметром error
            @heavy.on_max_concurrency()
            async def on_heavy_concurrency(ctx: Context, error: MaxConcurrencyReachedError):
                await ctx.send(f"Limit reached: {error.current}/{error.number}")

            # С параметрами limit и current (удобнее)
            @heavy.on_max_concurrency()
            async def on_heavy_concurrency(ctx: Context, limit: int, current: int):
                await ctx.send(f"Too many uses: {current}/{limit}")

            # Минимальный вариант -только ctx
            @heavy.on_max_concurrency()
            async def on_heavy_concurrency(ctx: Context):
                await ctx.send("Too many concurrent executions!")
        """

        def decorator(
            func: typing.Callable[..., typing.Awaitable],
        ) -> typing.Callable[..., typing.Awaitable]:
            if self._max_concurrency_handler is not None:
                raise ValueError(
                    f"Команда '{self.name}' уже имеет обработчик max concurrency. "
                    "Допускается только один decorator @.on_max_concurrency()."
                )
            self._max_concurrency_handler = func
            return func

        return decorator

    def before_invoke(
        self,
    ) -> typing.Callable[[typing.Callable[..., typing.Awaitable]], typing.Callable[..., typing.Awaitable]]:
        """
        Decorator для регистрации хука before_invoke для этой команды.

        Этот хук вызывается перед выполнением обработчика команды.
        Если хук возвращает False, выполнение команды будет отменено.

        Обработчик может принимать следующие необязательные параметры:
        - ctx (Context): Контекст команды
        - А также любые распарсенные аргументы команды с теми же именами

        Возвращает:
            Функцию-decorator

        Пример:
            @commands.command()
            async def test(ctx: Context, user: User):
                await ctx.send(f"Hello, {user.name}!")

            @test.before_invoke()
            async def before_test(ctx: Context):
                print(f"Command {ctx.command.name} is about to run")

            # С аргументами
            @test.before_invoke()
            async def before_test(ctx: Context, user: User):
                print(f"About to greet {user.name}")

            # Верните False для отмены команды
            @test.before_invoke()
            async def check_permissions(ctx: Context):
                if not await has_permission(ctx.author):
                    await ctx.send("No permission!")
                    return False
        """

        def decorator(
            func: typing.Callable[..., typing.Awaitable],
        ) -> typing.Callable[..., typing.Awaitable]:
            if self._before_invoke is not None:
                raise ValueError(
                    f"Команда '{self.name}' уже имеет обработчик before_invoke. "
                    "Допускается только один decorator @.before_invoke()."
                )
            self._before_invoke = func
            return func

        return decorator

    def after_invoke(
        self,
    ) -> typing.Callable[[typing.Callable[..., typing.Awaitable]], typing.Callable[..., typing.Awaitable]]:
        """
        Decorator для регистрации хука after_invoke для этой команды.

        Этот хук вызывается после завершения обработчика команды (успешно или с ошибкой).

        Обработчик может принимать следующие необязательные параметры:
        - ctx (Context): Контекст команды
        - result: Возвращаемое значение обработчика команды
        - error (Exception | None): Исключение при ошибке команды, None при успехе
        - А также любые распарсенные аргументы команды с теми же именами

        Возвращает:
            Функцию-decorator

        Пример:
            @commands.command()
            async def test(ctx: Context):
                return "success"

            @test.after_invoke()
            async def after_test(ctx: Context, result):
                print(f"Command returned: {result}")

            @test.after_invoke()
            async def after_test(ctx: Context, error):
                if error:
                    print(f"Command failed: {error}")
                else:
                    print("Command succeeded")
        """

        def decorator(
            func: typing.Callable[..., typing.Awaitable],
        ) -> typing.Callable[..., typing.Awaitable]:
            if self._after_invoke is not None:
                raise ValueError(
                    f"Команда '{self.name}' уже имеет обработчик after_invoke. "
                    "Допускается только один decorator @.after_invoke()."
                )
            self._after_invoke = func
            return func

        return decorator

    async def _invoke_hook(
        self,
        hook: typing.Callable[..., typing.Awaitable],
        ctx: Context,
        arguments: dict | None = None,
        **extra_kwargs,
    ) -> typing.Any:
        """
        Вызвать хук с инъекцией параметров.

        Аргументы:
            hook: Функция-хук
            ctx: Контекст команды
            arguments: Распарсенные аргументы команды
            **extra_kwargs: Дополнительные kwargs (result, error и т.д.)

        Возвращает:
            Результат вызова хука
        """
        available = {"ctx": ctx, **extra_kwargs}
        if arguments:
            available.update(arguments)
        return await inject_and_call(hook, available)

    def reset_cooldown(
        self,
        ctx: typing.Any = None,
        *,
        type: BucketType | None = None,
        user: int | None = None,
        chat: int | None = None,
    ):
        """
        Сбросить cooldown(ы) для этой команды.

        Аргументы:
            ctx: Необязательный Context, NewMessage или None
                - Если Context/NewMessage: сбросить cooldown для конкретного пользователя/чата по типу bucket
                - Если None и нет других аргументов: сбросить ВСЕ cooldown для этой команды
            type: Необязательный BucketType для фильтрации сбрасываемых cooldown
                - Если указан, сбрасывает только cooldown с этим типом
                - Если None, сбрасывает все cooldown
            user: ID пользователя для сброса cooldown (только для типов USER/MEMBER)
            chat: ID чата/peer для сброса cooldown (только для типов CHAT/MEMBER)

        Примеры:
            # Сбросить все cooldown для всех пользователей/чатов
            command.reset_cooldown()

            # Сбросить cooldown для конкретного пользователя (из контекста)
            command.reset_cooldown(ctx)

            # Сбросить только cooldown типа USER
            command.reset_cooldown(type=BucketType.USER)

            # Сбросить cooldown для конкретного ID пользователя
            command.reset_cooldown(user=123456)

            # Сбросить cooldown для конкретного чата
            command.reset_cooldown(chat=2000000001)

            # Сбросить cooldown для конкретного участника (пользователь в чате)
            command.reset_cooldown(user=123456, chat=2000000001)

            # Сбросить только CHAT cooldown для конкретного чата
            command.reset_cooldown(type=BucketType.CHAT, chat=2000000001)

            # В другой команде
            @commands.command()
            @is_admin()
            async def reset(self, ctx: commands.Context, cmd_name: str):
                cmd = getattr(self, cmd_name, None)
                if cmd:
                    cmd.reset_cooldown()
                    await ctx.send(f"Cooldown for {cmd_name} reset!")
        """
        for mapping in self._cooldown_mappings:
            if type is not None and mapping.type != type:
                continue

            mapping.reset(ctx, user=user, chat=chat)

    async def _run_through_filters(self, ctx: NewMessage) -> bool:
        """Обработка фильтров с поддержкой OnCooldownError и cog_check"""
        from vkflow.exceptions import StopCurrentHandlingError

        if self._cog is not None and hasattr(self._cog, "cog_check") and callable(self._cog.cog_check):
            check_ctx = await self._create_context(ctx, command=self)
            passed_cog_check = await self._cog.cog_check(check_ctx)
            if not passed_cog_check:
                return False

        if self.filter is not None:
            try:
                await self.filter.run_making_decision(ctx)
            except StopCurrentHandlingError as e:
                if e.__cause__ and isinstance(e.__cause__, OnCooldownError):
                    cooldown_error = e.__cause__
                    if self._cooldown_handler is not None:
                        check_ctx = await self._create_context(ctx, command=self)
                        await inject_and_call(
                            self._cooldown_handler,
                            {
                                "ctx": check_ctx,
                                "error": cooldown_error,
                                "remaining": cooldown_error.retry_after,
                            },
                        )
                return False
            else:
                return True
        return True

    async def handle_message(self, ctx: NewMessage) -> None:
        """Обработка сообщения с поддержкой max_concurrency"""
        from .cooldowns import MaxConcurrencyReachedError
        from vkflow.exceptions import ArgumentParsingError

        routing = await self._match_routing(ctx)
        if routing is not None:
            is_routing_matched, _, prefix, invoked_with = routing

            try:
                arguments = await self._make_arguments(
                    ctx,
                    ctx.msg.text[is_routing_matched.end() :],
                    prefix=prefix,
                    invoked_with=invoked_with,
                )
            except ArgumentParsingError as error:
                await self._handle_argument_parsing_error(ctx, error)
                return

            if arguments is not None:
                passed_filter = await self._run_through_filters(ctx)
                if passed_filter:
                    if self._max_concurrency_mapping is not None:
                        check_ctx = await self._create_context(
                            ctx, command=self, prefix=prefix, invoked_with=invoked_with
                        )

                        try:
                            async with self._max_concurrency_mapping(check_ctx):
                                await self._call_handler(ctx, arguments)
                        except MaxConcurrencyReachedError as e:
                            if self._max_concurrency_handler is not None:
                                await inject_and_call(
                                    self._max_concurrency_handler,
                                    {
                                        "ctx": check_ctx,
                                        "error": e,
                                        "limit": e.number,
                                        "current": e.current,
                                    },
                                )
                    else:
                        await self._call_handler(ctx, arguments)

    async def _dispatch_event(self, ctx: NewMessage, event_name: str, **kwargs) -> None:
        """Отправить событие через bot.dispatch_event (не блокирующий, для аналитики)."""
        bot = getattr(ctx, "bot", None)
        if bot is not None and hasattr(bot, "dispatch_event"):
            with contextlib.suppress(Exception):
                await bot.dispatch_event(event_name, **kwargs)

    async def _run_before_hooks(
        self, ctx: NewMessage, check_ctx: Context, arguments: ArgumentsDict
    ) -> bool:
        """
        Выполнить все before-хуки. Возвращает False если выполнение отменено.

        Порядок: middleware → cog_before_invoke → command.before_invoke
        """
        app = getattr(ctx, "app", None)
        if app is not None:
            manager = getattr(app, "middleware_manager", None)
            if manager is not None:
                should_continue = await manager.run_before_command_hooks(
                    check_ctx, command=self, arguments=arguments
                )
                if not should_continue:
                    return False

        if self._package is not None:
            for hook in getattr(self._package, "_before_command_hooks", []):
                result = await inject_and_call(hook, {"ctx": check_ctx, **arguments})
                if result is False:
                    return False

            pkg_handler = getattr(self._package, "_before_invoke_handler", None)
            if pkg_handler is not None:
                result = await self._invoke_hook(pkg_handler, check_ctx, arguments)
                if result is False:
                    return False

        if self._cog is not None and hasattr(self._cog, "cog_before_invoke"):
            cog_result = await self._invoke_hook(self._cog.cog_before_invoke, check_ctx, arguments)
            if cog_result is False:
                return False

        if self._before_invoke is not None:
            result = await self._invoke_hook(self._before_invoke, check_ctx, arguments)
            if result is False:
                return False

        return True

    async def _run_after_hooks(
        self,
        ctx: NewMessage,
        check_ctx: Context,
        arguments: ArgumentsDict,
        result: typing.Any = None,
        error: Exception | None = None,
    ) -> None:
        """
        Выполнить все after-хуки (всегда, даже при ошибке).

        Порядок: command.after_invoke → cog_after_invoke → middleware
        """
        if self._after_invoke is not None:
            try:
                await self._invoke_hook(
                    self._after_invoke,
                    check_ctx,
                    arguments,
                    result=result,
                    error=error,
                )
            except Exception as e:
                logger.exception(f"Ошибка в after_invoke хуке: {e}")

        if self._package is not None:
            pkg_handler = getattr(self._package, "_after_invoke_handler", None)
            if pkg_handler is not None:
                try:
                    await self._invoke_hook(pkg_handler, check_ctx, arguments, result=result, error=error)
                except Exception as e:
                    logger.exception(f"Ошибка в package after_invoke хуке: {e}")

            for hook in getattr(self._package, "_after_command_hooks", []):
                try:
                    await inject_and_call(
                        hook, {"ctx": check_ctx, "result": result, "error": error, **arguments}
                    )
                except Exception as e:
                    logger.exception(f"Ошибка в package after_command хуке: {e}")

        if self._cog is not None and hasattr(self._cog, "cog_after_invoke"):
            try:
                await self._invoke_hook(
                    self._cog.cog_after_invoke,
                    check_ctx,
                    arguments,
                    result=result,
                    error=error,
                )
            except Exception as e:
                logger.exception(f"Ошибка в cog_after_invoke хуке: {e}")

        app = getattr(ctx, "app", None)
        if app is not None:
            manager = getattr(app, "middleware_manager", None)
            if manager is not None:
                await manager.run_after_command_hooks(
                    check_ctx,
                    result=result,
                    error=error,
                    command=self,
                    arguments=arguments,
                )

    async def _handle_command_error(
        self,
        ctx: NewMessage,
        check_ctx: Context,
        error: Exception,
        arguments: ArgumentsDict,
    ) -> bool:
        """
        Цепочка обработки ошибок.

        1. Событие command_error (аналитика, всегда)
        2. Общая цепочка: cog_command_error → local → cog_fallback → app_fallback

        Возвращает True если ошибка была обработана.
        """
        await self._dispatch_event(
            ctx,
            "command_error",
            context=check_ctx,
            command=self,
            error=error,
        )

        return await self._find_error_handler(ctx, error, arguments, error_ctx=check_ctx)

    async def _call_handler(self, ctx: NewMessage, arguments: ArgumentsDict) -> None:
        """
        Вызов обработчика команды с полным lifecycle.

        Порядок выполнения:
        1. Логирование
        2. Создание контекста и зависимостей
        3. Before-хуки (middleware → cog → command)
        4. Выполнение обработчика
        5. Обработка ошибок (если есть)
        6. After-хуки (command → cog → middleware) -всегда
        """
        from vkflow.commands.command import format_mapping

        logger.opt(colors=True).success(
            **format_mapping(
                "Called command <m>{com_name}</m><w>({params})</w>",
                "<c>{key}</c>=<y>{value!r}</y>",
                arguments,
            ),
            com_name=self.handler.__name__,
        )

        prefix = (
            arguments.pop("__prefix__", None)
            if "__prefix__" in arguments
            else getattr(ctx, "_prefix", None)
        )
        invoked_with = (
            arguments.pop("__invoked_with__", None)
            if "__invoked_with__" in arguments
            else getattr(ctx, "_invoked_with", None)
        )
        check_ctx = await self._create_context(ctx, command=self, prefix=prefix, invoked_with=invoked_with)

        dependency_mapping = await self._dependency_mixin.make_dependency_arguments(ctx)

        result = None
        error = None

        if not await self._run_before_hooks(ctx, check_ctx, arguments):
            return

        try:
            await self._dispatch_event(
                ctx,
                "command",
                context=check_ctx,
                command=self,
                arguments=arguments,
            )

            result = await self.handler(**arguments, **dependency_mapping)

            if result is not None and isinstance(result, str):
                await ctx.reply(result)

            await self._dispatch_event(
                ctx,
                "command_complete",
                context=check_ctx,
                command=self,
                result=result,
            )

        except Exception as e:
            error = e
            handled = await self._handle_command_error(ctx, check_ctx, e, arguments)
            if not handled:
                raise

        finally:
            await self._run_after_hooks(ctx, check_ctx, arguments, result=result, error=error)


class GroupMixin:
    """
    Миксин, реализующий общую функциональность для групп.

    Используется классом Group для предоставления методов управления командами.
    Аналогичен GroupMixin из discord.py.

    Атрибуты:
        all_commands: Словарь соответствия имени команды объекту Command.
        case_insensitive: Регистронезависимый ли поиск команд.
    """

    all_commands: dict[str, Command]
    case_insensitive: bool

    def __init__(self, *args, **kwargs):
        self.all_commands: dict[str, Command] = {}
        self.case_insensitive: bool = kwargs.pop("case_insensitive", False)
        super().__init__(*args, **kwargs)

    @property
    def commands(self) -> set[Command]:
        """
        Уникальное множество команд без дубликатов.

        Поскольку команда может иметь несколько имён (псевдонимов),
        возвращаются уникальные объекты Command.
        """
        return set(self.all_commands.values())

    def add_command(self, command: Command) -> None:
        """
        Добавить команду в группу.

        Аргументы:
            command: Команда для добавления

        Исключения:
            TypeError: Если command не является экземпляром Command
            ValueError: Если команда с таким именем уже зарегистрирована
        """
        if not isinstance(command, Command):
            raise TypeError("Переданная команда должна быть подклассом Command")

        if command.name in self.all_commands:
            raise ValueError(f"Команда {command.name!r} уже зарегистрирована.")

        command.parent = self  # type: ignore

        self.all_commands[command.name] = command
        for alias in command.aliases:
            if alias in self.all_commands:
                self.remove_command(command.name)
                raise ValueError(f"Псевдоним {alias!r} уже зарегистрирован.")
            self.all_commands[alias] = command

    def remove_command(self, name: str) -> Command | None:
        """
        Удалить команду из группы.

        Аргументы:
            name: Имя удаляемой команды

        Возвращает:
            Удалённую команду или None, если не найдена
        """
        command = self.all_commands.pop(name, None)
        if command is None:
            return None

        for alias in command.aliases:
            self.all_commands.pop(alias, None)

        command.parent = None

        return command

    def get_command(self, name: str) -> Command | None:
        """
        Получить команду из группы.

        Аргументы:
            name: Имя или псевдоним команды

        Возвращает:
            Команду, если найдена, иначе None
        """
        if self.case_insensitive:
            name = name.lower()
            for cmd_name, cmd in self.all_commands.items():
                if cmd_name.lower() == name:
                    return cmd
            return None
        return self.all_commands.get(name)

    def walk_commands(self) -> typing.Generator[Command, None, None]:
        """
        Итератор, рекурсивно обходящий все команды и подкоманды.

        Генерирует:
            Command: Каждую команду в группе и её подгруппах
        """
        for command in self.commands:
            yield command
            if isinstance(command, GroupMixin):
                yield from command.walk_commands()

    def command(self, name: str | None = None, **kwargs) -> typing.Callable[[Handler], Command]:
        """
        Decorator для добавления подкоманды в эту группу.

        Аргументы:
            name: Имя подкоманды
            **kwargs: Дополнительные параметры для команды

        Возвращает:
            Функцию-decorator
        """

        def decorator(func: Handler) -> Command:
            cmd_name = name or func.__name__

            if hasattr(func, "__vkflow_checks__"):
                checks = func.__vkflow_checks__
                if checks:
                    combined_filter = kwargs.get("filter")
                    for check in checks:
                        combined_filter = check if combined_filter is None else combined_filter & check
                    kwargs["filter"] = combined_filter

            cmd = Command(func, name=cmd_name, **kwargs)

            if hasattr(self, "prefixes") and not cmd.prefixes and self.prefixes:
                cmd.prefixes = self.prefixes.copy()
                cmd._build_routing_regex()

            self.add_command(cmd)
            return cmd

        return decorator

    def group(self, name: str | None = None, **kwargs) -> typing.Callable[[Handler], Group]:
        """
        Decorator для добавления подгруппы в эту группу.

        Аргументы:
            name: Имя подгруппы
            **kwargs: Дополнительные параметры для группы

        Возвращает:
            Функцию-decorator
        """

        def decorator(func: Handler) -> Group:
            grp_name = name or func.__name__

            if hasattr(func, "__vkflow_checks__"):
                checks = func.__vkflow_checks__
                if checks:
                    combined_filter = kwargs.get("filter")
                    for check in checks:
                        combined_filter = check if combined_filter is None else combined_filter & check
                    kwargs["filter"] = combined_filter

            grp = Group(func, name=grp_name, **kwargs)

            if hasattr(self, "prefixes") and not grp.prefixes and self.prefixes:
                grp.prefixes = self.prefixes.copy()
                grp._build_routing_regex()

            self.add_command(grp)
            return grp

        return decorator


class Group(GroupMixin, Command):
    """
    Класс, представляющий группу команд.

    Наследуется от GroupMixin (управление подкомандами) и Command.

    Атрибуты:
        invoke_without_command: Вызывать ли обработчик группы, если подкоманда не найдена

    Пример:
        @commands.group()
        async def config(ctx: Context):
            '''Команды конфигурации'''
            if ctx.invoked_subcommand is None:
                await ctx.send("Неверная подкоманда")

        @config.command()
        async def show(ctx: Context):
            '''Показать конфигурацию'''
            await ctx.send("Config: ...")

        @commands.group(aliases=["cfg", "conf"])
        async def config(ctx: Context):
            pass
    """

    def __init__(
        self, callback: Handler, name: str | None = None, aliases: list[str] | None = None, **kwargs
    ):
        self.invoke_without_command = kwargs.pop("invoke_without_command", False)
        super().__init__(callback, name=name, aliases=aliases, **kwargs)

    def __get__(self, instance, owner):
        """Привязка подкоманд к экземпляру"""
        if instance is None:
            return self

        bound_group = super().__get__(instance, owner)

        bound_group.all_commands = {}
        for cmd_name, cmd in self.all_commands.items():
            if hasattr(cmd.handler, "__get__"):
                bound_subcmd = copy.copy(cmd)
                bound_subcmd.handler = cmd.handler.__get__(instance, owner)

                bound_subcmd._error_handlers = [
                    (_bind_if_descriptor(eh, instance, owner), et) for eh, et in cmd._error_handlers
                ]

                bound_subcmd._cooldown_handler = _bind_if_descriptor(cmd._cooldown_handler, instance, owner)
                bound_subcmd._max_concurrency_handler = _bind_if_descriptor(
                    cmd._max_concurrency_handler, instance, owner
                )
                bound_subcmd._before_invoke = _bind_if_descriptor(cmd._before_invoke, instance, owner)
                bound_subcmd._after_invoke = _bind_if_descriptor(cmd._after_invoke, instance, owner)

                bound_group.all_commands[cmd_name] = bound_subcmd
            else:
                bound_group.all_commands[cmd_name] = cmd

        return bound_group

    def update_prefix(self, *prefixes: str) -> None:
        """Обновление префиксов включая подкоманды"""
        super().update_prefix(*prefixes)
        for cmd in self.commands:
            cmd.update_prefix(*prefixes)

    async def handle_message(self, ctx: NewMessage) -> None:
        """Обработка сообщения с поддержкой подкоманд"""
        from vkflow.exceptions import ArgumentParsingError

        routing = await self._match_routing(ctx)
        if routing is not None:
            is_routing_matched, _, prefix, invoked_with = routing

            remaining_text = ctx.msg.text[is_routing_matched.end() :].lstrip()

            invoked_subcommand = None
            subcommand_obj = None

            if remaining_text:
                for cmd in self.all_commands.values():
                    for cmd_name_or_alias in cmd.names:
                        pattern = re.escape(cmd_name_or_alias) + r"(?:\s|$)"
                        match = re.match(pattern, remaining_text, flags=self.routing_re_flags)

                        if match:
                            invoked_subcommand = cmd_name_or_alias
                            subcommand_obj = cmd
                            remaining_text = remaining_text[match.end() :].lstrip()
                            break

                    if subcommand_obj:
                        break

            passed_group_filter = await self._run_through_filters(ctx)
            if not passed_group_filter:
                return

            if subcommand_obj is not None:
                try:
                    subcommand_arguments = await subcommand_obj._make_arguments(
                        ctx,
                        remaining_text,
                        prefix=prefix,
                        invoked_with=invoked_subcommand,
                    )
                except ArgumentParsingError as error:
                    await subcommand_obj._handle_argument_parsing_error(ctx, error)
                    return

                if subcommand_arguments is not None:
                    passed_subcommand_filter = await subcommand_obj._run_through_filters(ctx)
                    if not passed_subcommand_filter:
                        return

                    try:
                        group_arguments = await self._make_arguments(
                            ctx,
                            "",
                            prefix=prefix,
                            invoked_with=invoked_with,
                        )
                    except ArgumentParsingError as error:
                        await self._handle_argument_parsing_error(ctx, error)
                        return

                    if group_arguments is not None:
                        if self._ctx_argument_name:
                            group_ctx_arg = group_arguments.get(self._ctx_argument_name)
                            if isinstance(group_ctx_arg, Context):
                                group_ctx_arg.invoked_subcommand = subcommand_obj

                        await self._call_handler(ctx, group_arguments)

                    if subcommand_obj._ctx_argument_name:
                        subcmd_ctx_arg = subcommand_arguments.get(subcommand_obj._ctx_argument_name)
                        if isinstance(subcmd_ctx_arg, Context):
                            subcmd_ctx_arg.invoked_subcommand = None

                    await subcommand_obj._call_handler(ctx, subcommand_arguments)
            else:
                try:
                    arguments = await self._make_arguments(
                        ctx,
                        remaining_text,
                        prefix=prefix,
                        invoked_with=invoked_with,
                    )
                except ArgumentParsingError as error:
                    await self._handle_argument_parsing_error(ctx, error)
                    return

                if arguments is not None:
                    if self._ctx_argument_name:
                        ctx_arg = arguments.get(self._ctx_argument_name)
                        if isinstance(ctx_arg, Context):
                            ctx_arg.invoked_subcommand = None

                    await self._call_handler(ctx, arguments)


def command(
    name: str | None = None,
    *,
    aliases: list[str] | None = None,
    prefixes: list[str] | None = None,
    filter: BaseFilter | None = None,
    description: str | None = None,
    help: str | None = None,
    brief: str | None = None,
    usage: str | None = None,
    enabled: bool = True,
    hidden: bool = False,
    routing_re_flags: re.RegexFlag | int = re.IGNORECASE,
    exclude_from_autodoc: bool = False,
    invalid_argument_config: InvalidArgumentConfig | None = None,
    **kwargs,
) -> typing.Callable[[Handler], Command]:
    """
    Decorator, преобразующий корутину в Command.

    Аргументы:
        name: Имя команды. Если не указано, используется имя функции
        aliases: Альтернативные имена команды
        prefixes: Префиксы команды (переопределяют префиксы пакета)
        filter: Фильтр для применения к команде
        description: Подробное описание команды
        help: Текст справки команды
        brief: Краткое описание команды
        usage: Примеры использования команды (например, "<user> <reason>")
        enabled: Включена ли команда
        hidden: Скрыть ли из справки
        routing_re_flags: Флаги regex для маршрутизации команды
        exclude_from_autodoc: Исключить ли из autodoc
        invalid_argument_config: Конфигурация для невалидных аргументов
        **kwargs: Дополнительные параметры

    Возвращает:
        Функцию-decorator

    Пример:
        @commands.command()
        async def hello(ctx: Context):
            '''Поздороваться'''
            await ctx.send("Hello!")

        @commands.command(name="greet", aliases=["hi"], usage="<name>")
        async def greet_command(ctx: Context, name: str):
            '''Поприветствовать кого-то'''
            await ctx.send(f"Hello, {name}!")
    """

    def decorator(func: Handler) -> Command:
        cmd_kwargs = {
            "prefixes": prefixes or [],
            "filter": filter,
            "description": description,
            "help": help,
            "brief": brief,
            "usage": usage,
            "enabled": enabled,
            "hidden": hidden,
            "routing_re_flags": routing_re_flags,
            "exclude_from_autodoc": exclude_from_autodoc or hidden,
        }

        if invalid_argument_config is not None:
            cmd_kwargs["invalid_argument_config"] = invalid_argument_config

        cmd_kwargs.update(kwargs)

        if hasattr(func, "__vkflow_checks__"):
            checks = func.__vkflow_checks__
            if checks:
                combined_filter = cmd_kwargs["filter"]
                for check in checks:
                    combined_filter = check if combined_filter is None else combined_filter & check
                cmd_kwargs["filter"] = combined_filter

        return Command(func, name=name, aliases=aliases, **cmd_kwargs)

    return decorator


def group(
    name: str | None = None, *, aliases: list[str] | None = None, **kwargs
) -> typing.Callable[[Handler], Group]:
    """
    Decorator, преобразующий корутину в Group.

    Аргументы:
        name: Имя группы. Если не указано, используется имя функции
        aliases: Альтернативные имена группы
        **kwargs: Дополнительные параметры (те же, что у decorator command)

    Возвращает:
        Функцию-decorator

    Пример:
        @commands.group()
        async def config(ctx: Context):
            '''Команды конфигурации'''
            pass

        @config.command()
        async def show(ctx: Context):
            '''Показать конфигурацию'''
            await ctx.send("Config: ...")

        # С псевдонимами
        @commands.group(aliases=["cfg", "conf"])
        async def config(ctx: Context):
            pass
    """

    def decorator(func: Handler) -> Group:
        if hasattr(func, "__vkflow_checks__"):
            checks = func.__vkflow_checks__
            if checks:
                combined_filter = kwargs.get("filter")
                for check in checks:
                    combined_filter = check if combined_filter is None else combined_filter & check
                kwargs["filter"] = combined_filter

        return Group(func, name=name, aliases=aliases, **kwargs)

    return decorator
