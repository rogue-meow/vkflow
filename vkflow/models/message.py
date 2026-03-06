from __future__ import annotations

import io
import asyncio
import typing

import textwrap
import datetime

import functools
import dataclasses

from vkflow.base.wrapper import Wrapper
from vkflow.formatting import format_message
from vkflow.ui.view import View  # noqa: TC001
from vkflow.utils.helpers import peer, random_id as random_id_
from vkflow.file import File
from vkflow.models.attachment import (
    ATTACHMENT_TYPES,
    Attachment,
    Audio,
    AudioMessage,
    Document,
    Gift,
    Graffiti,
    Link,
    Market,
    MarketAlbum,
    Narrative,
    Photo,
    Poll,
    Sticker,
    Story,
    Video,
    Wall,
)

from vkflow.json_parsers import json_parser_policy

if typing.TYPE_CHECKING:  # pragma: no cover
    from vkflow.api import API, PhotoEntityTyping
    from vkflow.ui.carousel import Carousel
    from vkflow.ui.keyboard import Keyboard

    SingleAttachment: typing.TypeAlias = (
        str
        | Photo
        | Document
        | Video
        | Audio
        | Wall
        | Sticker
        | Gift
        | Market
        | MarketAlbum
        | Poll
        | Story
        | Narrative
        | Link
        | AudioMessage
        | Graffiti
        | File
        | PhotoEntityTyping
    )

    AttachmentsList: typing.TypeAlias = list[SingleAttachment]
    AttachmentsTyping: typing.TypeAlias = SingleAttachment | AttachmentsList

    RoutingParams: typing.TypeAlias = dict[str, typing.Any]


class TruncatedMessage(Wrapper):
    async def extend(self, api: API) -> None:
        if self.id:
            extended_message = await api.method(
                "messages.get_by_id",
                message_ids=self.id,
            )

        else:
            extended_message = await api.method(
                "messages.get_by_conversation_message_id",
                conversation_message_ids=self.cmid,
                peer_id=self.peer_id,
            )

        self._fields = extended_message["items"][0]
        self.fields["is_cropped"] = False

    @property
    def id(self) -> int:
        return self.fields["message_id"]

    @property
    def peer_id(self) -> int:
        return self.fields["peer_id"]

    @property
    def conversation_message_id(self) -> int:
        return self.fields["conversation_message_id"]

    @property
    def cmid(self) -> int:
        return self.conversation_message_id


