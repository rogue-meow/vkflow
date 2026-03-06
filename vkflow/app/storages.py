from __future__ import annotations

import asyncio
import dataclasses
import functools
import typing

from vkflow.exceptions import StopStateHandlingError
from vkflow.models.message import (
    CallbackButtonPressedMessage,
    Message,
    SentMessage,
)
from vkflow.models.page import Group, Page, User


class ArgumentPayload(dict):
    """
    Payload для обмена данными между каттерами при парсинге аргументов.

    Наследует dict для полной обратной совместимости, но предоставляет
    типизированный API для известных ключей.
    """

    @property
    def converter_context(self) -> typing.Any:
        """Кешированный Context из ext.commands (или None)."""
        return self.get("_converter_context")

    @converter_context.setter
    def converter_context(self, value: typing.Any) -> None:
        self["_converter_context"] = value

    @property
    def replied_user_used(self) -> bool:
        """Был ли уже использован пользователь из reply."""
        return self.get("_replied_user_used") is not None

    @replied_user_used.setter
    def replied_user_used(self, value: bool) -> None:
        self["_replied_user_used"] = ... if value else None

    @property
    def forward_page_iter_step(self) -> int:
        """Текущий шаг итерации по пересланным сообщениям."""
        return self.get("_forward_page_iter_step", 0)

    @forward_page_iter_step.setter
    def forward_page_iter_step(self, value: int) -> None:
        self["_forward_page_iter_step"] = value

    def get_attachment_used(self, att_type: str) -> int:
        """Количество уже использованных вложений данного типа."""
        return self.get(f"_attachment_used_{att_type}", 0)

    def increment_attachment_used(self, att_type: str) -> None:
        """Увеличить счётчик использованных вложений данного типа."""
        key = f"_attachment_used_{att_type}"
        self[key] = self.get(key, 0) + 1

    def set_attachment_used(self, att_type: str, count: int) -> None:
        """Установить счётчик использованных вложений данного типа."""
        self[f"_attachment_used_{att_type}"] = count


if typing.TYPE_CHECKING:  # pragma: no cover
    from vkflow.base.event import BaseEvent
    from vkflow.base.event_factories import BaseEventFactory
    from vkflow.app.bot import App, Bot
    from vkflow.models.attachment import Document, Photo

    SenderTypevar = typing.TypeVar("SenderTypevar", bound=Page)
    MessageFields: typing.TypeAlias = dict[str, typing.Any]


NewEventPayloadFieldTypevar = typing.TypeVar("NewEventPayloadFieldTypevar")

BotPayloadFieldTypevar = typing.TypeVar("BotPayloadFieldTypevar")
AppPayloadFieldTypevar = typing.TypeVar("AppPayloadFieldTypevar")


@dataclasses.dataclass
class NewEvent(
    typing.Generic[
        AppPayloadFieldTypevar,
        BotPayloadFieldTypevar,
        NewEventPayloadFieldTypevar,
    ]
):
    event: BaseEvent
    bot: Bot[BotPayloadFieldTypevar, AppPayloadFieldTypevar]
    payload_factory: type[NewEventPayloadFieldTypevar] = dataclasses.field(default=None)

    @classmethod
    async def from_event(
        cls,
        *,
        event: BaseEvent,
        bot: Bot,
    ):
        return cls(event=event, bot=bot)

    @functools.cached_property
    def payload(self) -> NewEventPayloadFieldTypevar:
        return self.payload_factory()

    @property
    def events_factory(self) -> BaseEventFactory:
        return self.bot.events_factory

    @property
    def app(self) -> App[AppPayloadFieldTypevar]:
        return self.bot.app


async def dump_user_lp_fields(
    event: BaseEvent,
    bot: Bot,
) -> MessageFields:
    message = {
        "id": event.content[1],
        "peer_id": event.content[3],
        "date": event.content[4],
        "text": event.content[5],
        "keyboard": event.content[6].get("keyboard"),
        "payload": event.content[6].get("payload"),
        "random_id": event.content[8],
        "conversation_message_id": event.content[9] if len(event.content) == 10 else None,
        "is_cropped": True,
        "out": event.content[2] & 2,
    }

    _, sender_schema = await bot.events_factory.api.define_token_owner()

    if "from" in event.content[6]:
        message["from_id"] = int(event.content[6]["from"])
    else:
        if message["out"]:
            (
                _,
                sender_schema,
            ) = await bot.events_factory.api.define_token_owner()

            message["from_id"] = sender_schema.id
        else:
            message["from_id"] = message["peer_id"]

    message["text"] = (
        message["text"]
        .replace("<br>", "\n")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
    )

    if "source_act" in event.content[6]:
        action_map = {
            "type": event.content[6]["source_act"],
            **{
                key: value
                for key, value in event.content[6].items()
                if key.startswith("source") and key != "source_act"
            },
        }

        message["action"] = action_map

    return message


