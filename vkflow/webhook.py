from __future__ import annotations

import asyncio
import dataclasses
import hmac
import hashlib
import signal
import sys

import aiohttp.web

from loguru import logger

from vkflow.api import API
from vkflow.app.bot import App, Bot, _prevent_shutdown_hang
from vkflow.app.storages import NewEvent
from vkflow.base.event import BaseEvent  # noqa: TC001
from vkflow.base.event_factories import BaseEventFactory
from vkflow.event import GroupEvent


class WebhookEventFactory(BaseEventFactory):
    """Event factory for webhook (Callback API) transport.

    Does not poll a long-poll server.  Events are pushed externally
    via :meth:`push_event`, which feeds any active :meth:`listen`
    generators (used by ``conquer_new_message``, ``run_state_handling``, etc.).
    """

    def __init__(self, *, api: API, **kwargs) -> None:
        super().__init__(api=api, **kwargs)
        self._stop_event: asyncio.Event | None = None

    async def _coroutine_run_polling(self) -> None:
        self._mark_ready()
        self._stop_event = asyncio.Event()
        await self._stop_event.wait()

    def stop(self) -> None:
        self._run = False
        if self._stop_event is not None:
            self._stop_event.set()
        if self._waiting_new_event_extra_task is not None:
            self._waiting_new_event_extra_task.cancel()

    async def push_event(self, event: BaseEvent) -> None:
        """Push an externally-received event through the callback chain."""
        await self._run_through_callbacks(event)

    def _mark_ready(self) -> None:
        self._is_ready = True
        if self._ready_event is None:
            self._ready_event = asyncio.Event()
        self._ready_event.set()

    async def close_session(self) -> None:
        self.stop()
        await super().close_session()


@dataclasses.dataclass
class WebhookBotEntry:
    """Configuration for a single bot in webhook (Callback API) mode.

    Example::

        WebhookBotEntry(
            "group-token-here",
            secret_key="my_secret",
            confirmation_key="abc123",
        )
    """

    token: str | API
    secret_key: str | None = None
    confirmation_key: str | None = None


@dataclasses.dataclass
class _GroupInfo:
    """Internal mapping: group_id -> bot + per-group keys."""

    bot: Bot
    secret_key: str | None
    confirmation_key: str | None


