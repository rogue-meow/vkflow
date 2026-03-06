"""
Система конвертеров для vkflow.commands

Этот модуль предоставляет:
- Базовый класс Converter для создания пользовательских конвертеров
- Встроенные конвертеры: UserConverter, GroupConverter, MentionConverter
- Специальные типы: Greedy[T] для жадного преобразования
- Интеграция с Union и Optional типами

Использование:
    from vkflow import commands
    from vkflow import User

    class MyCog(commands.Cog):
        @commands.command()
        async def userinfo(self, ctx: commands.Context, user: User):
            await ctx.send(f"User: {user.fullname}")

        @commands.command()
        async def multi(self, ctx: commands.Context, users: commands.Greedy[User]):
            await ctx.send(f"Got {len(users)} users")
"""

from __future__ import annotations

import abc
import re
import typing

if typing.TYPE_CHECKING:
    from vkflow.commands.context import Context
    from vkflow.models.page import User, Group

__all__ = (
    "ConversionError",
    "Converter",
    "Greedy",
    "GroupConverter",
    "MentionConverter",
    "ReplyMessage",
    "ReplyMessageConverter",
    "ReplyUser",
    "UserConverter",
)

T = typing.TypeVar("T")


class ConversionError(Exception):
    """
    Исключение, возникающее при неудачной конвертации аргумента.

    Атрибуты:
        converter: Конвертер, в котором произошла ошибка
        original: Исходное значение, которое не удалось преобразовать
        message: Сообщение об ошибке
    """

    def __init__(self, converter: type[Converter], original: str, message: str | None = None):
        self.converter = converter
        self.original = original

        if message is None:
            message = f'Не удалось преобразовать "{original}" в {converter.__name__}'

        super().__init__(message)


class Converter(abc.ABC):
    """
    Базовый класс для создания пользовательских конвертеров.

    Конвертеры используются для преобразования строковых аргументов в объекты Python.
    Наследуйтесь от этого класса и реализуйте метод convert для создания своих конвертеров.

    Пример:
        class ColorConverter(commands.Converter):
            async def convert(self, ctx: commands.Context, argument: str) -> str:
                if argument.startswith('#') and len(argument) == 7:
                    return argument
                raise commands.ConversionError(
                    self.__class__,
                    argument,
                    "Ожидается цвет в формате #RRGGBB"
                )

        @commands.command()
        async def setcolor(ctx: commands.Context, color: ColorConverter):
            await ctx.send(f"Цвет установлен: {color}")
    """

    @abc.abstractmethod
    def convert(self, ctx: Context, argument: str) -> typing.Any:
        """
        Преобразовать строковый аргумент в нужный тип.

        Может быть как sync, так и async методом.
        Async конвертеры определяются через `async def convert(...)`.

        Args:
            ctx: Контекст вызова
            argument: Строковый аргумент для преобразования

        Returns:
            Преобразованное значение

        Raises:
            ConversionError: Если преобразование не удалось
        """
        raise NotImplementedError("Подклассы должны реализовать этот метод")


class UserConverter(Converter):
    """
    Конвертер, преобразующий упоминания, ID или короткие имена пользователей в объекты User.

    Принимает:
        - Упоминания пользователей: [id123|Имя] или @id123
        - ID пользователей: 123
        - Короткие имена: durov

    Пример:
        @commands.command()
        async def userinfo(ctx: commands.Context, user: vkflow.User):
            await ctx.send(f"Пользователь: {user.fullname}")
    """

    MENTION_PATTERN = re.compile(r"\[id(\d+)\|?.*?\]")
    ID_PATTERN = re.compile(r"@?id(\d+)|^(\d+)$")

    async def convert(self, ctx: Context, argument: str) -> User:
        """
        Преобразовать аргумент в объект User.

        Args:
            ctx: Контекст команды
            argument: Строка для преобразования (упоминание, ID или короткое имя)

        Returns:
            Объект User

        Raises:
            ConversionError: Если пользователь не найден
        """
        from vkflow.models.page import User

        user_id = None

        mention_match = self.MENTION_PATTERN.match(argument)

        if mention_match:
            user_id = int(mention_match.group(1))
        else:
            id_match = self.ID_PATTERN.match(argument)

            if id_match:
                user_id = int(id_match.group(1) or id_match.group(2))

        if user_id:
            try:
                return await User.fetch_one(ctx.api, user_id)

            except Exception as e:
                raise ConversionError(
                    self.__class__, argument, f"Не удалось получить пользователя с ID {user_id}: {e}"
                ) from e

        try:
            return await User.fetch_one(ctx.api, argument)

        except Exception:
            raise ConversionError(
                self.__class__, argument, f'Пользователь "{argument}" не найден'
            ) from None


