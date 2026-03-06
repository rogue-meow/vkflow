"""
Tests for Listener in Cog
"""

import pytest
from vkflow.commands.listener import Listener, listener
from vkflow.commands.cog import Cog


def test_listener_in_cog():
    """Test that Listener works correctly in Cog"""

    class TestCog(Cog):
        def __init__(self):
            super().__init__()
            self.called = False

        @listener()
        async def on_message_new(self, text):
            self.called = True
            self.received_text = text

    # Create cog instance
    cog = TestCog()

    # Check that listener was collected
    assert "message_new" in cog._cog_event_handlers
    assert len(cog._cog_event_handlers["message_new"]) == 1

    # Get the bound listener
    handler = cog._cog_event_handlers["message_new"][0]
    assert isinstance(handler, Listener)

    # Check that callback is bound
    assert callable(handler.callback)


@pytest.mark.asyncio
async def test_listener_invoke_in_cog():
    """Test that Listener.invoke works in Cog"""

    class TestCog(Cog):
        def __init__(self):
            super().__init__()
            self.result = {}

        @listener()
        async def on_message_new(self, text, from_id):
            self.result["text"] = text
            self.result["from_id"] = from_id

    cog = TestCog()

    # Get the bound listener
    handler = cog._cog_event_handlers["message_new"][0]

    # Create fake event storage
    class FakeEvent:
        def __init__(self):
            self.object = {
                "text": "Hello from Cog",
                "from_id": 999,
            }
            self.type = "message_new"

    class FakeEventStorage:
        def __init__(self):
            self.event = FakeEvent()

    # Invoke the listener
    await handler.invoke(FakeEventStorage())

    # Check that it was called with correct parameters
    assert cog.result["text"] == "Hello from Cog"
    assert cog.result["from_id"] == 999


@pytest.mark.asyncio
async def test_listener_with_self_parameter():
    """Test that Listener works with self parameter"""

    class TestCog(Cog):
        def __init__(self):
            super().__init__()
            self.counter = 0

        @listener()
        async def on_message_new(self, text):
            # self should be available
            self.counter += 1
            assert isinstance(self, TestCog)

    cog = TestCog()
    handler = cog._cog_event_handlers["message_new"][0]

    class FakeEvent:
        def __init__(self):
            self.object = {"text": "Test"}
            self.type = "message_new"

    class FakeEventStorage:
        def __init__(self):
            self.event = FakeEvent()

    # Invoke multiple times
    await handler.invoke(FakeEventStorage())
    await handler.invoke(FakeEventStorage())
    await handler.invoke(FakeEventStorage())

    # Check that counter was incremented
    assert cog.counter == 3


@pytest.mark.asyncio
async def test_multiple_listeners_in_cog():
    """Test multiple listeners in one Cog"""

    class TestCog(Cog):
        def __init__(self):
            super().__init__()
            self.message_count = 0
            self.callback_count = 0

        @listener()
        async def on_message_new(self, text):
            self.message_count += 1

        @listener()
        async def on_callback(self, user_id):
            self.callback_count += 1

    cog = TestCog()

    # Check both listeners were collected
    assert "message_new" in cog._cog_event_handlers
    assert "message_event" in cog._cog_event_handlers  # callback -> message_event

    # Test message_new
    handler1 = cog._cog_event_handlers["message_new"][0]

    class FakeMessageEvent:
        def __init__(self):
            self.object = {"text": "Test"}
            self.type = "message_new"

    class FakeEventStorage:
        def __init__(self, event):
            self.event = event

    await handler1.invoke(FakeEventStorage(FakeMessageEvent()))
    assert cog.message_count == 1

    # Test callback
    handler2 = cog._cog_event_handlers["message_event"][0]

    class FakeCallbackEvent:
        def __init__(self):
            self.object = {"user_id": 123}
            self.type = "message_event"

    await handler2.invoke(FakeEventStorage(FakeCallbackEvent()))
    assert cog.callback_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
