from __future__ import annotations

import enum


class ButtonColor(enum.StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    POSITIVE = "positive"
    NEGATIVE = "negative"

    BLUE = "primary"
    WHITE = "secondary"
    DEFAULT = "secondary"
    GREEN = "positive"
    RED = "negative"


class ButtonType(enum.StrEnum):
    TEXT = "text"
    CALLBACK = "callback"
    LOCATION = "location"
    VKPAY = "vkpay"
    OPEN_LINK = "open_link"
    OPEN_APP = "open_app"


class CallbackActionType(enum.StrEnum):
    SHOW_SNACKBAR = "show_snackbar"
    OPEN_LINK = "open_link"
    OPEN_APP = "open_app"


Color = ButtonColor | str
BtnType = ButtonType | str
