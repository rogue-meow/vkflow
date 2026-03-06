"""
Имплементации разных JSON парсеров
"""

import json
import typing

from vkflow.base.json_parser import BaseJSONParser


try:
    import msgspec  # pyright: ignore[reportMissingImports]

    class MsgspecParser(BaseJSONParser):
        _encoder = msgspec.json.Encoder()

        @staticmethod
        def dumps(data: typing.Any) -> str:
            return MsgspecParser._encoder.encode(data).decode("utf8")

        @staticmethod
        def loads(string: str | bytes) -> typing.Any:
            return msgspec.json.decode(string)
except ImportError:  # pragma: no cover
    msgspec = None
    MsgspecParser = None

try:
    import orjson  # pyright: ignore[reportMissingImports]
except ImportError:  # pragma: no cover
    orjson = None

try:
    import ujson  # pyright: ignore[reportMissingImports]
except ImportError:  # pragma: no cover
    ujson = None


class BuiltinJsonParser(BaseJSONParser):
    @staticmethod
    def dumps(data: typing.Any) -> str:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def loads(string: str | bytes) -> typing.Any:
        return json.loads(string)


class OrjsonParser(BaseJSONParser):
    @staticmethod
    def dumps(data: typing.Any) -> str:
        return orjson.dumps(data).decode("utf8")  # pragma: no cover

    @staticmethod
    def loads(string: str | bytes) -> typing.Any:
        return orjson.loads(string)  # pragma: no cover


class UjsonParser(BaseJSONParser):
    @staticmethod
    def dumps(data: typing.Any) -> str:
        return ujson.dumps(data, ensure_ascii=False)  # pragma: no cover

    @staticmethod
    def loads(string: str | bytes) -> typing.Any:
        return ujson.loads(string)  # pragma: no cover


def _select_parser() -> type[BaseJSONParser]:
    if msgspec is not None:
        return MsgspecParser
    if orjson is not None:
        return OrjsonParser
    if ujson is not None:
        return UjsonParser
    return BuiltinJsonParser


json_parser_policy: type[BaseJSONParser] = _select_parser()
