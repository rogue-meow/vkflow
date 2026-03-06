"""
Реализации каттеров для системы конвертеров.
Внутренний модуль -связывает конвертеры с системой каттеров.
"""

from __future__ import annotations

import contextlib
import typing
import inspect

from vkflow.commands.parsing.cutter import Cutter, CutterParsingResponse
from vkflow.exceptions import BadArgumentError

from vkflow.commands.context import Context

if typing.TYPE_CHECKING:
    from vkflow.app.storages import NewMessage
    from vkflow.commands.parsing.converters import Converter


__all__ = (
    "ConverterCutter",
    "GreedyCutter",
    "GreedyUserWithReplyCutter",
    "GroupWithReplyCutter",
    "MessageWithReplyCutter",
    "ReplyMessageCutter",
    "ReplyUserCutter",
    "UserWithReplyCutter",
)


async def _ensure_extended(ctx) -> None:
    """Убедиться, что сообщение не обрезано (is_cropped), при необходимости загрузить полное."""
    if hasattr(ctx, "msg"):
        msg = ctx.msg
        if msg.is_cropped and hasattr(ctx, "api"):
            await msg.extend(ctx.api)


def _get_reply_message(ctx):
    """Получить reply_message из контекста, если есть."""
    if hasattr(ctx, "msg") and ctx.msg.reply_message is not None:
        return ctx.msg.reply_message
    return None


def _get_or_create_context(ctx) -> Context:
    """
    Получить кэшированный Context или создать новый.
    Кэширует в argument_processing_payload для переиспользования
    между несколькими конвертерами в одном цикле парсинга.
    """
    if hasattr(ctx, "argument_processing_payload"):
        cached = ctx.argument_processing_payload.converter_context
        if cached is not None:
            return cached

    command_ctx = Context.from_message(ctx)

    if hasattr(ctx, "argument_processing_payload"):
        ctx.argument_processing_payload.converter_context = command_ctx

    return command_ctx


def _extract_argument(text: str) -> tuple[str, str]:
    """
    Извлечь первый аргумент из текста с учётом:
    - VK-упоминаний с пробелами: [id123|Имя С Пробелами]
    - Строк в кавычках: "hello world" или 'hello world'

    Returns:
        Кортеж (аргумент, оставшийся_текст)
    """
    text = text.lstrip()
    if not text:
        return "", ""

    if text[0] in ('"', "'"):
        quote = text[0]
        end = text.find(quote, 1)
        if end != -1:
            argument = text[1:end]
            remaining = text[end + 1 :].lstrip()
            return argument, remaining

    if text.startswith("["):
        bracket_end = text.find("]")
        if bracket_end != -1:
            argument = text[: bracket_end + 1]
            remaining = text[bracket_end + 1 :].lstrip()
            return argument, remaining

    parts = text.split(maxsplit=1)
    argument = parts[0]
    remaining = parts[1] if len(parts) > 1 else ""
    return argument, remaining


class ConverterCutter(Cutter):
    """
    Каттер, использующий Converter для преобразования аргументов.

    Связующее звено между системой конвертеров (работает с Context)
    и системой каттеров (работает с NewMessage).
    """

    def __init__(self, converter: type[Converter] | Converter):
        """
        Инициализация каттера-конвертера.

        Args:
            converter: Класс или экземпляр конвертера для использования
        """
        if inspect.isclass(converter):
            self.converter = converter()
        else:
            self.converter = converter

        self.converter_class = converter if inspect.isclass(converter) else converter.__class__

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        """
        Вырезать и преобразовать следующий аргумент.

        Args:
            ctx: Контекст сообщения
            arguments_string: Оставшаяся строка аргументов

        Returns:
            CutterParsingResponse с преобразованным значением

        Raises:
            BadArgumentError: Если преобразование не удалось
        """
        argument, remaining = _extract_argument(arguments_string)

        if not argument:
            raise BadArgumentError("Не предоставлен аргумент для преобразования")

        command_ctx = _get_or_create_context(ctx)

        try:
            result = self.converter.convert(command_ctx, argument)
            if inspect.isawaitable(result):
                converted = await result
            else:
                converted = result
        except Exception as e:
            raise BadArgumentError(f"Ошибка преобразования: {e}") from e

        return CutterParsingResponse(parsed_part=converted, new_arguments_string=remaining)

    def gen_doc(self) -> str:
        """
        Сгенерировать документацию для этого каттера.

        Returns:
            Строка документации
        """
        converter_name = self.converter_class.__name__

        if converter_name.endswith("Converter"):
            converter_name = converter_name[:-9]

        doc = inspect.getdoc(self.converter_class)

        if doc:
            first_line = doc.split("\n")[0]

            return f"{converter_name}: {first_line}"
        return f"<code>{converter_name}</code>"


