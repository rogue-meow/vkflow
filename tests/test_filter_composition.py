"""
Тесты для композиции фильтров и Dynamic-фильтра
"""

import unittest.mock

import pytest

import vkflow as vf
from vkflow.app.filters import ChatOnly, DirectOnly, Dynamic, IgnoreBots, OnlyMe
from vkflow.exceptions import StopCurrentHandlingError


def _make_mock(**fields):
    mock = unittest.mock.Mock()
    mock.msg = unittest.mock.Mock()
    for key, value in fields.items():
        setattr(mock.msg, key, value)
    return mock


@pytest.mark.asyncio
async def test_dynamic_sync_filter_pass():
    """Dynamic с sync-предикатом пропускает"""
    f = Dynamic(executable=lambda ctx: ctx.msg.text == "hello")
    mock = _make_mock(text="hello")
    await f.make_decision(mock)


@pytest.mark.asyncio
async def test_dynamic_sync_filter_block():
    """Dynamic с sync-предикатом блокирует"""
    f = Dynamic(executable=lambda ctx: ctx.msg.text == "hello")
    mock = _make_mock(text="bye")
    with pytest.raises(StopCurrentHandlingError):
        await f.make_decision(mock)


@pytest.mark.asyncio
async def test_dynamic_async_filter_pass():
    """Dynamic с async-предикатом пропускает"""

    async def predicate(ctx):
        return ctx.msg.from_id > 0

    f = Dynamic(executable=predicate)
    mock = _make_mock(from_id=100)
    await f.make_decision(mock)


@pytest.mark.asyncio
async def test_dynamic_async_filter_block():
    """Dynamic с async-предикатом блокирует"""

    async def predicate(ctx):
        return ctx.msg.from_id > 0

    f = Dynamic(executable=predicate)
    mock = _make_mock(from_id=-100)
    with pytest.raises(StopCurrentHandlingError):
        await f.make_decision(mock)


@pytest.mark.asyncio
async def test_triple_and_composition():
    """Тройная AND-композиция фильтров"""
    f = OnlyMe() & IgnoreBots() & ChatOnly()
    mock = _make_mock(out=True, from_id=100, peer_id=vf.peer(1))
    await f.make_decision(mock)

    mock_fail = _make_mock(out=False, from_id=100, peer_id=vf.peer(1))
    with pytest.raises(StopCurrentHandlingError):
        await f.make_decision(mock_fail)


@pytest.mark.asyncio
async def test_triple_or_composition():
    """Тройная OR-композиция: достаточно одного"""
    f = OnlyMe() | IgnoreBots() | ChatOnly()

    mock = _make_mock(out=True, from_id=100, peer_id=100)
    await f.make_decision(mock)

    mock3 = _make_mock(out=False, from_id=100, peer_id=vf.peer(1))
    await f.make_decision(mock3)

    mock4 = _make_mock(out=False, from_id=100, peer_id=100)
    await f.make_decision(mock4)


@pytest.mark.asyncio
async def test_or_all_fail():
    """OR-композиция: все не проходят -> блокировка"""
    f = OnlyMe() | ChatOnly()

    mock = _make_mock(out=False, from_id=100, peer_id=100)
    with pytest.raises(StopCurrentHandlingError):
        await f.make_decision(mock)


@pytest.mark.asyncio
async def test_and_with_dynamic():
    """AND-композиция: встроенный + Dynamic"""
    f = IgnoreBots() & Dynamic(executable=lambda ctx: ctx.msg.text.startswith("!"))

    mock_pass = _make_mock(from_id=100, text="!ping")
    await f.make_decision(mock_pass)

    mock_fail_bot = _make_mock(from_id=-100, text="!ping")
    with pytest.raises(StopCurrentHandlingError):
        await f.make_decision(mock_fail_bot)

    mock_fail_prefix = _make_mock(from_id=100, text="ping")
    with pytest.raises(StopCurrentHandlingError):
        await f.make_decision(mock_fail_prefix)


@pytest.mark.asyncio
async def test_chat_only_direct_only_mutual_exclusion():
    """ChatOnly и DirectOnly взаимоисключающие"""
    chat = ChatOnly()
    direct = DirectOnly()

    mock_chat = _make_mock(peer_id=vf.peer(1))
    await chat.make_decision(mock_chat)
    with pytest.raises(StopCurrentHandlingError):
        await direct.make_decision(mock_chat)

    mock_direct = _make_mock(peer_id=100)
    await direct.make_decision(mock_direct)
    with pytest.raises(StopCurrentHandlingError):
        await chat.make_decision(mock_direct)


@pytest.mark.asyncio
async def test_negation_not_filter():
    """Инверсия фильтра через __invert__ (если поддерживается)"""
    f = IgnoreBots()
    if hasattr(f, "__invert__"):
        inverted = ~f
        mock_bot = _make_mock(from_id=-100)
        await inverted.make_decision(mock_bot)

        mock_user = _make_mock(from_id=100)
        with pytest.raises(StopCurrentHandlingError):
            await inverted.make_decision(mock_user)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
