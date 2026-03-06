from __future__ import annotations

import typing
import functools
import dataclasses

from vkflow.json_parsers import json_parser_policy
from vkflow.ui.button_types import ButtonColor, ButtonType, Color

if typing.TYPE_CHECKING:
    from vkflow.utils.vktypes import DecoratorFunction


@dataclasses.dataclass
class _ButtonHandler:
    handler: typing.Callable


@dataclasses.dataclass
class ButtonOnclickHandler(_ButtonHandler):
    handler: typing.Callable[..., typing.Awaitable]


@dataclasses.dataclass
class ButtonCallbackHandler(_ButtonHandler):
    handler: typing.Callable[..., typing.Awaitable]


class InitializedButton:
    def __init__(self, **scheme) -> None:
        self.scheme = {"action": scheme}

    def _on_action(self, handler: _ButtonHandler, **kwargs) -> InitializedButton:
        if self.scheme["action"].get("payload"):
            raise ValueError(
                "Payload has been already set. "
                "You can set only or onclick handler or "
                "custom payload, not bath at hte same time"
            )

        schema = {"command": handler.handler.__name__, "args": kwargs}
        self.scheme["action"]["payload"] = json_parser_policy.dumps(schema)

        return self


ClickableOrCallable = typing.TypeVar("ClickableOrCallable")


class _ColoredButton(InitializedButton):
    def positive(self: ClickableOrCallable) -> ClickableOrCallable:
        self.scheme["color"] = "positive"
        return self

    def negative(self: ClickableOrCallable) -> ClickableOrCallable:
        self.scheme["color"] = "negative"
        return self

    def primary(self: ClickableOrCallable) -> ClickableOrCallable:
        self.scheme["color"] = "primary"
        return self

    def secondary(self: ClickableOrCallable) -> ClickableOrCallable:
        self.scheme["color"] = "secondary"
        return self


class _ClickableColoredButton(_ColoredButton):
    def on_click(self, handler: ButtonOnclickHandler, **kwargs) -> InitializedButton:
        return self._on_action(handler, **kwargs)


class _CallableColoredButton(_ColoredButton):
    def on_called(self, handler: ButtonCallbackHandler, **kwargs):
        return self._on_action(handler, **kwargs)


class _UncoloredButton(InitializedButton): ...


def _convert_payload(func: DecoratorFunction) -> DecoratorFunction:
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if "payload" in kwargs:
            if isinstance(kwargs["payload"], dict):
                kwargs["payload"] = json_parser_policy.dumps(kwargs["payload"])

            elif not isinstance(kwargs["payload"], str):
                raise TypeError("Invalid type for payload. Payload can be only str, dict or not passed")

        return func(*args, **kwargs)

    return wrapper


class Button:
    @classmethod
    @_convert_payload
    def text(
        cls,
        label: str,
        *,
        payload: str | dict | None = None,
        color: Color = ButtonColor.SECONDARY,
    ) -> _ClickableColoredButton:
        btn = _ClickableColoredButton(label=label, type=ButtonType.TEXT.value, payload=payload)

        color_str = color.value if isinstance(color, ButtonColor) else color
        btn.scheme["color"] = color_str

        return btn

    @classmethod
    @_convert_payload
    def callback(
        cls,
        label: str,
        *,
        payload: str | dict | None = None,
        color: Color = ButtonColor.SECONDARY,
    ) -> _CallableColoredButton:
        btn = _CallableColoredButton(label=label, type=ButtonType.CALLBACK.value, payload=payload)

        color_str = color.value if isinstance(color, ButtonColor) else color
        btn.scheme["color"] = color_str

        return btn

    @classmethod
    @_convert_payload
    def location(
        cls,
        *,
        payload: str | dict | None = None,
    ) -> _UncoloredButton:
        return _UncoloredButton(type=ButtonType.LOCATION.value, payload=payload)

    @classmethod
    @_convert_payload
    def vkpay(
        cls,
        *,
        hash_: str,
        payload: str | dict | None = None,
    ) -> _UncoloredButton:
        return _UncoloredButton(hash=hash_, type=ButtonType.VKPAY.value, payload=payload)

    @classmethod
    @_convert_payload
    def open_link(
        cls,
        label: str,
        *,
        link: str,
        payload: str | dict | None = None,
    ) -> _UncoloredButton:
        return _UncoloredButton(
            label=label,
            link=link,
            type=ButtonType.OPEN_LINK.value,
            payload=payload,
        )

    @classmethod
    @_convert_payload
    def open_app(
        cls,
        label: str,
        *,
        app_id: int,
        owner_id: int,
        hash_: str = "",
        payload: str | dict | None = None,
    ) -> _UncoloredButton:
        return _UncoloredButton(
            label=label,
            app_id=app_id,
            owner_id=owner_id,
            hash=hash_,
            type=ButtonType.OPEN_APP.value,
            payload=payload,
        )
