from __future__ import annotations

import asyncio
import enum
import io
import os
import re
import time
import typing
import urllib.parse

import aiofiles
import aiohttp
import cachetools

from loguru import logger

from vkflow import error_codes
from vkflow.__meta__ import __vk_api_version__
from vkflow.base.api_serializable import APISerializableMixin
from vkflow.base.session_container import SessionContainerMixin
from vkflow.utils.media import download_file
from vkflow.models.attachment import (
    Document,
    Photo,
    Video as VideoWrapper,
)
from vkflow.models.page import Group, Page, User
from vkflow.exceptions import APIError
from vkflow.json_parsers import json_parser_policy
from vkflow.logger import format_mapping
from vkflow.pretty_view import pretty_view
from vkflow.utils.dotdict import wrap_response

if typing.TYPE_CHECKING:  # pragma: no cover
    from vkflow.base.json_parser import BaseJSONParser

    PhotoEntityTyping: typing.TypeAlias = str | bytes | typing.BinaryIO | os.PathLike
    RequestParams: typing.TypeAlias = dict[str, typing.Any]
    APIResponse: typing.TypeAlias = typing.Any
    MethodName: typing.TypeAlias = str


@enum.unique
class TokenOwner(enum.Enum):
    """
    Тип владельца токена: пользователь/группа/не определено
    """

    USER = enum.auto()
    GROUP = enum.auto()
    UNKNOWN = enum.auto()


