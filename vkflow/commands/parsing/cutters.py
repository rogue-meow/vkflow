import re

import enum
import typing

import dataclasses

from typing import Literal

from vkflow.commands.parsing.cutter import (
    Cutter,
    CutterParsingResponse,
    cut_part_via_regex,
)

from vkflow.exceptions import BadArgumentError
from vkflow.app.storages import NewMessage
from vkflow.utils.helpers import get_origin_typing
from vkflow.models.page import Group, Page, User
from vkflow.exceptions import APIError


NameCaseType = Literal["nom", "gen", "dat", "acc", "ins", "abl"]


@dataclasses.dataclass(frozen=True, slots=True)
class NameCase:
    """
    Аннотация для указания падежа при резолвинге User/Group.

    Используется с typing.Annotated для указания падежа имени пользователя
    при автоматическом парсинге аргументов команды.

    Arguments:
        case: Падеж для склонения имени:
            - "nom" - именительный (кто? что?) - по умолчанию
            - "gen" - родительный (кого? чего?)
            - "dat" - дательный (кому? чему?)
            - "acc" - винительный (кого? что?)
            - "ins" - творительный (кем? чем?)
            - "abl" - предложный (о ком? о чём?)

    Example:
        from typing import Annotated

        @command(names=["погладить"])
        async def pat(ctx, target: Annotated[User, NameCase("acc")] = None):
            # target.first_name будет в винительном падеже
            return f"Погладил {target.mention()}"

        # Работает с Union типами:
        @command(names=["обнять"])
        async def hug(ctx, target: Annotated[User, NameCase("acc")] | Group | str = None):
            ...
    """

    case: NameCaseType


@dataclasses.dataclass(frozen=True, slots=True)
class Strict:
    """
    Аннотация для указания strict режима при парсинге кастомных типов.

    Используется с typing.Annotated для управления поведением при ошибке парсинга:
    - strict=True (по умолчанию): ошибка парсинга → команда не выполняется
    - strict=False: ошибка парсинга → возвращается default значение

    Имеет более высокий приоритет чем атрибут класса __strict__.

    Arguments:
        value: Режим строгости парсинга (True/False)

    Example:
        from typing import Annotated

        class HexColor:
            __strict__ = False  # Fallback если не указан Strict в Annotated
            __consume_on_error__ = True  # Потреблять текст при ошибке

            def __init__(self, ctx, value: str):
                self.color = self._parse_hex(value)

        # Использование Annotated (высший приоритет):
        @command(names=["color"])
        async def color_cmd(ctx, color: Annotated[HexColor, Strict(False)] = None):
            # При невалидном значении color будет None
            if color is None:
                return "Некорректный цвет!"
            return f"Цвет: {color.color}"

        # Без Annotated - используется __strict__ класса:
        @command(names=["color2"])
        async def color_cmd2(ctx, color: HexColor = None):
            ...
    """

    value: bool = True


class IntegerCutter(Cutter):
    _pattern = re.compile(r"[+-]?\d+")

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse[int]:
        return cut_part_via_regex(
            self._pattern,
            arguments_string,
            factory=int,
            error_description=self.gen_message_doc(),
        )

    def gen_doc(self):
        return "целое положительное или отрицательное число"


class FloatCutter(Cutter):
    _pattern = re.compile(
        r"""
        [-+]?  # optional sign
        (?:
            (?: \d* \. \d+ )  # .1 .12 .123 etc 9.1 etc 98.1 etc
            |
            (?: \d+ \.? )  # 1. 12. 123. etc 1 12 123 etc
        )
        # followed by optional exponent part if desired
        (?: [Ee][+-]? \d+ )?
        """,
        flags=re.X,
    )

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse[float]:
        return cut_part_via_regex(
            self._pattern,
            arguments_string,
            factory=float,
            error_description=self.gen_message_doc(),
        )

    def gen_doc(self):
        return (
            "дробное положительное или отрицательное число "
            "в десятичной форме (3.14, 2.718...). "
            "Число также может быть записано в "
            "экспоненциальной форме (4e6, 3.5E-6...). "
            "Если целая часть равна нулю, то она может быть опущена: "
            ".45 это 0.45 "
        )


class WordCutter(Cutter):
    _pattern = re.compile(r""""((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|(\S+)""")

    @staticmethod
    def _unescape(s: str, quote: str) -> str:
        """Убрать экранирование из строки в кавычках."""
        return s.replace(f"\\{quote}", quote).replace("\\\\", "\\")

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse[str]:
        match = self._pattern.match(arguments_string)
        if not match:
            raise BadArgumentError(self.gen_message_doc())

        if match.group(1) is not None:
            parsed = self._unescape(match.group(1), '"')
        elif match.group(2) is not None:
            parsed = self._unescape(match.group(2), "'")
        else:
            parsed = match.group(3)

        return CutterParsingResponse(
            parsed_part=parsed,
            new_arguments_string=arguments_string[match.end() :],
        )

    def gen_doc(self):
        return "любое слово или строка в кавычках"


class StringCutter(Cutter):
    _pattern = re.compile(r".+", flags=re.DOTALL)

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse[str]:
        return cut_part_via_regex(
            self._pattern,
            arguments_string,
            error_description=self.gen_message_doc(),
        )

    def gen_doc(self):
        return "абсолютно любой текст"


