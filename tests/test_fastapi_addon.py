from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from vkflow.addons.fastapi import FastAPIAddon, get_addon, get_api, get_bot, get_vk_app
from vkflow.addons.fastapi.addon import _UvicornLoguruHandler
from vkflow.addons.fastapi.auth import APIKeyMiddleware
from vkflow.addons.fastapi.callback import setup_callback_routes


# --- Helpers ---


def _make_mock_bot(group_id: int | None = 12345) -> MagicMock:
    bot = MagicMock()
    bot.api = MagicMock()
    if group_id is not None:
        bot.api._owner_schema = MagicMock()
        bot.api._owner_schema.id = group_id
    else:
        bot.api._owner_schema = None
    bot.handle_event = AsyncMock()
    return bot


def _make_mock_app() -> MagicMock:
    app = MagicMock()
    return app


def _make_fastapi_with_state(
    vk_app=None,
    bots=None,
    addon=None,
) -> FastAPI:
    """Create a FastAPI app with vk state pre-set."""
    fastapi_app = FastAPI()
    fastapi_app.state.vk_app = vk_app or _make_mock_app()
    fastapi_app.state.vk_bots = bots or [_make_mock_bot()]
    fastapi_app.state.vk_addon = addon or FastAPIAddon()
    return fastapi_app


# --- Addon Meta ---


class TestAddonMeta:
    def test_addon_meta_fields(self):
        assert FastAPIAddon.meta.name == "fastapi"
        assert FastAPIAddon.meta.version == "1.0.0"
        assert "fastapi" in FastAPIAddon.meta.required_packages
        assert "uvicorn" in FastAPIAddon.meta.required_packages
        assert FastAPIAddon.meta.pip_extras == "fastapi"


# --- Setup & Dependencies ---


class TestSetup:
    def test_setup_calls_check_dependencies(self):
        addon = FastAPIAddon()
        mock_app = _make_mock_app()
        with patch.object(addon, "check_dependencies") as mock_check:
            addon.setup(mock_app)
            mock_check.assert_called_once()

    def test_setup_sets_app(self):
        addon = FastAPIAddon()
        mock_app = _make_mock_app()
        addon.setup(mock_app)
        assert addon._app is mock_app


# --- Include Router ---


class TestIncludeRouter:
    def test_include_router_before_startup_deferred(self):
        addon = FastAPIAddon()
        router = APIRouter()
        addon.include_router(router, prefix="/test")
        assert len(addon._pending_routers) == 1
        assert addon._pending_routers[0] == (router, {"prefix": "/test"})

    def test_include_router_after_app_created(self):
        fastapi_app = FastAPI()
        addon = FastAPIAddon(fastapi_app=fastapi_app)
        router = APIRouter()

        @router.get("/hello")
        def hello():
            return {"msg": "hi"}

        addon.include_router(router)
        # Router should be attached immediately (not pending)
        assert len(addon._pending_routers) == 0
        client = TestClient(fastapi_app)
        resp = client.get("/hello")
        assert resp.status_code == 200

    def test_add_middleware_before_startup_deferred(self):
        addon = FastAPIAddon()
        addon.add_middleware(APIKeyMiddleware, api_key="test")
        assert len(addon._pending_middlewares) == 1


# --- on_startup ---


def _patch_uvicorn():
    """Patch uvicorn.Server and uvicorn.Config for tests."""
    mock_server = MagicMock()
    mock_server.serve = AsyncMock()
    mock_server.should_exit = False
    server_patch = patch("uvicorn.Server", return_value=mock_server)
    config_patch = patch("uvicorn.Config")
    return server_patch, config_patch, mock_server


