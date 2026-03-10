"""
Тесты для системы проверок (checks)
"""

import unittest.mock

import pytest

from vkflow.commands.checks import Check, CheckFailureError, check, check_any
from vkflow.commands.core import Command
from vkflow.exceptions import StopCurrentHandlingError


def _make_ctx_mock():
    mock = unittest.mock.Mock()
    mock.msg = unittest.mock.Mock()
    mock.msg.from_id = 123
    mock.msg.peer_id = 456
    mock.msg.text = "test"
    mock.bot = unittest.mock.Mock()
    mock.api = unittest.mock.Mock()
    mock.app = unittest.mock.Mock()
    mock.send = unittest.mock.AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_check_sync_predicate_pass():
    """Sync-предикат проходит проверку"""

    def predicate(ctx):
        return True

    c = Check(predicate=predicate)
    mock = _make_ctx_mock()
    await c.make_decision(mock)


@pytest.mark.asyncio
async def test_check_sync_predicate_fail():
    """Sync-предикат не проходит -> StopCurrentHandlingError"""

    def predicate(ctx):
        return False

    c = Check(predicate=predicate)
    mock = _make_ctx_mock()
    with pytest.raises(StopCurrentHandlingError):
        await c.make_decision(mock)


@pytest.mark.asyncio
async def test_check_async_predicate_pass():
    """Async-предикат проходит проверку"""

    async def predicate(ctx):
        return True

    c = Check(predicate=predicate)
    mock = _make_ctx_mock()
    await c.make_decision(mock)


@pytest.mark.asyncio
async def test_check_async_predicate_fail():
    """Async-предикат не проходит"""

    async def predicate(ctx):
        return False

    c = Check(predicate=predicate)
    mock = _make_ctx_mock()
    with pytest.raises(StopCurrentHandlingError):
        await c.make_decision(mock)


@pytest.mark.asyncio
async def test_check_with_error_message():
    """Проваленная проверка с error_message отправляет сообщение"""
    from vkflow.commands.context import Context

    def predicate(ctx):
        return False

    c = Check(predicate=predicate, error_message="Нет доступа!")
    mock = _make_ctx_mock()

    with (
        pytest.raises(StopCurrentHandlingError),
        unittest.mock.patch.object(Context, "send", new_callable=unittest.mock.AsyncMock),
    ):
        await c.make_decision(mock)


def test_check_as_decorator_on_function():
    """Check работает как декоратор на функции"""

    def predicate(ctx):
        return True

    c = Check(predicate=predicate)

    async def handler(ctx):
        pass

    decorated = c(handler)
    assert hasattr(decorated, "__vkflow_checks__")
    assert c in decorated.__vkflow_checks__


def test_check_as_decorator_on_command():
    """Check работает как декоратор на Command"""

    def predicate(ctx):
        return True

    c = Check(predicate=predicate)

    async def handler():
        pass

    cmd = Command(handler, name="test")
    result = c(cmd)
    assert result is cmd
    assert result.filter is c


def test_check_stacking_on_command():
    """Несколько Check на одной команде комбинируются через AND"""

    def pred1(ctx):
        return True

    def pred2(ctx):
        return True

    c1 = Check(predicate=pred1)
    c2 = Check(predicate=pred2)

    async def handler():
        pass

    cmd = Command(handler, name="test")
    c1(cmd)
    c2(cmd)
    assert cmd.filter is not None


def test_check_factory():
    """check() создаёт Check через фабрику"""

    def predicate(ctx):
        return ctx.author in [1, 2, 3]

    c = check(predicate, error_message="Не в списке!")
    assert isinstance(c, Check)
    assert c.error_message == "Не в списке!"


def test_check_any_creation():
    """check_any() создаёт комбинированную проверку"""

    def pred1(ctx):
        return False

    def pred2(ctx):
        return True

    c1 = Check(predicate=pred1)
    c2 = Check(predicate=pred2)

    combined = check_any(c1, c2, error_message="Ни одна не прошла")
    assert isinstance(combined, Check)


@pytest.mark.asyncio
async def test_check_predicate_raises_stops_handling():
    """Исключение в предикате -> StopCurrentHandlingError"""

    def predicate(ctx):
        raise RuntimeError("broken")

    c = Check(predicate=predicate)
    mock = _make_ctx_mock()

    with pytest.raises(StopCurrentHandlingError):
        await c.make_decision(mock)


def test_check_failure_error():
    """CheckFailureError хранит check и message"""
    c = Check(predicate=lambda ctx: True)
    err = CheckFailureError(check=c, message="Нет доступа")
    assert err.check is c
    assert err.message == "Нет доступа"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