class GreedyCutter(Cutter):
    """
    Каттер, жадно потребляющий аргументы с помощью любого каттера.

    Продолжает преобразовывать аргументы, пока конвертация не завершится ошибкой,
    аргументы не закончатся или не будет достигнут лимит max_items.
    Возвращает список преобразованных значений.

    Поддерживает ограничения min/max через валидатор Between в синтаксисе Annotated:
        Annotated[Greedy[str], Between(2, 10)]
    """

    def __init__(self, inner_cutter: Cutter, *, min_items: int = 0, max_items: int | None = None):
        """
        Инициализация жадного каттера.

        Args:
            inner_cutter: Каттер для жадного использования (может быть любым типом Cutter)
            min_items: Минимальное количество элементов (по умолчанию: 0)
            max_items: Максимальное количество элементов (по умолчанию: None = без ограничений)
        """
        self.inner_cutter = inner_cutter
        self.min_items = min_items
        self.max_items = max_items

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        """
        Жадно вырезать и преобразовать аргументы.

        Args:
            ctx: Контекст сообщения
            arguments_string: Оставшаяся строка аргументов

        Returns:
            CutterParsingResponse со списком преобразованных значений

        Raises:
            BadArgumentError: Если ограничение min_items не выполнено
        """
        converted_values = []
        remaining = arguments_string.lstrip()

        while remaining:
            if self.max_items is not None and len(converted_values) >= self.max_items:
                break

            try:
                result = await self.inner_cutter.cut_part(ctx, remaining)
                converted_values.append(result.parsed_part)
                remaining = result.new_arguments_string.lstrip()
            except BadArgumentError:
                break

        if len(converted_values) < self.min_items:
            raise BadArgumentError(f"Требуется минимум {self.min_items} элементов")

        return CutterParsingResponse(parsed_part=converted_values, new_arguments_string=remaining)

    def gen_doc(self) -> str:
        """
        Сгенерировать документацию для этого каттера.

        Returns:
            Строка документации
        """
        inner_doc = self.inner_cutter.gen_doc()
        constraints = []

        if self.min_items > 0:
            constraints.append(f"мин. {self.min_items}")
        if self.max_items is not None:
            constraints.append(f"макс. {self.max_items}")

        if constraints:
            return f"Greedy[{inner_doc}] ({', '.join(constraints)})"
        return f"Greedy[{inner_doc}]"


class GreedyUserWithReplyCutter(Cutter):
    """
    Жадный каттер для User, который также проверяет сообщение-ответ.

    Сначала жадно потребляет аргументы User из текста.
    Если пользователи не найдены в тексте, использует автора сообщения-ответа.
    """

    def __init__(self):
        from vkflow.commands.parsing.converters import UserConverter

        self._converter = UserConverter()

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        """
        Жадно получить пользователей из текста; если не найдено -использовать автора ответа.
        """
        from vkflow.models.page import User

        converted_values = []
        remaining = arguments_string.lstrip()
        command_ctx = _get_or_create_context(ctx)

        while remaining:
            argument, next_remaining = _extract_argument(remaining)
            if not argument:
                break

            try:
                converted = await self._converter.convert(command_ctx, argument)
                converted_values.append(converted)
                remaining = next_remaining
            except Exception:
                break

        if not converted_values:
            await _ensure_extended(ctx)
            reply = _get_reply_message(ctx)
            if reply is not None:
                from_id = reply.from_id
                if from_id and from_id > 0:
                    try:
                        user = await User.fetch_one(ctx.api, from_id)
                        converted_values.append(user)
                    except Exception:
                        pass

        return CutterParsingResponse(parsed_part=converted_values, new_arguments_string=remaining)

    def gen_doc(self) -> str:
        return "Greedy[User] (текст или ответ)"


class ReplyMessageCutter(Cutter):
    """
    Каттер, извлекающий сообщение-ответ из контекста.

    Этот каттер НЕ потребляет текстовые аргументы -он извлекает
    сообщение, на которое был дан ответ, из контекста.
    """

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        """
        Извлечь сообщение-ответ из контекста.

        Args:
            ctx: Контекст сообщения
            arguments_string: Оставшаяся строка аргументов (не потребляется)

        Returns:
            CutterParsingResponse с Message или None
        """
        await _ensure_extended(ctx)
        reply_message = _get_reply_message(ctx)

        return CutterParsingResponse(parsed_part=reply_message, new_arguments_string=arguments_string)

    def gen_doc(self) -> str:
        return "Message (ответ)"


