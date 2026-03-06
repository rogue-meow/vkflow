"""
Дополнительные исключения
"""

from __future__ import annotations

import dataclasses
import typing


if typing.TYPE_CHECKING:
    ExceptionsStorage: typing.TypeAlias = dict[int, type["APIError"]]
    ParamsList: typing.TypeAlias = list["_ParamsScheme"]
    ExtraFields: typing.TypeAlias = dict[str, typing.Any]

exceptions_storage: ExceptionsStorage = {}


class _ParamsScheme(typing.TypedDict):
    """
    Структура параметров, возвращаемых
    при некорректном обращении к API
    """

    key: str
    value: str


_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _format_api_error(
    status_code: int,
    description: str,
    params: ParamsList,
    extra_fields: ExtraFields,
) -> str:
    lines = [f"[{_RED}{status_code}{_RESET}] {description}"]
    lines.extend(f"# {_YELLOW}{param['key']}{_RESET} = {_CYAN}{param['value']}{_RESET}" for param in params)
    if extra_fields:
        lines.append(f"{_BOLD}Extra fields:{_RESET} {extra_fields}")
    return "\n".join(lines)


@dataclasses.dataclass
class APIError(Exception):
    """
    Исключение, поднимаемое при некорректном вызове API запроса.

    Arguments:
        description: Описание ошибки (из API ответа)
        status_code: Статус-код ошибки (из API ответа)
        request_params: Параметры запроса, в ответ на который пришла ошибка
        extra_fields: Дополнительные поля (из API ответа)
    """

    description: str
    status_code: int
    request_params: ParamsList
    extra_fields: ExtraFields

    def __class_getitem__(cls, code: int | tuple[int, ...]) -> type[APIError] | tuple[type[APIError], ...]:
        """
        Позволяет получить класс исключения по коду ошибки API.

        Примеры использования:
            # Перехват одной ошибки
            try:
                await api.messages.send(...)
            except APIError[901]:
                print("Пользователь запретил сообщения")

            # Перехват нескольких ошибок
            try:
                await api.messages.send(...)
            except APIError[900, 901, 902]:
                print("Не удалось отправить сообщение")

        Arguments:
            code: Код ошибки или кортеж кодов ошибок

        Returns:
            Класс исключения для одиночного кода или
            кортеж классов для нескольких кодов
        """
        if isinstance(code, int):
            codes = (code,)
            single_code = True
        elif isinstance(code, tuple):
            codes = code
            single_code = False
        else:
            raise TypeError(f"APIError[] принимает int или tuple[int, ...], получен {type(code).__name__}")

        result_classes = []
        for error_code in codes:
            if error_code in exceptions_storage:
                result_classes.append(exceptions_storage[error_code])
            else:
                new_class = type(f"APIError{error_code}", (APIError,), {"error_code": error_code})
                new_class = typing.cast("type[APIError]", new_class)
                exceptions_storage[error_code] = new_class
                result_classes.append(new_class)

        if single_code:
            return result_classes[0]
        return tuple(result_classes)

    def __str__(self) -> str:
        return _format_api_error(
            self.status_code,
            self.description,
            self.request_params,
            self.extra_fields,
        )


VkApiError = APIError


if typing.TYPE_CHECKING:
    from vkflow.commands.parsing.cutter import CommandTextArgument
    from vkflow.app.storages import NewMessage


@dataclasses.dataclass
class BadArgumentError(Exception):
    description: str


@dataclasses.dataclass
class ArgumentParsingError(Exception):
    """
    Ошибка, возникающая в strict mode при неудачном парсинге аргументов.

    Атрибуты:
        argument: Аргумент, парсинг которого не удался
        remain_string: Оставшаяся необработанная строка
        ctx: Контекст сообщения
        original_error: Исходная BadArgumentError (если есть)
        reason: Человекочитаемое описание ошибки
        parsed_arguments: Словарь уже успешно распарсенных аргументов
    """

    argument: CommandTextArgument | None
    remain_string: str
    ctx: NewMessage
    original_error: BadArgumentError | None = None
    reason: str = ""
    parsed_arguments: dict[str, typing.Any] = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        if not self.reason:
            if self.original_error:
                self.reason = self.original_error.description
            elif self.argument:
                self.reason = f"Ошибка парсинга аргумента '{self.argument.argument_name}'"
            else:
                self.reason = "Ошибка парсинга аргументов"

    def __str__(self) -> str:
        parts = [self.reason]
        if self.parsed_arguments:
            parsed_names = ", ".join(self.parsed_arguments.keys())
            parts.append(f"(успешно распарсено: {parsed_names})")
        return " ".join(parts)


class CommandError(Exception):
    """Базовый класс для всех ошибок, связанных с выполнением команд."""


class StopCurrentHandlingError(Exception): ...


StopCurrentHandling = StopCurrentHandlingError


class StopStateHandlingError(Exception):
    def __init__(self, value: typing.Any = None, **payload):
        self.payload = value or payload


StopStateHandling = StopStateHandlingError


class EventTimeoutError(Exception):
    def __init__(self, event_name: str, timeout: float):
        self.event_name = event_name
        self.timeout = timeout

        super().__init__(f"Waiting for event '{event_name}' timed out after {timeout} seconds")


EventTimeout = EventTimeoutError
