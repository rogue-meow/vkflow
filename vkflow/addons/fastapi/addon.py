from __future__ import annotations

import asyncio
import contextlib
import logging as _logging
from typing import TYPE_CHECKING, Any

from loguru import logger

from vkflow.addons.base import AddonMeta, BaseAddon

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

    from vkflow.app.bot import App, Bot


class _UvicornLoguruHandler(_logging.Handler):
    """Перенаправляет логи uvicorn через loguru."""

    def emit(self, record: _logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.opt(exception=record.exc_info).log(level, record.getMessage())


class FastAPIAddon(BaseAddon):
    """FastAPI web server addon for VK bots."""

    meta = AddonMeta(
        name="fastapi",
        description="FastAPI web server for VK bots",
        version="1.0.0",
        required_packages=["fastapi", "uvicorn"],
        pip_extras="fastapi",
    )

    def __init__(
        self,
        fastapi_app: FastAPI | None = None,
        *,
        host: str = "0.0.0.0",
        port: int = 8080,
        callback_api: bool = False,
        callback_path: str = "/callback",
        callback_per_bot: bool = False,
        secret_key: str | None = None,
        secrets: dict[int, str] | None = None,
        confirmation_key: str | None = None,
        confirmations: dict[int, str] | None = None,
        api_key: str | None = None,
        auth_dependency: Any | None = None,
        log_level: str = "info",
        **uvicorn_kwargs: Any,
    ):
        super().__init__()
        self._fastapi_app = fastapi_app
        self._host = host
        self._port = port
        self._log_level = log_level

        self._callback_api = callback_api
        self._callback_path = callback_path
        self._callback_per_bot = callback_per_bot
        self._secret_key = secret_key
        self._secrets = secrets
        self._confirmation_key = confirmation_key
        self._confirmations = confirmations

        self._api_key = api_key
        self._auth_dependency = auth_dependency

        self._uvicorn_kwargs = uvicorn_kwargs

        self._pending_routers: list[tuple[APIRouter, dict[str, Any]]] = []
        self._pending_middlewares: list[tuple[type, dict[str, Any]]] = []
        self._server: Any = None
        self._server_task: asyncio.Task | None = None

    @property
    def fastapi_app(self) -> FastAPI:
        """Get the FastAPI application instance."""
        if self._fastapi_app is None:
            raise RuntimeError(
                "FastAPI app is not created yet. Call on_startup() first or pass fastapi_app to __init__."
            )
        return self._fastapi_app

    def setup(self, app: App) -> None:
        self.check_dependencies()
        super().setup(app)

    def include_router(self, router: APIRouter, **kwargs: Any) -> None:
        """Add a router. Deferred until startup if app not yet created."""
        if self._fastapi_app is not None:
            self._fastapi_app.include_router(router, **kwargs)
        else:
            self._pending_routers.append((router, kwargs))

    def add_middleware(self, cls: type, **kwargs: Any) -> None:
        """Add middleware. Deferred until startup if app not yet created."""
        if self._fastapi_app is not None:
            self._fastapi_app.add_middleware(cls, **kwargs)
        else:
            self._pending_middlewares.append((cls, kwargs))

    async def on_startup(self, app: App, bots: list[Bot]) -> None:
        import uvicorn
        from fastapi import FastAPI

        if self._fastapi_app is None:
            self._fastapi_app = FastAPI()

        self._fastapi_app.state.vk_app = app
        self._fastapi_app.state.vk_bots = bots
        self._fastapi_app.state.vk_addon = self

        for router, kwargs in self._pending_routers:
            self._fastapi_app.include_router(router, **kwargs)
        self._pending_routers.clear()

        for cls, kwargs in self._pending_middlewares:
            self._fastapi_app.add_middleware(cls, **kwargs)
        self._pending_middlewares.clear()

        if self._api_key is not None:
            from vkflow.addons.fastapi.auth import APIKeyMiddleware

            exclude = [self._callback_path] if self._callback_api else []
            self._fastapi_app.add_middleware(
                APIKeyMiddleware,
                api_key=self._api_key,
                exclude_paths=exclude,
            )

        if self._auth_dependency is not None:
            self._fastapi_app.router.dependencies.append(self._auth_dependency)

        if self._callback_api:
            from vkflow.addons.fastapi.callback import setup_callback_routes

            setup_callback_routes(self._fastapi_app, self, bots)

        self._setup_uvicorn_logging()

        config = uvicorn.Config(
            self._fastapi_app,
            host=self._host,
            port=self._port,
            log_config=None,
            **self._uvicorn_kwargs,
        )
        self._server = uvicorn.Server(config)

        self._server.install_signal_handlers = lambda: None

        self._server_task = asyncio.create_task(self._server.serve())

        logger.info(
            "FastAPI server started on {}:{}",
            self._host,
            self._port,
        )

    async def on_shutdown(self, app: App, bots: list[Bot]) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._server_task is not None:
            try:
                await asyncio.wait_for(self._server_task, timeout=5.0)
            except TimeoutError:
                logger.warning("FastAPI server shutdown timed out, forcing stop")
                self._server_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._server_task
            self._server_task = None
        logger.info("FastAPI server stopped")

    def _setup_uvicorn_logging(self) -> None:
        """Redirect uvicorn loggers through loguru."""
        level = getattr(_logging, self._log_level.upper(), _logging.INFO)
        handler = _UvicornLoguruHandler()
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            uv_logger = _logging.getLogger(name)
            uv_logger.handlers = [handler]
            uv_logger.setLevel(level)
            uv_logger.propagate = False