class Message(TruncatedMessage):
    @property
    def id(self) -> int:
        return self.fields["id"]

    @functools.cached_property
    def chat_id(self) -> int:
        chat_id = self.peer_id - peer()

        if chat_id < 0:
            raise ValueError("Can't get `chat_id` if message wasn't sent in a chat")

        return chat_id

    @functools.cached_property
    def date(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(self.fields["date"])

    @property
    def from_id(self) -> int:
        return self.fields["from_id"]

    @property
    def text(self) -> str:
        return self.fields["text"]

    @property
    def random_id(self) -> int:
        return self.fields["random_id"]

    @property
    def attachments(self) -> list[dict]:
        return self.fields["attachments"]

    @property
    def important(self) -> bool:
        return bool(self.fields["important"])

    @property
    def is_hidden(self) -> bool:
        return bool(self.fields["is_hidden"])

    @property
    def out(self) -> bool:
        return bool(self.fields["out"])

    @functools.cached_property
    def keyboard(self) -> dict | None:
        if "keyboard" in self.fields:
            return json_parser_policy.loads(self.fields["keyboard"])
        return None

    @functools.cached_property
    def fwd_messages(self) -> list[Message]:
        return list(map(self.__class__, self.fields["fwd_messages"]))

    @property
    def geo(self) -> dict | None:
        return self.fields.get("geo")

    @functools.cached_property
    def payload(self) -> dict | None:
        if "payload" in self.fields and self.fields["payload"] is not None:
            return json_parser_policy.loads(self.fields["payload"])
        return None

    @functools.cached_property
    def reply_message(self) -> Message | None:
        if "reply_message" in self.fields:
            return self.__class__(self.fields["reply_message"])
        return None

    @property
    def action(self) -> dict:
        return self.fields.get("action")

    @property
    def ref(self) -> str | None:
        return self.fields.get("ref")

    @property
    def ref_source(self) -> str | None:
        return self.fields.get("ref_source")

    @property
    def expire_ttl(self) -> int | None:
        return self.fields.get("expire_ttl")

    @property
    def admin_author_id(self) -> int | None:
        return self.fields.get("admin_author_id")

    @property
    def members_count(self) -> int | None:
        return self.fields.get("members_count")

    @property
    def is_cropped(self) -> bool:
        return bool(self.fields.get("is_cropped"))

    async def fetch_attachments(self, api: API) -> list:
        if self.is_cropped:
            await self.extend(api)
        return self.attachments

    async def fetch_photos(self, api: API) -> list[Photo]:
        """
        Возвращает только фотографии из всего,
        что есть во вложениях, оборачивая их в обертку
        """
        return [
            Photo(attachment["photo"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "photo"
        ]

    async def fetch_docs(self, api: API) -> list[Document]:
        """
        Возвращает только вложения с типом документ из всего,
        что есть во вложениях, оборачивая их в обертку
        """
        if self.is_cropped:
            await self.extend(api)

        return [
            Document(attachment["doc"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "doc"
        ]

    async def fetch_videos(self, api: API) -> list[Video]:
        return [
            Video(attachment["video"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "video"
        ]

    async def fetch_audios(self, api: API) -> list[Audio]:
        return [
            Audio(attachment["audio"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "audio"
        ]

    async def fetch_walls(self, api: API) -> list[Wall]:
        return [
            Wall(attachment["wall"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "wall"
        ]

    async def fetch_stickers(self, api: API) -> list[Sticker]:
        return [
            Sticker(attachment["sticker"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "sticker"
        ]

    async def fetch_gifts(self, api: API) -> list[Gift]:
        return [
            Gift(attachment["gift"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "gift"
        ]

    async def fetch_markets(self, api: API) -> list[Market]:
        return [
            Market(attachment["market"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "market"
        ]

    async def fetch_market_albums(self, api: API) -> list[MarketAlbum]:
        return [
            MarketAlbum(attachment["market_album"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "market_album"
        ]

    async def fetch_polls(self, api: API) -> list[Poll]:
        return [
            Poll(attachment["poll"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "poll"
        ]

    async def fetch_stories(self, api: API) -> list[Story]:
        return [
            Story(attachment["story"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "story"
        ]

    async def fetch_narratives(self, api: API) -> list[Narrative]:
        return [
            Narrative(attachment["narrative"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "narrative"
        ]

    async def fetch_links(self, api: API) -> list[Link]:
        return [
            Link(attachment["link"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "link"
        ]

    async def fetch_audio_messages(self, api: API) -> list[AudioMessage]:
        return [
            AudioMessage(attachment["audio_message"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "audio_message"
        ]

    async def fetch_graffiti(self, api: API) -> list[Graffiti]:
        return [
            Graffiti(attachment["graffiti"])
            for attachment in await self.fetch_attachments(api)
            if attachment["type"] == "graffiti"
        ]

    async def fetch_all_typed_attachments(self, api: API) -> list[Attachment]:
        typed_attachments = []

        for attachment in await self.fetch_attachments(api):
            att_type = attachment["type"]

            if att_type in ATTACHMENT_TYPES:
                attachment_class = ATTACHMENT_TYPES[att_type]
                typed_attachments.append(attachment_class(attachment[att_type]))

        return typed_attachments


_background_tasks: set = set()


@dataclasses.dataclass
class SentMessage:
    api: API
    truncated_message: TruncatedMessage

    async def _process_attachments(self, attachments: AttachmentsTyping | None) -> list[Attachment] | None:
        if attachments is None:
            return None

        if not isinstance(attachments, list):
            attachments = [attachments]

        processed = []

        for attachment in attachments:
            if isinstance(
                attachment,
                (
                    Photo,
                    Document,
                    Video,
                    Audio,
                    Wall,
                    Sticker,
                    Gift,
                    Market,
                    MarketAlbum,
                    Poll,
                    Story,
                    Narrative,
                    Link,
                    AudioMessage,
                    Graffiti,
                ),
            ):
                processed.append(attachment)

            elif isinstance(attachment, File):
                uploaded = await self._upload_file(attachment)
                processed.append(uploaded)

            elif isinstance(attachment, str):
                if "_" in attachment and not attachment.startswith(("http://", "https://", "/", ".", "~")):
                    processed.append(attachment)

                else:
                    file_obj = File(attachment)
                    uploaded = await self._upload_file(file_obj)
                    processed.append(uploaded)

            elif isinstance(attachment, (bytes, io.BytesIO)):
                file_obj = File(attachment)
                uploaded = await self._upload_file(file_obj)
                processed.append(uploaded)

            else:
                try:
                    file_obj = File(attachment)
                    uploaded = await self._upload_file(file_obj)
                    processed.append(uploaded)

                except Exception:
                    processed.append(attachment)

        return processed

    async def _upload_file(self, file: File) -> Attachment:
        if file.type == "photo":
            photos = await self.upload_photos(file.source)
            return photos[0] if photos else None

        if file.type == "video":
            try:
                return await self.upload_video(
                    file.source,
                    name=file.title or file.filename,
                )

            except Exception as e:
                from vkflow.exceptions import APIError

                if isinstance(e, APIError) and e.status_code == 27:
                    raise ValueError(
                        "Загрузка видео недоступна для группового токена. "
                        "Метод video.save не поддерживается при авторизации от имени группы. "
                        "\n\nВарианты решения:"
                        "\n1. Используйте пользовательский токен для загрузки видео"
                        "\n2. Загрузите видео заранее и используйте готовый attachment (video123_456)"
                        "\n3. Отправьте видео как документ: File(path, type='doc')"
                    ) from e

                raise

        elif file.type in ("doc", "audio_message", "graffiti"):
            if isinstance(file.source, bytes):
                content = file.source

            elif isinstance(file.source, io.BytesIO):
                content = file.source.getvalue()

            else:
                import aiofiles

                async with aiofiles.open(str(file.source), "rb") as f:
                    content = await f.read()

            return await self.upload_doc(
                content=content,
                filename=file.filename or "file",
                tags=file.tags,
                type=file.type,
            )

        else:
            raise ValueError(f"Unknown file type: {file.type}")

    def _get_routing_params(self, param_name: str = "message_id") -> RoutingParams:
        match (self.truncated_message.id, param_name):
            case (msg_id, "message_id") if msg_id:
                return {"message_id": msg_id, "peer_id": self.truncated_message.peer_id}

            case (msg_id, "message_ids") if msg_id:
                return {"message_ids": msg_id, "peer_id": self.truncated_message.peer_id}

            case (_, "message_id"):
                return {
                    "conversation_message_id": self.truncated_message.cmid,
                    "peer_id": self.truncated_message.peer_id,
                }

            case (_, "message_ids"):
                return {
                    "conversation_message_ids": self.truncated_message.cmid,
                    "peer_id": self.truncated_message.peer_id,
                }

            case _:
                return {"peer_id": self.truncated_message.peer_id}

    def _merge_attachments(
        self, attachment: SingleAttachment | None, attachments: AttachmentsList | None
    ) -> AttachmentsList | None:
        if attachment is None and attachments is None:
            return None

        if attachment is None:
            return attachments

        if attachments is None:
            return [attachment]

        return [attachment, *attachments]

    async def _send_message(self, params: dict) -> SentMessage:
        if params["message"] is not None and isinstance(params["message"], str):
            params["message"] = textwrap.dedent(params["message"]).strip()

            plain_text, format_data = format_message(params["message"])
            params["message"] = plain_text

            if format_data is not None:
                params["format_data"] = format_data

        merged = self._merge_attachments(params.get("attachment"), params.get("attachments"))

        if merged is not None:
            processed = await self._process_attachments(merged)
            params["attachment"] = processed

        params.pop("attachments", None)

        sent_message = await self.api.method("messages.send", **params)
        sent_message = TruncatedMessage(sent_message[0])

        return SentMessage(self.api, sent_message)

    async def upload_photos(self, *photos: PhotoEntityTyping) -> list[Photo]:
        return await self.api.upload_photos_to_message(*photos, peer_id=self.truncated_message.peer_id)

    async def upload_doc(
        self,
        content: str | bytes,
        filename: str,
        *,
        tags: str | None = None,
        return_tags: bool | None = None,
        type: typing.Literal["doc", "audio_message", "graffiti"] = "doc",
    ) -> Document:
        """
        Загружает документ для отправки в сообщение

        Arguments:
            content: Содержимое документа. Документ может быть
                как текстовым, так и содержать сырые байты
            filename: Имя файла
            tags: Теги для файла, используемые при поиске
            return_tags: Возвращать переданные теги при запросе
            type: Тип документа: файл/голосовое сообщение/граффити

        Returns:
            Враппер загруженного документа. Этот объект можно напрямую
            передать в поле `attachments` при отправке сообщения
        """
        return await self.api.upload_doc_to_message(
            content,
            filename,
            tags=tags,
            return_tags=return_tags,
            type=type,
            peer_id=self.truncated_message.peer_id,
        )

    async def upload_video(
        self,
        file: PhotoEntityTyping,
        *,
        name: str | None = None,
        description: str | None = None,
        is_private: bool = True,
        wallpost: bool = False,
        link: str | None = None,
        group_id: int | None = None,
        album_id: int | None = None,
        privacy_view: list[str] | None = None,
        privacy_comment: list[str] | None = None,
        no_comments: bool = False,
        repeat: bool = False,
        compression: bool = False,
    ) -> Video:
        """
        Загружает видео для отправки в сообщение

        Arguments:
            file: Видео файл в виде ссылки/пути до файла/сырых байтов/IO-хранилища
            name: Название видео
            description: Описание видео
            is_private: Является ли видео приватным
            wallpost: Опубликовать видео на стене после сохранения
            link: URL для встраивания видео с внешнего сайта
            group_id: ID сообщества (для сообществ)
            album_id: ID альбома, в который нужно загрузить видео
            privacy_view: Настройки приватности для просмотра
            privacy_comment: Настройки приватности для комментирования
            no_comments: Отключить комментарии
            repeat: Зациклить воспроизведение видео
            compression: Сжать видео для мобильных устройств

        Returns:
            Враппер загруженного видео. Этот объект можно напрямую
            передать в поле `attachments` при отправке сообщения
        """
        return await self.api.upload_video_to_message(
            file,
            name=name,
            description=description,
            is_private=is_private,
            wallpost=wallpost,
            link=link,
            group_id=group_id,
            album_id=album_id,
            privacy_view=privacy_view,
            privacy_comment=privacy_comment,
            no_comments=no_comments,
            repeat=repeat,
            compression=compression,
        )

    async def delete(
        self,
        *,
        spam: bool | None = None,
        group_id: int | None = None,
        delete_for_all: bool = True,
        delay: int | float | None = None,
    ) -> None:
        """
        Удаляет указанное сообщение (по умолчанию у всех)

        :param spam: Пометить сообщение как спам
        :param group_id: ID группы, от лица которого
            было отправлено сообщение
        :param delete_for_all: Нужно ли удалять сообщение у всех
        :param delay: Задержка перед удалением в секундах.
            Если None - удаляет сразу. Если указано число,
            удаляет сообщение через указанное время.
            При использовании delay удаление выполняется в фоновой задаче.

        Example:
            # Удалить сразу
            await msg.delete()

            # Удалить через 5 секунд
            await msg.delete(delay=5)

            # Удалить через 1.5 секунды
            await msg.delete(delay=1.5)
        """

        async def _delete() -> None:
            if delay is not None:
                await asyncio.sleep(delay)

            try:
                routing = self._get_routing_params("message_ids")

                await self.api.method(
                    "messages.delete",
                    spam=spam,
                    group_id=group_id,
                    delete_for_all=delete_for_all,
                    **routing,
                )

            except Exception:
                pass

        if delay is not None:
            task = asyncio.create_task(_delete())
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)

        else:
            routing = self._get_routing_params("message_ids")

            await self.api.method(
                "messages.delete",
                spam=spam,
                group_id=group_id,
                delete_for_all=delete_for_all,
                **routing,
            )

    @typing.overload
    async def edit(
        self,
        message: str,
        /,
        *,
        lat: float | None = None,
        long: float | None = None,
        attachment: SingleAttachment,
        keep_forward_messages: bool = True,
        keep_snippets: bool = True,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        dont_parse_links: bool = True,
        template: str | Carousel | None = None,
    ) -> int: ...

    @typing.overload
    async def edit(
        self,
        message: str | None = None,
        *,
        lat: float | None = None,
        long: float | None = None,
        attachment: SingleAttachment,
        keep_forward_messages: bool = True,
        keep_snippets: bool = True,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        dont_parse_links: bool = True,
        template: str | Carousel | None = None,
    ) -> int: ...

    @typing.overload
    async def edit(
        self,
        message: str | None = None,
        *,
        lat: float | None = None,
        long: float | None = None,
        attachments: AttachmentsList,
        keep_forward_messages: bool = True,
        keep_snippets: bool = True,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        dont_parse_links: bool = True,
        template: str | Carousel | None = None,
    ) -> int: ...

    @typing.overload
    async def edit(
        self,
        message: str | None = None,
        *,
        lat: float | None = None,
        long: float | None = None,
        attachment: SingleAttachment,
        attachments: AttachmentsList,
        keep_forward_messages: bool = True,
        keep_snippets: bool = True,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        dont_parse_links: bool = True,
        template: str | Carousel | None = None,
    ) -> int: ...

    @typing.overload
    async def edit(
        self,
        message: str | None = None,
        *,
        lat: float | None = None,
        long: float | None = None,
        keep_forward_messages: bool = True,
        keep_snippets: bool = True,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        dont_parse_links: bool = True,
        template: str | Carousel | None = None,
    ) -> int: ...

    async def edit(
        self,
        *args,
        message: str | None = None,
        lat: float | None = None,
        long: float | None = None,
        attachment: SingleAttachment | None = None,
        attachments: AttachmentsList | None = None,
        keep_forward_messages: bool = True,
        keep_snippets: bool = True,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        dont_parse_links: bool = True,
        template: str | Carousel | None = None,
    ) -> int:
        if args:
            if len(args) > 1:
                raise TypeError(f"edit() takes at most 1 positional argument ({len(args)} given)")

            message = args[0]
        routing = self._get_routing_params("message_id")

        params = {
            "lat": lat,
            "long": long,
            "keep_forward_messages": keep_forward_messages,
            "keep_snippets": keep_snippets,
            "group_id": group_id,
            "keyboard": keyboard,
            "dont_parse_links": dont_parse_links,
            "template": template,
            **routing,
        }

        if message is not None:
            plain_text, format_data = format_message(message)
            params["message"] = plain_text

            if format_data is not None:
                params["format_data"] = format_data

        merged = self._merge_attachments(attachment, attachments)

        processed_attachments = await self._process_attachments(merged)
        params["attachment"] = processed_attachments

        return await self.api.method("messages.edit", **params)

    @typing.overload
    async def reply(
        self,
        message: str | None = None,
        /,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        attachment: SingleAttachment,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        template: str | Carousel | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage: ...

    @typing.overload
    async def reply(
        self,
        message: str | None = None,
        /,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        attachments: AttachmentsList,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        template: str | Carousel | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage: ...

    @typing.overload
    async def reply(
        self,
        message: str | None = None,
        /,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        attachment: SingleAttachment,
        attachments: AttachmentsList,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        template: str | Carousel | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage: ...

    @typing.overload
    async def reply(
        self,
        message: str | None = None,
        /,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        template: str | Carousel | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage: ...

    async def reply(
        self,
        message: str | None = None,
        /,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        attachment: SingleAttachment | None = None,
        attachments: AttachmentsList | None = None,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        template: str | Carousel | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        view: View | None = None,
        **kwargs,
    ) -> SentMessage:
        """
        Отвечает на сообщение

        :param message: Текст сообщения
        :param delete_after: Удалить сообщение через указанное количество секунд.
            Если None - сообщение не удаляется автоматически.
        :param view: Interactive View with buttons

        Example:
            # Ответить и удалить через 5 секунд
            await msg.reply("Это сообщение исчезнет!", delete_after=5)
        """
        if view is not None:
            keyboard = view.to_keyboard()

        params = dict(
            message=message,
            random_id=random_id_() if random_id is None else random_id,
            lat=lat,
            long=long,
            attachment=attachment,
            attachments=attachments,
            sticker_id=sticker_id,
            group_id=group_id,
            keyboard=keyboard,
            payload=payload,
            dont_parse_links=dont_parse_links,
            disable_mentions=disable_mentions,
            intent=intent,
            expire_ttl=expire_ttl,
            silent=silent,
            subscribe_id=subscribe_id,
            content_source=content_source,
            template=template,
            peer_ids=self.truncated_message.peer_id,
            **kwargs,
        )

        match self.truncated_message.id:
            case msg_id if msg_id:
                params["reply_to"] = msg_id
            case _:
                params["forward"] = {
                    "is_reply": True,
                    "conversation_message_ids": [self.truncated_message.conversation_message_id],
                    "peer_id": self.truncated_message.peer_id,
                }

        sent_message = await self._send_message(params)

        if view is not None:
            view.message = sent_message

            if hasattr(self, "bot") and hasattr(self.bot, "app") and hasattr(self.bot.app, "view_store"):
                self.bot.app.view_store.add(view)

        if delete_after is not None:
            await sent_message.delete(delay=delete_after)

        return sent_message

    @typing.overload
    async def answer(
        self,
        message: str | None = None,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        attachment: SingleAttachment,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        template: str | Carousel | None = None,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage: ...

    @typing.overload
    async def answer(
        self,
        message: str | None = None,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        attachments: AttachmentsList,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        template: str | Carousel | None = None,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage: ...

    @typing.overload
    async def answer(
        self,
        message: str | None = None,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        attachment: SingleAttachment,
        attachments: AttachmentsList,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        template: str | Carousel | None = None,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage: ...

    @typing.overload
    async def answer(
        self,
        message: str | None = None,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        template: str | Carousel | None = None,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage: ...

    async def answer(
        self,
        message: str | None = None,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        attachment: SingleAttachment | None = None,
        attachments: AttachmentsList | None = None,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        template: str | Carousel | None = None,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        content_source: str | None = None,
        view: View | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage:
        """
        Отправляет сообщение в тот же чат

        :param message: Текст сообщения
        :param delete_after: Удалить сообщение через указанное количество секунд.
            Если None - сообщение не удаляется автоматически.

        Example:
            # Отправить сообщение и удалить через 5 секунд
            await msg.answer("Это сообщение исчезнет!", delete_after=5)
        """
        if view is not None:
            keyboard = view.to_keyboard()

        params = dict(
            message=message,
            random_id=random_id_() if random_id is None else random_id,
            lat=lat,
            long=long,
            attachment=attachment,
            attachments=attachments,
            sticker_id=sticker_id,
            group_id=group_id,
            keyboard=keyboard,
            payload=payload,
            dont_parse_links=dont_parse_links,
            disable_mentions=disable_mentions,
            intent=intent,
            expire_ttl=expire_ttl,
            silent=silent,
            subscribe_id=subscribe_id,
            content_source=content_source,
            template=template,
            peer_ids=self.truncated_message.peer_id,
            **kwargs,
        )

        sent_message = await self._send_message(params)

        if view is not None:
            view.message = sent_message

            if hasattr(self, "bot") and hasattr(self.bot, "app") and hasattr(self.bot.app, "view_store"):
                self.bot.app.view_store.add(view)

        if delete_after is not None:
            await sent_message.delete(delay=delete_after)

        return sent_message

    @typing.overload
    async def forward(
        self,
        message: str | None = None,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        attachment: SingleAttachment,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        template: str | Carousel | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage: ...

    @typing.overload
    async def forward(
        self,
        message: str | None = None,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        attachments: AttachmentsList,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        template: str | Carousel | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage: ...

    @typing.overload
    async def forward(
        self,
        message: str | None = None,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        attachment: SingleAttachment,
        attachments: AttachmentsList,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        template: str | Carousel | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage: ...

    @typing.overload
    async def forward(
        self,
        message: str | None = None,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        template: str | Carousel | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        **kwargs,
    ) -> SentMessage: ...

    async def forward(
        self,
        message: str | None = None,
        *,
        random_id: int | None = None,
        lat: float | None = None,
        long: float | None = None,
        attachment: SingleAttachment | None = None,
        attachments: AttachmentsList | None = None,
        sticker_id: int | None = None,
        group_id: int | None = None,
        keyboard: str | Keyboard | None = None,
        payload: str | None = None,
        dont_parse_links: bool | None = None,
        disable_mentions: bool = True,
        intent: str | None = None,
        expire_ttl: int | None = None,
        silent: bool | None = None,
        subscribe_id: int | None = None,
        template: str | Carousel | None = None,
        content_source: str | None = None,
        delete_after: int | float | None = None,
        view: View | None = None,
        **kwargs,
    ) -> SentMessage:
        """
        Пересылает сообщение

        :param message: Текст сообщения
        :param delete_after: Удалить сообщение через указанное количество секунд.
            Если None - сообщение не удаляется автоматически.
        :param view: Interactive View with buttons

        Example:
            # Переслать и удалить через 5 секунд
            await msg.forward("Пересланное сообщение", delete_after=5)
        """
        if view is not None:
            keyboard = view.to_keyboard()

        params = dict(
            message=message,
            random_id=random_id_() if random_id is None else random_id,
            lat=lat,
            long=long,
            attachment=attachment,
            attachments=attachments,
            sticker_id=sticker_id,
            group_id=group_id,
            keyboard=keyboard,
            payload=payload,
            dont_parse_links=dont_parse_links,
            disable_mentions=disable_mentions,
            intent=intent,
            expire_ttl=expire_ttl,
            silent=silent,
            subscribe_id=subscribe_id,
            content_source=content_source,
            template=template,
            peer_ids=self.truncated_message.peer_id,
            **kwargs,
        )

        match self.truncated_message.id:
            case msg_id if msg_id:
                params["forward_messages"] = msg_id
            case _:
                params["forward"] = {
                    "conversation_message_ids": [self.truncated_message.conversation_message_id],
                    "peer_id": self.truncated_message.peer_id,
                }

        sent_message = await self._send_message(params)

        if view is not None:
            view.message = sent_message

            if hasattr(self, "bot") and hasattr(self.bot, "app") and hasattr(self.bot.app, "view_store"):
                self.bot.app.view_store.add(view)

        if delete_after is not None:
            await sent_message.delete(delay=delete_after)

        return sent_message


class CallbackButtonPressedMessage(Wrapper):
    @property
    def peer_id(self) -> int:
        return self.fields["peer_id"]

    @property
    def user_id(self) -> int:
        return self.fields["user_id"]

    @property
    def from_id(self) -> int:
        return self.user_id

    @property
    def conversation_message_id(self) -> int:
        return self.fields["conversation_message_id"]

    @property
    def event_id(self) -> str:
        return self.fields["event_id"]

    @functools.cached_property
    def payload(self) -> dict | None:
        return self.fields["payload"]

    @property
    def cmid(self) -> int:
        return self.conversation_message_id