class ReplyUserCutter(Cutter):
    """
    Каттер, извлекающий пользователя из сообщения-ответа.

    Этот каттер НЕ потребляет текстовые аргументы -он извлекает
    пользователя, отправившего сообщение, на которое был дан ответ.
    """

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        """
        Извлечь пользователя из сообщения-ответа.

        Args:
            ctx: Контекст сообщения
            arguments_string: Оставшаяся строка аргументов (не потребляется)

        Returns:
            CutterParsingResponse с User или None
        """
        from vkflow.models.page import User

        reply_user = None
        await _ensure_extended(ctx)
        reply = _get_reply_message(ctx)

        if reply is not None:
            from_id = reply.from_id
            if from_id and from_id > 0:
                with contextlib.suppress(Exception):
                    reply_user = await User.fetch_one(ctx.api, from_id)

        return CutterParsingResponse(parsed_part=reply_user, new_arguments_string=arguments_string)

    def gen_doc(self) -> str:
        return "User (из ответа)"


class UserWithReplyCutter(Cutter):
    """
    Каттер, который сначала пытается получить User из текстового аргумента,
    а затем использует автора сообщения-ответа (только для пользователей, не для сообществ).

    Позволяет: `/cmd @user` ИЛИ `/cmd` (ответ на чьё-либо сообщение)

    Вызывает BadArgumentError если:
    - Текстовый аргумент не является валидным пользователем
    - Нет сообщения-ответа или ответ от сообщества (from_id < 0)
    """

    def __init__(self, *, name_case: str | None = None):
        from vkflow.commands.parsing.converters import UserConverter

        self._converter = UserConverter()
        self._name_case = name_case

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        """
        Попытаться получить User из текста, при неудаче -из автора ответа.
        Вызывает BadArgumentError, если пользователь не найден.
        """
        from vkflow.models.page import User

        argument, remaining = _extract_argument(arguments_string)

        if argument:
            command_ctx = _get_or_create_context(ctx)

            try:
                converted = await self._converter.convert(command_ctx, argument)
                if self._name_case and isinstance(converted, User):
                    converted = await User.fetch_one(ctx.api, converted.id, name_case=self._name_case)
                return CutterParsingResponse(parsed_part=converted, new_arguments_string=remaining)
            except Exception:
                raise BadArgumentError(self.gen_doc()) from None

        await _ensure_extended(ctx)
        reply = _get_reply_message(ctx)

        if reply is not None:
            from_id = reply.from_id
            if from_id and from_id > 0:
                try:
                    user = await User.fetch_one(ctx.api, from_id, name_case=self._name_case)
                    return CutterParsingResponse(parsed_part=user, new_arguments_string=arguments_string)
                except Exception:
                    pass

        raise BadArgumentError(self.gen_doc())

    def gen_doc(self) -> str:
        return "User (текст или ответ)"


class GroupWithReplyCutter(Cutter):
    """
    Каттер, который сначала пытается получить Group из текстового аргумента,
    а затем использует автора сообщения-ответа (только для сообществ, не для пользователей).

    Позволяет: `/cmd @group` ИЛИ `/cmd` (ответ на сообщение сообщества)

    Вызывает BadArgumentError если:
    - Текстовый аргумент не является валидным сообществом
    - Нет сообщения-ответа или ответ от пользователя (from_id > 0)
    """

    def __init__(self):
        from vkflow.commands.parsing.converters import GroupConverter

        self._converter = GroupConverter()

    async def cut_part(self, ctx: NewMessage, arguments_string: str) -> CutterParsingResponse:
        """
        Попытаться получить Group из текста, при неудаче -из автора ответа (если сообщество).
        Вызывает BadArgumentError, если сообщество не найдено.
        """
        from vkflow.models.page import Group

        argument, remaining = _extract_argument(arguments_string)

        if argument:
            command_ctx = _get_or_create_context(ctx)

            try:
                converted = await self._converter.convert(command_ctx, argument)
                return CutterParsingResponse(parsed_part=converted, new_arguments_string=remaining)
            except Exception:
                raise BadArgumentError(self.gen_doc()) from None

        await _ensure_extended(ctx)
        reply = _get_reply_message(ctx)

        if reply is not None:
            from_id = reply.from_id
            if from_id and from_id < 0:
                try:
                    group = await Group.fetch_one(ctx.api, abs(from_id))
                    return CutterParsingResponse(parsed_part=group, new_arguments_string=arguments_string)
                except Exception:
                    pass

        raise BadArgumentError(self.gen_doc())

    def gen_doc(self) -> str:
        return "Group (текст или ответ)"


MessageWithReplyCutter = ReplyMessageCutter