class OptionalCutter(Cutter):
    def __init__(
        self,
        typevar: Cutter,
        /,
        *,
        default: typing.Any | None = None,
        default_factory: typing.Callable[[], typing.Any] | None = None,
    ) -> None:
        self._default = default
        self._default_factory = default_factory

        self._typevar = typevar

    def _get_default(self) -> typing.Any:
        """Get the default value."""
        if self._default_factory is not None:
            return self._default_factory()
        return self._default

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        try:
            return await self._typevar.cut_part(ctx, arguments_string)

        except _NonStrictParsingError as e:
            if e.consume:
                parts = arguments_string.lstrip().split(maxsplit=1)
                remaining = parts[1] if len(parts) > 1 else ""
            else:
                remaining = arguments_string

            return CutterParsingResponse(
                parsed_part=self._get_default(),
                new_arguments_string=remaining,
            )

        except BadArgumentError:
            return CutterParsingResponse(
                parsed_part=self._get_default(),
                new_arguments_string=arguments_string,
            )

    def gen_doc(self):
        typevar_docstring = self._typevar.gen_doc()

        default = f"(по умолчанию -{self._default!r})" if self._default is not None else ""

        return typevar_docstring + f"\nАргумент опционален и может быть опущен {default}"


class UnionCutter(Cutter):
    """
    Каттер для Union типов (User | Group | str и т.д.).

    Порядок каттеров имеет значение: первый успешно распарсивший - побеждает.
    Более специфичные типы должны идти первыми (User перед str),
    иначе str поглотит всё раньше.

    Создаётся автоматически через `Cutter.__or__`:
        IntegerCutter() | FloatCutter()
    """

    def __init__(self, *typevars: Cutter):
        self._typevars = typevars

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        for typevar in self._typevars:
            try:
                parsed_value = await typevar.cut_part(ctx, arguments_string)
            except BadArgumentError:
                continue
            else:
                return parsed_value

        raise BadArgumentError(self.gen_message_doc())

    def gen_doc(self):
        header = "одно из следующих значений:<br><ol>{elements}</ol>"
        elements_docs = [f"<li>{typevar.gen_doc().capitalize()}</li>" for typevar in self._typevars]

        elements_docs = "\n".join(elements_docs)
        return header.format(elements=elements_docs)


class GroupCutter(Cutter):
    def __init__(self, *typevars: Cutter):
        self._typevars = typevars

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        parsed_parts = []

        for typevar in self._typevars:
            try:
                parsed_value = await typevar.cut_part(ctx, arguments_string)

            except BadArgumentError as err:
                raise BadArgumentError(self.gen_message_doc()) from err

            else:
                arguments_string = parsed_value.new_arguments_string
                parsed_parts.append(parsed_value.parsed_part)
                continue

        return CutterParsingResponse(
            parsed_part=tuple(parsed_parts),
            new_arguments_string=arguments_string,
        )

    def gen_doc(self):
        header = "последовательность следующих аргументов без пробелов:<br><ol>{elements}</ol>"
        elements_docs = [f"<li>{typevar.gen_doc()}</li>" for typevar in self._typevars]

        elements_docs = "\n".join(elements_docs)
        return header.format(elements=elements_docs)


class _SequenceCutter(Cutter):
    _factory: typing.Callable[[list], typing.Sequence]

    def __init__(self, typevar: Cutter):
        self._typevar = typevar

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        typevar = self._typevar
        parsed_values = []

        while True:
            try:
                parsing_response = await typevar.cut_part(ctx, arguments_string)

            except BadArgumentError:
                return CutterParsingResponse(
                    parsed_part=self._factory(parsed_values),
                    new_arguments_string=arguments_string,
                )

            else:
                arguments_string = parsing_response.new_arguments_string.lstrip().lstrip(",").lstrip()

                parsed_values.append(parsing_response.parsed_part)
                continue

    def gen_doc(self):
        typevar_docstring = self._typevar.gen_doc()

        return typevar_docstring + ". Аргументов может быть несколько (перечислены через запятую/пробел)"


class MutableSequenceCutter(_SequenceCutter):
    _factory = list


class ImmutableSequenceCutter(_SequenceCutter):
    _factory = tuple


class UniqueMutableSequenceCutter(_SequenceCutter):
    _factory = set


class UniqueImmutableSequenceCutter(_SequenceCutter):
    _factory = frozenset


class LiteralCutter(Cutter):
    def __init__(self, *container_values: str):
        self._container_values = tuple(map(re.compile, container_values))

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        for typevar in self._container_values:
            try:
                return cut_part_via_regex(typevar, arguments_string)
            except BadArgumentError:
                continue

        raise BadArgumentError(self.gen_message_doc())

    def gen_doc(self):
        header = "любое из следующих значений:<br><ol>{elements}</ol>"
        elements_docs = [f"<li><code>{typevar.pattern}</code></li>" for typevar in self._container_values]

        elements_docs = "\n".join(elements_docs)
        return header.format(elements=elements_docs)


UserID = typing.NewType("UserID", int)
GroupID = typing.NewType("GroupID", int)
PageID = typing.NewType("PageID", int)


T = typing.TypeVar("T")


@enum.unique
class PageType(enum.Enum):
    USER = enum.auto()
    GROUP = enum.auto()


@dataclasses.dataclass
class Mention(typing.Generic[T]):
    alias: str
    entity: T
    page_type: PageType


