"""
Тесты для цепочки обработки ошибок команд
"""

import unittest.mock

import pytest

from vkflow.commands.core import Command


def test_on_error_registers_handler():
    """on_error() регистрирует обработчик для типа ошибки"""

    async def handler():
        pass

    cmd = Command(handler, name="test")

    @cmd.on_error(ValueError)
    async def on_value_error(ctx, error):
        pass

    assert len(cmd._error_handlers) == 1
    registered_handler, registered_types = cmd._error_handlers[0]
    assert registered_handler is on_value_error
    assert ValueError in registered_types


def test_on_error_catch_all():
    """on_error() без аргументов — catch-all обработчик (types=None)"""

    async def handler():
        pass

    cmd = Command(handler, name="test")

    @cmd.on_error()
    async def on_any_error(ctx, error):
        pass

    assert len(cmd._error_handlers) == 1
    _, error_types = cmd._error_handlers[0]
    assert error_types is None


def test_on_error_duplicate_catchall_raises():
    """Два catch-all обработчика вызывают ValueError"""

    async def handler():
        pass

    cmd = Command(handler, name="test")

    @cmd.on_error()
    async def first(ctx, error):
        pass

    with pytest.raises(ValueError, match="уже есть универсальный обработчик"):

        @cmd.on_error()
        async def second(ctx, error):
            pass


def test_on_error_multiple_types():
    """on_error() с несколькими типами ошибок"""

    async def handler():
        pass

    cmd = Command(handler, name="test")

    @cmd.on_error(ValueError, TypeError)
    async def on_multi_error(ctx, error):
        pass

    _, error_types = cmd._error_handlers[0]
    assert ValueError in error_types
    assert TypeError in error_types


@pytest.mark.asyncio
async def test_try_local_error_handlers_specific():
    """Локальный обработчик вызывается для совпадающего типа ошибки"""
    handled = {}

    async def handler():
        pass

    cmd = Command(handler, name="test")

    @cmd.on_error(ValueError)
    async def on_value_error(ctx, error):
        handled["type"] = type(error).__name__

    mock_ctx = unittest.mock.Mock()
    mock_ctx.msg = unittest.mock.Mock()
    mock_ctx.msg.text = "/test"
    mock_ctx.msg.from_id = 123
    mock_ctx.msg.peer_id = 456
    mock_ctx.bot = unittest.mock.Mock()
    mock_ctx.api = unittest.mock.Mock()

    error = ValueError("test")
    result = await cmd._try_local_error_handlers(mock_ctx, error, {})
    assert result is True
    assert handled["type"] == "ValueError"


@pytest.mark.asyncio
async def test_try_local_error_handlers_no_match():
    """Нет совпадающего обработчика -> False"""

    async def handler():
        pass

    cmd = Command(handler, name="test")

    @cmd.on_error(ValueError)
    async def on_value_error(ctx, error):
        pass

    mock_ctx = unittest.mock.Mock()
    error = TypeError("wrong type")
    result = await cmd._try_local_error_handlers(mock_ctx, error, {})
    assert result is False


@pytest.mark.asyncio
async def test_try_local_error_handlers_catchall():
    """Catch-all обработчик ловит любой тип ошибки"""
    handled = {}

    async def handler():
        pass

    cmd = Command(handler, name="test")

    @cmd.on_error()
    async def catch_all(ctx, error):
        handled["caught"] = True

    mock_ctx = unittest.mock.Mock()
    error = RuntimeError("runtime")
    result = await cmd._try_local_error_handlers(mock_ctx, error, {})
    assert result is True
    assert handled["caught"] is True


@pytest.mark.asyncio
async def test_try_local_error_handlers_empty():
    """Без обработчиков -> False"""

    async def handler():
        pass

    cmd = Command(handler, name="test")
    mock_ctx = unittest.mock.Mock()
    result = await cmd._try_local_error_handlers(mock_ctx, ValueError("test"), {})
    assert result is False


def test_before_invoke_registration():
    """before_invoke() регистрирует хук"""

    async def handler():
        pass

    cmd = Command(handler, name="test")

    @cmd.before_invoke()
    async def before(ctx):
        pass

    assert cmd._before_invoke is not None


def test_after_invoke_registration():
    """after_invoke() регистрирует хук"""

    async def handler():
        pass

    cmd = Command(handler, name="test")

    @cmd.after_invoke()
    async def after(ctx, result, error):
        pass

    assert cmd._after_invoke is not None


@pytest.mark.asyncio
async def test_specific_handler_takes_priority_over_catchall():
    """Специфичный обработчик приоритетнее catch-all"""
    calls = []

    async def handler():
        pass

    cmd = Command(handler, name="test")

    @cmd.on_error(ValueError)
    async def on_value_error(ctx, error):
        calls.append("specific")

    @cmd.on_error()
    async def catch_all(ctx, error):
        calls.append("catchall")

    mock_ctx = unittest.mock.Mock()
    await cmd._try_local_error_handlers(mock_ctx, ValueError("test"), {})
    assert calls == ["specific"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
