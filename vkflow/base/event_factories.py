from __future__ import annotations

import abc
import asyncio
import typing

import aiohttp

from loguru import logger

from vkflow.base.event import BaseEvent
from vkflow.base.session_container import SessionContainerMixin
from vkflow.pretty_view import pretty_view

if typing.TYPE_CHECKING:  # pragma: no cover
    from vkflow.api import API
    from vkflow.base.json_parser import BaseJSONParser


EventsCallback = typing.Callable[[BaseEvent], typing.Awaitable[None]]


class BaseEventFactory(SessionContainerMixin, abc.ABC):
    api: API
    _new_event_callbacks: list[EventsCallback]

    _on_connect_callbacks: list[typing.Callable[[], typing.Awaitable[None]]]
    _on_disconnect_callbacks: list[typing.Callable[[], typing.Awaitable[None]]]

    def __init__(
        self,
        *,
        api: API,
        new_event_callbacks: list[EventsCallback] | None = None,
        requests_session: aiohttp.ClientSession | None = None,
        json_parser: BaseJSONParser | None = None,
    ):
        self.api = api
        self._run = False

        self._is_ready = False
        self._is_connected = False

        self._ready_event: asyncio.Event | None = None
        self._new_event_callbacks = new_event_callbacks or []

        self._on_connect_callbacks = []
        self._on_disconnect_callbacks = []

        SessionContainerMixin.__init__(self, requests_session=requests_session, json_parser=json_parser)

        self._polling_task: asyncio.Task | None = None
        self._waiting_new_event_extra_task: asyncio.Task | None = None

    def on_connect(
        self, func: typing.Callable[[], typing.Awaitable[None]]
    ) -> typing.Callable[[], typing.Awaitable[None]]:
        self._on_connect_callbacks.append(func)
        return func

    def on_disconnect(
        self, func: typing.Callable[[], typing.Awaitable[None]]
    ) -> typing.Callable[[], typing.Awaitable[None]]:
        self._on_disconnect_callbacks.append(func)
        return func

    async def _dispatch_connect(self) -> None:
        if not self._is_connected:
            self._is_connected = True
            logger.debug("Dispatching on_connect event")

            for callback in self._on_connect_callbacks:
                try:
                    await callback()
                except Exception as e:
                    logger.exception(f"Error in on_connect callback: {e}")

    async def _dispatch_disconnect(self) -> None:
        if self._is_connected:
            self._is_connected = False
            logger.debug("Dispatching on_disconnect event")

            for callback in self._on_disconnect_callbacks:
                try:
                    await callback()
                except Exception as e:
                    logger.exception(f"Error in on_disconnect callback: {e}")

    @abc.abstractmethod
    async def _coroutine_run_polling(self): ...

    async def listen(self) -> typing.AsyncGenerator[BaseEvent, None]:
        events_queue: asyncio.Queue[BaseEvent] = asyncio.Queue()
        logger.debug("Run events listening")

        try:
            self.add_event_callback(events_queue.put)

            if self._polling_task is None or self._polling_task.done():
                self._polling_task = asyncio.create_task(self.coroutine_run_polling())

            while True:
                new_event_task = asyncio.create_task(events_queue.get())
                self._waiting_new_event_extra_task = new_event_task

                try:
                    yield await new_event_task
                except asyncio.CancelledError:
                    return

        finally:
            logger.debug("End events listening")
            self.remove_event_callback(events_queue.put)

    def add_event_callback(self, func: EventsCallback) -> EventsCallback:
        logger.debug("Add event callback: {func}", func=func)
        self._new_event_callbacks.append(func)

        return func

    def remove_event_callback(self, func: EventsCallback) -> EventsCallback:
        logger.debug("Remove event callback: {func}", func=func)
        self._new_event_callbacks.remove(func)

        return func

    async def coroutine_run_polling(self) -> None:
        self._run = True

        logger.info("Run {polling_type} polling", polling_type=self.__class__.__name__)

        try:
            await self._coroutine_run_polling()
        finally:
            self._run = False
            logger.info(
                "End {polling_type} polling",
                polling_type=self.__class__.__name__,
            )

    async def _run_through_callbacks(self, event: BaseEvent) -> None:
        logger.debug(
            "New event: {event}",
            event=event,
        )

        logger.opt(lazy=True).debug(
            "Event content: {event_content}",
            event_content=lambda: pretty_view(event.content),
        )

        async with asyncio.TaskGroup() as tg:
            for callback in self._new_event_callbacks:
                tg.create_task(callback(event))

    def run_polling(self):
        asyncio.run(self.coroutine_run_polling())

    def is_ready(self) -> bool:
        return self._is_ready

    async def wait_until_ready(self) -> None:
        if self._ready_event is None:
            self._ready_event = asyncio.Event()

        if self._is_ready:
            return

        await self._ready_event.wait()

    @abc.abstractmethod
    def stop(self) -> None: ...