class MentionCutter(Cutter):
    mention_regex = re.compile(
        r"""
        \[
        (?P<page_type> (?:id) | (?:club) )  # User or group
        (?P<id> [1-9]\d* )  # ID of the page
        \|
        (?P<alias> .+? )  # Alias of the mention
        ]
        """,
        flags=re.X,
    )

    def __init__(self, page_type: T, *, name_case: NameCaseType | None = None):
        self._page_type = get_origin_typing(page_type)
        self._name_case = name_case
        fields = typing.get_args(page_type)

        if fields:
            self._fields = typing.get_args(fields[0])
        else:
            self._fields = None

    async def _make_user(self, ctx: NewMessage, page_id: int):
        return await User.fetch_one(ctx.api, page_id, fields=self._fields, name_case=self._name_case)

    async def _make_group(self, ctx: NewMessage, page_id: int):
        return await Group.fetch_one(ctx.api, page_id, fields=self._fields)

    async def _cast_type(self, ctx: NewMessage, page_id: int, page_type: PageType) -> T:
        match (self._page_type, page_type):
            case (_, _) if (
                (self._page_type is UserID and page_type == PageType.USER)
                or (self._page_type is GroupID and page_type == PageType.GROUP)
                or (self._page_type is PageID)
            ):
                return page_id

            case (_, _) if self._page_type is User and page_type == PageType.USER:
                return await self._make_user(ctx, page_id)

            case (_, _) if self._page_type is Group and page_type == PageType.GROUP:
                return await self._make_group(ctx, page_id)

            case (_, _) if self._page_type is Page and page_type == PageType.USER:
                return await self._make_user(ctx, page_id)

            case (_, _) if self._page_type is Page and page_type == PageType.GROUP:
                return await self._make_group(ctx, page_id)

            case _:
                raise BadArgumentError(self.gen_doc())

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse[Mention[T]]:
        parsing_response = cut_part_via_regex(self.mention_regex, arguments_string)

        match_object: typing.Match = parsing_response.extra["match_object"]

        page_id = int(match_object.group("id"))
        page_type_str = match_object.group("page_type")

        match page_type_str:
            case "id":
                page_type = PageType.USER
            case _:
                page_type = PageType.GROUP

        try:
            casted_part = await self._cast_type(ctx, page_id, page_type)

        except APIError as err:
            raise BadArgumentError("Invalid id") from err

        else:
            parsing_response.parsed_part = Mention(
                alias=match_object.group("alias"),
                entity=casted_part,
                page_type=page_type,
            )

            return parsing_response

    def gen_doc(self):
        if self._page_type in {User, UserID}:
            who = "пользователь"
        elif self._page_type in {Group, GroupID}:
            who = "группа"
        else:
            who = "пользователь или группа"

        return f"{who} в виде упоминания"