class TestOnStartup:
    @pytest.mark.asyncio
    async def test_creates_fastapi_app_if_not_provided(self):
        addon = FastAPIAddon()
        mock_app = _make_mock_app()
        bots = [_make_mock_bot()]

        server_p, config_p, _ = _patch_uvicorn()
        with server_p, config_p:
            await addon.on_startup(mock_app, bots)

            assert addon._fastapi_app is not None
            assert isinstance(addon._fastapi_app, FastAPI)

    @pytest.mark.asyncio
    async def test_uses_provided_fastapi_app(self):
        provided_app = FastAPI()
        addon = FastAPIAddon(fastapi_app=provided_app)
        mock_app = _make_mock_app()
        bots = [_make_mock_bot()]

        server_p, config_p, _ = _patch_uvicorn()
        with server_p, config_p:
            await addon.on_startup(mock_app, bots)

            assert addon._fastapi_app is provided_app

    @pytest.mark.asyncio
    async def test_state_injection(self):
        addon = FastAPIAddon()
        mock_app = _make_mock_app()
        bots = [_make_mock_bot()]

        server_p, config_p, _ = _patch_uvicorn()
        with server_p, config_p:
            await addon.on_startup(mock_app, bots)

            assert addon._fastapi_app.state.vk_app is mock_app
            assert addon._fastapi_app.state.vk_bots is bots
            assert addon._fastapi_app.state.vk_addon is addon

    @pytest.mark.asyncio
    async def test_pending_routers_attached_on_startup(self):
        addon = FastAPIAddon()
        router = APIRouter()

        @router.get("/test")
        def test_route():
            return {"ok": True}

        addon.include_router(router, prefix="/api")
        assert len(addon._pending_routers) == 1

        mock_app = _make_mock_app()
        bots = [_make_mock_bot()]

        server_p, config_p, _ = _patch_uvicorn()
        with server_p, config_p:
            await addon.on_startup(mock_app, bots)

            assert len(addon._pending_routers) == 0
            client = TestClient(addon._fastapi_app)
            resp = client.get("/api/test")
            assert resp.status_code == 200


# --- Dependencies ---


class TestDependencies:
    def test_get_vk_app(self):
        mock_vk_app = _make_mock_app()
        fastapi_app = _make_fastapi_with_state(vk_app=mock_vk_app)

        @fastapi_app.get("/test-app")
        def route(app=Depends(get_vk_app)):  # noqa: B008
            return {"id": id(app)}

        client = TestClient(fastapi_app)
        resp = client.get("/test-app")
        assert resp.status_code == 200

    def test_get_bot_by_index(self):
        bot = _make_mock_bot(group_id=111)
        fastapi_app = _make_fastapi_with_state(bots=[bot])

        @fastapi_app.get("/test-bot")
        def route(b=Depends(get_bot)):  # noqa: B008
            return {"group_id": b.api._owner_schema.id}

        client = TestClient(fastapi_app)
        resp = client.get("/test-bot")
        assert resp.status_code == 200
        assert resp.json()["group_id"] == 111

    def test_get_bot_by_group_id(self):
        bot1 = _make_mock_bot(group_id=111)
        bot2 = _make_mock_bot(group_id=222)
        fastapi_app = _make_fastapi_with_state(bots=[bot1, bot2])

        @fastapi_app.get("/test-bot")
        def route(b=Depends(get_bot)):  # noqa: B008
            return {"group_id": b.api._owner_schema.id}

        client = TestClient(fastapi_app)
        resp = client.get("/test-bot?group_id=222")
        assert resp.status_code == 200
        assert resp.json()["group_id"] == 222

    def test_get_bot_not_found(self):
        bot = _make_mock_bot(group_id=111)
        fastapi_app = _make_fastapi_with_state(bots=[bot])

        @fastapi_app.get("/test-bot")
        def route(b=Depends(get_bot)):  # noqa: B008
            return {"ok": True}

        client = TestClient(fastapi_app)
        resp = client.get("/test-bot?group_id=999")
        assert resp.status_code == 404

    def test_get_api(self):
        bot = _make_mock_bot(group_id=111)
        fastapi_app = _make_fastapi_with_state(bots=[bot])

        @fastapi_app.get("/test-api")
        def route(api=Depends(get_api)):  # noqa: B008
            return {"has_api": api is not None}

        client = TestClient(fastapi_app)
        resp = client.get("/test-api")
        assert resp.status_code == 200
        assert resp.json()["has_api"] is True

    def test_get_addon(self):
        addon = FastAPIAddon()
        fastapi_app = _make_fastapi_with_state(addon=addon)

        @fastapi_app.get("/test-addon")
        def route(a=Depends(get_addon)):  # noqa: B008
            return {"name": a.meta.name}

        client = TestClient(fastapi_app)
        resp = client.get("/test-addon")
        assert resp.status_code == 200
        assert resp.json()["name"] == "fastapi"


