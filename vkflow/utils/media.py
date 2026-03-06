import datetime
import re
import ssl

import aiohttp

from vkflow.json_parsers import json_parser_policy


async def download_file(
    url: str,
    *,
    session: aiohttp.ClientSession | None = None,
    **kwargs,
) -> bytes:
    """
    Скачивание файлов по их прямой ссылке.
    """
    if session is not None:
        async with session.get(url, **kwargs) as response:
            return await response.read()

    async with (
        aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=ssl.create_default_context()),
            skip_auto_headers={"User-Agent"},
            raise_for_status=True,
            json_serialize=json_parser_policy.dumps,
        ) as new_session,
        new_session.get(url, **kwargs) as response,
    ):
        return await response.read()


_registration_date_regex = re.compile('ya:created dc:date="(?P<date>.*?)"')


async def get_user_registration_date(
    id_: int, *, session: aiohttp.ClientSession | None = None
) -> datetime.datetime:
    """
    Получает дату регистрации пользователя ВКонтакте
    через публичный FOAF endpoint.
    """
    request_session = session or aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=False),
        skip_auto_headers={"User-Agent"},
        raise_for_status=True,
        json_serialize=json_parser_policy.dumps,
    )
    async with (
        request_session,
        request_session.get("https://vk.ru/foaf.php", params={"id": id_}) as response,
    ):
        user_info = await response.text()
        registration_date = _registration_date_regex.search(user_info)
        if registration_date is None:
            raise ValueError(f"No such user with id `{id_}`")
        registration_date = registration_date.group("date")
        return datetime.datetime.fromisoformat(registration_date)