@dataclasses.dataclass
class NewMessage(
    NewEvent[
        NewEventPayloadFieldTypevar,
        BotPayloadFieldTypevar,
        AppPayloadFieldTypevar,
    ],
    SentMessage,
):
    argument_processing_payload: ArgumentPayload = dataclasses.field(default_factory=ArgumentPayload)

    @classmethod
    async def from_event(
        cls,
        *,
        event: BaseEvent,
        bot: Bot,
        payload_factory: type[NewEventPayloadFieldTypevar] | None = None,
    ):
        match (event.type, event.object):
            case (4, _):
                message_data = await dump_user_lp_fields(event, bot)
            case (_, {"message": msg}):
                message_data = msg
            case (_, obj):
                message_data = obj

        message = Message(message_data)

        return cls(
            event=event,
            bot=bot,
            api=bot.api,
            truncated_message=message,
            payload_factory=payload_factory,
        )

    @functools.cached_property
    def msg(self) -> Message:
        return typing.cast("Message", self.truncated_message)

    async def conquer_new_message(
        self, *, same_chat: bool = True, same_user: bool = True
    ) -> typing.AsyncGenerator[NewMessage, None]:
        async for new_event in self.bot.events_factory.listen():
            if new_event.type in {
                "message_new",
                "message_reply",
                4,
            }:
                conquered_message = await NewMessage.from_event(event=new_event, bot=self.bot)

                if (conquered_message.msg.peer_id == self.msg.peer_id or not same_chat) and (
                    conquered_message.msg.from_id == self.msg.from_id or not same_user
                ):
                    yield conquered_message

    async def run_state_handling(self, app: App, /, payload: typing.Any = None) -> typing.Any:
        from vkflow.app.bot import Bot

        anonymous_bot = Bot(
            app=app,
            api=self.api,
            events_factory=self.events_factory,
            payload_factory=self.payload_factory,
        )

        async for event in self.events_factory.listen():
            new_event_storage = NewEvent(
                event=event,
                bot=anonymous_bot,
                payload_factory=lambda: payload,
            )

            try:
                await anonymous_bot.handle_event(new_event_storage, wrap_to_task=False)

            except StopStateHandlingError as err:
                return err.payload

        return None

    async def fetch_photos(self) -> list[Photo]:
        return await self.msg.fetch_photos(self.api)

    async def fetch_docs(self) -> list[Document]:
        return await self.msg.fetch_docs(self.api)

    async def download_photos(self) -> list[bytes]:
        photos = await self.fetch_photos()

        download_coroutines = [
            photo.download_max_size(session=self.api.requests_session) for photo in photos
        ]

        return await asyncio.gather(*download_coroutines)

    async def fetch_sender(
        self,
        typevar: type[SenderTypevar],
        /,
        *,
        fields: list[str] | None = None,
        name_case: str | None = None,
    ) -> SenderTypevar:
        if self.msg.from_id > 0 and typevar in {Page, User}:
            return await User.fetch_one(self.api, self.msg.from_id, fields=fields, name_case=name_case)
        if self.msg.from_id < 0 and typevar in {Page, Group}:
            return await Group.fetch_one(self.api, self.msg.from_id, fields=fields, name_case=name_case)
        raise ValueError(f"Can't make wrapper with typevar `{typevar}` and from_id `{self.msg.from_id}`")

    async def fetch_author(
        self,
        *,
        fields: list[str] | None = None,
        name_case: str | None = None,
    ) -> User | Group:
        """
        Получает автора сообщения с кэшированием.

        Повторные вызовы с теми же параметрами возвращают
        закэшированный результат без дополнительных API запросов.

        Arguments:
            fields: Дополнительные поля для запроса (bdate, city, etc.)
            name_case: Падеж для склонения имени:
                - "nom" - именительный (кто? что?)
                - "gen" - родительный (кого? чего?)
                - "dat" - дательный (кому? чему?)
                - "acc" - винительный (кого? что?)
                - "ins" - творительный (кем? чем?)
                - "abl" - предложный (о ком? о чём?)

        Returns:
            User или Group в зависимости от from_id

        Example:
            author = await ctx.fetch_author(name_case="acc")
            await ctx.reply(f"Погладил {author.mention()}")
        """
        cache_key = (tuple(fields) if fields else (), name_case)

        if not hasattr(self, "_author_cache"):
            self._author_cache: dict[tuple, User | Group] = {}

        if cache_key not in self._author_cache:
            self._author_cache[cache_key] = await self.fetch_sender(
                Page, fields=fields, name_case=name_case
            )

        return self._author_cache[cache_key]

    def __repr__(self):
        return f"<vkflow.NewMessage text={self.msg.text!r}>"


class CallbackButtonPressed(NewEvent):
    @functools.cached_property
    def msg(self) -> CallbackButtonPressedMessage:
        return CallbackButtonPressedMessage(self.event.object)

    @property
    def message(self) -> CallbackButtonPressedMessage:
        return self.msg

    async def _call_action(self, **event_data):
        return await self.bot.api.method(
            "messages.send_message_event_answer",
            event_id=self.msg.event_id,
            user_id=self.msg.user_id,
            peer_id=self.msg.peer_id,
            event_data=event_data,
        )

    async def show_snackbar(self, text: str) -> dict:
        return await self._call_action(text=text, type="show_snackbar")

    async def answer(self, text: str) -> dict:
        return await self.show_snackbar(text)

    async def open_link(self, link: str) -> dict:
        return await self._call_action(link=link, type="open_link")

    async def open_app(self, app_id: int, hash: str, owner_id: int | None = None) -> dict:
        return await self._call_action(app_id=app_id, hash=hash, owner_id=owner_id, type="open_app")

    async def edit(
        self,
        message: str | None = None,
        *,
        keyboard: dict | None = None,
        attachment: str | None = None,
        attachments: list[str] | None = None,
        **kwargs,
    ) -> dict:
        params = {
            "peer_id": self.msg.peer_id,
            "conversation_message_id": self.msg.conversation_message_id,
            **kwargs,
        }

        if message is not None:
            params["message"] = message

        if keyboard is not None:
            if hasattr(keyboard, "get_schema"):
                params["keyboard"] = keyboard.get_schema()
            else:
                params["keyboard"] = keyboard

        if attachment is not None or attachments is not None:
            attachment_list = []

            if attachment:
                attachment_list.append(attachment)
            if attachments:
                attachment_list.extend(attachments)

            if attachment_list:
                params["attachment"] = ",".join(attachment_list)

        return await self.bot.api.method("messages.edit", **params)
