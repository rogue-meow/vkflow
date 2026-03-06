from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    import aiohttp

from vkflow.base.api_serializable import APISerializableMixin
from vkflow.base.wrapper import Wrapper
from vkflow.utils.media import download_file


class Attachment(Wrapper, APISerializableMixin):
    _name = None

    def represent_as_api_param(self) -> str:
        access_key = f"""_{self.fields["access_key"]}""" if "access_key" in self.fields else ""

        return "{type}{owner_id}_{attachment_id}{access_key}".format(
            type=self._name,
            owner_id=self.fields["owner_id"],
            attachment_id=self.fields["id"],
            access_key=access_key,
        )


class Photo(Attachment):
    _name = "photo"

    async def download_min_size(self, *, session: aiohttp.ClientSession | None = None) -> bytes:
        return await download_file(self.fields["sizes"][0]["url"], session=session)

    async def download_with_size(
        self,
        size: str,
        *,
        session: aiohttp.ClientSession | None = None,
    ) -> bytes:
        for photo_size in self.fields["sizes"]:
            if photo_size["type"] == size:
                return await download_file(photo_size["url"], session=session)
        raise ValueError(f"There isn’t a size `{size}` in available sizes")

    async def download_max_size(self, *, session: aiohttp.ClientSession | None = None) -> bytes:
        return await download_file(self.fields["sizes"][-1]["url"], session=session)


class Document(Attachment):
    _name = "doc"

    async def download(self, *, session: aiohttp.ClientSession | None = None) -> bytes:
        return await download_file(self.fields["url"], session=session)

    @property
    def title(self) -> str:
        return self.fields.get("title", "")

    @property
    def ext(self) -> str:
        return self.fields.get("ext", "")

    @property
    def size(self) -> int:
        return self.fields.get("size", 0)


class Video(Attachment):
    _name = "video"

    @property
    def title(self) -> str:
        return self.fields.get("title", "")

    @property
    def description(self) -> str:
        return self.fields.get("description", "")

    @property
    def duration(self) -> int:
        return self.fields.get("duration", 0)

    @property
    def views(self) -> int:
        return self.fields.get("views", 0)


class Audio(Attachment):
    _name = "audio"

    @property
    def artist(self) -> str:
        return self.fields.get("artist", "")

    @property
    def title(self) -> str:
        return self.fields.get("title", "")

    @property
    def duration(self) -> int:
        return self.fields.get("duration", 0)

    @property
    def url(self) -> str:
        return self.fields.get("url", "")


class Wall(Attachment):
    _name = "wall"

    @property
    def text(self) -> str:
        return self.fields.get("text", "")

    @property
    def date(self) -> int:
        return self.fields.get("date", 0)


class Sticker(Attachment):
    _name = "sticker"

    @property
    def product_id(self) -> int:
        return self.fields.get("product_id", 0)

    @property
    def images(self) -> list[dict]:
        return self.fields.get("images", [])

    async def download_max_size(self, *, session: aiohttp.ClientSession | None = None) -> bytes:
        if not self.images:
            raise ValueError("No images available for this sticker")
        return await download_file(self.images[-1]["url"], session=session)


class Gift(Attachment):
    _name = "gift"

    @property
    def thumb_256(self) -> str:
        return self.fields.get("thumb_256", "")

    @property
    def thumb_96(self) -> str:
        return self.fields.get("thumb_96", "")

    @property
    def thumb_48(self) -> str:
        return self.fields.get("thumb_48", "")


class Market(Attachment):
    _name = "market"

    @property
    def title(self) -> str:
        return self.fields.get("title", "")

    @property
    def description(self) -> str:
        return self.fields.get("description", "")

    @property
    def price(self) -> dict:
        return self.fields.get("price", {})

    @property
    def thumb_photo(self) -> str:
        return self.fields.get("thumb_photo", "")


class MarketAlbum(Attachment):
    _name = "market_album"

    @property
    def title(self) -> str:
        return self.fields.get("title", "")

    @property
    def count(self) -> int:
        return self.fields.get("count", 0)


class Poll(Attachment):
    _name = "poll"

    @property
    def question(self) -> str:
        return self.fields.get("question", "")

    @property
    def votes(self) -> int:
        return self.fields.get("votes", 0)

    @property
    def answers(self) -> list[dict]:
        return self.fields.get("answers", [])

    @property
    def anonymous(self) -> bool:
        return self.fields.get("anonymous", False)


class Story(Attachment):
    _name = "story"

    @property
    def is_expired(self) -> bool:
        return self.fields.get("is_expired", False)

    @property
    def can_see(self) -> int:
        return self.fields.get("can_see", 0)


class Narrative(Attachment):
    _name = "narrative"

    @property
    def title(self) -> str:
        return self.fields.get("title", "")


class Link(Attachment):
    _name = "link"

    @property
    def url(self) -> str:
        return self.fields.get("url", "")

    @property
    def title(self) -> str:
        return self.fields.get("title", "")

    @property
    def description(self) -> str:
        return self.fields.get("description", "")

    @property
    def caption(self) -> str:
        return self.fields.get("caption", "")


class AudioMessage(Attachment):
    _name = "audio_message"

    @property
    def duration(self) -> int:
        return self.fields.get("duration", 0)

    @property
    def link_ogg(self) -> str:
        return self.fields.get("link_ogg", "")

    @property
    def link_mp3(self) -> str:
        return self.fields.get("link_mp3", "")

    async def download_ogg(self, *, session: aiohttp.ClientSession | None = None) -> bytes:
        return await download_file(self.link_ogg, session=session)

    async def download_mp3(self, *, session: aiohttp.ClientSession | None = None) -> bytes:
        return await download_file(self.link_mp3, session=session)


class Graffiti(Attachment):
    _name = "graffiti"

    @property
    def width(self) -> int:
        return self.fields.get("width", 0)

    @property
    def height(self) -> int:
        return self.fields.get("height", 0)

    @property
    def url(self) -> str:
        return self.fields.get("url", "")

    async def download(self, *, session: aiohttp.ClientSession | None = None) -> bytes:
        return await download_file(self.url, session=session)


ATTACHMENT_TYPES: dict[str, type[Attachment]] = {
    "photo": Photo,
    "doc": Document,
    "video": Video,
    "audio": Audio,
    "wall": Wall,
    "sticker": Sticker,
    "gift": Gift,
    "market": Market,
    "market_album": MarketAlbum,
    "poll": Poll,
    "story": Story,
    "narrative": Narrative,
    "link": Link,
    "audio_message": AudioMessage,
    "graffiti": Graffiti,
}
