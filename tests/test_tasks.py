from __future__ import annotations

import asyncio
import contextlib
import datetime

import pytest

from vkflow.utils.sentinel import MISSING, MissingSentinel
from vkflow.commands.tasks import (
    Loop,
    loop,
    ExponentialBackoff,
    SleepHandle,
    utcnow,
    compute_timedelta,
)


# ─── Helpers ───


async def dummy_coro():
    pass


call_count = 0


async def counting_coro():
    global call_count
    call_count += 1


def sync_func():
    pass


# ─── MissingSentinel tests ───


class TestMissingSentinel:
    def test_singleton(self):
        a = MissingSentinel()
        b = MissingSentinel()
        assert a is b

    def test_bool_is_false(self):
        assert not MISSING
        assert bool(MISSING) is False

    def test_repr(self):
        assert repr(MISSING) == "MISSING"

    def test_eq_only_identity(self):
        assert MISSING == MISSING
        assert MISSING != 42
        assert MISSING != None  # noqa: E711
        assert MISSING != False  # noqa: E712

    def test_hash_stable(self):
        assert hash(MISSING) == hash(MISSING)
        s = {MISSING, MISSING}
        assert len(s) == 1


# ─── utcnow / compute_timedelta tests ───


class TestTimeUtils:
    def test_utcnow_is_aware(self):
        now = utcnow()
        assert now.tzinfo is not None
        assert now.tzinfo == datetime.UTC

    def test_compute_timedelta_future(self):
        future = utcnow() + datetime.timedelta(seconds=10)
        delta = compute_timedelta(future)
        assert 9.0 <= delta <= 11.0

    def test_compute_timedelta_past_returns_zero(self):
        past = utcnow() - datetime.timedelta(seconds=10)
        delta = compute_timedelta(past)
        assert delta == 0.0

    def test_compute_timedelta_naive_treated_as_utc(self):
        now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        naive_future = now + datetime.timedelta(seconds=5)
        delta = compute_timedelta(naive_future)
        assert 3.0 <= delta <= 7.0


# ─── ExponentialBackoff tests ───


class TestExponentialBackoff:
    def test_delay_increases_exponentially_integral(self):
        backoff = ExponentialBackoff(base=1, integral=True)
        d1 = backoff.delay()
        d2 = backoff.delay()
        d3 = backoff.delay()
        assert d1 == 2
        assert d2 == 4
        assert d3 == 8

    def test_delay_with_jitter(self):
        backoff = ExponentialBackoff(base=1, integral=False)
        d = backoff.delay()
        assert 2.0 <= d <= 3.0

    def test_delay_caps_at_max(self):
        backoff = ExponentialBackoff(base=1, integral=True)
        for _ in range(20):
            d = backoff.delay()
        assert d == 1024

    def test_custom_base(self):
        backoff = ExponentialBackoff(base=2, integral=True)
        d1 = backoff.delay()
        assert d1 == 4


# ─── SleepHandle tests ───


class TestSleepHandle:
    @pytest.mark.asyncio
    async def test_sleep_handle_resolves(self):
        loop = asyncio.get_running_loop()
        dt = utcnow() + datetime.timedelta(milliseconds=50)
        handle = SleepHandle(dt=dt, loop=loop)
        result = await handle.wait()
        assert result is True
        assert handle.done()

    @pytest.mark.asyncio
    async def test_sleep_handle_cancel(self):
        loop = asyncio.get_running_loop()
        dt = utcnow() + datetime.timedelta(seconds=10)
        handle = SleepHandle(dt=dt, loop=loop)
        assert not handle.done()
        handle.cancel()
        assert handle.done()

    @pytest.mark.asyncio
    async def test_sleep_handle_recalculate(self):
        loop = asyncio.get_running_loop()
        dt_far = utcnow() + datetime.timedelta(seconds=100)
        handle = SleepHandle(dt=dt_far, loop=loop)
        assert not handle.done()

        dt_soon = utcnow() + datetime.timedelta(milliseconds=50)
        handle.recalculate(dt_soon)

        result = await handle.wait()
        assert result is True


# ─── Loop creation tests ───


