"""
Тесты для app.listener() — регистрация слушателей напрямую в приложении
"""

import pytest

import vkflow as vf
from vkflow.commands.listener import Listener


def test_app_listener_creates_listener():
    """app.listener() создаёт объект Listener"""
    app = vf.App()

    @app.listener()
    async def on_message_new(payload):
        pass

    assert isinstance(on_message_new, Listener)


def test_app_listener_registers_in_event_handlers():
    """app.listener() регистрирует слушателя в event_handlers"""
    app = vf.App()

    @app.listener()
    async def on_message_new(payload):
        pass

    assert "message_new" in app.event_handlers
    assert on_message_new in app.event_handlers["message_new"]


def test_app_listener_explicit_name():
    """app.listener(name) использует явное имя"""
    app = vf.App()

    @app.listener("message_reply")
    async def handle_reply(payload):
        pass

    assert "message_reply" in app.event_handlers
    assert handle_reply in app.event_handlers["message_reply"]


def test_app_listener_alias():
    """app.listener() поддерживает алиасы событий"""
    app = vf.App()

    @app.listener()
    async def on_callback(payload):
        pass

    assert "message_event" in app.event_handlers


def test_app_listener_chat_action_registered_as_message_new():
    """Chat-action слушатели регистрируются под message_new"""
    app = vf.App()

    @app.listener()
    async def on_member_join(event):
        pass

    assert "message_new" in app.event_handlers
    assert on_member_join in app.event_handlers["message_new"]


def test_app_listener_chat_action_is_chat_action():
    """Chat-action слушатель помечен как is_chat_action"""
    app = vf.App()

    @app.listener()
    async def on_member_join(event):
        pass

    assert on_member_join.is_chat_action is True


def test_app_listener_multiple():
    """Несколько слушателей для разных событий"""
    app = vf.App()

    @app.listener()
    async def on_message_new(payload):
        pass

    @app.listener()
    async def on_message_reply(payload):
        pass

    assert "message_new" in app.event_handlers
    assert "message_reply" in app.event_handlers


def test_app_listener_same_event_multiple():
    """Несколько слушателей для одного события"""
    app = vf.App()

    @app.listener("message_new")
    async def handler1(payload):
        pass

    @app.listener("message_new")
    async def handler2(payload):
        pass

    assert len(app.event_handlers["message_new"]) == 2


@pytest.mark.asyncio
async def test_app_listener_invoke():
    """Слушатель через app.listener() вызывается с инъекцией параметров"""
    app = vf.App()
    result = {}

    @app.listener()
    async def on_message_new(text, from_id):
        result["text"] = text
        result["from_id"] = from_id

    class FakeEvent:
        def __init__(self):
            self.object = {"text": "Hello", "from_id": 123}
            self.type = "message_new"

    class FakeBot:
        pass

    class FakeEventStorage:
        def __init__(self):
            self.event = FakeEvent()
            self.bot = FakeBot()

    await on_message_new.invoke(FakeEventStorage())

    assert result["text"] == "Hello"
    assert result["from_id"] == 123


def test_app_listener_on_prefix_stripped():
    """Префикс on_ убирается из имени функции"""
    app = vf.App()

    @app.listener()
    async def on_message_reply(payload):
        pass

    assert on_message_reply.event_name == "message_reply"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