@dataclasses.dataclass
class WebhookApp(App):
    """``App`` subclass that uses VK Callback API (webhooks) instead of LongPoll.

    All features of :class:`App` are fully supported -commands, cogs, FSM,
    middleware, event/message handlers, callback buttons, ViewStore,
    startup/shutdown hooks, ``on_ready``, ``wait_for``,
    ``conquer_new_message``, addons, and extensions.

    **Single bot**::

        app = WebhookApp(
            prefixes=["/"],
            secret_key="abc",
            confirmation_key="xyz",
        )

        @app.command("ping")
        async def ping(ctx):
            await ctx.reply("pong")

        app.run("token", host="0.0.0.0", port=8080)

    **Multi bot**::

        app = WebhookApp(prefixes=["/"])
        app.run(
            WebhookBotEntry("token1", secret_key="s1", confirmation_key="c1"),
            WebhookBotEntry("token2", secret_key="s2", confirmation_key="c2"),
            host="0.0.0.0", port=8080,
        )

    **Mixed (plain tokens inherit app-level keys)**::

        app = WebhookApp(
            prefixes=["/"],
            secret_key="shared_secret",
            confirmation_key="shared_conf",
        )
        app.run("token1", "token2", host="0.0.0.0", port=8080)

    **Manual integration with an existing aiohttp app**::

        async def main():
            await app.prepare("token")
            aiohttp_app = app.create_aiohttp_app()
            aiohttp.web.run_app(aiohttp_app)
    """

    secret_key: str | None = None
    confirmation_key: str | None = None
    path: str = "/webhook"

    def __post_init__(self) -> None:
        super().__post_init__()
        self._group_map: dict[int, _GroupInfo] = {}
        self._aiohttp_app: aiohttp.web.Application | None = None
        self._runner: aiohttp.web.AppRunner | None = None

    def run(  # type: ignore[override]
        self,
        *tokens: str | API | WebhookBotEntry,
        host: str = "0.0.0.0",
        port: int = 8080,
        bot_payload_factory: type | None = None,
    ) -> asyncio.Task | None:
        """Synchronous entry-point (mirrors ``App.run``)."""
        coro = self.start(
            *tokens,
            host=host,
            port=port,
            bot_payload_factory=bot_payload_factory,
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._run_sync(coro)
            return None
        else:
            return loop.create_task(coro, name="vkflow_webhook_app")

    async def start(  # type: ignore[override]
        self,
        *tokens: str | API | WebhookBotEntry,
        host: str = "0.0.0.0",
        port: int = 8080,
        bot_payload_factory: type | None = None,
    ) -> None:
        """Async: initialise bots, start aiohttp server, wait for signal."""
        await self.prepare(*tokens, bot_payload_factory=bot_payload_factory)

        app = self.create_aiohttp_app()
        self._runner = aiohttp.web.AppRunner(app)
        await self._runner.setup()

        site = aiohttp.web.TCPSite(self._runner, host, port)
        await site.start()

        logger.opt(colors=True).success(
            "Webhook server started on <b>{host}:{port}{path}</b> (<b>{count}</b> bot{postfix})",
            host=host,
            port=port,
            path=self.path,
            count=len(self._bots),
            postfix="s" if len(self._bots) > 1 else "",
        )

        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()

        def _signal_handler(sig: int) -> None:
            logger.opt(colors=True).warning(
                "Received signal <r>{sig_name}</r>, shutting down...",
                sig_name=signal.Signals(sig).name,
            )
            loop.call_soon_threadsafe(shutdown_event.set)

        if sys.platform == "win32":
            signal.signal(signal.SIGINT, lambda s, f: _signal_handler(s))
            signal.signal(signal.SIGTERM, lambda s, f: _signal_handler(s))
        else:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda s=sig: _signal_handler(s))

        try:
            await shutdown_event.wait()
        except asyncio.CancelledError:
            logger.opt(colors=True).warning("Tasks cancelled, shutting down...")
        finally:
            await self.close()

            if sys.platform == "win32":
                signal.signal(signal.SIGINT, signal.default_int_handler)
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
            else:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.remove_signal_handler(sig)

            executor = getattr(loop, "_default_executor", None)
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)

            _prevent_shutdown_hang()

    async def prepare(
        self,
        *tokens: str | API | WebhookBotEntry,
        bot_payload_factory: type | None = None,
    ) -> None:
        """Initialise bots without starting the HTTP server.

        Useful for manual integration with an existing aiohttp application
        (call :meth:`create_aiohttp_app` afterwards).
        """
        await self._init_bots(*tokens, bot_payload_factory=bot_payload_factory)

        if self._ready_event is None:
            self._ready_event = asyncio.Event()

        for info in self._group_map.values():
            info.bot.events_factory._mark_ready()

        await self._call_startup(*self._bots)

        for bot in self._bots:
            await self.dispatch_event("ready", bot=bot)

    def create_aiohttp_app(self) -> aiohttp.web.Application:
        """Return an ``aiohttp.web.Application`` with the webhook route registered."""
        app = aiohttp.web.Application()
        app.router.add_post(self.path, self._handle_webhook)
        self._aiohttp_app = app
        return app

    async def close(self) -> None:
        """Graceful shutdown: stop factories, cleanup runner, call shutdown handlers, close sessions."""
        for info in self._group_map.values():
            info.bot.events_factory.stop()

        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

        if self._bots:
            await self._call_shutdown(*self._bots)

            for bot in self._bots:
                await bot.close_sessions()

    async def _handle_webhook(self, request: aiohttp.web.Request) -> aiohttp.web.Response:
        try:
            data = await request.json()
        except Exception as e:
            logger.error("Failed to parse webhook JSON: {error}", error=e)
            return aiohttp.web.Response(text="Bad Request", status=400)

        group_id = data.get("group_id")
        info = self._group_map.get(group_id)

        if info is None and len(self._group_map) == 1:
            info = next(iter(self._group_map.values()))

        if info is None:
            logger.warning(
                "Unknown group_id in webhook: {group_id}",
                group_id=group_id,
            )
            return aiohttp.web.Response(text="Unknown group", status=404)

        event_type = data.get("type")

        if event_type == "confirmation":
            if info.confirmation_key:
                return aiohttp.web.Response(text=info.confirmation_key)
            return aiohttp.web.Response(text="", status=403)

        if info.secret_key and data.get("secret") != info.secret_key:
            logger.warning(
                "Secret key mismatch for group {group_id}",
                group_id=group_id,
            )
            return aiohttp.web.Response(text="Forbidden", status=403)

        task = asyncio.create_task(
            self._process_webhook_event(info, data),
            name=f"webhook_event_{event_type}",
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        return aiohttp.web.Response(text="ok")

    async def _process_webhook_event(self, info: _GroupInfo, data: dict) -> None:
        event = GroupEvent(data)
        await info.bot.events_factory.push_event(event)
        new_event = await NewEvent.from_event(event=event, bot=info.bot)
        await info.bot.handle_event(new_event)

    async def _init_bots(
        self,
        *tokens: str | API | WebhookBotEntry,
        bot_payload_factory: type | None = None,
    ) -> None:
        entries = [self._resolve_entry(t) for t in tokens]

        apis: list[API] = []
        for entry in entries:
            api = entry.token if isinstance(entry.token, API) else API(entry.token)
            apis.append(api)

        async with asyncio.TaskGroup() as tg:
            for api in apis:
                tg.create_task(api.define_token_owner())

        for entry, api in zip(entries, apis, strict=True):
            factory = WebhookEventFactory(api=api)
            bot = Bot(
                app=self,
                api=api,
                events_factory=factory,
                payload_factory=bot_payload_factory,
            )

            group_id = api._owner_schema.id
            self._group_map[group_id] = _GroupInfo(
                bot=bot,
                secret_key=entry.secret_key,
                confirmation_key=entry.confirmation_key,
            )

        self._bots = [info.bot for info in self._group_map.values()]

        logger.opt(colors=True).success(
            "Initialized <b>{count}</b> webhook bot{postfix}",
            count=len(self._bots),
            postfix="s" if len(self._bots) > 1 else "",
        )

    def _resolve_entry(self, token: str | API | WebhookBotEntry) -> WebhookBotEntry:
        if isinstance(token, WebhookBotEntry):
            return WebhookBotEntry(
                token=token.token,
                secret_key=token.secret_key if token.secret_key is not None else self.secret_key,
                confirmation_key=token.confirmation_key
                if token.confirmation_key is not None
                else self.confirmation_key,
            )
        return WebhookBotEntry(
            token=token,
            secret_key=self.secret_key,
            confirmation_key=self.confirmation_key,
        )


class WebhookValidator:
    """Utility for manual validation of VK webhook requests.

    Supports secret-key comparison and HMAC signature verification.
    """

    @staticmethod
    def validate_secret(data: dict, secret_key: str) -> bool:
        received_secret = data.get("secret")
        return received_secret == secret_key

    @staticmethod
    def validate_signature(body: bytes, secret_key: str, received_signature: str) -> bool:
        expected_signature = hmac.new(secret_key.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_signature, received_signature)
