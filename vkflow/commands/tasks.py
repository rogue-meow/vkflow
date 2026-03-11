# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
import datetime
import inspect
import random

from collections.abc import Callable, Coroutine, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    TypeVar,
    cast,
    overload,
)

import aiohttp

from vkflow.commands.cron import next_cron_time, validate_cron
from vkflow.logger import logger
from vkflow.utils.sentinel import MISSING, MissingSentinel

if TYPE_CHECKING:
    from typing import Self

__all__ = ["Loop", "loop"]

T = TypeVar("T")

LF = TypeVar("LF", bound=Callable[..., Coroutine[Any, Any, Any]])
FT = TypeVar("FT", bound=Callable[..., Coroutine[Any, Any, Any]])
ET = TypeVar("ET", bound=Callable[[Any, BaseException], Coroutine[Any, Any, Any]])


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def compute_timedelta(dt: datetime.datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)

    now = utcnow()
    return max((dt - now).total_seconds(), 0)


class ExponentialBackoff:
    def __init__(self, base: int = 1, *, integral: bool = False, max_delay: float | None = None):
        self._base = base
        self._max_delay = max_delay

        self._exp = 0
        self._max = 10

        self._reset_time = base * 2**11
        self._last_invocation = utcnow()

        self._integral = integral
        self._attempts = 0

    @property
    def attempts(self) -> int:
        return self._attempts

    def reset(self) -> None:
        self._exp = 0
        self._attempts = 0
        self._last_invocation = utcnow()

    def delay(self) -> float:
        invocation = utcnow()
        interval = (invocation - self._last_invocation).total_seconds()

        self._last_invocation = invocation

        if interval > self._reset_time:
            self._exp = 0

        self._exp = min(self._exp + 1, self._max)
        self._attempts += 1

        if self._integral:
            result = self._base * 2**self._exp
        else:
            result = self._base * 2**self._exp + random.uniform(0, self._base)

        if self._max_delay is not None:
            return min(result, self._max_delay)

        return result