class TestLoopCreation:
    def test_create_with_seconds(self):
        lp = Loop(dummy_coro, seconds=5)
        assert lp.seconds == 5.0
        assert lp.minutes == 0.0
        assert lp.hours == 0.0
        assert lp.time is None
        assert lp.count is None

    def test_create_with_minutes(self):
        lp = Loop(dummy_coro, minutes=10)
        assert lp.minutes == 10.0

    def test_create_with_hours(self):
        lp = Loop(dummy_coro, hours=2)
        assert lp.hours == 2.0

    def test_create_with_count(self):
        lp = Loop(dummy_coro, seconds=1, count=5)
        assert lp.count == 5

    def test_create_with_time(self):
        t = datetime.time(12, 0, tzinfo=datetime.UTC)
        lp = Loop(dummy_coro, time=t)
        assert lp.time == [t]
        assert lp.seconds is None

    def test_create_with_time_sequence(self):
        t1 = datetime.time(8, 0, tzinfo=datetime.UTC)
        t2 = datetime.time(20, 0, tzinfo=datetime.UTC)
        lp = Loop(dummy_coro, time=[t2, t1])
        assert lp.time == [t1, t2]

    def test_create_with_time_deduplicates(self):
        t = datetime.time(12, 0, tzinfo=datetime.UTC)
        lp = Loop(dummy_coro, time=[t, t, t])
        assert lp.time == [t]

    def test_naive_time_gets_utc(self):
        t = datetime.time(12, 0)
        lp = Loop(dummy_coro, time=t)
        assert lp.time[0].tzinfo == datetime.UTC

    def test_reject_sync_function(self):
        with pytest.raises(TypeError, match="Expected coroutine function"):
            Loop(sync_func, seconds=1)

    def test_reject_zero_count(self):
        with pytest.raises(ValueError, match="count must be greater than 0"):
            Loop(dummy_coro, seconds=1, count=0)

    def test_reject_negative_count(self):
        with pytest.raises(ValueError, match="count must be greater than 0"):
            Loop(dummy_coro, seconds=1, count=-1)

    def test_reject_negative_interval(self):
        with pytest.raises(ValueError, match="less than zero"):
            Loop(dummy_coro, seconds=-10)

    def test_reject_mixed_time_and_interval(self):
        t = datetime.time(12, 0, tzinfo=datetime.UTC)
        with pytest.raises(TypeError, match="Cannot mix"):
            Loop(dummy_coro, time=t, seconds=5)

    def test_reject_empty_time_sequence(self):
        with pytest.raises(ValueError, match="must not be an empty sequence"):
            Loop(dummy_coro, time=[])

    def test_reject_invalid_time_type(self):
        with pytest.raises(TypeError, match="Expected a sequence of"):
            Loop(dummy_coro, time="not a time")

    def test_reject_invalid_time_in_sequence(self):
        t = datetime.time(12, 0, tzinfo=datetime.UTC)
        with pytest.raises(TypeError, match="at index 1"):
            Loop(dummy_coro, time=[t, "bad"])


# ─── Loop __repr__ tests ───


class TestLoopRepr:
    def test_repr_seconds(self):
        lp = Loop(dummy_coro, seconds=5)
        r = repr(lp)
        assert "<Loop" in r
        assert "seconds=5.0" in r
        assert "running=False" in r

    def test_repr_minutes_hours(self):
        lp = Loop(dummy_coro, minutes=10, hours=2)
        r = repr(lp)
        assert "minutes=10.0" in r
        assert "hours=2.0" in r

    def test_repr_with_count(self):
        lp = Loop(dummy_coro, seconds=1, count=3)
        r = repr(lp)
        assert "count=3" in r

    def test_repr_with_time(self):
        t = datetime.time(12, 0, tzinfo=datetime.UTC)
        lp = Loop(dummy_coro, time=t)
        r = repr(lp)
        assert "time=" in r
        assert "seconds=" not in r

    def test_repr_coro_name(self):
        lp = Loop(dummy_coro, seconds=1)
        assert "dummy_coro" in repr(lp)


# ─── Loop properties (not running) ───


class TestLoopProperties:
    def test_current_loop_initial(self):
        lp = Loop(dummy_coro, seconds=1)
        assert lp.current_loop == 0

    def test_next_iteration_not_running(self):
        lp = Loop(dummy_coro, seconds=1)
        assert lp.next_iteration is None

    def test_is_running_initial(self):
        lp = Loop(dummy_coro, seconds=1)
        assert lp.is_running() is False

    def test_failed_initial(self):
        lp = Loop(dummy_coro, seconds=1)
        assert lp.failed() is False

    def test_is_being_cancelled_initial(self):
        lp = Loop(dummy_coro, seconds=1)
        assert lp.is_being_cancelled() is False

    def test_get_task_initial(self):
        lp = Loop(dummy_coro, seconds=1)
        assert lp.get_task() is None


