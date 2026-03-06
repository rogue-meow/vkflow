from __future__ import annotations

import re
import enum
import types
import typing
import inspect
import functools

from vkflow.commands.parsing.cutter import Argument, CommandTextArgument, Cutter
from vkflow.commands.parsing.cutters import (
    ATTACHMENT_CUTTERS,
    ATTACHMENT_LIST_CUTTERS,
    AttachmentCutter,
    AttachmentListCutter,
    AutoConverterCutter,
    BoolCutter,
    BoolValues,
    EntityCutter,
    FloatCutter,
    GroupCutter,
    GroupID,
    ImmutableSequenceCutter,
    IntegerCutter,
    LiteralCutter,
    Mention,
    MentionCutter,
    MutableSequenceCutter,
    NameCase,
    OptionalCutter,
    PageID,
    Strict,
    StringCutter,
    UnionCutter,
    EnumCutter,
    DictCutter,
    Flag,
    Named,
    FlagCutter,
    NamedArgCutter,
    UniqueImmutableSequenceCutter,
    UniqueMutableSequenceCutter,
    UserID,
    ValidatingCutter,
    WordCutter,
)
from vkflow.commands.parsing.validators import Validator, Between
from vkflow.commands.parsing.registry import get_registered_cutter

from vkflow.models.page import Group, Page, User
from vkflow.models.attachment import (
    ATTACHMENT_TYPES,
)


_NAMED_MISSING = object()


@functools.cache
def _core_imports():
    """
    Ленивый импорт core.commands для избежания циклических зависимостей.
    Результат кешируется -импорт происходит ровно один раз.
    """
    from types import SimpleNamespace

    from vkflow.commands.parsing.converters import (
        Converter,
        UserConverter,
        GroupConverter,
        ReplyMessageConverter,
        _Greedy,
        ReplyMessage,
        ReplyUser,
    )

    from vkflow.commands.parsing.converter_cutters import (
        ConverterCutter,
        GreedyCutter,
        GreedyUserWithReplyCutter,
        ReplyMessageCutter,
        ReplyUserCutter,
        UserWithReplyCutter,
        GroupWithReplyCutter,
        MessageWithReplyCutter,
    )

    return SimpleNamespace(
        Converter=Converter,
        UserConverter=UserConverter,
        GroupConverter=GroupConverter,
        ReplyMessageConverter=ReplyMessageConverter,
        _Greedy=_Greedy,
        ReplyMessage=ReplyMessage,
        ReplyUser=ReplyUser,
        ConverterCutter=ConverterCutter,
        GreedyCutter=GreedyCutter,
        GreedyUserWithReplyCutter=GreedyUserWithReplyCutter,
        ReplyMessageCutter=ReplyMessageCutter,
        ReplyUserCutter=ReplyUserCutter,
        UserWithReplyCutter=UserWithReplyCutter,
        GroupWithReplyCutter=GroupWithReplyCutter,
        MessageWithReplyCutter=MessageWithReplyCutter,
    )


def resolve_typing(parameter: inspect.Parameter) -> CommandTextArgument:
    if isinstance(parameter.default, Argument):
        arg_settings = parameter.default
    elif parameter.default != parameter.empty:
        arg_settings = Argument(default=parameter.default)
    else:
        arg_settings = Argument()

    has_default = parameter.default != parameter.empty or arg_settings.default_factory is not None
    origin = typing.get_origin(parameter.annotation)

    ext = _core_imports()

    is_greedy = isinstance(parameter.annotation, ext._Greedy)

    if has_default and not is_greedy:
        args = typing.get_args(parameter.annotation) if origin else ()
        has_none = type(None) in args

        if not has_none:
            try:
                arg_annotation = parameter.annotation | None
            except TypeError:
                arg_annotation = parameter.annotation | None
        else:
            arg_annotation = parameter.annotation
    else:
        arg_annotation = parameter.annotation

    cutter = _resolve_cutter(
        arg_name=parameter.name,
        arg_annotation=arg_annotation,
        arg_settings=arg_settings,
        arg_kind=parameter.kind,
    )
    return CommandTextArgument(
        argument_name=parameter.name,
        argument_settings=arg_settings,
        cutter=cutter,
    )