class GroupConverter(Converter):
    """
    Конвертер, преобразующий упоминания, ID или короткие имена сообществ в объекты Group.

    Принимает:
        - Упоминания сообществ: [club123|Название] или @club123
        - ID сообществ: 123
        - Короткие имена: apiclub

    Пример:
        @commands.command()
        async def groupinfo(ctx: commands.Context, group: vkflow.Group):
            await ctx.send(f"Сообщество: {group.fullname}")
    """

    MENTION_PATTERN = re.compile(r"\[(?:club|public)(\d+)\|?.*?\]")
    ID_PATTERN = re.compile(r"@?(?:club|public)?(\d+)")

    async def convert(self, ctx: Context, argument: str) -> Group:
        """
        Преобразовать аргумент в объект Group.

        Args:
            ctx: Контекст команды
            argument: Строка для преобразования (упоминание, ID или короткое имя)

        Returns:
            Объект Group

        Raises:
            ConversionError: Если сообщество не найдено
        """
        from vkflow.models.page import Group

        group_id = None

        mention_match = self.MENTION_PATTERN.match(argument)

        if mention_match:
            group_id = int(mention_match.group(1))
        else:
            id_match = self.ID_PATTERN.match(argument)

            if id_match:
                group_id = int(id_match.group(1))

        if group_id:
            try:
                return await Group.fetch_one(ctx.api, group_id)
            except Exception as e:
                raise ConversionError(
                    self.__class__, argument, f"Не удалось получить сообщество с ID {group_id}: {e}"
                ) from e

        try:
            return await Group.fetch_one(ctx.api, argument)

        except Exception:
            raise ConversionError(self.__class__, argument, f'Сообщество "{argument}" не найдено') from None


class MentionConverter(Converter):
    """
    Конвертер, извлекающий ID пользователя или сообщества из упоминаний.

    Принимает:
        - Упоминания пользователей: [id123|Имя]
        - Упоминания сообществ: [club123|Название], [public123|Название]

    Возвращает:
        Кортеж (entity_type, entity_id), где entity_type -'user' или 'group'

    Пример:
        @commands.command()
        async def mention(ctx: commands.Context, mention: MentionConverter):
            entity_type, entity_id = mention
            await ctx.send(f"Упомянут {entity_type} с ID {entity_id}")
    """

    MENTION_PATTERN = re.compile(r"\[(id|club|public)(\d+)\|?.*?\]")

    async def convert(self, ctx: Context, argument: str) -> tuple[str, int]:
        """
        Преобразовать упоминание в кортеж (entity_type, entity_id).

        Args:
            ctx: Контекст команды
            argument: Строка с упоминанием

        Returns:
            Кортеж (entity_type, entity_id)

        Raises:
            ConversionError: Если упоминание невалидно
        """
        match = self.MENTION_PATTERN.match(argument)
        if not match:
            raise ConversionError(
                self.__class__,
                argument,
                "Ожидается упоминание в формате [id123|Имя] или [club123|Название]",
            )

        prefix = match.group(1)
        entity_id = int(match.group(2))

        entity_type = "user" if prefix == "id" else "group"

        return (entity_type, entity_id)


class ReplyMessageConverter(Converter):
    """
    Конвертер, извлекающий сообщение-ответ из текущего сообщения.

    Этот конвертер НЕ потребляет текстовые аргументы. Вместо этого он
    извлекает сообщение, на которое отвечает текущее сообщение (если есть).

    Возвращает:
        Объект Message ответного сообщения, или None если ответа нет

    Пример:
        from vkflow import Message
        from vkflow import commands

        @commands.command()
        async def quote(ctx: commands.Context, reply: Message | None = None):
            if reply is None:
                await ctx.send("Ответьте на сообщение, чтобы процитировать его!")
            else:
                await ctx.send(f"Цитата: {reply.text}")

        @commands.command()
        async def quote(ctx: commands.Context, reply: Message):
            if reply:
                await ctx.send(f"Вы отвечаете на: {reply.text}")
    """

    async def convert(self, ctx: Context, argument: str) -> typing.Any:
        """
        Извлечь сообщение-ответ из контекста.

        Примечание: этот конвертер игнорирует параметр argument, так как
        извлекает данные из контекста сообщения, а не из текстовых аргументов.

        Args:
            ctx: Контекст команды
            argument: Игнорируется

        Returns:
            Объект Message ответного сообщения, или None если ответа нет
        """
        from vkflow.models.message import Message

        if hasattr(ctx, "message") and hasattr(ctx.message, "msg"):
            msg = ctx.message.msg

            if msg.is_cropped and hasattr(ctx, "api"):
                await msg.extend(ctx.api)

            if msg.reply_message is not None:
                return Message(msg.reply_message)

        return None


if typing.TYPE_CHECKING:
    Greedy = list