# --- Callback API ---


class TestCallbackAPI:
    def test_callback_confirmation(self):
        addon = FastAPIAddon(
            callback_api=True,
            confirmation_key="test_confirm_123",
        )
        bot = _make_mock_bot(group_id=12345)
        fastapi_app = _make_fastapi_with_state(bots=[bot], addon=addon)
        setup_callback_routes(fastapi_app, addon, [bot])

        client = TestClient(fastapi_app)
        resp = client.post(
            "/callback",
            json={
                "type": "confirmation",
                "group_id": 12345,
            },
        )
        assert resp.status_code == 200
        assert resp.text == "test_confirm_123"

    def test_callback_confirmation_per_group(self):
        addon = FastAPIAddon(
            callback_api=True,
            confirmations={111: "confirm_111", 222: "confirm_222"},
        )
        bot1 = _make_mock_bot(group_id=111)
        bot2 = _make_mock_bot(group_id=222)
        fastapi_app = _make_fastapi_with_state(bots=[bot1, bot2], addon=addon)
        setup_callback_routes(fastapi_app, addon, [bot1, bot2])

        client = TestClient(fastapi_app)

        resp = client.post("/callback", json={"type": "confirmation", "group_id": 111})
        assert resp.text == "confirm_111"

        resp = client.post("/callback", json={"type": "confirmation", "group_id": 222})
        assert resp.text == "confirm_222"

    def test_callback_secret_validation_reject(self):
        addon = FastAPIAddon(
            callback_api=True,
            secret_key="my_secret",
            confirmation_key="confirm",
        )
        bot = _make_mock_bot(group_id=12345)
        fastapi_app = _make_fastapi_with_state(bots=[bot], addon=addon)
        setup_callback_routes(fastapi_app, addon, [bot])

        client = TestClient(fastapi_app)
        resp = client.post(
            "/callback",
            json={
                "type": "message_new",
                "group_id": 12345,
                "object": {},
                "secret": "wrong_secret",
            },
        )
        assert resp.status_code == 403

    def test_callback_secret_validation_accept(self):
        addon = FastAPIAddon(
            callback_api=True,
            secret_key="my_secret",
            confirmation_key="confirm",
        )
        bot = _make_mock_bot(group_id=12345)
        fastapi_app = _make_fastapi_with_state(bots=[bot], addon=addon)
        setup_callback_routes(fastapi_app, addon, [bot])

        client = TestClient(fastapi_app)
        resp = client.post(
            "/callback",
            json={
                "type": "message_new",
                "group_id": 12345,
                "object": {},
                "secret": "my_secret",
            },
        )
        assert resp.status_code == 200
        assert resp.text == "ok"

    def test_callback_event_injection(self):
        addon = FastAPIAddon(
            callback_api=True,
            confirmation_key="confirm",
        )
        bot = _make_mock_bot(group_id=12345)
        fastapi_app = _make_fastapi_with_state(bots=[bot], addon=addon)
        setup_callback_routes(fastapi_app, addon, [bot])

        client = TestClient(fastapi_app)
        resp = client.post(
            "/callback",
            json={
                "type": "message_new",
                "group_id": 12345,
                "object": {"message": {"text": "hello"}},
            },
        )
        assert resp.status_code == 200
        assert resp.text == "ok"
        bot.handle_event.assert_called_once()

    def test_callback_per_bot_endpoints(self):
        addon = FastAPIAddon(
            callback_api=True,
            callback_per_bot=True,
            confirmation_key="confirm_default",
            confirmations={111: "confirm_111"},
        )
        bot1 = _make_mock_bot(group_id=111)
        bot2 = _make_mock_bot(group_id=222)
        fastapi_app = _make_fastapi_with_state(bots=[bot1, bot2], addon=addon)
        setup_callback_routes(fastapi_app, addon, [bot1, bot2])

        client = TestClient(fastapi_app)

        # Per-bot endpoint
        resp = client.post(
            "/callback/111",
            json={
                "type": "confirmation",
                "group_id": 111,
            },
        )
        assert resp.status_code == 200
        assert resp.text == "confirm_111"

        # Common endpoint
        resp = client.post(
            "/callback",
            json={
                "type": "confirmation",
                "group_id": 222,
            },
        )
        assert resp.status_code == 200
        assert resp.text == "confirm_default"