# ─── Loop exception type management ───


class TestExceptionTypes:
    def test_default_exception_types(self):
        lp = Loop(dummy_coro, seconds=1)
        assert OSError in lp._valid_exception
        assert asyncio.TimeoutError in lp._valid_exception

    def test_add_exception_type(self):
        lp = Loop(dummy_coro, seconds=1)
        lp.add_exception_type(KeyError)
        assert KeyError in lp._valid_exception

    def test_add_non_class_raises(self):
        lp = Loop(dummy_coro, seconds=1)
        with pytest.raises(TypeError, match="must be a class"):
            lp.add_exception_type("not a class")

    def test_add_non_exception_raises(self):
        lp = Loop(dummy_coro, seconds=1)
        with pytest.raises(TypeError, match="must inherit from BaseException"):
            lp.add_exception_type(int)

    def test_remove_exception_type(self):
        lp = Loop(dummy_coro, seconds=1)
        result = lp.remove_exception_type(OSError)
        assert result is True
        assert OSError not in lp._valid_exception

    def test_remove_nonexistent_returns_false(self):
        lp = Loop(dummy_coro, seconds=1)
        result = lp.remove_exception_type(KeyError)
        assert result is False

    def test_clear_exception_types(self):
        lp = Loop(dummy_coro, seconds=1)
        lp.clear_exception_types()
        assert lp._valid_exception == ()


# ─── Loop clone tests ───


class TestLoopClone:
    def test_clone_preserves_interval(self):
        lp = Loop(dummy_coro, seconds=5, minutes=10)
        clone = lp.clone()
        assert clone.seconds == 5.0
        assert clone.minutes == 10.0
        assert clone is not lp

    def test_clone_preserves_count(self):
        lp = Loop(dummy_coro, seconds=1, count=3)
        clone = lp.clone()
        assert clone.count == 3

    def test_clone_preserves_reconnect(self):
        lp = Loop(dummy_coro, seconds=1, reconnect=False)
        clone = lp.clone()
        assert clone.reconnect is False

    def test_clone_preserves_callbacks(self):
        lp = Loop(dummy_coro, seconds=1)

        @lp.before_loop
        async def before():
            pass

        @lp.after_loop
        async def after():
            pass

        clone = lp.clone()
        assert clone._before_loop is before
        assert clone._after_loop is after

    def test_clone_preserves_time(self):
        t = datetime.time(12, 0, tzinfo=datetime.UTC)
        lp = Loop(dummy_coro, time=t)
        clone = lp.clone()
        assert clone.time == [t]

    def test_clone_independent_state(self):
        lp = Loop(dummy_coro, seconds=1)
        clone = lp.clone()
        clone.add_exception_type(KeyError)
        assert KeyError not in lp._valid_exception


# ─── Loop callback decorators ───


class TestCallbackDecorators:
    def test_before_loop_decorator(self):
        lp = Loop(dummy_coro, seconds=1)

        @lp.before_loop
        async def my_before():
            pass

        assert lp._before_loop is my_before

    def test_after_loop_decorator(self):
        lp = Loop(dummy_coro, seconds=1)

        @lp.after_loop
        async def my_after():
            pass

        assert lp._after_loop is my_after

    def test_error_decorator(self):
        lp = Loop(dummy_coro, seconds=1)

        @lp.error
        async def my_error(exc):
            pass

        assert lp._error_handler is my_error

    def test_before_loop_rejects_sync(self):
        lp = Loop(dummy_coro, seconds=1)
        with pytest.raises(TypeError, match="Expected coroutine function"):

            @lp.before_loop
            def not_async():
                pass

    def test_after_loop_rejects_sync(self):
        lp = Loop(dummy_coro, seconds=1)
        with pytest.raises(TypeError, match="Expected coroutine function"):

            @lp.after_loop
            def not_async():
                pass

    def test_error_rejects_sync(self):
        lp = Loop(dummy_coro, seconds=1)
        with pytest.raises(TypeError, match="Expected coroutine function"):

            @lp.error
            def not_async(exc):
                pass


# ─── Loop change_interval tests ───