else:

    class _GreedyMeta(type):
        """Метакласс для Greedy, включающий синтаксис подписки."""

        def __getitem__(cls, item: type[T]) -> _Greedy[T]:
            """Включить синтаксис Greedy[T]."""
            return _Greedy(item)

    class Greedy(metaclass=_GreedyMeta):
        """
        Специальная аннотация типа для жадного потребления аргументов.

        При использовании с типом конвертера жадно потребляет аргументы этого типа,
        пока конвертация не завершится ошибкой или аргументы не закончатся.

        Жадный конвертер потребляет максимальное количество аргументов, возвращая
        список преобразованных значений. Если ни одно значение не удалось преобразовать,
        возвращает пустой список.

        Greedy можно использовать в любой позиции списка аргументов.
        Если он не последний, потребление останавливается при неудаче конвертации
        следующего аргумента, позволяя последующим аргументам быть распознанными нормально.

        Это полезно для команд вроде массового бана с причиной в конце:
            !ban @user1 @user2 @user3 спам

        Для поддержки IDE/проверки типов Greedy[T] типизирован как list[T],
        так что автодополнение для методов списка и итерации работает корректно.

        Пример:
            @commands.command()
            async def ban(ctx: commands.Context, users: commands.Greedy[vkflow.User], *, reason: str = "Без причины"):
                for user in users:
                    await ban_user(user)
                await ctx.send(f"Забанено {len(users)} пользователей. Причина: {reason}")

            @commands.command()
            async def greet(ctx: commands.Context, users: commands.Greedy[vkflow.User] = []):
                if not users:
                    await ctx.send("Пользователи не указаны!")
                else:
                    for user in users:
                        await ctx.send(f"Привет, {user.first_name}!")
        """

        __slots__ = ()

        def __class_getitem__(cls, item: type[T]) -> _Greedy[T]:
            """Поддержка как Greedy[T], так и прямого создания экземпляра."""
            return _Greedy(item)


class _Greedy(typing.Generic[T]):
    """
    Внутреннее представление Greedy[T].

    В рантайме это то, что создаёт Greedy[T].
    Результат парсинга Greedy[T] всегда list[T].
    """

    __slots__ = ("converter", "default")

    def __init__(self, converter: type[T], default: list[T] | None = None):
        """
        Инициализация жадного конвертера.

        Args:
            converter: Тип для жадного преобразования
            default: Значение по умолчанию, если ни один аргумент не подошёл (по умолчанию пустой список)
        """
        self.converter = converter
        self.default = default if default is not None else []

    def __repr__(self) -> str:
        converter_name = getattr(self.converter, "__name__", repr(self.converter))
        return f"Greedy[{converter_name}]"

    def __or__(self, other):
        """
        Поддержка синтаксиса Greedy[T] | None (хотя обычно не требуется).

        Поскольку Greedy всегда возвращает список (возможно пустой), возвращает self.
        """
        if other is type(None):
            return self
        return typing.Union[self, other]  # noqa: UP007

    def __ror__(self, other):
        """Поддержка синтаксиса None | Greedy[T]."""
        return self.__or__(other)


class _ReplyMessageMeta(type):
    """Метакласс для аннотации типа ReplyMessage."""


class ReplyMessage(metaclass=_ReplyMessageMeta):
    """
    Специальная аннотация типа для извлечения сообщения-ответа.

    При использовании как аннотация типа извлекает сообщение, на которое
    отвечает текущее сообщение. НЕ потребляет текстовые аргументы.

    Возвращает:
        Объект Message, если есть ответ на сообщение, иначе None

    Пример:
        from vkflow.commands import ReplyMessage

        @commands.command()
        async def quote(ctx: Context, reply: ReplyMessage):
            if reply is None:
                await ctx.send("Ответьте на сообщение!")
            else:
                await ctx.send(f"Цитата: {reply.text}")

        @commands.command()
        async def quote(ctx: Context, reply: ReplyMessage | None = None):
            if reply:
                await ctx.send(f"Цитата: {reply.text}")
    """

    __slots__ = ()


class _ReplyUserMeta(type):
    """Метакласс для аннотации типа ReplyUser."""


class ReplyUser(metaclass=_ReplyUserMeta):
    """
    Специальная аннотация типа для извлечения пользователя из сообщения-ответа.

    При использовании как аннотация типа извлекает объект User отправителя
    сообщения, на которое отвечает текущее сообщение.
    НЕ потребляет текстовые аргументы.

    Возвращает:
        Объект User, если есть ответ на сообщение пользователя, иначе None

    Пример:
        from vkflow.commands import ReplyUser

        @commands.command()
        async def info(ctx: Context, user: ReplyUser):
            if user is None:
                await ctx.send("Ответьте на чьё-нибудь сообщение!")
            else:
                await ctx.send(f"Пользователь: {user.first_name} {user.last_name}")

        @commands.command()
        async def info(ctx: Context, user: ReplyUser | None = None):
            if user:
                await ctx.send(f"ID пользователя: {user.id}")
    """

    __slots__ = ()
