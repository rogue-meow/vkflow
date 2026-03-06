from __future__ import annotations

import abc
import typing

import dataclasses

from vkflow.exceptions import BadArgumentError

if typing.TYPE_CHECKING:
    from vkflow.app.storages import NewMessage

T = typing.TypeVar("T")


class CommandTextArgument(typing.NamedTuple):
    argument_name: str
    cutter: Cutter
    argument_settings: Argument


@dataclasses.dataclass
class Argument:
    description: str | None = None
    default: typing.Any | None = None
    default_factory: typing.Callable[[], typing.Any] | None = None
    cutter_preferences: dict = dataclasses.field(default_factory=dict)

    def setup_cutter(self, **kwargs) -> Argument:
        if self.cutter_preferences:
            raise ValueError(
                "Cutter preferences have already been set. "
                "Cannot modify cutter preferences after initialization. "
                f"Current preferences: {self.cutter_preferences}"
            )

        self.cutter_preferences = kwargs
        return self


@dataclasses.dataclass
class CutterParsingResponse(typing.Generic[T]):
    parsed_part: T
    new_arguments_string: str
    extra: dict = dataclasses.field(default_factory=dict)


class Cutter(abc.ABC):
    @abc.abstractmethod
    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse: ...

    @abc.abstractmethod
    def gen_doc(self) -> str: ...

    def gen_message_doc(self) -> str:
        message = self.gen_doc()
        return html_list_to_message(message)

    def __or__(self, other: Cutter) -> Cutter:
        """
        Объединение каттеров через оператор |.

        Создаёт UnionCutter, который пробует каждый каттер по очереди.

        Пример:
            cutter = IntegerCutter() | FloatCutter()
            # Эквивалент UnionCutter(IntegerCutter(), FloatCutter())

            # Цепочка из нескольких каттеров:
            cutter = IntegerCutter() | FloatCutter() | WordCutter()
        """
        from vkflow.commands.parsing.cutters import UnionCutter

        left_cutters = list(other._typevars) if isinstance(other, UnionCutter) else [other]
        self_cutters = list(self._typevars) if isinstance(self, UnionCutter) else [self]
        return UnionCutter(*(self_cutters + left_cutters))


def cut_part_via_regex(
    regex: typing.Pattern,
    arguments_string: str,
    *,
    group: str | int = 0,
    factory: typing.Callable[[str], T] | None = None,
    error_description: str | None = None,
) -> CutterParsingResponse[T]:
    matched = regex.match(arguments_string)

    if matched:
        new_arguments_string = arguments_string[matched.end() :]
        parsed_part = matched.group(group)

        if factory is not None:
            parsed_part = factory(parsed_part)

        return CutterParsingResponse(parsed_part, new_arguments_string, extra={"match_object": matched})

    raise BadArgumentError(
        error_description or f"Regex pattern did not match. Expected format matching: {regex.pattern}"
    )


class InvalidArgumentConfig:
    prefix_sign: str = "💡"

    invalid_argument_template: str = (
        "{prefix_sign} Некорректное значение `{incorrect_value}`. Необходимо передать {cutter_description}"
    )

    laked_argument_template: str = "{prefix_sign} Необходимо передать {cutter_description}"

    prefix_sign_used: bool = True
    incorrect_value_used: bool = True
    cutter_description_used: bool = True

    async def on_invalid_argument(
        self,
        *,
        remain_string: str,
        ctx: NewMessage,
        argument: CommandTextArgument,
    ):
        prefix_sign = self.prefix_sign if self.prefix_sign_used else ""
        cutter_description = (
            (argument.argument_settings.description or argument.cutter.gen_message_doc())
            if self.cutter_description_used
            else ""
        )

        if remain_string == "":
            tip_response = self.laked_argument_template.format(
                prefix_sign=prefix_sign,
                cutter_description=cutter_description,
            )

        elif not self.incorrect_value_used:
            tip_response = self.invalid_argument_template.format(
                prefix_sign=prefix_sign,
                incorrect_value="",
                cutter_description=cutter_description,
            )

        else:
            incorrect_value = remain_string.split(maxsplit=1)[0]
            tip_response = self.invalid_argument_template.format(
                prefix_sign=prefix_sign,
                incorrect_value=incorrect_value,
                cutter_description=cutter_description,
            )

        await ctx.reply(tip_response)


def html_list_to_message(view: str) -> str:
    return (
        view.replace("<br>", "\n")
        .replace("</ol>", "")
        .replace("<ol><li>", "\n- ")
        .replace("</li>\n<li>", "\n- ")
        .replace("</li>", "")
        .replace("<code>", "`")
        .replace("</code>", "`")
    )
