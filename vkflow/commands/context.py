"""
Класс Context для команд
"""

from __future__ import annotations

import re
import typing
import dataclasses

if typing.TYPE_CHECKING:
    from vkflow.api import API
    from vkflow.app.bot import App, Bot
    from vkflow.app.storages import NewEvent, NewMessage
    from vkflow.ui.view import View
    from vkflow.models.message import (
        Message,
        SentMessage,
        SingleAttachment,
        AttachmentsList,
    )
    from vkflow.models.page import Page
    from vkflow.models.attachment import Document, Photo
    from vkflow.models.chat import Chat
    from .core import Command, Group

    SenderTypevar = typing.TypeVar("SenderTypevar", bound=Page)


__all__ = ("Context",)


@dataclasses.dataclass
class Context:
    """
    Контекст, в котором вызывается команда.

    Этот класс предоставляет удобный доступ к часто используемым
    атрибутам и методам при обработке команд.

    Атрибуты:
        message: Экземпляр NewMessage, вызвавший команду
        bot: Экземпляр Bot
        app: Экземпляр App
        command: Вызываемая команда (Command)
        prefix: Префикс, использованный для вызова команды
        invoked_with: Имя/алиас, использованный для вызова команды

    Пример:
        @commands.command()
        async def hello(ctx: commands.Context):
            await ctx.send(f"Hello, {ctx.author}!")

        @commands.command()
        async def userinfo(ctx: commands.Context):
            user = await ctx.fetch_sender(User)
            await ctx.send(f"User: {user.first_name}")
    """

    _message: NewMessage
    command: Command | None = None
    prefix: str | None = None
    invoked_with: str | None = None
    invoked_subcommand: Command | None = None
    _cached_chat: Chat | None = dataclasses.field(default=None, init=False, repr=False)
    _chat_resolved: bool = dataclasses.field(default=False, init=False, repr=False)

    @classmethod
    def from_message(
        cls,
        message: NewMessage,
        *,
        command: Command | None = None,
        prefix: str | None = None,
        invoked_with: str | None = None,
    ) -> Context:
        """
        Создать Context из NewMessage.

        Аргументы:
            message: Экземпляр NewMessage
            command: Вызываемая команда (Command)
            prefix: Использованный префикс
            invoked_with: Использованный алиас/имя

        Возвращает:
            Экземпляр Context
        """
        return cls(_message=message, command=command, prefix=prefix, invoked_with=invoked_with)

    @property
    def message(self) -> NewMessage:
        """Экземпляр NewMessage"""
        return self._message

    @property
    def msg(self) -> Message:
        """Объект Message"""
        return self._message.msg

    @property
    def bot(self) -> Bot:
        """Экземпляр Bot"""
        return self._message.bot

    @property
    def me(self) -> Bot:
        """
        Экземпляр Bot (алиас для ctx.bot).

        Возвращает:
            Bot: Экземпляр Bot

        Пример:
            @commands.command()
            async def info(ctx: commands.Context):
                mention = await ctx.me.mention()
                await ctx.send(f"I am {mention}")
        """
        return self.bot

    @property
    def app(self) -> App:
        """Экземпляр App"""
        return self._message.bot.app

    @property
    def api(self) -> API:
        """Экземпляр API"""
        return self._message.api

    @property
    def author(self) -> int:
        """ID автора сообщения"""
        return self.msg.from_id

    @property
    def peer_id(self) -> int:
        """Peer ID (ID чата/пользователя)"""
        return self.msg.peer_id

    @property
    def text(self) -> str:
        """Текст сообщения"""
        return self.msg.text

    @property
    def payload(self) -> dict | None:
        """Payload сообщения"""
        return self.msg.payload

    @property
    def guild(self) -> int | None:
        """
        ID беседы.
        Возвращает peer_id, если это чат, иначе None.
        """
        if self.peer_id > 2000000000:
            return self.peer_id
        return None

    @property
    def channel(self) -> int:
        """ID канала/peer"""
        return self.peer_id

    @property
    def chat_id(self) -> int | None:
        """
        ID чата (локальный, без смещения 2000000000).
        Возвращает None, если сообщение не из чата.

        Пример:
            if ctx.chat_id:
                print(f"Сообщение из чата {ctx.chat_id}")
        """
        if self.peer_id > 2000000000:
            return self.peer_id - 2000000000
        return None

    @property
    def chat(self) -> Chat | None:
        """
        Chat обёртка для управления чатом.
        Возвращает None, если сообщение не из чата.
        Результат кешируется для повторных обращений.

        Пример:
            if ctx.chat:
                members = await ctx.chat.get_members()
                await ctx.chat.kick(user_id=123)
        """
        if self._chat_resolved:
            return self._cached_chat

        from vkflow.models.chat import Chat

        if self.peer_id > 2000000000:
            self._cached_chat = Chat(self.api, self.peer_id)
        else:
            self._cached_chat = None

        self._chat_resolved = True
        return self._cached_chat

    @property
    def valid(self) -> bool:
        """
        Валиден ли контекст для вызова команды.

        Возвращает:
            True, если команда может быть вызвана
        """
        return self.command is not None and self.prefix is not None

    @property
    def extra(self) -> dict[str, typing.Any]:
        """
        Дополнительные данные, прикреплённые к команде.

        Возвращает:
            Словарь дополнительных данных команды
        """
        if self.command is not None:
            return self.command.extra
        return {}

    def is_on_cooldown(self) -> bool:
        """
        Проверить, находится ли текущая команда на кулдауне для этого контекста.

        Возвращает:
            True если на кулдауне, False иначе

        Пример:
            if ctx.is_on_cooldown():
                remaining = ctx.get_cooldown_retry_after()
                await ctx.send(f"Подожди {remaining:.1f}с")
        """
        if self.command is None:
            return False
        if not hasattr(self.command, "_cooldown_mappings"):
            return False
        for mapping in self.command._cooldown_mappings:
            bucket = mapping.get_bucket(self)
            if bucket.get_retry_after() > 0:
                return True
        return False

    def get_cooldown_retry_after(self) -> float:
        """
        Получить максимальное оставшееся время кулдауна (в секундах).

        Возвращает:
            Секунды до окончания кулдауна (0.0 если не на кулдауне)

        Пример:
            remaining = ctx.get_cooldown_retry_after()
            if remaining > 0:
                await ctx.send(f"Команда доступна через {remaining:.1f}с")
        """
        if self.command is None:
            return 0.0
        if not hasattr(self.command, "_cooldown_mappings"):
            return 0.0
        max_retry = 0.0
        for mapping in self.command._cooldown_mappings:
            bucket = mapping.get_bucket(self)
            retry = bucket.get_retry_after()
            if retry > max_retry:
                max_retry = retry
        return max_retry

    @property
    def clean_prefix(self) -> str:
        """
        Префикс без упоминания.

        Если было использовано упоминание (например, `[club123|@bot]`),
        возвращает пустую строку. Иначе возвращает префикс как есть.

        Возвращает:
            str: Чистый префикс или пустая строка для упоминания

        Пример:
            # Если prefix = "!"
            ctx.clean_prefix  # "!"

            # Если prefix = "[club123456|@bot]"
            ctx.clean_prefix  # ""

            # Использование в сообщениях
            await ctx.send(f"Использование: {ctx.clean_prefix}{ctx.command.name} <arg>")
        """
        if self.prefix is None:
            return ""

        mention_pattern = r"^\[(?:club|public|id)\d+\|[^\]]*\]$"

        if re.match(mention_pattern, self.prefix.strip()):
            return ""

        return self.prefix

    @property
    def invoked_parents(self) -> list[Group]:
        """
        Список родительских групп, через которые была вызвана эта команда.

        Возвращает:
            list[Group]: Список групп от ближайшего родителя к корню

        Пример:
            @config.group()
            async def settings(ctx: Context):
                pass

            @settings.command()
            async def show(ctx: Context):
                for parent in ctx.invoked_parents:
                    print(f"Родитель: {parent.name}")
        """
        if self.command is None:
            return []

        return self.command.parents

    @staticmethod
    def _normalize_attachments(
        attachment: SingleAttachment | None,
        attachments: AttachmentsList | None,
        file: SingleAttachment | None,
        files: AttachmentsList | None,
    ) -> tuple[SingleAttachment | None, AttachmentsList | None]:
        """Объединить attachment/file и attachments/files в единую пару."""
        if file is not None:
            if attachment is None:
                attachment = file
            else:
                attachments = [file] + (list(attachments) if attachments else [])

        if files is not None:
            attachments = files if attachments is None else list(attachments) + list(files)

        return attachment, attachments

    async def send(
        self,
        message: str | None = None,
        *,
        attachment: SingleAttachment | None = None,
        attachments: AttachmentsList | None = None,
        file: SingleAttachment | None = None,
        files: AttachmentsList | None = None,
        keyboard: dict | None = None,
        payload: dict | None = None,
        view: View | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage:
        """
        Отправить сообщение в тот же чат.

        Аргументы:
            message: Текст сообщения
            attachment: Одно вложение
            attachments: Список вложений
            file: Одно вложение (алиас для attachment)
            files: Список вложений (алиас для attachments)
            keyboard: Клавиатура
            payload: Payload сообщения
            view: Интерактивный View с кнопками
            delete_after: Удалить сообщение через указанное количество секунд
            **kwargs: Дополнительные параметры для messages.send

        Пример:
            msg = await ctx.send("Привет!")
            await msg.edit("Привет, мир!")

            await ctx.send("Фото", file=File("photo.jpg"))

            await ctx.send("Исчезну!", delete_after=5)
        """
        attachment, attachments = self._normalize_attachments(attachment, attachments, file, files)

        return await self._message.answer(
            message,
            attachment=attachment,
            attachments=attachments,
            keyboard=keyboard,
            payload=payload,
            view=view,
            delete_after=delete_after,
            **kwargs,
        )

    async def reply(
        self,
        message: str | None = None,
        *,
        attachment: SingleAttachment | None = None,
        attachments: AttachmentsList | None = None,
        file: SingleAttachment | None = None,
        files: AttachmentsList | None = None,
        keyboard: dict | None = None,
        payload: dict | None = None,
        view: View | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage:
        """
        Ответить на сообщение.

        Аргументы:
            message: Текст сообщения
            attachment: Одно вложение
            attachments: Список вложений
            file: Одно вложение (алиас для attachment)
            files: Список вложений (алиас для attachments)
            keyboard: Клавиатура
            payload: Payload сообщения
            view: Интерактивный View с кнопками
            delete_after: Удалить сообщение через указанное количество секунд
            **kwargs: Дополнительные параметры для messages.send

        Пример:
            msg = await ctx.reply("Привет!")
            await msg.edit("Обновлённый привет!")

            await ctx.reply("Исчезну!", delete_after=5)
        """
        attachment, attachments = self._normalize_attachments(attachment, attachments, file, files)

        return await self._message.reply(
            message,
            attachment=attachment,
            attachments=attachments,
            keyboard=keyboard,
            payload=payload,
            view=view,
            delete_after=delete_after,
            **kwargs,
        )

    async def forward(
        self,
        peer_id: int,
        message: str | None = None,
        *,
        attachment: SingleAttachment | None = None,
        attachments: AttachmentsList | None = None,
        file: SingleAttachment | None = None,
        files: AttachmentsList | None = None,
        keyboard: dict | None = None,
        payload: dict | None = None,
        view: View | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage:
        """
        Переслать текущее сообщение в другой чат.

        Аргументы:
            peer_id: ID чата-получателя
            message: Текст для пересылки
            attachment: Одно вложение
            attachments: Список вложений
            file: Одно вложение (алиас для attachment)
            files: Список вложений (алиас для attachments)
            keyboard: Клавиатура
            payload: Payload сообщения
            view: Интерактивный View с кнопками
            delete_after: Удалить сообщение через указанное количество секунд
            **kwargs: Дополнительные параметры для messages.send

        Пример:
            await ctx.forward(peer_id=123456789)
            await ctx.forward(peer_id=123456789, message="Смотри!")
        """
        attachment, attachments = self._normalize_attachments(attachment, attachments, file, files)

        return await self._message.forward(
            message,
            attachment=attachment,
            attachments=attachments,
            keyboard=keyboard,
            payload=payload,
            view=view,
            delete_after=delete_after,
            peer_ids=peer_id,
            **kwargs,
        )

    async def fetch_sender(
        self,
        typevar: type[SenderTypevar],
        /,
        *,
        fields: list[str] | None = None,
        name_case: str | None = None,
    ) -> SenderTypevar:
        """
        Получить отправителя сообщения.

        Аргументы:
            typevar: Тип отправителя (User, Group или Page)
            fields: Дополнительные поля для получения
            name_case: Падеж имени

        Возвращает:
            Объект отправителя
        """
        return await self._message.fetch_sender(typevar, fields=fields, name_case=name_case)

    async def fetch_author(
        self,
        *,
        fields: list[str] | None = None,
        name_case: str | None = None,
    ) -> Page:
        """
        Получить автора сообщения с кешированием.

        Повторные вызовы с теми же параметрами возвращают закешированный
        результат без дополнительных API-запросов.

        Аргументы:
            fields: Дополнительные поля для получения (bdate, city и т.д.)
            name_case: Падеж для склонения:
                - "nom" - именительный (кто? что?)
                - "gen" - родительный (кого? чего?)
                - "dat" - дательный (кому? чему?)
                - "acc" - винительный (кого? что?)
                - "ins" - творительный (кем? чем?)
                - "abl" - предложный (о ком? о чём?)

        Возвращает:
            User или Group в зависимости от from_id

        Пример:
            author = await ctx.fetch_author(name_case="acc")
            await ctx.reply(f"Погладил {author.mention()}")
        """
        return await self._message.fetch_author(fields=fields, name_case=name_case)

    async def fetch_photos(self) -> list[Photo]:
        """Получить фотографии из сообщения"""
        return await self._message.fetch_photos()

    async def fetch_docs(self) -> list[Document]:
        """Получить документы из сообщения"""
        return await self._message.fetch_docs()

    async def download_photos(self) -> list[bytes]:
        """Скачать все фотографии из сообщения"""
        return await self._message.download_photos()

    async def invoke(self, command: Command | None = None, *args, **kwargs) -> typing.Any:
        """
        Вызвать команду в этом контексте.

        Проходит через ВСЕ проверки (кулдауны, чеки, фильтры, max_concurrency).

        Аргументы:
            command: Команда для вызова. Если None, вызывает self.command
            *args: Позиционные аргументы для handler команды
            **kwargs: Именованные аргументы для handler команды

        Возвращает:
            Возвращаемое значение handler команды

        Исключения:
            ValueError: Если нет команды для вызова
            OnCooldownError: Если команда на кулдауне
            CheckFailureError: Если проверка не пройдена
            MaxConcurrencyReachedError: Если превышен лимит max_concurrency

        Пример:
            @commands.command()
            async def parent(ctx: commands.Context):
                await ctx.invoke(other_command, arg1="value")

            @commands.command()
            async def chain(ctx: commands.Context):
                await ctx.invoke(ctx.command.commands["sub"])
        """
        cmd = command or self.command
        if cmd is None:
            raise ValueError("Нет команды для вызова")

        invoke_ctx = await self.app.get_context(
            self._message,
            command=cmd,
            prefix=self.prefix,
            invoked_with=cmd.name,
        )

        passed_filter = await cmd._run_through_filters(self._message)
        if not passed_filter:
            from .checks import CheckFailureError

            raise CheckFailureError(check=None, message="Проверка фильтра не пройдена")

        if hasattr(cmd, "_max_concurrency_mapping") and cmd._max_concurrency_mapping is not None:
            async with cmd._max_concurrency_mapping(invoke_ctx):
                return await cmd.handler(invoke_ctx, *args, **kwargs)
        else:
            return await cmd.handler(invoke_ctx, *args, **kwargs)

    async def reinvoke(self, command: Command | None = None, *args, **kwargs) -> typing.Any:
        """
        Повторно вызвать команду, пропуская ВСЕ проверки.

        Пропускает ВСЕ проверки: кулдауны, чеки, фильтры, max_concurrency.
        Напрямую вызывает handler команды.

        Аргументы:
            command: Команда для вызова. Если None, вызывает self.command
            *args: Позиционные аргументы для handler команды
            **kwargs: Именованные аргументы для handler команды

        Возвращает:
            Возвращаемое значение handler команды

        Исключения:
            ValueError: Если нет команды для вызова

        Пример:
            @commands.command()
            async def admin_retry(ctx: commands.Context, cmd_name: str):
                '''Админ-команда для повтора без проверок'''
                cmd = ctx.app.get_command(cmd_name)

                if cmd:
                    await ctx.reinvoke(cmd)

            @commands.command()
            async def retry(ctx: commands.Context):
                '''Повторить текущую команду'''
                await ctx.reinvoke()
        """
        cmd = command or self.command
        if cmd is None:
            raise ValueError("Нет команды для вызова")

        invoke_ctx = await self.app.get_context(
            self._message,
            command=cmd,
            prefix=self.prefix,
            invoked_with=cmd.name,
        )

        return await cmd.handler(invoke_ctx, *args, **kwargs)

    async def wait_for(
        self,
        event_name: str,
        *,
        timeout: float | None = None,
        check: typing.Callable[..., bool] | None = None,
    ) -> NewEvent | tuple:
        """
        Ожидание события. Делегирует в App.wait_for().

        Аргументы:
            event_name: Тип события для ожидания (например, "message_new")
            timeout: Таймаут в секундах. None -ждать бесконечно
            check: Предикат для фильтрации событий

        Возвращает:
            NewEvent или tuple в зависимости от события

        Исключения:
            EventTimeoutError: Если таймаут превышен
        """
        return await self.app.wait_for(event_name, timeout=timeout, check=check)

    async def wait_for_message(
        self,
        *,
        timeout: float | None = None,
        check: typing.Callable[..., bool] | None = None,
        filter_peer: bool = True,
        filter_author: bool = True,
    ) -> NewMessage:
        """
        Ожидание нового сообщения с опциональной фильтрацией по peer_id и автору.

        По умолчанию фильтрует по тому же peer_id и from_id, что и текущий контекст.
        Используйте filter_peer=False / filter_author=False для отключения.

        Аргументы:
            timeout: Таймаут в секундах. None -ждать бесконечно
            check: Дополнительный предикат после встроенных фильтров
            filter_peer: Фильтровать по peer_id == ctx.peer_id
            filter_author: Фильтровать по from_id == ctx.author

        Возвращает:
            Экземпляр NewMessage

        Исключения:
            EventTimeoutError: Если таймаут превышен

        Пример:
            @commands.command()
            async def ask_name(ctx: commands.Context):
                await ctx.send("Как тебя зовут?")
                reply = await ctx.wait_for_message(timeout=30)
                await ctx.send(f"Привет, {reply.msg.text}!")
        """
        from vkflow.app.storages import NewMessage as _NewMessage

        my_peer_id = self.peer_id
        my_author = self.author

        def _combined_check(event, **kw):
            raw = event.event.object if hasattr(event, "event") else {}
            msg = raw.get("message", raw) if isinstance(raw, dict) else {}
            if filter_peer and msg.get("peer_id") != my_peer_id:
                return False
            if filter_author and msg.get("from_id") != my_author:
                return False
            if check is not None:
                return check(event, **kw)
            return True

        result = await self.app.wait_for("message_new", timeout=timeout, check=_combined_check)

        event_obj = result.event if hasattr(result, "event") else result
        bot_obj = result.bot if hasattr(result, "bot") else self.bot
        return await _NewMessage.from_event(event=event_obj, bot=bot_obj)

    def __repr__(self):
        return (
            f"<Context message={self.msg.text!r} "
            f"author={self.author} "
            f"command={self.command.name if self.command else None}>"
        )