class TestChangeInterval:
    def test_change_to_seconds(self):
        lp = Loop(dummy_coro, seconds=1)
        lp.change_interval(seconds=10)
        assert lp.seconds == 10.0

    def test_change_to_time(self):
        lp = Loop(dummy_coro, seconds=1)
        t = datetime.time(15, 0, tzinfo=datetime.UTC)
        lp.change_interval(time=t)
        assert lp.time == [t]
        assert lp.seconds is None

    def test_change_from_time_to_interval(self):
        t = datetime.time(12, 0, tzinfo=datetime.UTC)
        lp = Loop(dummy_coro, time=t)
        lp.change_interval(minutes=30)
        assert lp.minutes == 30.0
        assert lp.time is None

    def test_change_rejects_mixed(self):
        lp = Loop(dummy_coro, seconds=1)
        t = datetime.time(12, 0, tzinfo=datetime.UTC)
        with pytest.raises(TypeError, match="Cannot mix"):
            lp.change_interval(time=t, seconds=5)


# ─── Loop start / stop / cancel (async) ───


class TestLoopExecution:
    @pytest.mark.asyncio
    async def test_start_and_count(self):
        results = []

        async def track():
            results.append(1)

        lp = Loop(track, seconds=0, count=3)
        task = lp.start()
        await task
        assert len(results) == 3
        assert lp.is_running() is False

    @pytest.mark.asyncio
    async def test_start_twice_raises(self):
        async def slow():
            await asyncio.sleep(10)

        lp = Loop(slow, seconds=0, count=1)
        lp.start()
        with pytest.raises(RuntimeError, match="already launched"):
            lp.start()
        lp.cancel()
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_stop_gracefully(self):
        results = []

        async def track():
            results.append(1)
            if len(results) >= 2:
                lp.stop()

        lp = Loop(track, seconds=0)
        task = lp.start()
        await task
        assert len(results) >= 2

    @pytest.mark.asyncio
    async def test_cancel(self):
        async def forever():
            await asyncio.sleep(100)

        lp = Loop(forever, seconds=0, count=1)
        lp.start()
        await asyncio.sleep(0.01)
        lp.cancel()
        await asyncio.sleep(0.05)
        assert lp.is_running() is False

    @pytest.mark.asyncio
    async def test_get_task_while_running(self):
        async def slow():
            await asyncio.sleep(10)

        lp = Loop(slow, seconds=0, count=1)
        task = lp.start()
        assert lp.get_task() is task
        lp.cancel()
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_current_loop_increments(self):
        iterations = []

        async def track():
            iterations.append(lp.current_loop)

        lp = Loop(track, seconds=0, count=3)
        await lp.start()
        assert iterations == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_is_running_true_while_active(self):
        running_states = []

        async def track():
            running_states.append(lp.is_running())

        lp = Loop(track, seconds=0, count=1)
        await lp.start()
        assert running_states == [True]
        assert lp.is_running() is False


# ─── Loop before/after hooks ───


class TestLoopHooks:
    @pytest.mark.asyncio
    async def test_before_loop_called(self):
        order = []

        async def body():
            order.append("body")

        lp = Loop(body, seconds=0, count=1)

        @lp.before_loop
        async def before():
            order.append("before")

        await lp.start()
        assert order == ["before", "body"]

    @pytest.mark.asyncio
    async def test_after_loop_called(self):
        order = []

        async def body():
            order.append("body")

        lp = Loop(body, seconds=0, count=1)

        @lp.after_loop
        async def after():
            order.append("after")

        await lp.start()
        assert order == ["body", "after"]

    @pytest.mark.asyncio
    async def test_before_and_after_order(self):
        order = []

        async def body():
            order.append("body")

        lp = Loop(body, seconds=0, count=2)

        @lp.before_loop
        async def before():
            order.append("before")

        @lp.after_loop
        async def after():
            order.append("after")

        await lp.start()
        assert order == ["before", "body", "body", "after"]

    @pytest.mark.asyncio
    async def test_after_loop_called_on_cancel(self):
        after_called = []

        async def slow():
            await asyncio.sleep(100)

        lp = Loop(slow, seconds=0, count=1)

        @lp.after_loop
        async def after():
            after_called.append(True)

        lp.start()
        await asyncio.sleep(0.01)
        lp.cancel()
        await asyncio.sleep(0.1)
        assert after_called == [True]


# ─── Loop error handling ───


