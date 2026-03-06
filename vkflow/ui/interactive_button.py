from __future__ import annotations

import typing

from vkflow.ui.button import InitializedButton

if typing.TYPE_CHECKING:  # pragma: no cover
    from vkflow.app.storages import CallbackButtonPressed


class InteractiveButton(InitializedButton):
    def __init__(
        self,
        label: str,
        *,
        color: str = "secondary",
        payload: dict | str | None = None,
        custom_id: str | None = None,
    ):
        self.custom_id = custom_id or self.__class__.__name__

        self._label = label
        self._color = color

        self._base_payload = payload or {}

        if isinstance(self._base_payload, dict):
            callback_payload = {
                **self._base_payload,
                "__button_class": self.__class__.__name__,
                "__button_id": self.custom_id,
            }
        else:
            callback_payload = self._base_payload

        super().__init__(
            label=label,
            type="callback",
            payload=callback_payload,
        )

        self.scheme["color"] = color

    async def callback(self, interaction: CallbackButtonPressed) -> None:
        pass

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, value: str) -> None:
        self._label = value
        self.scheme["action"]["label"] = value

    @property
    def color(self) -> str:
        return self._color

    @color.setter
    def color(self, value: str) -> None:
        self._color = value
        self.scheme["color"] = value
