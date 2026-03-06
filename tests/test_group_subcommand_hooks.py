"""
Tests for Group subcommand hook binding via descriptor protocol (__get__).

Verifies that _cooldown_handler, _max_concurrency_handler,
_before_invoke, and _after_invoke are correctly bound to the
Cog instance when accessed through Group.__get__.
"""

import pytest

from vkflow.commands.core import Command, Group


class FakeCog:
    """Minimal Cog-like class for testing descriptor protocol"""


def _make_group_with_subcommand():
    """
    Create a Group with a subcommand, both having all four hooks set
    as plain functions (unbound methods).
    """

    async def group_handler(self):
        pass

    async def sub_handler(self):
        pass

    grp = Group(group_handler, name="grp")
    sub = Command(sub_handler, name="sub")
    grp.add_command(sub)
    return grp, sub


def test_subcommand_cooldown_handler_bound():
    """_cooldown_handler of a subcommand must be bound to the cog instance"""
    grp, sub = _make_group_with_subcommand()

    async def on_cd(self, ctx):
        pass

    sub._cooldown_handler = on_cd

    cog = FakeCog()
    bound_grp = grp.__get__(cog, FakeCog)

    bound_sub = bound_grp.all_commands["sub"]
    assert bound_sub._cooldown_handler is not None
    assert hasattr(bound_sub._cooldown_handler, "__self__")
    assert bound_sub._cooldown_handler.__self__ is cog


def test_subcommand_max_concurrency_handler_bound():
    """_max_concurrency_handler of a subcommand must be bound to the cog instance"""
    grp, sub = _make_group_with_subcommand()

    async def on_mc(self, ctx):
        pass

    sub._max_concurrency_handler = on_mc

    cog = FakeCog()
    bound_grp = grp.__get__(cog, FakeCog)

    bound_sub = bound_grp.all_commands["sub"]
    assert bound_sub._max_concurrency_handler is not None
    assert hasattr(bound_sub._max_concurrency_handler, "__self__")
    assert bound_sub._max_concurrency_handler.__self__ is cog


def test_subcommand_before_invoke_bound():
    """_before_invoke of a subcommand must be bound to the cog instance"""
    grp, sub = _make_group_with_subcommand()

    async def before(self, ctx):
        pass

    sub._before_invoke = before

    cog = FakeCog()
    bound_grp = grp.__get__(cog, FakeCog)

    bound_sub = bound_grp.all_commands["sub"]
    assert bound_sub._before_invoke is not None
    assert hasattr(bound_sub._before_invoke, "__self__")
    assert bound_sub._before_invoke.__self__ is cog


def test_subcommand_after_invoke_bound():
    """_after_invoke of a subcommand must be bound to the cog instance"""
    grp, sub = _make_group_with_subcommand()

    async def after(self, ctx):
        pass

    sub._after_invoke = after

    cog = FakeCog()
    bound_grp = grp.__get__(cog, FakeCog)

    bound_sub = bound_grp.all_commands["sub"]
    assert bound_sub._after_invoke is not None
    assert hasattr(bound_sub._after_invoke, "__self__")
    assert bound_sub._after_invoke.__self__ is cog


def test_subcommand_hooks_none_when_not_set():
    """Hooks must stay None if they were not set on the subcommand"""
    grp, _ = _make_group_with_subcommand()

    cog = FakeCog()
    bound_grp = grp.__get__(cog, FakeCog)

    bound_sub = bound_grp.all_commands["sub"]
    assert bound_sub._cooldown_handler is None
    assert bound_sub._max_concurrency_handler is None
    assert bound_sub._before_invoke is None
    assert bound_sub._after_invoke is None


def test_subcommand_non_descriptor_hooks_copied():
    """Non-descriptor hooks (e.g. lambdas) must be copied as-is"""
    grp, sub = _make_group_with_subcommand()

    # lambda doesn't have __get__ that produces bound methods
    # but actually it does in Python - all functions have __get__
    # So let's use a non-function callable
    class PlainCallable:
        """Callable without __get__ descriptor behavior for methods"""

        def __init__(self):
            # Remove __get__ to simulate a non-descriptor
            pass

        def __call__(self):
            pass

    handler = PlainCallable()
    # Explicitly delete __get__ so it's treated as non-descriptor
    # Actually objects don't have __get__ by default, only functions do
    # PlainCallable instances won't have __get__ unless inherited
    # But all functions in Python have __get__, so let's test with a
    # regular callable object
    sub._cooldown_handler = handler

    cog = FakeCog()
    bound_grp = grp.__get__(cog, FakeCog)

    bound_sub = bound_grp.all_commands["sub"]
    # Should be the same object, not bound
    assert bound_sub._cooldown_handler is handler


@pytest.mark.asyncio
async def test_subcommand_cooldown_handler_receives_self():
    """
    Integration test: the bound cooldown handler must actually
    receive the cog instance as `self` when called.
    """
    grp, sub = _make_group_with_subcommand()

    received_self = None

    async def on_cd(self):
        nonlocal received_self
        received_self = self

    sub._cooldown_handler = on_cd

    cog = FakeCog()
    bound_grp = grp.__get__(cog, FakeCog)

    bound_sub = bound_grp.all_commands["sub"]
    await bound_sub._cooldown_handler()

    assert received_self is cog


@pytest.mark.asyncio
async def test_subcommand_all_hooks_receive_self():
    """
    Integration test: all four hooks of a subcommand receive the
    cog instance as `self` when called.
    """
    grp, sub = _make_group_with_subcommand()

    results = {}

    async def on_cd(self):
        results["cooldown"] = self

    async def on_mc(self):
        results["max_concurrency"] = self

    async def before(self):
        results["before"] = self

    async def after(self):
        results["after"] = self

    sub._cooldown_handler = on_cd
    sub._max_concurrency_handler = on_mc
    sub._before_invoke = before
    sub._after_invoke = after

    cog = FakeCog()
    bound_grp = grp.__get__(cog, FakeCog)
    bound_sub = bound_grp.all_commands["sub"]

    await bound_sub._cooldown_handler()
    await bound_sub._max_concurrency_handler()
    await bound_sub._before_invoke()
    await bound_sub._after_invoke()

    assert results["cooldown"] is cog
    assert results["max_concurrency"] is cog
    assert results["before"] is cog
    assert results["after"] is cog
