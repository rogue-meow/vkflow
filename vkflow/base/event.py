from __future__ import annotations

import abc
import typing


EventType = str | int
ContentT = typing.TypeVar("ContentT", dict, list)


class BaseEvent(abc.ABC, typing.Generic[ContentT]):
    def __init__(self, content: ContentT):
        self._content = content

    @property
    def content(self) -> ContentT:
        """
        Сырой объект события (то, что пришло в `updates`)
        """
        return self._content

    @property
    @abc.abstractmethod
    def object(self) -> dict | list: ...

    @property
    @abc.abstractmethod
    def type(self) -> EventType: ...

    def __repr__(self) -> str:
        return f"<vkflow.{self.__class__.__name__} type={self.type!r}>"