class TestLoopErrors:
    @pytest.mark.asyncio
    async def test_reconnect_on_valid_exception(self):
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise OSError("network error")

        lp = Loop(flaky, seconds=0, count=1, reconnect=True)
        lp.clear_exception_types()
        lp.add_exception_type(OSError)
        await lp.start()
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_no_reconnect_raises(self):
        async def fail():
            raise OSError("fatal")

        lp = Loop(fail, seconds=0, count=1, reconnect=False)
        with pytest.raises(OSError, match="fatal"):
            await lp.start()
        # _has_failed is reset in finally block after task completes
        assert lp.is_running() is False

    @pytest.mark.asyncio
    async def test_custom_error_handler(self):
        caught = []

        async def fail():
            raise ValueError("test error")

        lp = Loop(fail, seconds=0, count=1)

        @lp.error
        async def on_error(exc):
            caught.append(exc)

        with pytest.raises(ValueError):
            await lp.start()

        assert len(caught) == 1
        assert str(caught[0]) == "test error"

    @pytest.mark.asyncio
    async def test_failed_flag_set_on_unhandled(self):
        async def fail():
            raise ValueError("boom")

        lp = Loop(fail, seconds=0, count=1)

        with contextlib.suppress(ValueError):
            await lp.start()

        assert lp.failed() is False


# ─── Loop descriptor protocol ───


class TestDescriptorProtocol:
    def test_class_access_returns_loop(self):
        class MyCog:
            @loop(seconds=1)
            async def my_task(self):
                pass

        assert isinstance(MyCog.my_task, Loop)

    @pytest.mark.asyncio
    async def test_instance_access_returns_bound_clone(self):
        class MyCog:
            @loop(seconds=0, count=1)
            async def my_task(self):
                pass

        cog = MyCog()
        bound = cog.my_task
        assert isinstance(bound, Loop)
        assert bound._injected is cog
        assert bound is not MyCog.my_task

    @pytest.mark.asyncio
    async def test_bound_task_receives_self(self):
        received_self = []

        class MyCog:
            @loop(seconds=0, count=1)
            async def my_task(self):
                received_self.append(self)

        cog = MyCog()
        await cog.my_task.start()
        assert len(received_self) == 1
        assert received_self[0] is cog

    @pytest.mark.asyncio
    async def test_different_instances_independent(self):
        results = {"a": [], "b": []}

        class MyCog:
            def __init__(self, name):
                self.name = name

            @loop(seconds=0, count=2)
            async def my_task(self):
                results[self.name].append(1)

        a = MyCog("a")
        b = MyCog("b")
        await a.my_task.start()
        await b.my_task.start()
        assert len(results["a"]) == 2
        assert len(results["b"]) == 2


# ─── Loop __call__ tests ───


class TestLoopCall:
    @pytest.mark.asyncio
    async def test_call_directly(self):
        called = []

        async def body():
            called.append(True)

        lp = Loop(body, seconds=1)
        await lp()
        assert called == [True]

    @pytest.mark.asyncio
    async def test_call_with_injected(self):
        received = []

        async def body(self):
            received.append(self)

        lp = Loop(body, seconds=1)
        lp._injected = "mock_self"
        await lp()
        assert received == ["mock_self"]


# ─── loop() decorator tests ───


class TestLoopDecorator:
    def test_basic_usage(self):
        @loop(seconds=5)
        async def my_task():
            pass

        assert isinstance(my_task, Loop)
        assert my_task.seconds == 5.0

    def test_with_count(self):
        @loop(seconds=1, count=10)
        async def my_task():
            pass

        assert my_task.count == 10

    def test_rejects_sync(self):
        with pytest.raises(TypeError, match="must be a coroutine"):

            @loop(seconds=1)
            def not_async():
                pass

    def test_custom_cls(self):
        class MyLoop(Loop):
            pass

        @loop(MyLoop, seconds=5)
        async def my_task():
            pass

        assert isinstance(my_task, MyLoop)

    def test_rejects_non_callable_cls(self):
        with pytest.raises(TypeError, match="cls argument must be callable"):
            loop(42, seconds=1)


# ─── Loop stop/cancel edge cases ───


class TestLoopEdgeCases:
    def test_stop_when_not_running_noop(self):
        lp = Loop(dummy_coro, seconds=1)
        lp.stop()

    def test_cancel_when_not_running_noop(self):
        lp = Loop(dummy_coro, seconds=1)
        lp.cancel()

    @pytest.mark.asyncio
    async def test_restart(self):
        results = []

        async def body():
            results.append(1)

        lp = Loop(body, seconds=0, count=1)
        await lp.start()
        assert len(results) == 1

        await lp.start()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_next_iteration_none_after_done(self):
        async def body():
            pass

        lp = Loop(body, seconds=0, count=1)
        await lp.start()
        assert lp.next_iteration is None