class SleepHandle:
    __slots__ = ("future", "handle", "loop")

    def __init__(self, dt: datetime.datetime, *, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.future: asyncio.Future[bool] = loop.create_future()

        relative_delta = compute_timedelta(dt)
        self.handle = loop.call_later(relative_delta, self.future.set_result, True)

    def recalculate(self, dt: datetime.datetime) -> None:
        self.handle.cancel()
        relative_delta = compute_timedelta(dt)
        self.handle = self.loop.call_later(relative_delta, self.future.set_result, True)

    def wait(self) -> asyncio.Future[bool]:
        return self.future

    def done(self) -> bool:
        return self.future.done()

    def cancel(self) -> None:
        self.handle.cancel()
        self.future.cancel()


class Loop(Generic[LF]):
    def __init__(
        self,
        coro: LF,
        *,
        seconds: float = 0,
        minutes: float = 0,
        hours: float = 0,
        time: datetime.time | Sequence[datetime.time] = MISSING,
        cron: str | MissingSentinel = MISSING,
        count: int | None = None,
        reconnect: bool = True,
    ) -> None:
        if not inspect.iscoroutinefunction(coro):
            raise TypeError(f"Expected coroutine function, not {type(coro).__name__!r}.")

        if count is not None and count <= 0:
            raise ValueError("count must be greater than 0 or None.")

        self.coro: LF = coro
        self.reconnect: bool = reconnect
        self.count: int | None = count

        self._current_loop = 0

        self._handle: SleepHandle | None = None
        self._task: asyncio.Task[None] | None = None

        self._injected: Any = None

        self._valid_exception = (
            OSError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        )

        self._before_loop = None
        self._after_loop = None

        self._error_handler = None
        self._is_being_cancelled = False
        self._has_failed = False

        self._stop_next_iteration = False
        self._last_iteration_failed = False

        self._last_iteration: datetime.datetime | None = None
        self._next_iteration: datetime.datetime | None = None

        self._time_index: int = 0

        self._seconds: float | MissingSentinel = MISSING
        self._minutes: float | MissingSentinel = MISSING
        self._hours: float | MissingSentinel = MISSING
        self._time: list[datetime.time] | MissingSentinel = MISSING
        self._interval_seconds: float | MissingSentinel = MISSING
        self._cron: str | MissingSentinel = MISSING

        self.change_interval(seconds=seconds, minutes=minutes, hours=hours, time=time, cron=cron)

    def __repr__(self) -> str:
        attrs = [
            f"coro={self.coro.__qualname__}",
        ]

        if self._cron is not MISSING:
            attrs.append(f"cron={self._cron!r}")
        elif self._time is not MISSING:
            attrs.append(f"time={self._time!r}")
        else:
            if self._seconds:
                attrs.append(f"seconds={self._seconds}")
            if self._minutes:
                attrs.append(f"minutes={self._minutes}")
            if self._hours:
                attrs.append(f"hours={self._hours}")

        if self.count is not None:
            attrs.append(f"count={self.count}")

        attrs.append(f"running={self.is_running()}")

        if self.is_running():
            attrs.append(f"current_loop={self._current_loop}")
        return f"<Loop {' '.join(attrs)}>"

    async def _call_loop_function(self, name: str, *args: Any, **kwargs: Any) -> None:
        coro = getattr(self, "_" + name)

        if coro is None:
            return
        if self._injected is not None:
            await coro(self._injected, *args, **kwargs)
        else:
            await coro(*args, **kwargs)

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    def _try_sleep_until(self, dt: datetime.datetime) -> asyncio.Future[bool]:
        self._handle = SleepHandle(dt=dt, loop=self._get_loop())
        return self._handle.wait()

    async def _loop(self, *args: Any, **kwargs: Any) -> None:
        backoff = ExponentialBackoff()

        try:
            await self._call_loop_function("before_loop")
            self._last_iteration_failed = False

            if self._cron is not MISSING:
                self._next_iteration = next_cron_time(self._cron)
            elif self._time is not MISSING:
                self._prepare_time_index()
                self._next_iteration = self._get_next_sleep_time()
            else:
                self._next_iteration = utcnow()

            await self._try_sleep_until(self._next_iteration)

            while True:
                if not self._last_iteration_failed:
                    self._last_iteration = self._next_iteration
                    if self._cron is not MISSING:
                        self._next_iteration = next_cron_time(self._cron, after=self._last_iteration)
                    else:
                        self._next_iteration = self._get_next_sleep_time()

                try:
                    await self.coro(*args, **kwargs)
                    self._last_iteration_failed = False

                except self._valid_exception:
                    self._last_iteration_failed = True

                    if not self.reconnect:
                        raise
                    await asyncio.sleep(backoff.delay())

                else:
                    await self._try_sleep_until(self._next_iteration)

                    if self._stop_next_iteration:
                        return

                    now = utcnow()

                    if now > self._next_iteration:
                        if self._cron is not MISSING:
                            self._next_iteration = next_cron_time(self._cron, after=now)
                        else:
                            self._next_iteration = now.replace(microsecond=0)

                            if self._time is not MISSING:
                                self._prepare_time_index(now)

                    self._current_loop += 1

                    if self._current_loop == self.count:
                        break

        except asyncio.CancelledError:
            self._is_being_cancelled = True
            raise

        except Exception as exc:
            self._has_failed = True
            await self._call_loop_function("error_handler", exc)
            raise

        finally:
            await self._call_loop_function("after_loop")

            if self._handle is not None:
                self._handle.cancel()

            self._is_being_cancelled = False
            self._current_loop = 0
            self._stop_next_iteration = False
            self._has_failed = False

    def __get__(self, obj: T, objtype: type[T]) -> Self:
        if obj is None:
            return self  # type: ignore[return-value]

        clone = self.clone()
        clone._injected = obj

        setattr(obj, self.coro.__name__, clone)
        return clone  # type: ignore[return-value]

    def clone(self) -> Self:
        instance = type(self)(
            self.coro,
            seconds=self._seconds if self._seconds is not MISSING else 0,
            hours=self._hours if self._hours is not MISSING else 0,
            minutes=self._minutes if self._minutes is not MISSING else 0,
            time=self._time if self._time is not MISSING else MISSING,
            cron=self._cron if self._cron is not MISSING else MISSING,
            count=self.count,
            reconnect=self.reconnect,
        )

        instance._before_loop = self._before_loop
        instance._after_loop = self._after_loop
        instance._error_handler = self._error_handler
        instance._injected = self._injected
        instance._valid_exception = self._valid_exception

        return instance  # type: ignore[return-value]

    @property
    def seconds(self) -> float | None:
        if self._seconds is not MISSING:
            return self._seconds
        return None

    @property
    def minutes(self) -> float | None:
        if self._minutes is not MISSING:
            return self._minutes
        return None

    @property
    def hours(self) -> float | None:
        if self._hours is not MISSING:
            return self._hours
        return None

    @property
    def time(self) -> list[datetime.time] | None:
        if self._time is not MISSING:
            return self._time.copy()
        return None

    @property
    def cron(self) -> str | None:
        """Cron-выражение, если задано."""
        if self._cron is not MISSING:
            return self._cron
        return None

    @property
    def current_loop(self) -> int:
        return self._current_loop

    @property
    def next_iteration(self) -> datetime.datetime | None:
        if self._task is None or self._task.done() or self._stop_next_iteration:
            return None
        return self._next_iteration

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if self._injected is not None:
            args = (self._injected, *args)
        return await self.coro(*args, **kwargs)

    def start(self, *args: Any, **kwargs: Any) -> asyncio.Task[None]:
        if self._task is not None and not self._task.done():
            raise RuntimeError("Task is already launched and is not completed.")

        if self._injected is not None:
            args = (self._injected, *args)

        loop = self._get_loop()
        self._task = loop.create_task(self._loop(*args, **kwargs))
        return self._task

    def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._stop_next_iteration = True

    def _can_be_cancelled(self) -> bool:
        return bool(not self._is_being_cancelled and self._task and not self._task.done())

    def cancel(self) -> None:
        if self._can_be_cancelled():
            self._task.cancel()

    def restart(self, *args: Any, **kwargs: Any) -> None:
        def restart_when_over(fut: Any, *, args: Any = args, kwargs: Any = kwargs) -> None:
            self._task.remove_done_callback(restart_when_over)
            self.start(*args, **kwargs)

        if self._can_be_cancelled():
            self._task.add_done_callback(restart_when_over)
            self._task.cancel()

    def add_exception_type(self, *exceptions: type[BaseException]) -> None:
        for exc in exceptions:
            if not inspect.isclass(exc):
                raise TypeError(f"{exc!r} must be a class.")
            if not issubclass(exc, BaseException):
                raise TypeError(f"{exc!r} must inherit from BaseException.")
        self._valid_exception = (*self._valid_exception, *exceptions)

    def clear_exception_types(self) -> None:
        self._valid_exception = ()

    def remove_exception_type(self, *exceptions: type[BaseException]) -> bool:
        old_length = len(self._valid_exception)
        self._valid_exception = tuple(x for x in self._valid_exception if x not in exceptions)
        return len(self._valid_exception) == old_length - len(exceptions)

    def get_task(self) -> asyncio.Task[None] | None:
        return self._task

    def is_being_cancelled(self) -> bool:
        return self._is_being_cancelled

    def failed(self) -> bool:
        return self._has_failed

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def wait(self) -> None:
        if self._task is not None and not self._task.done():
            await self._task

    async def _default_error_handler(self, exception: Exception) -> None:
        logger.opt(exception=exception).error(
            f"Unhandled exception in internal background task {self.coro.__name__!r}."
        )

    async def _error_handler(self, *args: Any) -> None:
        exception: Exception = args[-1]
        await self._default_error_handler(exception)

    def before_loop(self, coro: FT) -> FT:
        if not inspect.iscoroutinefunction(coro):
            raise TypeError(f"Expected coroutine function, received {coro.__class__.__name__!r}.")

        self._before_loop = coro
        return coro

    def after_loop(self, coro: FT) -> FT:
        if not inspect.iscoroutinefunction(coro):
            raise TypeError(f"Expected coroutine function, received {coro.__class__.__name__!r}.")

        self._after_loop = coro
        return coro

    def error(self, coro: ET) -> ET:
        if not inspect.iscoroutinefunction(coro):
            raise TypeError(f"Expected coroutine function, received {coro.__class__.__name__!r}.")

        self._error_handler = coro  # type: ignore[assignment]
        return coro

    def _get_next_sleep_time(self) -> datetime.datetime:
        if self._interval_seconds is not MISSING:
            return self._last_iteration + datetime.timedelta(seconds=self._interval_seconds)

        if self._time_index >= len(self._time):
            self._time_index = 0

            if self._current_loop == 0:
                return datetime.datetime.combine(
                    utcnow() + datetime.timedelta(days=1),
                    self._time[0],
                )

        next_time = self._time[self._time_index]

        if self._current_loop == 0:
            self._time_index += 1

            if next_time > utcnow().replace(microsecond=0).timetz():
                return datetime.datetime.combine(utcnow(), next_time)

            return datetime.datetime.combine(
                utcnow() + datetime.timedelta(days=1),
                next_time,
            )

        next_date = self._last_iteration

        if next_time < next_date.timetz():
            next_date += datetime.timedelta(days=1)

        self._time_index += 1
        return datetime.datetime.combine(next_date, next_time)

    def _prepare_time_index(self, now: datetime.datetime | None = None) -> None:
        time_now = (now if now is not None else utcnow()).replace(microsecond=0).timetz()

        for idx, t in enumerate(self._time):
            if t >= time_now:
                self._time_index = idx
                break
        else:
            self._time_index = 0

    def _get_time_parameter(
        self,
        time: datetime.time | Sequence[datetime.time],
        *,
        dt: type[datetime.time] = datetime.time,
        utc: datetime.timezone = datetime.UTC,
    ) -> list[datetime.time]:
        if isinstance(time, dt):
            inner = time if time.tzinfo is not None else time.replace(tzinfo=utc)
            return [inner]

        if not isinstance(time, Sequence):
            raise TypeError(
                f"Expected datetime.time or a sequence of datetime.time "
                f"for ``time``, received {type(time)!r} instead."
            )

        if not time:
            raise ValueError("time parameter must not be an empty sequence.")

        ret: list[datetime.time] = []

        for index, t in enumerate(time):
            if not isinstance(t, dt):
                raise TypeError(
                    f"Expected a sequence of {dt!r} for ``time``, "
                    f"received {type(t).__name__!r} at index {index} instead."
                )
            ret.append(t if t.tzinfo is not None else t.replace(tzinfo=utc))

        return sorted(set(ret))

    def change_interval(
        self,
        *,
        seconds: float = 0,
        minutes: float = 0,
        hours: float = 0,
        time: datetime.time | Sequence[datetime.time] = MISSING,
        cron: str | MissingSentinel = MISSING,
    ) -> None:
        if cron is not MISSING:
            if any((seconds, minutes, hours)) or time is not MISSING:
                raise TypeError("Cannot mix cron with other scheduling parameters.")

            if not validate_cron(cron):
                raise ValueError(f"Invalid cron expression: {cron!r}")

            self._cron = cron
            self._interval_seconds = MISSING
            self._seconds = MISSING
            self._minutes = MISSING
            self._hours = MISSING
            self._time = MISSING

        elif time is not MISSING:
            if any((seconds, minutes, hours)):
                raise TypeError("Cannot mix explicit time with relative time.")

            self._time = self._get_time_parameter(time)
            self._cron = MISSING
            self._interval_seconds = MISSING
            self._seconds = MISSING
            self._minutes = MISSING
            self._hours = MISSING

        else:
            seconds = seconds or 0
            minutes = minutes or 0
            hours = hours or 0
            total = seconds + (minutes * 60.0) + (hours * 3600.0)

            if total < 0:
                raise ValueError("Total number of seconds cannot be less than zero.")

            self._interval_seconds = total
            self._seconds = float(seconds)
            self._hours = float(hours)
            self._minutes = float(minutes)
            self._time = MISSING
            self._cron = MISSING

        if self.is_running() and self._last_iteration is not None:
            if self._cron is not MISSING:
                self._next_iteration = next_cron_time(self._cron, after=self._last_iteration)
            elif self._time is not MISSING:
                self._prepare_time_index(now=self._last_iteration)
                self._next_iteration = self._get_next_sleep_time()
            else:
                self._next_iteration = self._get_next_sleep_time()

            if self._handle is not None and not self._handle.done():
                self._handle.recalculate(self._next_iteration)


L_co = TypeVar("L_co", bound=Loop[Any], covariant=True)


@overload
def loop(
    *,
    seconds: float = ...,
    minutes: float = ...,
    hours: float = ...,
    time: datetime.time | Sequence[datetime.time] = ...,
    cron: str = ...,
    count: int | None = None,
    reconnect: bool = True,
) -> Callable[[LF], Loop[LF]]: ...


@overload
def loop(cls: Callable[..., L_co], *_: Any, **kwargs: Any) -> Callable[[LF], L_co]: ...


def loop(
    cls: Callable[..., L_co] = Loop[Any],
    **kwargs: Any,
) -> Callable[[LF], L_co]:
    """Декоратор для запуска фоновой задачи по расписанию.

    Поддерживает интервалы, точное время и cron-выражения.

    Args:
        seconds: Количество секунд между итерациями.
        minutes: Количество минут между итерациями.
        hours: Количество часов между итерациями.
        time: Точное время запуска (UTC).
        cron: Cron-выражение (5 полей: minute hour day month weekday).
        count: Количество итераций, None — бесконечно.
        reconnect: Автоматический перезапуск при сетевых ошибках.

    Example::

        @tasks.loop(minutes=5)
        async def my_task(self):
            print("Каждые 5 минут")

        @tasks.loop(cron="0 9 * * mon-fri")
        async def weekday_report(self):
            print("Каждый будний день в 9:00")
    """
    if not callable(cls):
        raise TypeError("cls argument must be callable.")

    def decorator(func: LF) -> L_co:
        if not inspect.iscoroutinefunction(func):
            raise TypeError("The decorated function must be a coroutine function.")
        return cast("type[L_co]", cls)(func, **kwargs)

    return decorator
