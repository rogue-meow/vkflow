from __future__ import annotations

import uuid
import typing
import inspect

import asyncio
import functools

from dataclasses import dataclass

from vkflow.ui.keyboard import Keyboard

if typing.TYPE_CHECKING:  # pragma: no cover
    from vkflow.app.storages import CallbackButtonPressed
    from vkflow.models.message import SentMessage
    from vkflow.app.fsm.storage import BaseStorage


@dataclass
class ButtonMetadata:
    callback: typing.Callable
    custom_id: str | None = None

    label: str | None = None
    emoji: str | None = None

    color: str = "secondary"

    row: int | None = None
    disabled: bool = False


class ViewButton:
    def __init__(
        self,
        callback: typing.Callable,
        *,
        label: str | None = None,
        emoji: str | None = None,
        custom_id: str | None = None,
        color: str = "secondary",
        row: int | None = None,
        disabled: bool = False,
    ):
        self.callback = callback
        self.label = label or callback.__name__
        self.emoji = emoji
        self.custom_id = custom_id
        self.color = color
        self.row = row
        self.disabled = disabled
        self.metadata = ButtonMetadata(
            callback=callback,
            custom_id=custom_id,
            label=self.label,
            emoji=emoji,
            color=color,
            row=row,
            disabled=disabled,
        )

        functools.update_wrapper(self, callback)

    def __set_name__(self, owner, name):
        self.name = name

        if self.custom_id is None:
            self.custom_id = name

        self.metadata.custom_id = self.custom_id

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return functools.partial(self.callback, instance)


def button(
    *,
    label: str | None = None,
    emoji: str | None = None,
    custom_id: str | None = None,
    color: str = "secondary",
    row: int | None = None,
    disabled: bool = False,
) -> typing.Callable:
    def decorator(func: typing.Callable) -> ViewButton:
        return ViewButton(
            func,
            label=label,
            emoji=emoji,
            custom_id=custom_id,
            color=color,
            row=row,
            disabled=disabled,
        )

    return decorator


class ViewStore:
    def __init__(self):
        self._views: dict[str, View] = {}

    def add(self, view: View) -> None:
        self._views[view.id] = view
        view._attach_to_store(self)

    def remove(self, view_id: str) -> None:
        self._views.pop(view_id, None)

    def get(self, view_id: str) -> View | None:
        return self._views.get(view_id)

    async def process_interaction(self, interaction: CallbackButtonPressed) -> bool:
        if not interaction.msg.payload:
            return False

        payload = interaction.msg.payload
        view_id = payload.get("__view_id")

        button_id = payload.get("__button_id")

        if not view_id or not button_id:
            return False

        view = self.get(view_id)

        if not view:
            return False

        return await view._process_interaction(interaction, button_id)


