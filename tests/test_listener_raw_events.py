"""
Tests for raw event listeners (on_raw_*)
"""

import pytest
from vkflow.commands.listener import listener


@pytest.mark.asyncio
async def test_raw_event_listener():
    """Test that raw event listeners receive dict payload without field injection"""

    result = {}

    @listener()
    async def on_raw_message_new(payload):
        """Raw event listener - should receive payload as dict"""
        result["payload"] = payload
        result["payload_type"] = type(payload).__name__

    # Check that it was marked as raw
    assert on_raw_message_new.is_raw is True
    assert on_raw_message_new.event_name == "message_new"

    # Create fake event storage
    class FakeEvent:
        def __init__(self):
            self.object = {
                "text": "Hello",
                "from_id": 123,
                "id": 456,
            }
            self.type = "message_new"

    class FakeEventStorage:
        def __init__(self):
            self.event = FakeEvent()

    # Invoke the listener
    await on_raw_message_new.invoke(FakeEventStorage())

    # Check that payload was passed as dict
    assert result["payload"] == {"text": "Hello", "from_id": 123, "id": 456}
    assert result["payload_type"] == "dict"


@pytest.mark.asyncio
async def test_raw_event_with_field_injection():
    """Test that raw events also support automatic field injection"""

    result = {}

    @listener()
    async def on_raw_message_new(text, from_id):
        """Raw events can also inject fields from payload"""
        result["text"] = text
        result["from_id"] = from_id

    # Create fake event storage
    class FakeEvent:
        def __init__(self):
            self.object = {
                "text": "Hello",
                "from_id": 123,
            }
            self.type = "message_new"

    class FakeEventStorage:
        def __init__(self):
            self.event = FakeEvent()

    # Invoke the listener - should work with field injection
    await on_raw_message_new.invoke(FakeEventStorage())

    # Verify that fields were injected
    assert result["text"] == "Hello"
    assert result["from_id"] == 123


@pytest.mark.asyncio
async def test_normal_vs_raw_event():
    """Test that normal events do field injection but raw events don't"""

    normal_result = {}
    raw_result = {}

    @listener()
    async def on_message_new(text, from_id):
        """Normal event - should do field injection"""
        normal_result["text"] = text
        normal_result["from_id"] = from_id

    @listener()
    async def on_raw_message_reply(payload):
        """Raw event - should receive payload dict"""
        raw_result["payload"] = payload

    # Check event types
    assert on_message_new.is_raw is False
    assert on_raw_message_reply.is_raw is True

    # Create fake event storage
    class FakeEvent:
        def __init__(self, event_data):
            self.object = event_data
            self.type = "message_new"

    class FakeEventStorage:
        def __init__(self, event_data):
            self.event = FakeEvent(event_data)

    event_data = {
        "text": "Test message",
        "from_id": 999,
        "id": 111,
    }

    # Test normal event - should inject fields
    await on_message_new.invoke(FakeEventStorage(event_data))
    assert normal_result["text"] == "Test message"
    assert normal_result["from_id"] == 999

    # Test raw event - should pass payload dict
    await on_raw_message_reply.invoke(FakeEventStorage(event_data))
    assert raw_result["payload"] == event_data


@pytest.mark.asyncio
async def test_raw_event_with_event_parameter():
    """Test that raw events can still receive event parameter"""

    result = {}

    @listener()
    async def on_raw_message_new(event, payload):
        """Raw event can receive both event and payload"""
        result["event"] = event
        result["payload"] = payload

    # Create fake event storage
    class FakeEvent:
        def __init__(self):
            self.object = {"text": "Hello", "from_id": 123}
            self.type = "message_new"

    class FakeEventStorage:
        def __init__(self):
            self.event = FakeEvent()

    event_storage = FakeEventStorage()

    # Invoke the listener
    await on_raw_message_new.invoke(event_storage)

    # Check that both event and payload were passed
    assert result["event"] == event_storage
    assert result["payload"] == {"text": "Hello", "from_id": 123}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