class EntityCutter(MentionCutter):
    screen_name_regex = re.compile(
        r"""
        # Optional protocol
        (?: https?:// )? 

        # Optional vk domain (vk.com or vk.ru)
        (?: vk\.(?:com|ru)/ )?

        # Screen name of user or group


        (?P<screen_name> 
            (?:
                [a-z](?=[\d_\.a-z]) |
                \d{1,2}(?=[a-z])
            )

            # First character can be either a digit or a letter
            # Cannot start with more than two consecutive digits

            (?:
                [a-z](?=[\d_\.a-z]) | 
                # Rules for a letter

                \d(?=[a-z\d_]) | 
                # Rules for a digit

                \.(?=[a-z])|
                # Rules for a dot

                _(?=[_\da-z])
                # Rules for an underscore

            ){,30}
            # Length check (up to 32)

            (?<!\.[a-z_\d]{2})(?<!\.[a-z_\d]{1})(?<!\.)
            # If possible, check separately the last four characters in the string,
            # Because there must be 4 or more characters after a dot.

            [a-z\d](?![a-z_\.\d:])
            # Last character can be either a digit or a letter
        )

        # URL path part
        /?

        # Example:
        # vk.ru/deknowny
        # vk.ru/id100
        # https://vk.ru/eee
        """,
        flags=re.X | re.IGNORECASE,
    )

    raw_id_regex = re.compile(
        r"""
        # Type of id: group/user. Positive ID means user, negative -- group
        (?P<type>
            [+-]? | (?:id) | (?:club)
        ) 

        # ID of user/group
        (?P<id> \d+ )
        """,
        flags=re.X,
    )

    def gen_doc(self):
        if self._page_type in {User, UserID}:
            who = "пользователя"
        elif self._page_type in {Group, GroupID}:
            who = "группы"
        else:
            who = "пользователя или группы"
        return (
            f"упоминание/ID/короткое имя/ссылку на страницу {who}. "
            "Также можно просто переслать сообщение пользователя"
        )

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        for method in (
            self._mention_method,
            self._link_method,
            self._raw_id_method,
            self._attached_method,
        ):
            try:
                return await method(ctx, arguments_string)
            except BadArgumentError:
                continue

        raise BadArgumentError(self.gen_doc())

    async def _mention_method(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        parsing_response = await MentionCutter.cut_part(self, ctx, arguments_string)

        parsing_response.parsed_part = parsing_response.parsed_part.entity
        return parsing_response

    async def _link_method(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        parsing_response = cut_part_via_regex(self.screen_name_regex, arguments_string, group="screen_name")

        resolved_screen_name = await ctx.api.use_cache().method(
            "utils.resolve_screen_name",
            screen_name=parsing_response.parsed_part,
        )

        if not resolved_screen_name:
            raise BadArgumentError("Invalid screen name")

        match resolved_screen_name["type"]:
            case "user":
                page_type = PageType.USER
            case "group":
                page_type = PageType.GROUP
            case _:
                raise BadArgumentError("Invalid screen name")

        parsing_response.parsed_part = await self._cast_type(
            ctx, resolved_screen_name["object_id"], page_type
        )

        return parsing_response

    async def _raw_id_method(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        parsing_response = cut_part_via_regex(self.raw_id_regex, arguments_string)

        match_object: typing.Match = parsing_response.extra["match_object"]

        match match_object.group("type"):
            case "+" | "id" | "":
                page_type = PageType.USER
            case _:
                page_type = PageType.GROUP

        parsing_response.parsed_part = await self._cast_type(ctx, match_object.group("id"), page_type)

        return parsing_response

    async def _attached_method(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        if ctx.msg.is_cropped:
            await ctx.msg.extend(ctx.api)

        if ctx.msg.reply_message is not None:
            page_id = ctx.msg.reply_message.from_id

            if not ctx.argument_processing_payload.replied_user_used:
                ctx.argument_processing_payload.replied_user_used = True

            else:
                raise BadArgumentError(
                    "Пользователь из ответного сообщения уже использован другим аргументом"
                )

        else:
            forwarded_pages = ctx.msg.fwd_messages
            step = ctx.argument_processing_payload.forward_page_iter_step

            if step == 0:
                ctx.argument_processing_payload.forward_page_iter_step = 1
            else:
                ctx.argument_processing_payload.forward_page_iter_step = step + 1

            try:
                page_id = forwarded_pages[step].from_id
            except IndexError:
                raise BadArgumentError(self.gen_doc()) from None

        parsed_part = await self._cast_type(
            ctx,
            abs(page_id),
            PageType.USER if page_id > 0 else PageType.GROUP,
        )

        return CutterParsingResponse(parsed_part=parsed_part, new_arguments_string=arguments_string)


class AutoConverterCutter(Cutter):
    """
    Cutter that automatically creates instances of classes.

    Supports two initialization methods (in priority order):

    1. Async classmethod `create`:
        @classmethod
        async def create(cls, ctx, value: str) -> Self:
            instance = cls(...)
            # async initialization
            return instance

    2. Regular `__init__`:
        def __init__(self, ctx, value: str):
            ...

    Parameters (ctx, value) are OPTIONAL - only passed if the method accepts them:
    - (cls/self) - no parameters
    - (cls/self, ctx) - only context
    - (cls/self, value) - only value
    - (cls/self, ctx, value) - both

    If the constructor/create raises an exception, behavior depends on strict mode:
    - strict=True: raises BadArgumentError, command won't execute
    - strict=False (default): returns None (or default), command continues

    Class attributes for configuration:
    - __strict__: bool = False - default strict mode (can be overridden by Annotated[T, Strict(True)])
    - __consume_on_error__: bool = False - whether to consume text on error

    Example with async create:
        class HexColor:
            def __init__(self, ctx, value: str):
                self.ctx = ctx
                self.color = value

            @classmethod
            async def create(cls, ctx, value: str):
                instance = cls(ctx, value)
                instance.color = await instance._parse_hex(value)
                return instance

            async def _parse_hex(self, value: str) -> str:
                # Can do async operations here
                ...

        @command(names=["color"])
        async def color_cmd(ctx, color: HexColor = None):
            if color is None:
                return "Invalid color!"
            ...

    Example with simple __init__:
        class PositiveInt:
            def __init__(self, value: str):  # No ctx needed
                num = int(value)
                if num <= 0:
                    raise ValueError("Must be positive")
                self.value = num

    Override strict mode via Annotated:
        from typing import Annotated
        from vkflow import Strict

        @command(names=["color"])
        async def color_cmd(ctx, color: Annotated[HexColor, Strict(True)] = None):
            # Will fail on invalid input
            ...
    """

    def __init__(self, target_class: type, *, strict: bool | None = None):

        self._target_class = target_class
        self._explicit_strict = strict

        self._has_async_create = self._check_has_async_create()

        if self._has_async_create:
            self._accepts_ctx, self._accepts_value = self._analyze_method_params(self._target_class.create)
        else:
            self._accepts_ctx, self._accepts_value = self._analyze_method_params(
                self._target_class.__init__
            )

    def _check_has_async_create(self) -> bool:
        """Check if class has async classmethod 'create'."""
        import inspect

        if not hasattr(self._target_class, "create"):
            return False

        create_method = self._target_class.create

        if not isinstance(inspect.getattr_static(self._target_class, "create"), classmethod):
            return False

        func = getattr(create_method, "__func__", create_method)

        return inspect.iscoroutinefunction(func)

    def _analyze_method_params(self, method) -> tuple[bool, bool]:
        """
        Analyze method signature to determine which parameters it accepts.

        Строит список _call_params для точной передачи аргументов по именам
        параметров метода (а не только 'ctx'/'value').

        Returns:
            (accepts_ctx, accepts_value) tuple of bools
        """
        import inspect

        try:
            func = getattr(method, "__func__", method)
            sig = inspect.signature(func)
            params = list(sig.parameters.values())

            if params and params[0].name in ("self", "cls"):
                params = params[1:]

            if not params:
                self._call_params = []
                return False, False

            self._call_params = []

            for p in params:
                if p.default != inspect.Parameter.empty:
                    break

                is_ctx = p.name == "ctx" or (
                    p.annotation != inspect.Parameter.empty and self._is_ctx_annotation(p.annotation)
                )

                if is_ctx:
                    self._call_params.append(("ctx", p.name))
                else:
                    self._call_params.append(("value", p.name))

            accepts_ctx = any(role == "ctx" for role, _ in self._call_params)
            accepts_value = any(role == "value" for role, _ in self._call_params)

            return accepts_ctx, accepts_value

        except (ValueError, TypeError):
            self._call_params = [("value", "value")]
            return False, True

    def _is_ctx_annotation(self, annotation) -> bool:
        """Check if annotation is a Context/NewMessage type."""
        if annotation is None:
            return False

        ann_name = getattr(annotation, "__name__", str(annotation))
        return ann_name in ("Context", "NewMessage")

    @property
    def strict(self) -> bool:
        """
        Get the effective strict mode.

        Priority:
        1. Explicit strict parameter (from Annotated[T, Strict(...)])
        2. Class __strict__ attribute
        3. Default: False (non-strict by default for custom types)
        """
        if self._explicit_strict is not None:
            return self._explicit_strict

        return getattr(self._target_class, "__strict__", False)

    @property
    def consume_on_error(self) -> bool:
        """
        Get whether to consume text on error.

        From class __consume_on_error__ attribute, default: False
        """
        return getattr(self._target_class, "__consume_on_error__", False)

    def _build_kwargs(self, ctx: NewMessage, value: str) -> dict:
        """
        Build kwargs dict based on what the method accepts.
        Использует реальные имена параметров из _call_params,
        чтобы работали методы с произвольными именами параметров
        (не только 'ctx'/'value').
        """
        kwargs = {}

        for role, param_name in self._call_params:
            if role == "ctx":
                kwargs[param_name] = ctx
            elif role == "value":
                kwargs[param_name] = value

        return kwargs

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        arguments_string = arguments_string.lstrip()

        if not arguments_string:
            raise BadArgumentError(self.gen_doc())

        parts = arguments_string.split(maxsplit=1)
        value = parts[0]
        remaining = parts[1] if len(parts) > 1 else ""

        try:
            kwargs = self._build_kwargs(ctx, value)

            if self._has_async_create:
                instance = await self._target_class.create(**kwargs)
            else:
                instance = self._target_class(**kwargs)

        except Exception as e:
            if self.strict:
                error_msg = str(e) if str(e) else self.gen_doc()
                raise BadArgumentError(error_msg) from e
            raise _NonStrictParsingError(
                consume=self.consume_on_error,
                consumed_text=value,
                original_error=e,
            ) from e

        return CutterParsingResponse(
            parsed_part=instance,
            new_arguments_string=remaining,
        )

    def gen_doc(self) -> str:
        class_name = self._target_class.__name__

        if hasattr(self._target_class, "__doc__") and self._target_class.__doc__:
            first_line = self._target_class.__doc__.strip().split("\n")[0]

            if first_line:
                return f"{class_name}: {first_line}"

        return f"значение типа {class_name}"


class _NonStrictParsingError(BadArgumentError):
    """
    Special error for non-strict parsing mode.

    This error is raised by AutoConverterCutter when:
    - strict=False
    - Parsing failed

    OptionalCutter handles this specially to decide whether to consume text.
    """

    def __init__(self, *, consume: bool, consumed_text: str, original_error: Exception):
        self.consume = consume
        self.consumed_text = consumed_text
        self.original_error = original_error
        super().__init__(str(original_error) if str(original_error) else "Parsing failed")


@dataclasses.dataclass(frozen=True, slots=True)
class BoolValues:
    """
    Annotated-маркер для настройки допустимых значений BoolCutter.

    Example:
        from typing import Annotated

        @command()
        async def toggle(ctx, state: Annotated[bool, BoolValues(
            true=["вкл", "включить"],
            false=["выкл", "выключить"],
        )]):
            ...
    """

    true: list[str] = dataclasses.field(default_factory=lambda: ["1", "да", "yes", "+", "on", "вкл"])
    false: list[str] = dataclasses.field(default_factory=lambda: ["0", "нет", "no", "-", "off", "выкл"])


class BoolCutter(Cutter):
    _default_true: typing.ClassVar[list[str]] = ["1", "да", "yes", "+", "on", "вкл"]
    _default_false: typing.ClassVar[list[str]] = ["0", "нет", "no", "-", "off", "выкл"]

    def __init__(self, bool_values: BoolValues | None = None):
        if bool_values is not None:
            self.true_values = bool_values.true
            self.false_values = bool_values.false
        else:
            self.true_values = self._default_true
            self.false_values = self._default_false

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse[bool]:
        arguments_string = arguments_string.lstrip()
        lowered = arguments_string.lower()

        for true_value in self.true_values:
            if lowered.startswith(true_value):
                rest = arguments_string[len(true_value) :]

                if not rest or rest[0].isspace():
                    return CutterParsingResponse(
                        parsed_part=True,
                        new_arguments_string=rest,
                    )

        for false_value in self.false_values:
            if lowered.startswith(false_value):
                rest = arguments_string[len(false_value) :]

                if not rest or rest[0].isspace():
                    return CutterParsingResponse(
                        parsed_part=False,
                        new_arguments_string=rest,
                    )

        raise BadArgumentError(self.gen_doc())

    def gen_doc(self) -> str:
        return "булево значение: {} в качестве истины и {} для лжи".format(
            "/".join(self.true_values),
            "/".join(self.false_values),
        )


class AttachmentCutter(Cutter):
    """
    Base cutter for extracting attachments from messages.

    Attachments are extracted from:
    1. Current message
    2. Reply message
    3. Forwarded messages

    This cutter does NOT consume text from the arguments string.
    """

    _attachment_type: str
    _attachment_class: type
    _type_name_ru: str

    def __init__(self):
        from vkflow.models.attachment import ATTACHMENT_TYPES

        if not hasattr(self, "_attachment_class"):
            self._attachment_class = ATTACHMENT_TYPES.get(self._attachment_type)

    async def _get_attachments_from_message(self, msg, api) -> list:
        """Extract attachments of the required type from a message."""
        from vkflow.models.attachment import ATTACHMENT_TYPES

        if msg.is_cropped:
            await msg.extend(api)

        result = []

        for attachment in msg.attachments:
            if attachment["type"] == self._attachment_type:
                att_class = ATTACHMENT_TYPES.get(self._attachment_type)

                if att_class:
                    result.append(att_class(attachment[self._attachment_type]))

        return result

    async def _collect_all_attachments(self, ctx: NewMessage) -> list:
        """
        Collect attachments from current, reply, and forwarded messages.

        Priority: current -> reply -> forwarded
        """
        all_attachments = []

        all_attachments.extend(await self._get_attachments_from_message(ctx.msg, ctx.api))

        if ctx.msg.reply_message is not None:
            all_attachments.extend(await self._get_attachments_from_message(ctx.msg.reply_message, ctx.api))

        for fwd_msg in ctx.msg.fwd_messages:
            all_attachments.extend(await self._get_attachments_from_message(fwd_msg, ctx.api))

        return all_attachments

    def _get_used_count(self, ctx: NewMessage) -> int:
        """Получить количество уже использованных вложений данного типа."""
        return ctx.argument_processing_payload.get_attachment_used(self._attachment_type)

    def _increment_used_count(self, ctx: NewMessage) -> None:
        """Увеличить счётчик использованных вложений данного типа."""
        ctx.argument_processing_payload.increment_attachment_used(self._attachment_type)

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        all_attachments = await self._collect_all_attachments(ctx)
        used_count = self._get_used_count(ctx)

        if used_count >= len(all_attachments):
            raise BadArgumentError(self.gen_doc())

        attachment = all_attachments[used_count]
        self._increment_used_count(ctx)

        return CutterParsingResponse(
            parsed_part=attachment,
            new_arguments_string=arguments_string,
        )

    def gen_doc(self) -> str:
        return f"вложение типа {self._type_name_ru}"


class AttachmentListCutter(AttachmentCutter):
    """
    Cutter for extracting all attachments of a specific type as a list.

    Returns all attachments that haven't been consumed by previous arguments.
    """

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        all_attachments = await self._collect_all_attachments(ctx)
        used_count = self._get_used_count(ctx)

        remaining_attachments = all_attachments[used_count:]

        ctx.argument_processing_payload.set_attachment_used(self._attachment_type, len(all_attachments))

        return CutterParsingResponse(
            parsed_part=remaining_attachments,
            new_arguments_string=arguments_string,
        )

    def gen_doc(self) -> str:
        return f"список вложений типа {self._type_name_ru}"


class PhotoCutter(AttachmentCutter):
    _attachment_type = "photo"
    _type_name_ru = "фотография"


class PhotoListCutter(AttachmentListCutter):
    _attachment_type = "photo"
    _type_name_ru = "фотография"


class DocumentCutter(AttachmentCutter):
    _attachment_type = "doc"
    _type_name_ru = "документ"


class DocumentListCutter(AttachmentListCutter):
    _attachment_type = "doc"
    _type_name_ru = "документ"


class VideoCutter(AttachmentCutter):
    _attachment_type = "video"
    _type_name_ru = "видео"


class VideoListCutter(AttachmentListCutter):
    _attachment_type = "video"
    _type_name_ru = "видео"


class AudioCutter(AttachmentCutter):
    _attachment_type = "audio"
    _type_name_ru = "аудио"


class AudioListCutter(AttachmentListCutter):
    _attachment_type = "audio"
    _type_name_ru = "аудио"


class AudioMessageCutter(AttachmentCutter):
    _attachment_type = "audio_message"
    _type_name_ru = "голосовое сообщение"


class AudioMessageListCutter(AttachmentListCutter):
    _attachment_type = "audio_message"
    _type_name_ru = "голосовое сообщение"


class StickerCutter(AttachmentCutter):
    _attachment_type = "sticker"
    _type_name_ru = "стикер"


class StickerListCutter(AttachmentListCutter):
    _attachment_type = "sticker"
    _type_name_ru = "стикер"


class WallCutter(AttachmentCutter):
    _attachment_type = "wall"
    _type_name_ru = "запись на стене"


class WallListCutter(AttachmentListCutter):
    _attachment_type = "wall"
    _type_name_ru = "запись на стене"


class GiftCutter(AttachmentCutter):
    _attachment_type = "gift"
    _type_name_ru = "подарок"


class GiftListCutter(AttachmentListCutter):
    _attachment_type = "gift"
    _type_name_ru = "подарок"


class GraffitiCutter(AttachmentCutter):
    _attachment_type = "graffiti"
    _type_name_ru = "граффити"


class GraffitiListCutter(AttachmentListCutter):
    _attachment_type = "graffiti"
    _type_name_ru = "граффити"


class LinkCutter(AttachmentCutter):
    _attachment_type = "link"
    _type_name_ru = "ссылка"


class LinkListCutter(AttachmentListCutter):
    _attachment_type = "link"
    _type_name_ru = "ссылка"


class PollCutter(AttachmentCutter):
    _attachment_type = "poll"
    _type_name_ru = "опрос"


class PollListCutter(AttachmentListCutter):
    _attachment_type = "poll"
    _type_name_ru = "опрос"


class MarketCutter(AttachmentCutter):
    _attachment_type = "market"
    _type_name_ru = "товар"


class MarketListCutter(AttachmentListCutter):
    _attachment_type = "market"
    _type_name_ru = "товар"


class StoryCutter(AttachmentCutter):
    _attachment_type = "story"
    _type_name_ru = "история"


class StoryListCutter(AttachmentListCutter):
    _attachment_type = "story"
    _type_name_ru = "история"


class ValidatingCutter(Cutter):
    """
    Wrapper cutter that applies validators after parsing.

    This cutter wraps an inner cutter and applies a list of validators
    to the parsed value. If any validator fails, BadArgumentError is raised.

    Usage:
        from typing import Annotated
        from vkflow import Range

        @command()
        async def roll(ctx, sides: Annotated[int, Range(1, 100)] = 6):
            ...
    """

    def __init__(self, inner_cutter: Cutter, validators: list):
        """
        Initialize validating cutter.

        Args:
            inner_cutter: The cutter to wrap
            validators: List of Validator instances to apply
        """
        self._inner = inner_cutter
        self._validators = validators

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        """
        Парсинг и валидация аргумента.

        Поддерживает как синхронные, так и асинхронные валидаторы.
        """
        import inspect

        response = await self._inner.cut_part(ctx, arguments_string)

        for validator in self._validators:
            try:
                result = validator.validate(response.parsed_part)
                if inspect.isawaitable(result):
                    result = await result
                response.parsed_part = result
            except (ValueError, TypeError, AttributeError) as e:
                raise BadArgumentError(str(e)) from e

        return response

    def gen_doc(self) -> str:
        """Generate documentation including validator constraints."""
        inner_doc = self._inner.gen_doc()
        constraints = ", ".join(v.description() for v in self._validators if v.description())
        if constraints:
            return f"{inner_doc} ({constraints})"
        return inner_doc


from vkflow.utils.sentinel import MISSING as _MISSING  # noqa: E402


@dataclasses.dataclass(frozen=True, slots=True)
class Flag:
    """
    Annotated-маркер для boolean флаг-аргументов.

    Флаги извлекаются из любого места строки аргументов (не последовательно).
    Используют синтаксис --name / --no-name.

    Example:
        from typing import Annotated
        from vkflow import Flag

        @command(names=["бан"])
        async def ban(ctx, user: User,
                      silent: Annotated[bool, Flag()] = False,
                      *, reason: str = "нет причины"):
            # !бан @user --silent причина бана
            # !бан @user --no-silent причина
            ...
    """

    short: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Named:
    """
    Annotated-маркер для именованных аргументов (--key value).

    Именованные аргументы извлекаются из любого места строки аргументов.

    Example:
        from typing import Annotated
        from vkflow import Named

        @command(names=["настройки"])
        async def settings(ctx,
                           timeout: Annotated[int, Named()] = 30,
                           mode: Annotated[str, Named()] = "normal"):
            # !настройки --timeout 60 --mode strict
            ...
    """

    name: str | None = None


class FlagCutter(Cutter):
    """
    Cutter для --flag аргументов.
    Сканирует всю строку аргументов, ищет --name или --no-name.
    Не потребляет текст последовательно -удаляет флаг из строки.
    """

    is_non_positional = True

    def __init__(self, flag_name: str, *, default: bool = False, short: str | None = None):
        self._flag_name = flag_name
        self._default = default
        self._short = short

    @staticmethod
    def _find_token(text: str, token: str) -> int | None:
        """Найти токен в тексте с проверкой границ слова."""
        idx = 0
        while True:
            idx = text.find(token, idx)
            if idx == -1:
                return None

            if idx > 0 and not text[idx - 1].isspace():
                idx += 1
                continue

            end = idx + len(token)
            if end < len(text) and not text[end].isspace():
                idx += 1
                continue

            return idx

    @staticmethod
    def _remove_token(text: str, start: int, length: int) -> str:
        """Удалить токен из текста, почистив пробелы."""
        before = text[:start]
        after = text[start + length :]
        return (before.rstrip() + " " + after.lstrip()).strip()

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse[bool]:
        patterns = [
            (f"--no-{self._flag_name}", False),
            (f"--{self._flag_name}", True),
        ]
        if self._short:
            patterns.append((f"-{self._short}", True))

        for pattern, value in patterns:
            idx = self._find_token(arguments_string, pattern)
            if idx is not None:
                new_string = self._remove_token(arguments_string, idx, len(pattern))
                return CutterParsingResponse(
                    parsed_part=value,
                    new_arguments_string=new_string,
                )

        return CutterParsingResponse(
            parsed_part=self._default,
            new_arguments_string=arguments_string,
        )

    def gen_doc(self) -> str:
        parts = [f"--{self._flag_name}"]
        if self._short:
            parts.append(f"-{self._short}")
        return f"флаг {'/'.join(parts)}"


class NamedArgCutter(Cutter):
    """
    Cutter для именованных аргументов (--key value).
    Сканирует всю строку, ищет --name и извлекает следующее слово как значение.
    Поддерживает значения в кавычках: --reason "длинная причина".
    """

    is_non_positional = True

    def __init__(self, arg_name: str, value_cutter: Cutter, *, default=_MISSING):
        self._arg_name = arg_name
        self._value_cutter = value_cutter
        self._default = default

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        flag = f"--{self._arg_name}"
        idx = FlagCutter._find_token(arguments_string, flag)

        if idx is not None:
            after_flag_start = idx + len(flag)
            after_flag = arguments_string[after_flag_start:]
            after_flag_stripped = after_flag.lstrip()

            if after_flag_stripped:
                value_str, after_value = _extract_named_value(after_flag_stripped)

                if value_str is not None:
                    try:
                        cutter_input = f'"{value_str}"' if " " in value_str else value_str

                        parsed = await self._value_cutter.cut_part(ctx, cutter_input)
                        before = arguments_string[:idx].rstrip()
                        new_string = (before + " " + after_value.lstrip()).strip()
                        return CutterParsingResponse(
                            parsed_part=parsed.parsed_part,
                            new_arguments_string=new_string,
                        )
                    except BadArgumentError:
                        pass

        if self._default is not _MISSING:
            return CutterParsingResponse(
                parsed_part=self._default,
                new_arguments_string=arguments_string,
            )

        raise BadArgumentError(self.gen_doc())

    def gen_doc(self) -> str:
        return f"--{self._arg_name} <{self._value_cutter.gen_doc()}>"


def _extract_named_value(text: str) -> tuple[str, str]:
    """Извлечь значение из текста, поддерживая кавычки и экранирование."""
    text = text.lstrip()
    if not text:
        return "", ""

    if text[0] in ('"', "'"):
        quote = text[0]
        i = 1
        while i < len(text):
            if text[i] == "\\" and i + 1 < len(text):
                i += 2
                continue
            if text[i] == quote:
                value = text[1:i].replace(f"\\{quote}", quote).replace("\\\\", "\\")
                return value, text[i + 1 :]
            i += 1

    parts = text.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else ""


class EnumCutter(Cutter):
    """
    Cutter для enum.Enum типов.
    Матчит значения enum (value) и имена (name), case-insensitive.

    Example:
        class Action(enum.Enum):
            BAN = "бан"
            MUTE = "мут"
            WARN = "варн"

        @command()
        async def mod(ctx, action: Action, user: User):
            ...
    """

    def __init__(self, enum_class: type):
        self._enum_class = enum_class
        self._lookup: list[tuple[str, typing.Any]] = []

        pairs: dict[str, typing.Any] = {}
        for member in enum_class:
            pairs[str(member.value).lower()] = member
            pairs[member.name.lower()] = member

        self._lookup = sorted(pairs.items(), key=lambda x: len(x[0]), reverse=True)

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        arguments_string = arguments_string.lstrip()
        if not arguments_string:
            raise BadArgumentError(self.gen_doc())

        lowered = arguments_string.lower()

        for key, member in self._lookup:
            if lowered.startswith(key):
                rest = arguments_string[len(key) :]
                if not rest or rest[0].isspace():
                    return CutterParsingResponse(
                        parsed_part=member,
                        new_arguments_string=rest,
                    )

        raise BadArgumentError(self.gen_doc())

    def gen_doc(self) -> str:
        values = [str(m.value) for m in self._enum_class]
        return f"одно из значений: {', '.join(values)}"


class DictCutter(Cutter):
    """
    Cutter для dict[str, T] типов.
    Парсит пары ключ=значение, разделённые пробелами.

    Example:
        @command()
        async def set(ctx, params: dict[str, int]):
            # !set hp=100 mp=50
            ...
    """

    _pair_pattern = re.compile(r'(\S+?)=("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\S+)')

    def __init__(self, value_cutter: Cutter):
        self._value_cutter = value_cutter

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        result = {}
        remaining = arguments_string.lstrip()

        while remaining:
            remaining = remaining.lstrip()
            match = self._pair_pattern.match(remaining)
            if not match:
                break

            key = match.group(1)
            raw_value = match.group(2)

            if raw_value.startswith('"') and raw_value.endswith('"'):
                raw_value = raw_value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            elif raw_value.startswith("'") and raw_value.endswith("'"):
                raw_value = raw_value[1:-1].replace("\\'", "'").replace("\\\\", "\\")

            try:
                if " " in raw_value:
                    escaped = raw_value.replace("\\", "\\\\").replace('"', '\\"')
                    cutter_input = f'"{escaped}"'
                else:
                    cutter_input = raw_value
                parsed = await self._value_cutter.cut_part(ctx, cutter_input)
                result[key] = parsed.parsed_part
                remaining = remaining[match.end() :]
            except BadArgumentError:
                break

        return CutterParsingResponse(
            parsed_part=result,
            new_arguments_string=remaining,
        )

    def gen_doc(self) -> str:
        value_doc = self._value_cutter.gen_doc()
        return f"пары ключ=значение (значение: {value_doc})"


ATTACHMENT_CUTTERS: dict[str, type[AttachmentCutter]] = {
    "photo": PhotoCutter,
    "doc": DocumentCutter,
    "video": VideoCutter,
    "audio": AudioCutter,
    "audio_message": AudioMessageCutter,
    "sticker": StickerCutter,
    "wall": WallCutter,
    "gift": GiftCutter,
    "graffiti": GraffitiCutter,
    "link": LinkCutter,
    "poll": PollCutter,
    "market": MarketCutter,
    "story": StoryCutter,
}


ATTACHMENT_LIST_CUTTERS: dict[str, type[AttachmentListCutter]] = {
    "photo": PhotoListCutter,
    "doc": DocumentListCutter,
    "video": VideoListCutter,
    "audio": AudioListCutter,
    "audio_message": AudioMessageListCutter,
    "sticker": StickerListCutter,
    "wall": WallListCutter,
    "gift": GiftListCutter,
    "graffiti": GraffitiListCutter,
    "link": LinkListCutter,
    "poll": PollListCutter,
    "market": MarketListCutter,
    "story": StoryListCutter,
}
