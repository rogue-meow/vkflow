"""
Tests for the listener system
"""

import pytest
from vkflow.commands.listener import Listener, listener, normalize_event_name


def test_normalize_event_name():
    """Test event name normalization"""
    assert normalize_event_name("on_message_new") == ("message_new", False)
    assert normalize_event_name("message_new") == ("message_new", False)
    assert normalize_event_name("callback") == ("message_event", False)
    assert normalize_event_name("on_callback") == ("message_event", False)
    # Test raw events
    assert normalize_event_name("on_raw_message_new") == ("message_new", True)
    assert normalize_event_name("raw_message_new") == ("message_new", True)


def test_listener_creation():
    """Test creating a listener"""

    async def handler(payload):
        pass

    # Test with explicit name
    lst = listener("message_new")(handler)
    assert isinstance(lst, Listener)
    assert lst.event_name == "message_new"

    # Test with name from function
    async def on_message_reply(payload):
        pass

    lst2 = listener()(on_message_reply)
    assert isinstance(lst2, Listener)
    assert lst2.event_name == "message_reply"


def test_listener_parameter_parsing():
    """Test parameter parsing"""

    async def handler(text, from_id, optional=None):
        pass

    lst = listener("message_new")(handler)
    assert "text" in lst._params
    assert "from_id" in lst._params
    assert "optional" in lst._params
    assert lst._params["optional"]["has_default"] is True


def test_listener_callback_alias():
    """Test callback alias"""

    async def on_callback(user_id):
        pass

    lst = listener()(on_callback)
    assert lst.event_name == "message_event"


@pytest.mark.asyncio
async def test_listener_invoke():
    """Test listener invocation with parameter injection"""
    result = {}

    async def handler(text, from_id):
        result["text"] = text
        result["from_id"] = from_id

    lst = listener("message_new")(handler)

    # Create a fake event storage
    class FakeEvent:
        def __init__(self):
            self.object = {
                "text": "Hello",
                "from_id": 123,
                "peer_id": 456,
            }
            self.type = "message_new"

    class FakeBot:
        pass

    class FakeEventStorage:
        def __init__(self):
            self.event = FakeEvent()
            self.bot = FakeBot()

    await lst.invoke(FakeEventStorage())

    assert result["text"] == "Hello"
    assert result["from_id"] == 123


@pytest.mark.asyncio
async def test_listener_with_payload():
    """Test listener with full payload"""
    result = {}

    async def handler(payload):
        result["payload"] = payload

    lst = listener("message_new")(handler)

    class FakeEvent:
        def __init__(self):
            self.object = {"text": "Test", "from_id": 123}
            self.type = "message_new"

    class FakeEventStorage:
        def __init__(self):
            self.event = FakeEvent()

    await lst.invoke(FakeEventStorage())

    assert result["payload"] == {"text": "Test", "from_id": 123}


@pytest.mark.asyncio
async def test_listener_optional_params():
    """Test listener with optional parameters"""
    result = {}

    async def handler(text, action=None):
        result["text"] = text
        result["action"] = action

    lst = listener("message_new")(handler)

    # Event without action
    class FakeEvent:
        def __init__(self):
            self.object = {"text": "Hello"}
            self.type = "message_new"

    class FakeEventStorage:
        def __init__(self):
            self.event = FakeEvent()

    await lst.invoke(FakeEventStorage())

    assert result["text"] == "Hello"
    assert result["action"] is None


def test_listener_cog_attributes():
    """Test that listener has correct Cog attributes"""

    async def on_message_new(text):
        pass

    lst = listener()(on_message_new)

    assert hasattr(lst, "__cog_listener__")
    assert lst.__cog_listener__ is True
    assert lst.__cog_listener_name__ == "message_new"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
