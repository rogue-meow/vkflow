"""
Тесты для системы middleware
"""

import pytest

from vkflow.commands.middleware import (
    Middleware,
    MiddlewareManager,
    MiddlewarePriority,
    after_command,
    before_command,
    middleware,
)


def test_middleware_priority_ordering():
    """Middleware сортируются по приоритету"""
    manager = MiddlewareManager()

    async def low_handler():
        pass

    async def high_handler():
        pass

    async def normal_handler():
        pass

    m_low = Middleware(callback=low_handler, priority=MiddlewarePriority.LOW)
    m_high = Middleware(callback=high_handler, priority=MiddlewarePriority.HIGH)
    m_normal = Middleware(callback=normal_handler, priority=MiddlewarePriority.NORMAL)

    manager.add_middleware(m_low)
    manager.add_middleware(m_high)
    manager.add_middleware(m_normal)

    assert manager._middlewares[0].priority == MiddlewarePriority.HIGH
    assert manager._middlewares[1].priority == MiddlewarePriority.NORMAL
    assert manager._middlewares[2].priority == MiddlewarePriority.LOW


def test_middleware_remove():
    """Удаление middleware из менеджера"""
    manager = MiddlewareManager()

    async def handler():
        pass

    mw = Middleware(callback=handler, event_types=["message_new"])
    manager.add_middleware(mw)
    assert len(manager._middlewares) == 1
    assert len(manager._event_middlewares.get("message_new", [])) == 1

    result = manager.remove_middleware(mw)
    assert result is True
    assert len(manager._middlewares) == 0
    assert len(manager._event_middlewares.get("message_new", [])) == 0


def test_middleware_remove_nonexistent():
    """Удаление несуществующего middleware возвращает False"""
    manager = MiddlewareManager()

    async def handler():
        pass

    mw = Middleware(callback=handler)
    result = manager.remove_middleware(mw)
    assert result is False


def test_get_middlewares_for_event_global_and_specific():
    """Глобальные и специфичные middleware объединяются"""
    manager = MiddlewareManager()

    async def global_handler():
        pass

    async def specific_handler():
        pass

    m_global = Middleware(callback=global_handler, event_types=None)
    m_specific = Middleware(callback=specific_handler, event_types=["message_new"])

    manager.add_middleware(m_global)
    manager.add_middleware(m_specific)

    result = manager.get_middlewares_for_event("message_new")
    assert len(result) == 2

    result_other = manager.get_middlewares_for_event("message_reply")
    assert len(result_other) == 1
    assert result_other[0].callback is global_handler


@pytest.mark.asyncio
async def test_before_command_hooks_all_pass():
    """Before-command хуки: все проходят -> True"""
    manager = MiddlewareManager()
    calls = []

    async def hook1(ctx):
        calls.append("hook1")

    async def hook2(ctx):
        calls.append("hook2")

    manager.add_before_command_hook(hook1)
    manager.add_before_command_hook(hook2)

    from unittest.mock import Mock

    ctx = Mock()
    result = await manager.run_before_command_hooks(ctx)
    assert result is True
    assert calls == ["hook1", "hook2"]


@pytest.mark.asyncio
async def test_before_command_hook_cancels():
    """Before-command хук возвращает False -> команда отменяется"""
    manager = MiddlewareManager()
    calls = []

    async def cancel_hook(ctx):
        calls.append("cancel")
        return False

    async def should_not_run(ctx):
        calls.append("after_cancel")

    manager.add_before_command_hook(cancel_hook)
    manager.add_before_command_hook(should_not_run)

    from unittest.mock import Mock

    ctx = Mock()
    result = await manager.run_before_command_hooks(ctx)
    assert result is False
    assert calls == ["cancel"]


@pytest.mark.asyncio
async def test_after_command_hooks_run():
    """After-command хуки вызываются с result и error"""
    manager = MiddlewareManager()
    captured = {}

    async def hook(ctx, result, error):
        captured["result"] = result
        captured["error"] = error

    manager.add_after_command_hook(hook)

    from unittest.mock import Mock

    ctx = Mock()
    await manager.run_after_command_hooks(ctx, result="ok", error=None)
    assert captured["result"] == "ok"
    assert captured["error"] is None


@pytest.mark.asyncio
async def test_after_command_hooks_with_error():
    """After-command хуки получают ошибку"""
    manager = MiddlewareManager()
    captured = {}

    async def hook(ctx, error):
        captured["error"] = error

    manager.add_after_command_hook(hook)

    from unittest.mock import Mock

    ctx = Mock()
    err = ValueError("boom")
    await manager.run_after_command_hooks(ctx, error=err)
    assert captured["error"] is err


@pytest.mark.asyncio
async def test_before_command_hook_exception_does_not_crash():
    """Исключение в before-command хуке не ломает выполнение"""
    manager = MiddlewareManager()

    async def broken_hook(ctx):
        raise RuntimeError("broken")

    async def next_hook(ctx):
        pass

    manager.add_before_command_hook(broken_hook)
    manager.add_before_command_hook(next_hook)

    from unittest.mock import Mock

    ctx = Mock()
    result = await manager.run_before_command_hooks(ctx)
    assert result is True


def test_middleware_decorator():
    """Декоратор middleware() создаёт объект Middleware"""

    @middleware(priority=MiddlewarePriority.HIGH, event_types=["message_new"])
    async def my_mw(ctx, call_next):
        pass

    assert isinstance(my_mw, Middleware)
    assert my_mw.priority == MiddlewarePriority.HIGH
    assert my_mw.event_types == ["message_new"]


def test_before_command_decorator():
    """Декоратор before_command() устанавливает маркер"""

    @before_command
    async def my_hook(ctx):
        pass

    assert hasattr(my_hook, "__vkflow_before_command__")
    assert my_hook.__vkflow_before_command__ is True


def test_after_command_decorator():
    """Декоратор after_command() устанавливает маркер"""

    @after_command
    async def my_hook(ctx, result, error):
        pass

    assert hasattr(my_hook, "__vkflow_after_command__")
    assert my_hook.__vkflow_after_command__ is True


def test_before_command_decorator_with_parens():
    """before_command() работает и как @before_command, и как @before_command()"""

    @before_command()
    async def my_hook(ctx):
        pass

    assert my_hook.__vkflow_before_command__ is True


def test_middleware_event_type_routing():
    """Middleware с event_types регистрируются в _event_middlewares"""
    manager = MiddlewareManager()

    async def handler():
        pass

    mw = Middleware(callback=handler, event_types=["message_new", "message_reply"])
    manager.add_middleware(mw)

    assert mw in manager._event_middlewares["message_new"]
    assert mw in manager._event_middlewares["message_reply"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
