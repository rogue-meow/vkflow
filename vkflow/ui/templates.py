from __future__ import annotations

import typing

from vkflow.ui.button import Button, InitializedButton
from vkflow.ui.keyboard import Keyboard

if typing.TYPE_CHECKING:
    from types import EllipsisType


class KeyboardTemplates:
    @staticmethod
    def confirm_cancel(
        *,
        confirm_label: str = "✅ Подтвердить",
        cancel_label: str = "❌ Отменить",
        confirm_payload: dict | str | None = None,
        cancel_payload: dict | str | None = None,
        inline: bool = False,
    ) -> Keyboard:
        confirm_btn = Button.text(confirm_label, payload=confirm_payload).positive()

        cancel_btn = Button.text(cancel_label, payload=cancel_payload).negative()
        return Keyboard(confirm_btn, cancel_btn, inline=inline, one_time=True)

    @staticmethod
    def yes_no(
        *,
        yes_label: str = "Да",
        no_label: str = "Нет",
        yes_payload: dict | str | None = None,
        no_payload: dict | str | None = None,
        inline: bool = False,
    ) -> Keyboard:
        yes_btn = Button.text(yes_label, payload=yes_payload).positive()
        no_btn = Button.text(no_label, payload=no_payload).negative()

        return Keyboard(yes_btn, no_btn, inline=inline, one_time=True)

    @staticmethod
    def pagination(
        *,
        current_page: int,
        total_pages: int,
        prev_label: str = "◀️ Назад",
        next_label: str = "Вперёд ▶️",
        page_info: bool = True,
        inline: bool = True,
    ) -> Keyboard:
        buttons: list[InitializedButton] = []

        if current_page > 1:
            prev_btn = Button.text(
                prev_label,
                payload={"action": "prev", "page": current_page - 1},
            ).primary()

            buttons.append(prev_btn)

        if page_info:
            page_btn = Button.text(
                f"{current_page}/{total_pages}",
                payload={"action": "current", "page": current_page},
            ).secondary()

            buttons.append(page_btn)

        if current_page < total_pages:
            next_btn = Button.text(
                next_label,
                payload={"action": "next", "page": current_page + 1},
            ).primary()

            buttons.append(next_btn)

        return Keyboard(*buttons, inline=inline, one_time=False)

    @staticmethod
    def menu(
        *items: tuple[str, dict | str | None],
        columns: int = 2,
        inline: bool = False,
    ) -> Keyboard:
        buttons: list[InitializedButton | EllipsisType] = []

        for i, (label, payload) in enumerate(items):
            btn = Button.text(label, payload=payload).primary()
            buttons.append(btn)

            if (i + 1) % columns == 0 and i + 1 < len(items):
                buttons.append(...)

        return Keyboard(*buttons, inline=inline, one_time=False)

    @staticmethod
    def choice(
        *options: str,
        payloads: list[dict | str | None] | None = None,
        inline: bool = False,
    ) -> Keyboard:
        if payloads is None:
            payloads = [{"choice": i} for i in range(len(options))]

        buttons = [
            Button.text(option, payload=payload).primary()
            for option, payload in zip(options, payloads, strict=False)
        ]

        return Keyboard(*buttons, inline=inline, one_time=True)

    @staticmethod
    def inline_url_buttons(*items: tuple[str, str], columns: int = 1) -> Keyboard:
        buttons: list[InitializedButton | EllipsisType] = []

        for i, (label, url) in enumerate(items):
            btn = Button.open_link(label, link=url)
            buttons.append(btn)

            if (i + 1) % columns == 0 and i + 1 < len(items):
                buttons.append(...)

        return Keyboard(*buttons, inline=True, one_time=False)


confirm_cancel = KeyboardTemplates.confirm_cancel
yes_no = KeyboardTemplates.yes_no
pagination = KeyboardTemplates.pagination
menu = KeyboardTemplates.menu
choice = KeyboardTemplates.choice
inline_url_buttons = KeyboardTemplates.inline_url_buttons
