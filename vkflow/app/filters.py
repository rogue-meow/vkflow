from __future__ import annotations

import typing
import inspect
import dataclasses

from vkflow.base.filter import BaseFilter
from vkflow.exceptions import StopCurrentHandlingError
from vkflow.utils.helpers import peer

if typing.TYPE_CHECKING:  # pragma: no cover
    from vkflow.app.storages import NewMessage


class OnlyMe(BaseFilter):
    """Принимает только сообщения, отправленные самим ботом."""

    async def make_decision(self, ctx: NewMessage, **kwargs):
        if not ctx.msg.out:
            raise StopCurrentHandlingError()


class IgnoreBots(BaseFilter):
    """Пропускает сообщения от ботов (from_id < 0 в VK API)."""

    async def make_decision(self, ctx: NewMessage, **kwargs):
        if ctx.msg.from_id < 0:
            raise StopCurrentHandlingError()


class ChatOnly(BaseFilter):
    """Пропускает личные сообщения, принимает только групповые чаты."""

    async def make_decision(self, ctx: NewMessage, **kwargs):
        if ctx.msg.peer_id < peer():
            raise StopCurrentHandlingError()


class DirectOnly(BaseFilter):
    """Пропускает групповые чаты, принимает только личные сообщения."""

    async def make_decision(self, ctx: NewMessage, **kwargs):
        if ctx.msg.peer_id >= peer():
            raise StopCurrentHandlingError()


@dataclasses.dataclass
class Dynamic(BaseFilter):
    """Пользовательский фильтр через callable. Поддерживает sync и async функции."""

    executable: typing.Callable[[NewMessage], typing.Any]

    async def make_decision(self, ctx: NewMessage, **kwargs):
        result = self.executable(ctx)
        if inspect.isawaitable(result):
            result = await result
        if not result:
            raise StopCurrentHandlingError()
