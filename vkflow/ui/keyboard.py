from __future__ import annotations

import typing

from vkflow.base.ui_builder import UIBuilder
from vkflow.ui.button import InitializedButton

if typing.TYPE_CHECKING:
    from types import EllipsisType


class Keyboard(UIBuilder):
    """
    Генерирует клавиатуру на основе переданных кнопок.
    Чтобы добавить новый ряд, передайте Ellipsis (три точки)
    вместо кнопки. Клавиатуру можно создать и в другом стиле:
    вызывая `.add()` для каждой новой кнопки и `.new_line()`
    для перехода на следующий ряд

    Настройки `one_time` и `inline` передаются при самой инициализации

    Объект можно напрямую передать в поле `keyboard`
    при отправке сообщения
    """

    def __init__(
        self, *buttons: InitializedButton | EllipsisType, one_time: bool = True, inline: bool = False
    ) -> None:
        self.scheme = {"inline": inline, "buttons": [[]]}

        if not inline:
            self.scheme.update(one_time=one_time)

        self._build(*buttons)

    @staticmethod
    def empty() -> str:
        """
        Returns:
            Пустую клавиатуру. Используйте, чтобы удалить текущую
        """
        return '{"buttons":[],"one_time":true}'

    def add(self, button: InitializedButton) -> Keyboard:
        """
        Добавляет в клавиатуру кнопку

        Arguments:
            button: Кнопка, которую надо добавить

        Returns:
            Текущая клавиатура
        """
        self.scheme["buttons"][-1].append(button.scheme)
        return self

    def new_line(self) -> Keyboard:
        """
        Добавляет новый ряд клавиатуре
        """
        if not self.scheme["buttons"][-1]:
            raise ValueError(
                "Cannot add a new line: the last line is empty. "
                "Add at least one button before creating a new line."
            )

        self.scheme["buttons"].append([])
        return self

    def row(self) -> Keyboard:
        return self.new_line()

    def add_button(
        self,
        text: str | None = None,
        color: str = "secondary",
        *,
        in_row: bool = True,
        button: InitializedButton | None = None,
        **kwargs: typing.Any,
    ) -> Keyboard:
        """
        Добавляет кнопку в клавиатуру

        Arguments:
            text: Текст кнопки (для text кнопок)
            color: Цвет кнопки (positive, negative, primary, secondary)
            in_row: Находится ли в строке с другими кнопками или занимает всю строку
            button: Готовая кнопка (если передана, text и color игнорируются)
            **kwargs: Дополнительные параметры для кнопки (payload и т.п.)

        Returns:
            Текущая клавиатура
        """
        from vkflow.ui.button import Button

        if button is None:
            if text is None:
                raise ValueError("Either 'text' or 'button' must be provided")

            button = Button.text(text, **kwargs)

            if hasattr(button, color):
                button = getattr(button, color)()

        if not in_row and self.scheme["buttons"][-1]:
            self.new_line()

        self.add(button)

        if not in_row:
            self.new_line()

        return self

    def _build(self, *buttons: InitializedButton | EllipsisType) -> None:
        """
        Вспомогательный метод для построения рядов кнопок

        Arguments:
            buttons: Кнопки или Ellipsis (для новой линии)
        """
        for button in buttons:
            if button is ...:
                self.new_line()
            elif isinstance(button, InitializedButton):
                self.add(button)