# --- API Key Middleware ---


class TestAPIKeyMiddleware:
    def test_401_without_key(self):
        app = FastAPI()

        @app.get("/protected")
        def protected():
            return {"ok": True}

        app.add_middleware(APIKeyMiddleware, api_key="secret123")

        client = TestClient(app)
        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_200_with_correct_key(self):
        app = FastAPI()

        @app.get("/protected")
        def protected():
            return {"ok": True}

        app.add_middleware(APIKeyMiddleware, api_key="secret123")

        client = TestClient(app)
        resp = client.get("/protected", headers={"Authorization": "Bearer secret123"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_401_with_wrong_key(self):
        app = FastAPI()

        @app.get("/protected")
        def protected():
            return {"ok": True}

        app.add_middleware(APIKeyMiddleware, api_key="secret123")

        client = TestClient(app)
        resp = client.get("/protected", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_exclude_paths(self):
        app = FastAPI()

        @app.get("/callback")
        def callback():
            return {"ok": True}

        @app.get("/protected")
        def protected():
            return {"secret": True}

        app.add_middleware(
            APIKeyMiddleware,
            api_key="secret123",
            exclude_paths=["/callback"],
        )

        client = TestClient(app)

        # Callback should be accessible without key
        resp = client.get("/callback")
        assert resp.status_code == 200

        # Protected still needs key
        resp = client.get("/protected")
        assert resp.status_code == 401


# --- Custom Auth Dependency ---


class TestCustomAuth:
    def test_custom_auth_dependency(self):
        from fastapi import Header

        async def verify_custom_token(x_custom_token: str = Header()):
            if x_custom_token != "valid-token":
                from fastapi import HTTPException

                raise HTTPException(status_code=403, detail="Invalid token")

        app = FastAPI(dependencies=[Depends(verify_custom_token)])

        @app.get("/data")
        def data():
            return {"data": "secret"}

        client = TestClient(app)

        resp = client.get("/data")
        assert resp.status_code == 422  # Missing header

        resp = client.get("/data", headers={"X-Custom-Token": "wrong"})
        assert resp.status_code == 403

        resp = client.get("/data", headers={"X-Custom-Token": "valid-token"})
        assert resp.status_code == 200


# --- Shutdown ---


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_stops_server(self):
        addon = FastAPIAddon()
        mock_app = _make_mock_app()
        bots = [_make_mock_bot()]

        server_p, config_p, mock_server = _patch_uvicorn()
        with server_p, config_p:
            await addon.on_startup(mock_app, bots)

            assert addon._server is not None
            assert addon._server_task is not None

            await addon.on_shutdown(mock_app, bots)

            assert mock_server.should_exit is True
            assert addon._server_task is None

    @pytest.mark.asyncio
    async def test_shutdown_without_startup(self):
        addon = FastAPIAddon()
        mock_app = _make_mock_app()
        bots = [_make_mock_bot()]
        # Should not raise
        await addon.on_shutdown(mock_app, bots)


# --- FastAPI app property ---


class TestFastAPIAppProperty:
    def test_fastapi_app_property_raises_before_startup(self):
        addon = FastAPIAddon()
        with pytest.raises(RuntimeError, match="not created yet"):
            _ = addon.fastapi_app

    def test_fastapi_app_property_returns_app(self):
        provided = FastAPI()
        addon = FastAPIAddon(fastapi_app=provided)
        assert addon.fastapi_app is provided


# --- Signal handler isolation ---


class TestSignalHandlerIsolation:
    @pytest.mark.asyncio
    async def test_uvicorn_signal_handlers_disabled(self):
        """Uvicorn must not install its own signal handlers."""
        addon = FastAPIAddon()
        mock_app = _make_mock_app()
        bots = [_make_mock_bot()]

        server_p, config_p, mock_server = _patch_uvicorn()
        with server_p, config_p:
            await addon.on_startup(mock_app, bots)

            # install_signal_handlers should be replaced with a no-op
            assert callable(mock_server.install_signal_handlers)
            # Calling it should do nothing (no-op lambda)
            mock_server.install_signal_handlers()


# --- Logging redirect ---


class TestUvicornLogging:
    def test_setup_uvicorn_logging_redirects_handlers(self):
        """All uvicorn loggers must use _UvicornLoguruHandler."""
        addon = FastAPIAddon()
        addon._setup_uvicorn_logging()

        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            uv_logger = logging.getLogger(name)
            assert len(uv_logger.handlers) == 1
            assert isinstance(uv_logger.handlers[0], _UvicornLoguruHandler)
            assert uv_logger.propagate is False

    def test_setup_uvicorn_logging_custom_level(self):
        """log_level parameter should control uvicorn logger level."""
        addon = FastAPIAddon(log_level="warning")
        addon._setup_uvicorn_logging()

        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            uv_logger = logging.getLogger(name)
            assert uv_logger.level == logging.WARNING

    def test_uvicorn_loguru_handler_emits(self):
        """_UvicornLoguruHandler should emit log records through loguru."""
        handler = _UvicornLoguruHandler()
        record = logging.LogRecord(
            name="uvicorn",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message %s",
            args=("hello",),
            exc_info=None,
        )
        # Should not raise
        handler.emit(record)

    @pytest.mark.asyncio
    async def test_log_config_none_passed_to_uvicorn(self):
        """uvicorn.Config must receive log_config=None."""
        addon = FastAPIAddon()
        mock_app = _make_mock_app()
        bots = [_make_mock_bot()]

        mock_server = MagicMock()
        mock_server.serve = AsyncMock()
        mock_server.should_exit = False

        with patch("uvicorn.Server", return_value=mock_server), patch("uvicorn.Config") as mock_config_cls:
            await addon.on_startup(mock_app, bots)

            mock_config_cls.assert_called_once()
            _, kwargs = mock_config_cls.call_args
            assert kwargs.get("log_config") is None


# --- Shutdown timeout ---


class TestShutdownTimeout:
    @pytest.mark.asyncio
    async def test_shutdown_timeout_forces_cancel(self):
        """If server doesn't stop within timeout, task should be cancelled."""
        addon = FastAPIAddon()

        # Simulate a server that never finishes
        never_done = asyncio.Future()
        addon._server = MagicMock()
        addon._server.should_exit = False
        addon._server_task = asyncio.ensure_future(never_done)

        mock_app = _make_mock_app()
        bots = [_make_mock_bot()]

        # Patch wait_for timeout to 0.1s for fast test
        with patch.object(asyncio, "wait_for", side_effect=asyncio.TimeoutError):
            await addon.on_shutdown(mock_app, bots)

        assert addon._server_task is None
        assert addon._server.should_exit is True