_ATTACHMENT_TYPE_TO_NAME: dict[type, str] = {
    cls: name for name, cls in ATTACHMENT_TYPES.items() if name in ATTACHMENT_CUTTERS
}


def _is_attachment_type(annotation: typing.Any) -> bool:
    """Проверить, является ли аннотация типом вложения."""
    try:
        return annotation in _ATTACHMENT_TYPE_TO_NAME
    except TypeError:
        return False


def _get_attachment_cutter(annotation: type) -> AttachmentCutter | None:
    """Получить каттер для типа вложения."""
    att_name = _ATTACHMENT_TYPE_TO_NAME.get(annotation)
    if att_name is not None:
        return ATTACHMENT_CUTTERS[att_name]()
    return None


def _get_attachment_list_cutter(annotation: type) -> AttachmentListCutter | None:
    """Получить список-каттер для типа вложения."""
    att_name = _ATTACHMENT_TYPE_TO_NAME.get(annotation)
    if att_name is not None:
        return ATTACHMENT_LIST_CUTTERS[att_name]()
    return None


def _resolve_cutter(
    *,
    arg_name: str,
    arg_annotation: typing.Any,
    arg_settings: Argument,
    arg_kind,
    name_case: str | None = None,
    strict: bool | None = None,
    bool_values: BoolValues | None = None,
) -> Cutter:
    ext = _core_imports()

    origin = typing.get_origin(arg_annotation)

    if origin is typing.Annotated:
        args = typing.get_args(arg_annotation)
        base_type = args[0]
        metadata = args[1:]

        extracted_name_case = name_case
        extracted_strict = strict
        extracted_bool_values = None
        validators = []

        for meta in metadata:
            if isinstance(meta, NameCase):
                extracted_name_case = meta.case
            elif isinstance(meta, Strict):
                extracted_strict = meta.value
            elif isinstance(meta, BoolValues):
                extracted_bool_values = meta
            elif isinstance(meta, Flag):
                default = arg_settings.default if arg_settings.default is not None else False
                return FlagCutter(arg_name, default=default, short=meta.short)
            elif isinstance(meta, Named):
                flag_name = meta.name or arg_name
                inner_cutter = _resolve_cutter(
                    arg_name=arg_name,
                    arg_annotation=base_type,
                    arg_settings=arg_settings,
                    arg_kind=arg_kind,
                    name_case=name_case,
                    strict=strict,
                )
                default = arg_settings.default if arg_settings.default is not None else _NAMED_MISSING
                return NamedArgCutter(flag_name, inner_cutter, default=default)
            elif isinstance(meta, Validator):
                validators.append(meta)

        if isinstance(base_type, ext._Greedy):
            between = None
            other_validators = []
            for v in validators:
                if isinstance(v, Between):
                    between = v
                else:
                    other_validators.append(v)

            inner_type = base_type.converter

            if inner_type is User:
                cutter = ext.GreedyUserWithReplyCutter()
            else:
                inner_cutter = _resolve_cutter(
                    arg_name=arg_name,
                    arg_annotation=inner_type,
                    arg_settings=arg_settings,
                    arg_kind=arg_kind,
                    name_case=extracted_name_case,
                    strict=extracted_strict,
                )

                if between:
                    cutter = ext.GreedyCutter(inner_cutter, min_items=between.min, max_items=between.max)
                else:
                    cutter = ext.GreedyCutter(inner_cutter)

            if other_validators:
                return ValidatingCutter(cutter, other_validators)
            return cutter

        inner_cutter = _resolve_cutter(
            arg_name=arg_name,
            arg_annotation=base_type,
            arg_settings=arg_settings,
            arg_kind=arg_kind,
            name_case=extracted_name_case,
            strict=extracted_strict,
            bool_values=extracted_bool_values,
        )

        if validators:
            inner_cutter = ValidatingCutter(inner_cutter, validators)

        if extracted_strict is False:
            inner_cutter = OptionalCutter(
                inner_cutter,
                default=arg_settings.default,
                default_factory=arg_settings.default_factory,
            )

        return inner_cutter

    if inspect.isclass(arg_annotation):
        registered_cutter = get_registered_cutter(arg_annotation)

        if registered_cutter is not None:
            return registered_cutter()

    if isinstance(arg_annotation, ext._Greedy):
        inner_type = arg_annotation.converter

        if inner_type is User:
            return ext.GreedyUserWithReplyCutter()

        inner_cutter = _resolve_cutter(
            arg_name=arg_name,
            arg_annotation=inner_type,
            arg_settings=arg_settings,
            arg_kind=arg_kind,
            name_case=name_case,
            strict=strict,
        )

        return ext.GreedyCutter(inner_cutter)

    if inspect.isclass(arg_annotation) and issubclass(arg_annotation, ext.Converter):
        return ext.ConverterCutter(arg_annotation)

    if inspect.isclass(arg_annotation) and issubclass(arg_annotation, enum.Enum):
        return EnumCutter(arg_annotation)

    if _is_attachment_type(arg_annotation):
        cutter = _get_attachment_cutter(arg_annotation)

        if cutter is not None:
            return cutter

    match arg_annotation:
        case type() if arg_annotation is int:
            return IntegerCutter()
        case type() if arg_annotation is float:
            return FloatCutter()
        case type() if arg_annotation is bool:
            return BoolCutter(bool_values)
        case type() if arg_annotation is str:
            return StringCutter() if arg_kind == inspect.Parameter.KEYWORD_ONLY else WordCutter()

    args = typing.get_args(arg_annotation)

    match origin:
        case typing.Union | types.UnionType if type(None) in args:
            non_none_args = [arg for arg in args if arg is not type(None)]

            if len(non_none_args) == 1:
                return OptionalCutter(
                    _resolve_cutter(
                        arg_name=arg_name,
                        arg_annotation=non_none_args[0],
                        arg_settings=arg_settings,
                        arg_kind=arg_kind,
                        name_case=name_case,
                        strict=strict,
                    ),
                    default=arg_settings.default,
                    default_factory=arg_settings.default_factory,
                )

            typevar_cutters = (
                _resolve_cutter(
                    arg_name=arg_name,
                    arg_annotation=typevar,
                    arg_settings=arg_settings,
                    arg_kind=arg_kind,
                    name_case=name_case,
                    strict=strict,
                )
                for typevar in non_none_args
            )

            return OptionalCutter(
                UnionCutter(*typevar_cutters),
                default=arg_settings.default,
                default_factory=arg_settings.default_factory,
            )

        case _ if origin is typing.Union:
            typevar_cutters = (
                _resolve_cutter(
                    arg_name=arg_name,
                    arg_annotation=typevar,
                    arg_settings=arg_settings,
                    arg_kind=arg_kind,
                    name_case=name_case,
                    strict=strict,
                )
                for typevar in args
            )
            return UnionCutter(*typevar_cutters)

        case types.UnionType:
            typevar_cutters = (
                _resolve_cutter(
                    arg_name=arg_name,
                    arg_annotation=typevar,
                    arg_settings=arg_settings,
                    arg_kind=arg_kind,
                    name_case=name_case,
                    strict=strict,
                )
                for typevar in args
            )

            return UnionCutter(*typevar_cutters)

        case _ if origin is list:
            inner_type = args[0] if args else None

            if inner_type is not None and _is_attachment_type(inner_type):
                list_cutter = _get_attachment_list_cutter(inner_type)

                if list_cutter is not None:
                    return list_cutter

            typevar_cutter = _resolve_cutter(
                arg_name=arg_name,
                arg_annotation=args[0],
                arg_settings=arg_settings,
                arg_kind=arg_kind,
                name_case=name_case,
                strict=strict,
            )

            return MutableSequenceCutter(typevar_cutter)

        case _ if origin is tuple and Ellipsis in args:
            typevar_cutter = _resolve_cutter(
                arg_name=arg_name,
                arg_annotation=args[0],
                arg_settings=arg_settings,
                arg_kind=arg_kind,
                name_case=name_case,
                strict=strict,
            )

            return ImmutableSequenceCutter(typevar_cutter)

        case _ if origin is tuple:
            typevar_cutters = (
                _resolve_cutter(
                    arg_name=arg_name,
                    arg_annotation=typevar,
                    arg_settings=arg_settings,
                    arg_kind=arg_kind,
                    name_case=name_case,
                    strict=strict,
                )
                for typevar in args
            )

            return GroupCutter(*typevar_cutters)

        case _ if origin is set:
            typevar_cutter = _resolve_cutter(
                arg_name=arg_name,
                arg_annotation=args[0],
                arg_settings=arg_settings,
                arg_kind=arg_kind,
                name_case=name_case,
                strict=strict,
            )

            return UniqueMutableSequenceCutter(typevar_cutter)

        case _ if origin is frozenset:
            typevar_cutter = _resolve_cutter(
                arg_name=arg_name,
                arg_annotation=args[0],
                arg_settings=arg_settings,
                arg_kind=arg_kind,
                name_case=name_case,
                strict=strict,
            )

            return UniqueImmutableSequenceCutter(typevar_cutter)

        case _ if origin is dict:
            key_type = args[0] if args else str
            value_type = args[1] if len(args) > 1 else str

            if key_type is not str:
                raise TypeError(
                    f"dict keys must be str, got {key_type.__name__}. "
                    f"Use dict[str, {value_type.__name__ if hasattr(value_type, '__name__') else value_type}]."
                )

            value_cutter = _resolve_cutter(
                arg_name=arg_name,
                arg_annotation=value_type,
                arg_settings=arg_settings,
                arg_kind=arg_kind,
                name_case=name_case,
                strict=strict,
            )

            return DictCutter(value_cutter)

        case _ if origin is typing.Literal:
            escaped_args = []
            for arg in args:
                if isinstance(arg, str):
                    escaped_args.append(re.escape(arg) + r"(?=\s|$)")
                elif isinstance(arg, (int, float, bool)):
                    escaped_args.append(re.escape(str(arg)) + r"(?=\s|$)")
                else:
                    raise TypeError(
                        f"Unsupported Literal value type: {type(arg).__name__}. "
                        f"Only str, int, float, bool are supported."
                    )
            return LiteralCutter(*escaped_args)

        case _ if origin is Mention:
            return MentionCutter(args[0], name_case=name_case)

    if arg_annotation is User:
        return ext.UserWithReplyCutter(name_case=name_case)

    if arg_annotation is Group:
        return ext.GroupWithReplyCutter()

    if arg_annotation is ext.ReplyMessage:
        return ext.ReplyMessageCutter()

    if arg_annotation is ext.ReplyUser:
        return ext.ReplyUserCutter()

    from vkflow.models.message import Message

    if arg_annotation is Message:
        return ext.MessageWithReplyCutter()

    entity_types = {UserID, GroupID, PageID, User, Group, Page}

    if origin in entity_types or arg_annotation in entity_types:
        return EntityCutter(arg_annotation, name_case=name_case)

    if inspect.isclass(arg_annotation) and _is_auto_convertible(arg_annotation):
        return AutoConverterCutter(arg_annotation, strict=strict)

    raise TypeError(f"Can't resolve cutter from argument `{arg_name}`")


def _is_auto_convertible(cls: type) -> bool:
    """
    Check if a class can be used as an auto-converter.

    A class is auto-convertible if it has:
    1. An async classmethod `create(cls, ...)` - highest priority
    2. Or an `__init__(self, ...)` with appropriate parameters

    Parameters (ctx, value) are optional - the method can accept:
    - No parameters (besides self/cls)
    - Only ctx
    - Only value
    - Both ctx and value

    Built-in types and types without custom __init__ are not auto-convertible.
    """
    if hasattr(cls, "create"):
        create_method = cls.create

        if isinstance(inspect.getattr_static(cls, "create"), classmethod):
            func = getattr(create_method, "__func__", create_method)

            if inspect.iscoroutinefunction(func):
                return True

    try:
        if cls.__init__ is object.__init__:
            return False

        sig = inspect.signature(cls.__init__)
        params = list(sig.parameters.values())

        if params and params[0].name == "self":
            params = params[1:]

        if not params:
            return False

        param_names = {p.name for p in params}
        has_ctx_or_value = "ctx" in param_names or "value" in param_names

        positional_params = [
            p
            for p in params
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]

        return has_ctx_or_value or len(positional_params) >= 1

    except (ValueError, TypeError):
        return False
