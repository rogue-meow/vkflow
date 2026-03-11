from __future__ import annotations

import contextlib
import re

import typing
import inspect

import warnings
import dataclasses

from loguru import logger

from vkflow.commands.parsing.cutter import InvalidArgumentConfig
from vkflow.base.handler_container import HandlerMixin
from vkflow.commands.parsing.adapters import resolve_typing
from vkflow.app.dependency import DependencyMixin, Depends
from vkflow.exceptions import ArgumentParsingError, BadArgumentError, StopCurrentHandlingError
from vkflow.app.prefixes import PrefixType, resolve_prefixes
from vkflow.app.storages import NewMessage
from vkflow.utils.helpers import get_origin_typing
from vkflow.logger import format_mapping

if typing.TYPE_CHECKING:
    from vkflow.base.filter import BaseFilter
    from vkflow.commands.parsing.cutter import CommandTextArgument

    ArgumentsDict: typing.TypeAlias = dict[str, typing.Any]
    DependencyMapping: typing.TypeAlias = dict[str, typing.Any]


Handler = typing.TypeVar("Handler", bound=typing.Callable[..., typing.Awaitable])


@dataclasses.dataclass
class Command(HandlerMixin[Handler]):
    prefixes: PrefixType = dataclasses.field(default_factory=list)
    names: list[str] = dataclasses.field(default_factory=list)
    routing_re_flags: re.RegexFlag | int = re.IGNORECASE
    filter: BaseFilter | None = None
    description: str | None = None
    exclude_from_autodoc: bool = False
    invalid_argument_config: InvalidArgumentConfig = dataclasses.field(
        default_factory=InvalidArgumentConfig
    )
    extra: dict[str, typing.Any] = dataclasses.field(default_factory=dict)

    @property
    def __name__(self) -> str:
        if hasattr(self.handler, "__name__"):
            return self.handler.__name__
        return self.names[0] if self.names else "unknown"

    def __set_name__(self, owner, name):
        self._cog_class = owner
        self._method_name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self

        import copy

        bound_command = copy.copy(self)

        if hasattr(self.handler, "__get__"):
            bound_command.handler = self.handler.__get__(instance, owner)

        bound_command._error_handlers = []

        for error_handler, error_types in self._error_handlers:
            if hasattr(error_handler, "__get__"):
                bound_handler = error_handler.__get__(instance, owner)
                bound_command._error_handlers.append((bound_handler, error_types))
            else:
                bound_command._error_handlers.append((error_handler, error_types))

        return bound_command

    def __post_init__(self):
        self._dependency_mixin = DependencyMixin()

        self._original_prefixes = self.prefixes

        if isinstance(self.prefixes, str):
            self.prefixes = [self.prefixes]

        self.names = list(self.names)

        self._text_arguments: list[CommandTextArgument] = []
        self._ctx_argument_name = None
        self._ctx_argument_name: str
        self._ctx_type = None
        self._parse_handler_arguments()

        self._routing_regex: typing.Pattern | None = None

        if isinstance(self.prefixes, list):
            self._build_routing_regex()

        self._error_handlers: list[
            tuple[typing.Callable[..., typing.Awaitable], tuple[type[Exception], ...] | None]
        ] = []
        self._cog: typing.Any = None
        self._package: typing.Any = None

    async def _create_context(self, ctx: NewMessage, **kwargs) -> typing.Any:
        """
        Создаёт экземпляр Context, делегируя app.get_context() при наличии.

        Позволяет подклассам App глобально переопределять создание контекста.
        Если app недоступен, используется Context.from_message().
        """
        app = getattr(getattr(ctx, "bot", None), "app", None)

        if app is not None and hasattr(app, "get_context"):
            return await app.get_context(ctx, **kwargs)

        from vkflow.commands.context import Context

        return Context.from_message(ctx, **kwargs)

    @property
    def trusted_description(self) -> str:
        if self.description is None:
            docstring = inspect.getdoc(self.handler)

            if docstring is None:
                return "Описание отсутствует"
            return docstring
        return self.description

    @property
    def text_arguments(self) -> list[CommandTextArgument]:
        return self._text_arguments

    def update_prefix(self, *prefixes: str | PrefixType) -> None:
        if self.prefixes and (isinstance(self.prefixes, list) and len(self.prefixes) > 0):
            return

        if len(prefixes) == 1 and not isinstance(prefixes[0], str):
            self.prefixes = prefixes[0]
            self._original_prefixes = prefixes[0]

            if callable(self.prefixes):
                self._routing_regex = None
            else:
                self._build_routing_regex()
        else:
            self.prefixes = list(set(prefixes))
            self._original_prefixes = self.prefixes

            self._build_routing_regex()

    def on_error(
        self, *error_types: type[Exception]
    ) -> typing.Callable[[typing.Callable[..., typing.Awaitable]], typing.Callable[..., typing.Awaitable]]:
        def decorator(
            func: typing.Callable[..., typing.Awaitable],
        ) -> typing.Callable[..., typing.Awaitable]:
            is_catchall = len(error_types) == 0

            if is_catchall:
                has_catchall = any(types is None for _, types in self._error_handlers)

                if has_catchall:
                    raise ValueError(
                        f"У команды '{self.__name__}' уже есть универсальный обработчик ошибок. "
                        "Допускается только один @.on_error() без аргументов."
                    )

            self._error_handlers.append((func, error_types if error_types else None))

            return func

        return decorator

    async def _match_routing(self, ctx: NewMessage):
        """
        Общая логика маршрутизации: resolve prefixes, build regex, match.

        Возвращает:
            Tuple (match, resolved_prefixes, prefix, invoked_with) или None
        """
        resolved_prefixes = await resolve_prefixes(ctx, self._original_prefixes)

        if not resolved_prefixes:
            resolved_prefixes = []

        if callable(self._original_prefixes) or self._routing_regex is None:
            routing_regex = self._build_dynamic_routing_regex(resolved_prefixes)
        else:
            routing_regex = self._routing_regex

        match = routing_regex.match(ctx.msg.text)
        if match is None:
            return None

        matched_text = match.group(0).strip()
        prefix, invoked_with = self._extract_prefix_and_name(matched_text, resolved_prefixes)
        return match, resolved_prefixes, prefix, invoked_with

    async def handle_message(self, ctx: NewMessage) -> None:
        routing = await self._match_routing(ctx)
        if routing is None:
            return

        match, _, prefix, invoked_with = routing

        try:
            arguments = await self._make_arguments(
                ctx,
                ctx.msg.text[match.end() :],
                prefix=prefix,
                invoked_with=invoked_with,
            )
        except ArgumentParsingError as error:
            await self._handle_argument_parsing_error(ctx, error)
            return

        if arguments is not None:
            try:
                passed_filter = await self._run_through_filters(ctx)
            except Exception as check_error:
                await self._dispatch_check_error(ctx, check_error)
                return

            if passed_filter:
                await self._call_handler(ctx, arguments)

    def _extract_prefix_and_name(
        self, matched_text: str, prefixes: list[str] | None = None
    ) -> tuple[str, str]:
        prefixes_to_check = (
            prefixes if prefixes is not None else (self.prefixes if isinstance(self.prefixes, list) else [])
        )

        for prefix in prefixes_to_check:
            if matched_text.startswith(prefix):
                invoked_with = matched_text[len(prefix) :].strip()
                return prefix, invoked_with

        return prefixes_to_check[0] if prefixes_to_check else "", matched_text

    async def _run_through_filters(self, ctx: NewMessage) -> bool:
        if self._cog is not None and hasattr(self._cog, "cog_check") and callable(self._cog.cog_check):
            check_ctx = await self._create_context(ctx, command=self)
            passed_cog_check = await self._cog.cog_check(check_ctx)

            if not passed_cog_check:
                return False

        if self.filter is not None:
            try:
                await self.filter.run_making_decision(ctx)
            except StopCurrentHandlingError:
                return False
            else:
                return True

        return True

    async def _make_arguments(
        self,
        ctx: NewMessage,
        arguments_string: str,
        prefix: str | None = None,
        invoked_with: str | None = None,
    ) -> ArgumentsDict | None:
        arguments = {}
        remain_string = arguments_string.lstrip()

        app = getattr(getattr(ctx, "bot", None), "app", None)

        argtype = None

        non_positional = [a for a in self._text_arguments if getattr(a.cutter, "is_non_positional", False)]
        positional = [a for a in self._text_arguments if not getattr(a.cutter, "is_non_positional", False)]

        for argtype in non_positional:
            try:
                parsing_response = await argtype.cutter.cut_part(ctx, remain_string)
            except BadArgumentError as e:
                if getattr(app, "strict_mode", False):
                    error = ArgumentParsingError(
                        argument=argtype,
                        remain_string=remain_string,
                        ctx=ctx,
                        original_error=e,
                        reason=e.description,
                        parsed_arguments=arguments.copy(),
                    )
                    await self._dispatch_argument_error(ctx, error)
                    raise error from e

                if self.invalid_argument_config is not None and getattr(app, "debug", False):
                    await self.invalid_argument_config.on_invalid_argument(
                        remain_string=remain_string,
                        ctx=ctx,
                        argument=argtype,
                    )
                return None
            else:
                remain_string = parsing_response.new_arguments_string
                arguments[argtype.argument_name] = parsing_response.parsed_part

        for argtype in positional:
            remain_string = remain_string.lstrip()

            try:
                parsing_response = await argtype.cutter.cut_part(ctx, remain_string)

            except BadArgumentError as e:
                if getattr(app, "strict_mode", False):
                    error = ArgumentParsingError(
                        argument=argtype,
                        remain_string=remain_string,
                        ctx=ctx,
                        original_error=e,
                        reason=e.description,
                        parsed_arguments=arguments.copy(),
                    )
                    await self._dispatch_argument_error(ctx, error)
                    raise error from e

                if self.invalid_argument_config is not None and getattr(app, "debug", False):
                    await self.invalid_argument_config.on_invalid_argument(
                        remain_string=remain_string,
                        ctx=ctx,
                        argument=argtype,
                    )

                return None

            else:
                remain_string = parsing_response.new_arguments_string.lstrip()
                value = parsing_response.parsed_part

                if (
                    getattr(app, "strict_mode", False)
                    and isinstance(value, (list, set, frozenset, tuple))
                    and len(value) == 0
                    and argtype.argument_settings.default is None
                    and argtype.argument_settings.default_factory is None
                ):
                    error = ArgumentParsingError(
                        argument=argtype,
                        remain_string=remain_string,
                        ctx=ctx,
                        reason=f"Аргумент '{argtype.argument_name}' требует хотя бы одно значение",
                        parsed_arguments=arguments.copy(),
                    )
                    await self._dispatch_argument_error(ctx, error)
                    raise error

                arguments[argtype.argument_name] = value

        if remain_string:
            app_debug = getattr(app, "debug", False)
            strict_mode = getattr(app, "strict_mode", False)

            if argtype is None:
                if strict_mode:
                    error = ArgumentParsingError(
                        argument=None,
                        remain_string=remain_string,
                        ctx=ctx,
                        original_error=None,
                        reason="Команда не принимает аргументов",
                        parsed_arguments=arguments.copy(),
                    )
                    await self._dispatch_argument_error(ctx, error)
                    raise error

                if app_debug:
                    await ctx.reply("Команда не принимает аргументов")

                return None

            if strict_mode:
                error = ArgumentParsingError(
                    argument=argtype,
                    remain_string=remain_string,
                    ctx=ctx,
                    original_error=None,
                    reason=f"Лишний текст после аргументов: '{remain_string[:50]}{'...' if len(remain_string) > 50 else ''}'",
                    parsed_arguments=arguments.copy(),
                )
                await self._dispatch_argument_error(ctx, error)
                raise error

            if self.invalid_argument_config is not None and app_debug:
                await self.invalid_argument_config.on_invalid_argument(
                    remain_string=remain_string,
                    ctx=ctx,
                    argument=argtype,
                )

            return None

        if self._ctx_argument_name is not None:
            from vkflow.commands.context import Context

            if self._ctx_type is NewMessage:
                arguments[self._ctx_argument_name] = ctx

            elif (
                Context is not None
                and isinstance(self._ctx_type, type)
                and issubclass(self._ctx_type, Context)
            ):
                arguments[self._ctx_argument_name] = await self._create_context(
                    ctx,
                    command=self,
                    prefix=prefix,
                    invoked_with=invoked_with,
                )

            else:
                arguments[self._ctx_argument_name] = ctx

        return arguments

    async def _call_handler(self, ctx: NewMessage, arguments: ArgumentsDict) -> None:
        logger.opt(colors=True).success(
            **format_mapping(
                "Called command <m>{com_name}</m><w>({params})</w>",
                "<c>{key}</c>=<y>{value!r}</y>",
                arguments,
            ),
            com_name=self.handler.__name__,
        )

        dependency_mapping = await self._dependency_mixin.make_dependency_arguments(ctx)

        try:
            handler_response = await self.handler(**arguments, **dependency_mapping)

            if handler_response is not None and isinstance(handler_response, str):
                await ctx.reply(handler_response)

            await self._dispatch_command_complete(ctx, arguments)

        except Exception as error:
            from vkflow.commands.checks import CheckFailureError
            from vkflow.commands.cooldowns import OnCooldownError

            if isinstance(error, OnCooldownError):
                await self._dispatch_cooldown_error(ctx, error)
            elif isinstance(error, CheckFailureError):
                await self._dispatch_check_error(ctx, error)
            else:
                await self._dispatch_command_error(ctx, error)

            app = getattr(ctx, "app", None)
            if app is not None and hasattr(app, "on_command_error"):
                with contextlib.suppress(Exception):
                    await app.on_command_error(ctx, error)

            handled = await self._find_error_handler(ctx, error, arguments)
            if not handled:
                raise

    async def _invoke_error_handler(
        self,
        error_handler: typing.Callable[..., typing.Awaitable],
        ctx: NewMessage,
        error: Exception,
        arguments: ArgumentsDict,
    ) -> None:
        from vkflow.commands.context import Context
        from vkflow.utils.inject import inject_and_call

        if isinstance(self._ctx_type, type) and issubclass(self._ctx_type, Context):
            ctx_value = await self._create_context(ctx, command=self, prefix="", invoked_with="")
        else:
            ctx_value = ctx

        await inject_and_call(
            error_handler,
            {
                "ctx": ctx_value,
                "error": error,
                "args": arguments.copy(),
            },
        )

    async def _try_local_error_handlers(
        self, ctx: NewMessage, error: Exception, arguments: ArgumentsDict
    ) -> bool:
        """
        Попробовать локальные error_handlers команды.

        Возвращает True если ошибка была обработана.
        """
        if not self._error_handlers:
            return False

        catchall_handler = None
        for error_handler, error_types in self._error_handlers:
            if error_types is None:
                catchall_handler = error_handler
            elif isinstance(error, error_types):
                try:
                    await self._invoke_error_handler(error_handler, ctx, error, arguments)
                    return True
                except Exception as exc:
                    logger.warning("Error handler raised an exception: {}", exc)
                break

        if catchall_handler is not None:
            try:
                await self._invoke_error_handler(catchall_handler, ctx, error, arguments)
                return True
            except Exception as exc:
                logger.warning("Catch-all error handler raised an exception: {}", exc)

        return False

    async def _find_error_handler(
        self, ctx: NewMessage, error: Exception, arguments: ArgumentsDict, *, error_ctx: typing.Any = None
    ) -> bool:
        """
        Цепочка поиска обработчика ошибки.

        Порядок:
        1. cog_command_error (информационный, вызывается всегда)
        2. Локальные error_handlers команды
        3. cog_command_fallback
        4. app.on_command_error_fallback

        Аргументы:
            ctx: NewMessage -для _invoke_error_handler
            error: Исключение
            arguments: Распарсенные аргументы
            error_ctx: Контекст для cog/app методов (если None -создаётся автоматически)

        Возвращает True если ошибка обработана.
        """
        owner = self._cog or self._package
        owner_ctx = error_ctx
        if owner_ctx is None and owner is not None:
            owner_ctx = await self._create_context(ctx, command=self)

        if (
            self._cog is not None
            and hasattr(self._cog, "cog_command_error")
            and callable(self._cog.cog_command_error)
        ):
            with contextlib.suppress(Exception):
                await self._cog.cog_command_error(owner_ctx, error)
        elif self._package is not None and getattr(self._package, "_error_handler_func", None) is not None:
            with contextlib.suppress(Exception):
                from vkflow.utils.inject import inject_and_call

                await inject_and_call(self._package._error_handler_func, {"ctx": owner_ctx, "error": error})

        if await self._try_local_error_handlers(ctx, error, arguments):
            return True

        if (
            self._cog is not None
            and hasattr(self._cog, "cog_command_fallback")
            and callable(self._cog.cog_command_fallback)
        ):
            try:
                await self._cog.cog_command_fallback(owner_ctx, error)
                return True
            except Exception as exc:
                logger.warning("cog_command_fallback raised an exception: {}", exc)
        elif self._package is not None and getattr(self._package, "_error_fallback_func", None) is not None:
            try:
                from vkflow.utils.inject import inject_and_call

                await inject_and_call(
                    self._package._error_fallback_func, {"ctx": owner_ctx, "error": error}
                )
                return True
            except Exception as exc:
                logger.warning("package error_fallback raised an exception: {}", exc)

        app = getattr(ctx, "app", None)
        if app is not None and hasattr(app, "on_command_error_fallback"):
            try:
                app_ctx = owner_ctx if owner_ctx is not None else ctx
                await app.on_command_error_fallback(app_ctx, error)
                return True
            except Exception as exc:
                logger.warning("on_command_error_fallback raised an exception: {}", exc)

        return False

    def _parse_handler_arguments(self) -> None:
        from vkflow.commands.context import Context

        parameters = inspect.signature(self.handler).parameters

        for name, argument in parameters.items():
            if name in ("self", "cls"):
                continue

            arg_type = get_origin_typing(argument.annotation)
            context_types = [NewMessage, Context]

            def _is_context_type(t, context_types=context_types):
                if t in context_types:
                    return True
                if Context is not None and isinstance(t, type):
                    try:
                        return issubclass(t, Context)
                    except TypeError:
                        return False
                return False

            match (arg_type, argument.default):
                case (type(), _) if _is_context_type(arg_type):
                    self._ctx_argument_name = argument.name
                    self._ctx_type = arg_type

                    if self._text_arguments:
                        warnings.warn(
                            "Аргумент `NewMessage`/`Context` рекомендуется ставить "
                            "первым в функции (стилистическая рекомендация)",
                            stacklevel=2,
                        )

                case (_, Depends()):
                    continue

                case _:
                    text_argument = resolve_typing(argument)
                    self._text_arguments.append(text_argument)

        self._dependency_mixin.parse_dependency_arguments(self.handler)

    async def _dispatch_command_error(self, ctx: NewMessage, error: Exception) -> None:
        if hasattr(ctx, "app"):
            await ctx.app.dispatch_event("command_error", ctx=ctx, error=error, command=self)

    async def _dispatch_check_error(self, ctx: NewMessage, error: Exception) -> None:
        if hasattr(ctx, "app"):
            await ctx.app.dispatch_event("check_error", ctx=ctx, error=error, command=self)

    async def _dispatch_cooldown_error(self, ctx: NewMessage, error: Exception) -> None:
        if hasattr(ctx, "app"):
            await ctx.app.dispatch_event("cooldown_error", ctx=ctx, error=error, command=self)

    async def _dispatch_command_complete(self, ctx: NewMessage, arguments: ArgumentsDict) -> None:
        if hasattr(ctx, "app"):
            await ctx.app.dispatch_event("command_complete", ctx=ctx, command=self, arguments=arguments)

    async def _dispatch_argument_error(self, ctx: NewMessage, error: ArgumentParsingError) -> None:
        if hasattr(ctx, "app"):
            await ctx.app.dispatch_event("argument_error", ctx=ctx, error=error, command=self)

    async def _handle_argument_parsing_error(self, ctx: NewMessage, error: ArgumentParsingError) -> None:
        """
        Обработка ArgumentParsingError в strict режиме.

        Ищет подходящий обработчик через общую цепочку.
        Если не найден - перевыбрасывает ошибку.
        """
        handled = await self._find_error_handler(ctx, error, {})
        if not handled:
            raise error

    def _compile_routing_regex(self, prefixes: list[str]) -> typing.Pattern:
        """
        Компилирует регулярное выражение для маршрутизации команды.
        Не включает аргументы -для них своя логика парсинга.
        """
        names = {re.escape(name) for name in self.names}

        mention_patterns = []
        regular_prefixes = []

        for prefix in prefixes:
            if prefix.startswith(r"\["):
                mention_patterns.append(prefix + r"\s+")
            else:
                regular_prefixes.append(re.escape(prefix))

        names_regex = "|".join(names)

        all_prefixes = mention_patterns + regular_prefixes
        prefixes_regex = "|".join(all_prefixes) if all_prefixes else ""

        if len(self.names) > 1:
            names_regex = f"(?:{names_regex})"

        if len(all_prefixes) > 1:
            prefixes_regex = f"(?:{prefixes_regex})"

        summary_regex = prefixes_regex + names_regex

        if self._text_arguments and summary_regex:
            summary_regex += r"(?:$|\s+)"

        return re.compile(
            summary_regex,
            flags=self.routing_re_flags,
        )

    def _build_routing_regex(self) -> None:
        if not isinstance(self.prefixes, list):
            return
        self._routing_regex = self._compile_routing_regex(self.prefixes)

    def _build_dynamic_routing_regex(self, prefixes: list[str]) -> typing.Pattern:
        return self._compile_routing_regex(prefixes)
