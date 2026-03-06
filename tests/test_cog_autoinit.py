"""
Tests for automatic Cog initialization (no need for super().__init__())
"""

import pytest
from vkflow.commands.cog import Cog
from vkflow.commands.core import command
from vkflow.commands.listener import listener
from vkflow.commands.context import Context


def test_cog_without_init():
    """Test that Cog works without __init__ at all"""

    class SimpleCog(Cog):
        @command()
        async def hello(self, ctx: Context):
            await ctx.send("Hello")

    cog = SimpleCog()

    # Check that base initialization happened
    assert hasattr(cog, "_cog_commands")
    assert hasattr(cog, "_cog_event_handlers")
    assert cog.app is None
    assert cog.bot is None

    # Check that command was collected
    assert len(cog._cog_commands) == 1
    assert cog._cog_commands[0].name == "hello"


def test_cog_with_init_without_super():
    """Test that Cog works with __init__ but WITHOUT super().__init__()"""

    class CounterCog(Cog):
        def __init__(self):
            # No super().__init__()!
            self.counter = 0

        @command()
        async def count(self, ctx: Context):
            self.counter += 1
            await ctx.send(f"Count: {self.counter}")

    cog = CounterCog()

    # Check that user's initialization happened
    assert cog.counter == 0

    # Check that base initialization happened automatically
    assert hasattr(cog, "_cog_commands")
    assert cog.app is None
    assert cog.bot is None

    # Check that command was collected
    assert len(cog._cog_commands) == 1
    assert cog._cog_commands[0].name == "count"


def test_cog_with_init_with_super():
    """Test backward compatibility - Cog with super().__init__() should still work"""

    class OldCog(Cog):
        def __init__(self):
            super().__init__()  # Old style with super()
            self.data = {}

        @command()
        async def save(self, ctx: Context):
            await ctx.send("Saved")

    cog = OldCog()

    # Check that user's initialization happened
    assert cog.data == {}

    # Check that base initialization happened (only once!)
    assert hasattr(cog, "_cog_commands")
    assert cog.app is None

    # Check that command was collected (should not be duplicated)
    assert len(cog._cog_commands) == 1
    assert cog._cog_commands[0].name == "save"


def test_cog_with_parameters():
    """Test Cog with __init__ parameters"""

    class ConfigCog(Cog):
        def __init__(self, name, value):
            # No super().__init__()
            self.name = name
            self.value = value

        @command()
        async def show_config(self, ctx: Context):
            await ctx.send(f"{self.name}: {self.value}")

    cog = ConfigCog("test", 42)

    # Check user's initialization
    assert cog.name == "test"
    assert cog.value == 42

    # Check base initialization
    assert hasattr(cog, "_cog_commands")
    assert len(cog._cog_commands) == 1


def test_cog_metadata_collected():
    """Test that metaclass collects metadata correctly"""

    class TestCog(Cog):
        @command()
        async def cmd1(self, ctx: Context):
            pass

        @command()
        async def cmd2(self, ctx: Context):
            pass

        @listener()
        async def on_message_new(self, payload):
            pass

    # Check metadata at class level
    assert hasattr(TestCog, "__cog_commands_meta__")
    assert "cmd1" in TestCog.__cog_commands_meta__
    assert "cmd2" in TestCog.__cog_commands_meta__
    assert "message_new" in TestCog.__cog_event_handlers_meta__

    # Check instance
    cog = TestCog()
    assert len(cog._cog_commands) == 2
    assert len(cog._cog_event_handlers["message_new"]) == 1


def test_cog_no_double_collection():
    """Test that commands are not collected twice when super().__init__() is called"""

    class TestCog(Cog):
        def __init__(self):
            super().__init__()  # Should not cause double collection

        @command()
        async def test(self, ctx: Context):
            pass

    cog = TestCog()

    # Commands should be collected only once
    assert len(cog._cog_commands) == 1


def test_cog_inheritance():
    """Test Cog inheritance"""

    class BaseCog(Cog):
        def __init__(self):
            self.base_value = 1

        @command()
        async def base_cmd(self, ctx: Context):
            pass

    class ChildCog(BaseCog):
        def __init__(self):
            super().__init__()
            self.child_value = 2

        @command()
        async def child_cmd(self, ctx: Context):
            pass

    cog = ChildCog()

    # Check inheritance worked
    assert cog.base_value == 1
    assert cog.child_value == 2

    # Check that both commands are collected
    # Note: child should have both base and child commands
    assert len(cog._cog_commands) == 1  # Only child_cmd, base_cmd is in parent class
    assert cog._cog_commands[0].name == "child_cmd"


def test_cog_qualified_name():
    """Test that qualified_name property works"""

    class MyCog(Cog):
        pass

    cog = MyCog()
    assert cog.qualified_name == "MyCog"


def test_cog_description():
    """Test that description property works"""

    class DocumentedCog(Cog):
        """This is a documented cog"""

    cog = DocumentedCog()
    assert cog.description == "This is a documented cog"


def test_multiple_cog_instances():
    """Test that multiple instances of the same Cog work correctly"""

    class CounterCog(Cog):
        def __init__(self):
            self.counter = 0

        @command()
        async def count(self, ctx: Context):
            pass

    cog1 = CounterCog()
    cog2 = CounterCog()

    # Each instance should have its own counter
    cog1.counter = 10
    cog2.counter = 20

    assert cog1.counter == 10
    assert cog2.counter == 20

    # But both should have commands
    assert len(cog1._cog_commands) == 1
    assert len(cog2._cog_commands) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
