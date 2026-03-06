"""
Tests for on_ready event and wait_until_ready() functionality
"""

import asyncio
import pytest
from unittest.mock import MagicMock

from vkflow import App
from vkflow import commands


class TestOnReady:
    """Test suite for on_ready event functionality"""

    @pytest.mark.asyncio
    async def test_on_ready_listener_in_cog(self):
        """Test that on_ready listener is called in Cog"""
        app = App()

        # Track if on_ready was called
        ready_called = []

        class TestCog(commands.Cog):
            @commands.listener()
            async def on_ready(self, bot):
                ready_called.append(bot)

        cog = TestCog()
        await app.add_cog(cog)

        # Simulate ready event
        mock_bot = MagicMock()
        await app.dispatch_event("ready", bot=mock_bot)

        # Give event handlers time to run
        await asyncio.sleep(0.1)

        # Verify on_ready was called
        assert len(ready_called) == 1
        assert ready_called[0] == mock_bot

    @pytest.mark.asyncio
    async def test_on_ready_with_custom_name(self):
        """Test that on_ready listener works with custom event name"""
        app = App()

        ready_called = []

        class TestCog(commands.Cog):
            @commands.listener("ready")
            async def handle_ready(self, bot):
                ready_called.append(bot)

        cog = TestCog()
        await app.add_cog(cog)

        mock_bot = MagicMock()
        await app.dispatch_event("ready", bot=mock_bot)

        await asyncio.sleep(0.1)

        assert len(ready_called) == 1

    @pytest.mark.asyncio
    async def test_wait_until_ready_single_bot(self):
        """Test wait_until_ready() with single bot"""
        app = App()

        # Track order of events
        events = []

        async def waiter():
            events.append("waiting")
            await app.wait_until_ready()
            events.append("ready")

        # Start waiter task
        waiter_task = asyncio.create_task(waiter())

        # Simulate bot becoming ready
        await asyncio.sleep(0.1)
        mock_bot = MagicMock()
        app._bots = [mock_bot]
        await app.dispatch_event("ready", bot=mock_bot)

        # Wait for waiter to complete
        await asyncio.wait_for(waiter_task, timeout=1.0)

        assert events == ["waiting", "ready"]

    @pytest.mark.asyncio
    async def test_wait_until_ready_multiple_bots(self):
        """Test wait_until_ready() waits for all bots"""
        app = App()

        ready_count = 0

        async def waiter():
            nonlocal ready_count
            await app.wait_until_ready()
            ready_count = len(app._bots)

        # Simulate 3 bots
        mock_bots = [MagicMock(), MagicMock(), MagicMock()]
        app._bots = mock_bots

        waiter_task = asyncio.create_task(waiter())

        # Simulate bots becoming ready one by one
        await asyncio.sleep(0.1)

        # Only dispatch ready for 2 bots - should not complete yet
        for i in range(2):
            await app.dispatch_event("ready", bot=mock_bots[i])
            await asyncio.sleep(0.05)

        # Check that waiter is still waiting
        assert not waiter_task.done()

        # Dispatch ready for the last bot
        await app.dispatch_event("ready", bot=mock_bots[2])
        await asyncio.sleep(0.1)

        # Now waiter should complete
        await asyncio.wait_for(waiter_task, timeout=1.0)
        assert ready_count == 3

    @pytest.mark.asyncio
    async def test_on_ready_app_level_handler(self):
        """Test on_ready event handler at app level"""
        app = App()

        ready_bots = []

        @app.on_event("ready")
        async def on_ready_handler(event, **kwargs):
            bot = kwargs.get("bot") or (event.bot if hasattr(event, "bot") else None)
            ready_bots.append(bot)

        mock_bot = MagicMock()
        await app.dispatch_event("ready", bot=mock_bot)

        await asyncio.sleep(0.1)

        # Note: dispatch_event creates a fake event, so we check if handler was called
        # The actual bot parameter is passed via kwargs
        assert len(ready_bots) >= 1

    @pytest.mark.asyncio
    async def test_multiple_on_ready_listeners(self):
        """Test multiple on_ready listeners are all called"""
        app = App()

        called_listeners = []

        class TestCog1(commands.Cog):
            @commands.listener()
            async def on_ready(self, bot):
                called_listeners.append("cog1")

        class TestCog2(commands.Cog):
            @commands.listener()
            async def on_ready(self, bot):
                called_listeners.append("cog2")

        await app.add_cog(TestCog1())
        await app.add_cog(TestCog2())

        mock_bot = MagicMock()
        await app.dispatch_event("ready", bot=mock_bot)

        await asyncio.sleep(0.1)

        assert "cog1" in called_listeners
        assert "cog2" in called_listeners
        assert len(called_listeners) == 2

    @pytest.mark.asyncio
    async def test_on_ready_receives_correct_bot(self):
        """Test that on_ready receives the correct bot instance"""
        app = App()

        received_bot = None

        class TestCog(commands.Cog):
            @commands.listener()
            async def on_ready(self, bot):
                nonlocal received_bot
                received_bot = bot

        await app.add_cog(TestCog())

        mock_bot = MagicMock()
        mock_bot.api = "test_api"
        await app.dispatch_event("ready", bot=mock_bot)

        await asyncio.sleep(0.1)

        assert received_bot is not None
        assert received_bot.api == "test_api"

    @pytest.mark.asyncio
    async def test_wait_until_ready_cancelled_on_close(self):
        """Test wait_until_ready() raises CancelledError when app is closed"""
        app = App()

        async def waiter():
            await app.wait_until_ready()

        waiter_task = asyncio.create_task(waiter())
        await asyncio.sleep(0.1)

        # Close the app — should unblock wait_until_ready with CancelledError
        await app.close()
        await asyncio.sleep(0.05)

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(waiter_task, timeout=1.0)

    @pytest.mark.asyncio
    async def test_wait_until_ready_after_close_raises(self):
        """Test wait_until_ready() raises immediately if app already closed"""
        app = App()
        await app.close()

        with pytest.raises(asyncio.CancelledError):
            await app.wait_until_ready()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
