from __future__ import annotations

import typing

from vkflow.base.ui_builder import UIBuilder
from vkflow.models.attachment import Photo

if typing.TYPE_CHECKING:
    from vkflow.ui.button import InitializedButton


class Element(UIBuilder):
    def __init__(
        self,
        *,
        buttons: list[InitializedButton],
        title: str | None = None,
        description: str | None = None,
        photo_id: str | Photo | None = None,
    ) -> None:
        self.scheme = {"buttons": [but.scheme for but in buttons]}
        if title is not None:
            self.scheme.update(title=title)

        if description is not None:
            self.scheme.update(description=description)

        if photo_id is not None:
            if isinstance(photo_id, Photo):
                photo_id = photo_id.represent_as_api_param()
            self.scheme.update(photo_id=photo_id)

    def open_link(self, link) -> Element:
        self.scheme["action"] = {"type": "open_link", "link": link}
        return self

    def open_photo(self) -> Element:
        self.scheme["action"] = {"type": "open_photo"}
        return self


class Carousel(UIBuilder):
    def __init__(self, gen: typing.Callable[..., typing.Iterator[Element]]) -> None:
        self._gen = gen
        self.scheme = {
            "type": "carousel",
            "elements": [elem.scheme for elem in self._gen()],
        }

    @classmethod
    def build(cls, *elements: Element) -> Carousel:
        return cls(elements.__iter__)