class View:
    """
    Interactive view with callback buttons.

    Supports optional FSM integration via fsm_storage class attribute.
    When set, button callbacks can receive an 'fsm' parameter that will
    be automatically injected with FSMContext.

    Examples:
        # Basic view (no FSM)
        class MyView(View):
            @button(label="Click me")
            async def click(self, ctx):
                await ctx.show_snackbar("Clicked!")

        # View with FSM
        class OrderView(View):
            fsm_storage = my_storage  # Set FSM storage

            @button(label="Confirm")
            async def confirm(self, ctx, fsm):
                data = await fsm.finish()
                await ctx.show_snackbar(f"Order: {data}")
    """

    fsm_storage: BaseStorage | None = None
    fsm_strategy: str = "user_chat"

    def __init__(self, *, timeout: float | None = 180, inline: bool = True):
        self.id = str(uuid.uuid4())
        self.timeout = timeout
        self.inline = inline
        self.message: SentMessage | None = None
        self._buttons: dict[str, ViewButton] = {}
        self._finished = False
        self._dispatching = False
        self._timeout_task: asyncio.Task | None = None
        self._wait_future: asyncio.Future | None = None
        self._store: ViewStore | None = None

        for name in dir(self):
            attr = getattr(type(self), name, None)

            if isinstance(attr, ViewButton):
                self._buttons[attr.custom_id] = attr

    def _attach_to_store(self, store: ViewStore) -> None:
        self._store = store
        self._start_timeout()

    async def on_timeout(self) -> None:
        pass

    async def interaction_check(self, interaction: CallbackButtonPressed) -> bool:
        return True

    def stop(self) -> None:
        if self._finished:
            return

        self._finished = True
        self._cancel_timeout()

        if self._store is not None:
            self._store.remove(self.id)

        if self._wait_future and not self._wait_future.done():
            self._wait_future.set_result(False)

    def refresh(self) -> None:
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
        self._start_timeout()

    def is_finished(self) -> bool:
        return self._finished

    def is_dispatching(self) -> bool:
        return self._dispatching

    def is_persistent(self) -> bool:
        return self.timeout is None

    async def wait(self) -> bool:
        if self._finished:
            return False

        self._wait_future = asyncio.Future()

        if self._timeout_task is None:
            self._start_timeout()

        try:
            return await self._wait_future
        finally:
            self._cancel_timeout()

    def _start_timeout(self) -> None:
        if self.timeout is None:
            return

        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()

        self._timeout_task = asyncio.create_task(self._timeout_handler())

    def _cancel_timeout(self) -> None:
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
            self._timeout_task = None

    async def _timeout_handler(self) -> None:
        try:
            await asyncio.sleep(self.timeout)
            self._finished = True

            if self._store is not None:
                self._store.remove(self.id)

            await self.on_timeout()

            if self._wait_future and not self._wait_future.done():
                self._wait_future.set_result(True)
        except asyncio.CancelledError:
            pass

    async def _process_interaction(self, interaction: CallbackButtonPressed, button_id: str) -> bool:
        if self._finished:
            return False

        button = self._buttons.get(button_id)

        if not button:
            return False

        if not await self.interaction_check(interaction):
            return False

        self._dispatching = True

        try:
            callback = button.__get__(self, type(self))

            sig = inspect.signature(callback)
            kwargs: dict[str, typing.Any] = {}

            for param_name in sig.parameters:
                if param_name in ("ctx", "interaction"):
                    kwargs[param_name] = interaction
                elif param_name == "fsm":
                    if self.fsm_storage is not None:
                        from vkflow.app.fsm import Context as FSMContext

                        kwargs["fsm"] = FSMContext.from_message(
                            self.fsm_storage,
                            interaction,
                            strategy=self.fsm_strategy,
                        )
                    else:
                        raise ValueError(
                            f"Button callback '{button.name}' requires 'fsm' parameter "
                            "but fsm_storage is not configured on the View. "
                            "Set fsm_storage as a class attribute."
                        )

            if not kwargs:
                await callback(interaction)
            else:
                await callback(**kwargs)
        finally:
            self._dispatching = False

        return True

    def get_fsm(self, interaction: CallbackButtonPressed) -> typing.Any:
        """
        Get FSMContext for an interaction.

        Args:
            interaction: The callback button interaction

        Returns:
            FSMContext instance

        Raises:
            ValueError: If fsm_storage is not configured
        """
        if self.fsm_storage is None:
            raise ValueError("fsm_storage not configured on View. Set it as a class attribute.")

        from vkflow.app.fsm import Context as FSMContext

        return FSMContext.from_message(
            self.fsm_storage,
            interaction,
            strategy=self.fsm_strategy,
        )

    def to_keyboard(self, *, inline: bool | None = None, one_time: bool = False) -> Keyboard:
        from vkflow.ui.button import Button

        if inline is None:
            inline = self.inline

        keyboard = Keyboard(inline=inline, one_time=one_time)

        rows: dict[int, list[tuple[str, ViewButton]]] = {}
        auto_row = 0

        for button_id, button in self._buttons.items():
            row_num = button.row if button.row is not None else auto_row

            if button.row is None:
                auto_row += 1

            if row_num not in rows:
                rows[row_num] = []

            rows[row_num].append((button_id, button))

        first = True

        for row_num in sorted(rows.keys()):
            if not first:
                keyboard.new_line()
            first = False

            for button_id, btn in rows[row_num]:
                label = btn.label

                if btn.emoji:
                    label = f"{btn.emoji} {label}"

                payload = {
                    "__view_id": self.id,
                    "__button_id": button_id,
                }

                vk_button = Button.callback(label=label, payload=payload)

                if hasattr(vk_button, btn.color):
                    vk_button = getattr(vk_button, btn.color)()

                keyboard.add(vk_button)

        return keyboard