class API(SessionContainerMixin):
    def __init__(
        self,
        token: str,
        token_owner: TokenOwner = TokenOwner.UNKNOWN,
        version: str = __vk_api_version__,
        requests_url: str = "https://api.vk.ru/method/",
        requests_session: aiohttp.ClientSession | None = None,
        json_parser: BaseJSONParser | None = None,
        cache_table: cachetools.Cache | None = None,
        proxies: list[str] | None = None,
        max_retries: int = 5,
        retry_initial_delay: float = 1.0,
        retry_max_delay: float = 30.0,
    ):
        SessionContainerMixin.__init__(self, requests_session=requests_session, json_parser=json_parser)

        if token.startswith("$"):
            self._token = os.environ[token[1:]]
        else:
            self._token = token

        self._version = version
        self._token_owner = token_owner
        self._owner_schema = None
        self._requests_url = requests_url
        self._proxies = proxies
        self._cache_table = cache_table or cachetools.TTLCache(ttl=7200, maxsize=2**12)

        self._method_name = ""
        self._last_request_timestamp = 0.0
        self._use_cache = False

        self._stable_request_params = {
            "access_token": self._token,
            "v": self._version,
        }

        self._max_retries = max_retries
        self._retry_initial_delay = retry_initial_delay
        self._retry_max_delay = retry_max_delay
        self._rate_limit_lock = asyncio.Lock()

        self._update_requests_delay()

    @property
    def token_owner(self) -> TokenOwner:
        return self._token_owner

    @property
    def owner(self) -> Page | None:
        return self._owner_schema

    def use_cache(self) -> API:
        """
        Включает кэширование для следующего запроса.
        Кэширование выключается автоматически, т.е.
        кэширование будет использовано только для первого следующего
        выполняемого API запроса.

        Включение кэширования подразумевает, что следующий запрос
        будет занесен в специальную кэш-таблицу. Ключ кэша
        привязывается к имени вызываемого метода и переданным параметрам,
        а значение -- к ответу API. Если запрос с таким именем метода
        и такими параметрами уже был выполнен когда-то, то вместо
        отправки запроса будет возвращено значение из кэш-таблицы

        Если необходимо передать свою собственную имплементацию
        кэш-таблицы, укажите соответствующий инстанс при инициализации объекта
        в поле `cache_table`. По умолчанию используется TTL-алгоритм.

        Returns:
            Тот же самый инстанс API, готовый к кэшированному запросу
        """
        self._use_cache = True
        return self

    async def define_token_owner(self) -> tuple[TokenOwner, Page]:
        """
        Позволяет определить владельца токена: группа или пользователь.

        Метод использует кэширование, поэтому в своем коде
        можно смело каждый раз вызывать этот метод, не боясь лишних
        исполняемых запросов

        Владелец токена будет определен автоматически после первого выполненного
        запроса для определения задержки, если `token_owner` поле
        не было установленно вручную при инициализации объекта

        Returns:
            Возвращает словарь, первый элемент которого TokenOwner значение,
            указывающее, группа это или пользователь, а в второй -- сама схема объекта
            сущности пользователя/группы, обернутая соответствующим враппером
        :rtype:
        """
        if self._token_owner != TokenOwner.UNKNOWN and self._owner_schema is not None:
            return self._token_owner, self._owner_schema

        owner_schema = await self.use_cache().method("users.get")

        if owner_schema and isinstance(owner_schema, list) and len(owner_schema) > 0:
            self._owner_schema = User(owner_schema[0])
            self._token_owner = TokenOwner.USER

        else:
            owner_schema = await self.use_cache().method("groups.get_by_id")

            if owner_schema and isinstance(owner_schema, (list, dict)):
                group_data = None

                if isinstance(owner_schema, list) and len(owner_schema) > 0:
                    group_data = owner_schema[0]

                elif isinstance(owner_schema, dict):
                    if (
                        "groups" in owner_schema
                        and isinstance(owner_schema["groups"], list)
                        and len(owner_schema["groups"]) > 0
                    ):
                        group_data = owner_schema["groups"][0]
                    elif "id" in owner_schema:
                        group_data = owner_schema
                    else:
                        raise ValueError(
                            f"groups.get_by_id returned invalid response: {owner_schema}. "
                            "Expected group object with 'id' field or dict with 'groups' key. "
                            "Please check your access token."
                        )

                if group_data is None or not isinstance(group_data, dict) or "id" not in group_data:
                    raise ValueError(
                        f"groups.get_by_id returned invalid group data: {group_data}. "
                        "Expected dict with 'id' field."
                    )

                self._owner_schema = Group(group_data)
                self._token_owner = TokenOwner.GROUP

            else:
                raise ValueError(
                    "Unable to determine token owner. "
                    "Both users.get and groups.get_by_id failed. "
                    "Please check your access token."
                )

        self._update_requests_delay()
        return self._token_owner, self._owner_schema

    def _update_requests_delay(self) -> None:
        """
        Устанавливает необходимую задержку в секундах между
        исполняемыми запросами
        """
        if self._token_owner in {TokenOwner.USER, TokenOwner.UNKNOWN}:
            self._requests_delay = 1 / 3
        else:
            self._requests_delay = 1 / 20

    def __getattr__(self, attribute: str) -> API:
        """
        Используя `__getattr__`, класс предоставляет возможность
        вызывать методы API, как будто бы обращаясь к атрибутам.

        Arguments:
            attribute: Имя/заголовок названия метода
        Returns:
            Собственный инстанс класса для того,
            чтобы была возможность продолжить выстроить имя метода через точку
        """
        if self._method_name:
            self._method_name += f".{attribute}"
        else:
            self._method_name = attribute

        return self

    async def __call__(
        self,
        **request_params,
    ) -> typing.Any:
        """
        Вызывает метод `method` после обращения к имени метода через `__getattr__`

        Arguments:
            request_params: Параметры, принимаемые методом, которые описаны в документации API

        Returns:
            Пришедший от API ответ
        """
        method_name = self._method_name
        self._method_name = ""

        return await self.method(method_name, **request_params)

    async def method(self, method_name: str, **request_params: typing.Any) -> typing.Any:
        """
        Выполняет необходимый API запрос с нужным методом и параметрами.
        Вызов метода поддерживает конвертацию из snake_case в camelCase.

        Перед вызовом этого метода может быть вызван `.use_cache()` для
        включения возможности кэш-логики запроса

        Каждый передаваемый параметр проходит специальный этап конвертации перед
        передачей в запрос по следующему принципу:

        * Все элементы списков, кортежей и множеств проходят конвертацию рекурсивно и
            объединяются в строку через `,`
        * Все словари автоматически дампятся в JSON-строку установленным JSON-парсером
        * Все True/False значения становятся 1 и 0 соответственно (требуется для aiohttp)
        * Если переданный объект имплементирует класс `APISerializableMixin`,
            вызывается соответствующий метод класса для конвертации в желаемое
            значение

        К параметрам автоматически добавляются `access_token` (ключ доступа) и `v` (версия API),
        переданные при инициализации, но каждый из этих полей может быть задан вручную для
        конкретного запроса. Например, необходимо вызвать метод с другой версией API
        или передать другой токен.


        Arguments:
            method_name: Имя вызываемого метода API
            request_params: Параметры, принимаемые методом, которые описаны в документации API.

        Returns:
            Пришедший от API ответ.

        Raises:
            VKAPIError: В случае ошибки, пришедшей от некорректного вызова запроса.
        """
        use_cache = self._use_cache
        self._use_cache = False

        return await self._make_api_request(
            method_name=method_name,
            request_params=request_params,
            use_cache=use_cache,
        )

    async def execute(self, *code: str | CallMethod) -> typing.Any:
        """
        Исполняет API метод `execute` с переданным VKScript-кодом.

        Arguments:
            code: VKScript код

        Returns:
            Пришедший ответ от API

        Raises:
            VKAPIError: В случае ошибки, пришедшей от некорректного вызова запроса.
        """
        if not isinstance(code[0], str):
            code = "return [{}];".format(", ".join(call.to_execute() for call in code))

        return await self.method("execute", code=code)

    async def _make_api_request(
        self,
        method_name: str,
        request_params: dict[str, typing.Any],
        use_cache: bool,
    ) -> typing.Any:
        """
        Выполняет API запрос на определенный метод с заданными параметрами

        Arguments:
            method_name: Имя метода API
            request_params: Параметры, переданные для метода
            use_cache: Использовать кэширование

        Raises:
            VKAPIError: В случае ошибки, пришедшей от некорректного вызова запроса.
        """
        real_method_name = _convert_method_name(method_name)
        real_request_params = _convert_params_for_api(request_params)

        extra_request_params = self._stable_request_params.copy()
        extra_request_params.update(real_request_params)

        if self._token_owner is None:
            self._token_owner = TokenOwner.UNKNOWN

        if use_cache:
            cache_hash = urllib.parse.urlencode(real_request_params)
            cache_hash = f"{method_name}#{cache_hash}"

            if cache_hash in self._cache_table:
                return self._cache_table[cache_hash]

        async with self._rate_limit_lock:
            api_request_delay = self._get_waiting_time()
            await asyncio.sleep(api_request_delay)

        response = await self._send_api_request(real_method_name, extra_request_params)

        logger.opt(colors=True).info(
            **format_mapping(
                "Called method <m>{method_name}</m>({params})",
                "<c>{key}</c>=<y>{value!r}</y>",
                real_request_params,
            ),
            method_name=real_method_name,
        )

        logger.opt(lazy=True).debug("Response is: {response}", response=lambda: pretty_view(response))

        if "error" in response:
            error = response["error"].copy()
            exception_class = APIError[error["error_code"]]

            raise exception_class(
                status_code=error.pop("error_code"),
                description=error.pop("error_msg"),
                request_params=error.pop("request_params"),
                extra_fields=error,
            )
        response = response["response"]
        response = wrap_response(response)

        if use_cache:
            self._cache_table[cache_hash] = response

        return response

    def _get_retry_delay(self, attempt: int) -> float:
        delay = self._retry_initial_delay * (2**attempt)
        return min(delay, self._retry_max_delay)

    async def _send_api_request(self, method_name: str, params: dict) -> dict:
        """
        Выполняет сам API запрос с готовыми параметрами и именем метода

        Arguments:
            method_name: Имя метода
            params: Словарь параметров

        Returns:
            Сырой ответ от API
        """
        if self._proxies is not None:
            current_proxy = self._proxies.pop(0)
            self._proxies.append(current_proxy)
        else:
            current_proxy = None

        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                async with self.requests_session.post(
                    self._requests_url + method_name, data=params, proxy=current_proxy
                ) as response:
                    response = await self.parse_json_body(response)
                    if "error" in response and response["error"]["error_code"] == 10:
                        delay = self._get_retry_delay(attempt)
                        logger.opt(colors=True).warning(
                            **format_mapping(
                                "VK Internal server error while calling <m>{method_name}</m>({params}): {error_message}. "
                                "Retry {attempt}/{max_retries} in {delay}s...",
                                "<c>{key}</c>=<y>{value!r}</y>",
                                params,
                            ),
                            method_name=method_name,
                            error_message=response["error"]["error_msg"],
                            attempt=attempt + 1,
                            max_retries=self._max_retries,
                            delay=delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        return response

            except aiohttp.ClientResponseError as error:
                if error.status >= 500:
                    delay = self._get_retry_delay(attempt)
                    logger.opt(colors=True).warning(
                        **format_mapping(
                            "Server error while calling <m>{method_name}</m>({params}): {error_message}. "
                            "Retry {attempt}/{max_retries} in {delay}s...",
                            "<c>{key}</c>=<y>{value!r}</y>",
                            params,
                        ),
                        method_name=method_name,
                        error_message=error.message,
                        attempt=attempt + 1,
                        max_retries=self._max_retries,
                        delay=delay,
                    )

                    last_error = error
                    await asyncio.sleep(delay)
                else:
                    raise error

            except aiohttp.ServerDisconnectedError:
                last_error = aiohttp.ServerDisconnectedError()
                await self.refresh_session()

        raise ConnectionError(
            f"Max retries ({self._max_retries}) exceeded for {method_name}"
        ) from last_error

    async def _fetch_file_entity(self, file: str | bytes | typing.BinaryIO | os.PathLike) -> bytes:
        """
        Получает байты файла через IO-хранилища/ссылку/путь до файла
        """
        if isinstance(file, bytes):
            return file
        if isinstance(file, io.BytesIO):
            return file.getvalue()
        if isinstance(file, str) and file.startswith("http"):
            return await download_file(file, session=self.requests_session)
        if isinstance(file, (str, os.PathLike)):
            async with aiofiles.open(file, "rb") as f:
                return await f.read()
        else:
            raise TypeError(
                "Can't recognize file entity. "
                "Accept only bytes, BytesIO, "
                "URL-like string and Path-like object or string"
            )

    async def upload_photos_to_message(self, *photos: PhotoEntityTyping, peer_id: int = 0) -> list[Photo]:
        """
        Загружает фотографию в сообщения

        Arguments:
            photos: Фотографии в виде ссылки/пути до файла/сырых байтов/
                IO-хранилища/Path-like объекта
            peer_id: ID диалога или беседы, куда загружаются фотографии. Если
                не передавать, то фотографии загрузятся в скрытый альбом. Рекомендуется
                исключительно для тестирования, т.к. такой альбом имеет лимиты
        Returns:
            Список врапперов загруженных фотографий, который можно напрямую
            передать в поле `attachment` при отправке сообщения
        """
        photo_bytes_coroutines = [self._fetch_file_entity(photo) for photo in photos]

        photo_bytes = await asyncio.gather(*photo_bytes_coroutines)

        async def upload_batch(batch: list[bytes]) -> list[Photo]:
            data_storage = aiohttp.FormData()

            for ind, photo in enumerate(batch):
                data_storage.add_field(
                    f"file{ind}",
                    photo,
                    content_type="multipart/form-data",
                    filename="a.png",
                )

            uploading_info = await self.method("photos.get_messages_upload_server", peer_id=peer_id)

            async with self.requests_session.post(
                uploading_info["upload_url"], data=data_storage
            ) as response:
                response = await self.parse_json_body(response, content_type=None)

            try:
                uploaded_photos = await self.method("photos.save_messages_photo", **response)
            except APIError[error_codes.CODE_1_UNKNOWN]:
                logger.exception(
                    "Не удалось загрузить фотографии в беседу сообщества. "
                    "VK пока не позволяет загружать фотографии в беседу сообщества"
                )

                return []
            else:
                return [Photo(uploaded_photo) for uploaded_photo in uploaded_photos]

        batches = [photo_bytes[i : i + 5] for i in range(0, len(photo_bytes), 5)]

        upload_coroutines = [upload_batch(batch) for batch in batches]
        results = await asyncio.gather(*upload_coroutines)

        result_photos = []

        for batch_result in results:
            result_photos.extend(batch_result)

        return result_photos

    async def upload_doc_to_message(
        self,
        content: str | bytes,
        filename: str,
        *,
        tags: str | None = None,
        return_tags: bool | None = None,
        type: typing.Literal["doc", "audio_message", "graffiti"] = "doc",
        peer_id: int = 0,
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
            peer_id: ID диалога или беседы, куда загружается документ

        Returns:
            Враппер загруженного документа. Этот объект можно напрямую
            передать в поле `attachment` при отправке сообщения
        """
        if "." not in filename:
            filename = f"{filename}.txt"

        data_storage = aiohttp.FormData()
        data_storage.add_field(
            "file",
            content,
            content_type="multipart/form-data",
            filename=filename,
        )

        uploading_info = await self.method("docs.get_messages_upload_server", peer_id=peer_id, type=type)

        async with self.requests_session.post(uploading_info["upload_url"], data=data_storage) as response:
            response = await self.parse_json_body(response, content_type=None)

        document = await self.method(
            "docs.save",
            **response,
            tags=tags,
            title=filename,
            return_tags=return_tags,
        )

        return Document(document[type])

    async def upload_video_to_message(
        self,
        file: str | bytes | typing.BinaryIO | os.PathLike,
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
    ) -> VideoWrapper:
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
        file_bytes = await self._fetch_file_entity(file)

        data_storage = aiohttp.FormData()
        data_storage.add_field(
            "video_file",
            file_bytes,
            content_type="multipart/form-data",
            filename=name or "video.mp4",
        )

        save_params = {
            "name": name,
            "description": description,
            "is_private": is_private,
            "wallpost": wallpost,
            "link": link,
            "group_id": group_id,
            "album_id": album_id,
            "privacy_view": privacy_view,
            "privacy_comment": privacy_comment,
            "no_comments": no_comments,
            "repeat": repeat,
            "compression": compression,
        }

        save_params = {k: v for k, v in save_params.items() if v is not None}
        uploading_info = await self.method("video.save", **save_params)

        async with self.requests_session.post(uploading_info["upload_url"], data=data_storage) as response:
            await self.parse_json_body(response, content_type=None)

        return VideoWrapper(
            {
                "id": uploading_info.get("video_id"),
                "owner_id": uploading_info.get("owner_id"),
                "title": name or "",
                "description": description or "",
            }
        )

    def _get_waiting_time(self) -> float:
        """
        Рассчитывает обязательное время задержки после
        последнего API запроса. Для групп -- 0.05s,
        для пользователей/сервисных токенов -- 0.333s

        Returns:
            Время, необходимое для ожидания.
        """
        now = time.time()
        diff = now - self._last_request_timestamp

        if diff < self._requests_delay:
            wait_time = self._requests_delay - diff
            self._last_request_timestamp += wait_time

            return wait_time

        self._last_request_timestamp = now
        return 0.0


def _convert_param_value(value, /):
    """
    Конвертирует параметр API запроса в соответствии
    с особенностями API и дополнительными удобствами

    Arguments:
        value: Текущее значение параметра

    Returns:
        Новое значение параметра

    """
    match value:
        case list() | set() | tuple():
            updated_sequence = map(_convert_param_value, value)
            return ",".join(updated_sequence)
        case dict():
            return json_parser_policy.dumps(value)
        case bool():
            return int(value)
        case APISerializableMixin():
            new_value = value.represent_as_api_param()
            return _convert_param_value(new_value)
        case _:
            return str(value)


def _convert_params_for_api(params: dict, /):
    """
    Конвертирует словарь из параметров для метода API,
    учитывая определенные особенности

    Arguments:
        params: Параметры, передаваемые для вызова метода API

    Returns:
        Новые параметры, которые можно передать
        в запрос и получить ожидаемый результат

    """
    return {key: _convert_param_value(value) for key, value in params.items() if value is not None}


def _upper_zero_group(match: typing.Match, /) -> str:
    """
    Поднимает все символы в верхний
    регистр у captured-группы `let`. Используется
    для конвертации snake_case в camelCase.

    Arguments:
      match: Регекс-группа, полученная в результате `re.sub`

    Returns:
        Ту же букву из группы, но в верхнем регистре

    """
    return match.group("let").upper()


def _convert_method_name(name: str, /) -> str:
    """
    Конвертирует snake_case в camelCase.

    Arguments:
      name: Имя метода, который необходимо перевести в camelCase

    Returns:
        Новое имя метода в camelCase

    """
    return re.sub(r"_(?P<let>[a-z])", _upper_zero_group, name)


class CallMethod:
    pattern = "API.{name}({{{params}}})"
    param_pattern = "{key!r}: {value!r}"

    def __init__(self, name: str, **params):
        self.name = name
        self.params = params

    def to_execute(self) -> str:
        params_string = ", ".join(
            self.param_pattern.format(key=key, value=_convert_param_value(value))
            for key, value in self.params.items()
        )

        return self.pattern.format(name=self.name, params=params_string)