class BaseLongPoll(BaseEventFactory):
    def __init__(
        self,
        *,
        api: API,
        event_wrapper: type[BaseEvent],
        new_event_callbacks: list[EventsCallback] | None = None,
        requests_session: aiohttp.ClientSession | None = None,
        json_parser: BaseJSONParser | None = None,
    ):
        self._event_wrapper = event_wrapper

        self._baked_request: asyncio.Task | None = None
        self._requests_query_params: dict | None = None

        self._server_url: str | None = None
        self._background_tasks: set = set()

        BaseEventFactory.__init__(
            self,
            api=api,
            new_event_callbacks=new_event_callbacks,
            requests_session=requests_session,
            json_parser=json_parser,
        )

    @abc.abstractmethod
    async def _setup(self) -> None:
        """
        Обновляет или получает информацию о LongPoll сервере
        и открывает соединение
        """

    async def _coroutine_run_polling(self) -> None:
        await self._setup()
        self._requests_query_params = typing.cast("dict", self._requests_query_params)

        self._update_baked_request()
        self._is_ready = True

        if self._ready_event is None:
            self._ready_event = asyncio.Event()
        self._ready_event.set()

        await self._dispatch_connect()
        logger.debug("LongPoll connection is ready")

        while True:
            try:
                response = await self._baked_request
            except TimeoutError:
                self._update_baked_request()
                continue

            except (aiohttp.ClientOSError, aiohttp.ClientResponseError, aiohttp.ServerDisconnectedError):
                await self._dispatch_disconnect()
                await self.refresh_session()

                self._update_baked_request()

                await self._dispatch_connect()
                continue

            except asyncio.CancelledError:
                await self._dispatch_disconnect()
                return

            except (AttributeError, RuntimeError, aiohttp.ClientConnectionError) as e:
                logger.debug(f"Shutdown detected: {type(e).__name__}: {e}")

                await self._dispatch_disconnect()
                return

            except Exception as e:
                logger.exception(f"Unexpected error in polling: {e}")

                await self._dispatch_disconnect()
                await asyncio.sleep(1)

                try:
                    await self.refresh_session()
                    self._update_baked_request()
                    await self._dispatch_connect()
                except Exception:
                    return

                continue

            else:
                async with response:
                    if "X-Next-Ts" in response.headers:
                        self._requests_query_params.update(ts=response.headers["X-Next-Ts"])

                        self._update_baked_request()
                        data = await self.parse_json_body(response)

                        if "updates" not in data:
                            await self._resolve_faileds(data)
                            continue

                    else:
                        data = await self.parse_json_body(response)
                        await self._resolve_faileds(data)
                        continue

                if not data["updates"]:
                    continue

                for update in data["updates"]:
                    event = self._event_wrapper(update)
                    task = asyncio.create_task(
                        self._run_through_callbacks(event),
                        name=f"callback_{event.type if hasattr(event, 'type') else 'event'}",
                    )
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)

    async def _resolve_faileds(self, response: dict):
        self._requests_query_params = typing.cast("dict", self._requests_query_params)

        if response["failed"] == 1:
            self._requests_query_params.update(ts=response["ts"])
        elif response["failed"] in (2, 3):
            await self._setup()
        else:
            raise ValueError("Invalid longpoll version")

        self._update_baked_request()

    def _update_baked_request(self) -> None:
        if self._baked_request is not None and not self._baked_request.done():
            self._baked_request.cancel()

        self._server_url = typing.cast("str", self._server_url)

        baked_request = self.requests_session.get(self._server_url, params=self._requests_query_params)

        self._baked_request = asyncio.create_task(baked_request)

    async def close_session(self) -> None:
        await self.api.close_session()
        await BaseEventFactory.close_session(self)

    def stop(self) -> None:
        self._run = False

        if self._baked_request is not None:
            self._baked_request.cancel()

        if self._waiting_new_event_extra_task is not None:
            self._waiting_new_event_extra_task.cancel()
