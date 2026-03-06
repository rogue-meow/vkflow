"""
Система middleware для vkflow.commands

Предоставляет хуки для обработки событий и команд до/после выполнения.
"""

from __future__ import annotations

import typing
import traceback
from dataclasses import dataclass
from enum import Enum, auto

if typing.TYPE_CHECKING:
    from .context import Context

    Handler = typing.Callable[..., typing.Awaitable]


__all__ = (
    "Middleware",
    "MiddlewareManager",
    "MiddlewarePriority",
    "after_command",
    "before_command",
    "middleware",
)


class MiddlewarePriority(Enum):
    """Уровни приоритета для порядка выполнения middleware."""

    HIGHEST = auto()
    HIGH = auto()
    NORMAL = auto()
    LOW = auto()
    LOWEST = auto()


@dataclass
class Middleware:
    """
    Middleware, перехватывающий и обрабатывающий события/команды.

    Middleware может использоваться для:
    - Логирования команд/событий
    - Аутентификации/авторизации
    - Модификации контекста перед выполнением команды
    - Глобальной обработки ошибок
    - Сбора аналитики

    Пример:
        @app.middleware()
        async def logging_middleware(ctx: Context, call_next):
            print(f"Команда {ctx.command.name} запущена")
            result = await call_next()
            print(f"Команда {ctx.command.name} завершена")
            return result
    """

    callback: Handler
    priority: MiddlewarePriority = MiddlewarePriority.NORMAL
    event_types: list[str] | None = None

    async def __call__(self, *args, **kwargs):
        return await self.callback(*args, **kwargs)


class MiddlewareManager:
    """
    Управляет регистрацией и выполнением middleware.
    """

    def __init__(self):
        self._middlewares: list[Middleware] = []
        self._before_command_hooks: list[Handler] = []
        self._after_command_hooks: list[Handler] = []
        self._event_middlewares: dict[str, list[Middleware]] = {}

    def add_middleware(
        self,
        middleware: Middleware,
    ) -> None:
        """Добавить middleware в менеджер."""
        self._middlewares.append(middleware)
        self._middlewares.sort(key=lambda m: m.priority.value)

        if middleware.event_types:
            for event_type in middleware.event_types:
                if event_type not in self._event_middlewares:
                    self._event_middlewares[event_type] = []
                self._event_middlewares[event_type].append(middleware)
                self._event_middlewares[event_type].sort(key=lambda m: m.priority.value)

    def remove_middleware(self, middleware: Middleware) -> bool:
        """Удалить middleware из менеджера."""
        if middleware in self._middlewares:
            self._middlewares.remove(middleware)

            if middleware.event_types:
                for event_type in middleware.event_types:
                    if (
                        event_type in self._event_middlewares
                        and middleware in self._event_middlewares[event_type]
                    ):
                        self._event_middlewares[event_type].remove(middleware)
            return True
        return False

    def add_before_command_hook(self, hook: Handler) -> None:
        """Добавить хук, вызываемый перед выполнением команды."""
        self._before_command_hooks.append(hook)

    def add_after_command_hook(self, hook: Handler) -> None:
        """Добавить хук, вызываемый после выполнения команды."""
        self._after_command_hooks.append(hook)

    def get_middlewares_for_event(self, event_type: str) -> list[Middleware]:
        """Получить все middleware, применимые к типу события."""
        global_middlewares = [m for m in self._middlewares if m.event_types is None]
        event_specific = self._event_middlewares.get(event_type, [])

        all_middlewares = global_middlewares + event_specific
        all_middlewares.sort(key=lambda m: m.priority.value)
        return all_middlewares

    async def run_before_command_hooks(self, ctx: Context, **kwargs) -> bool:
        """
        Выполнить все before_command хуки.

        Возвращает:
            True если все хуки прошли, False если команда отменена
        """
        from vkflow.utils.inject import inject_and_call

        available = {"ctx": ctx, **kwargs}

        for hook in self._before_command_hooks:
            try:
                result = await inject_and_call(hook, available)

                if result is False:
                    return False

            except Exception:
                traceback.print_exc()

        return True

    async def run_after_command_hooks(
        self, ctx: Context, result: typing.Any = None, error: Exception | None = None, **kwargs
    ) -> None:
        """Выполнить все after_command хуки."""
        from vkflow.utils.inject import inject_and_call

        available = {"ctx": ctx, "result": result, "error": error, **kwargs}

        for hook in self._after_command_hooks:
            try:
                await inject_and_call(hook, available)
            except Exception:
                traceback.print_exc()


def middleware(
    *,
    priority: MiddlewarePriority = MiddlewarePriority.NORMAL,
    event_types: list[str] | None = None,
) -> typing.Callable[[Handler], Middleware]:
    """
    Декоратор для создания middleware.

    Аргументы:
        priority: Приоритет выполнения
        event_types: Список типов событий, к которым применяется middleware (None -ко всем)

    Пример:
        @middleware(priority=MiddlewarePriority.HIGH)
        async def auth_middleware(ctx, call_next):
            if not is_authenticated(ctx.author):
                await ctx.send("Нет авторизации!")
                return
            return await call_next()
    """

    def decorator(func: Handler) -> Middleware:
        return Middleware(
            callback=func,
            priority=priority,
            event_types=event_types,
        )

    return decorator


def before_command(func: Handler | None = None) -> Handler | typing.Callable[[Handler], Handler]:
    """
    Декоратор для регистрации хука before_command.

    Хук вызывается перед каждым выполнением команды.
    Если хук вернёт False, команда будет отменена.

    Аргументы:
        func: Функция хука

    Пример:
        @app.before_command()
        async def log_command(ctx: Context):
            print(f"Команда {ctx.command.name} от {ctx.author}")

        @app.before_command()
        async def check_banned(ctx: Context):
            if ctx.author in BANNED_USERS:
                await ctx.send("Вы заблокированы!")
                return False
    """

    def decorator(f: Handler) -> Handler:
        f.__vkflow_before_command__ = True
        return f

    if func is not None:
        return decorator(func)
    return decorator


def after_command(func: Handler | None = None) -> Handler | typing.Callable[[Handler], Handler]:
    """
    Декоратор для регистрации хука after_command.

    Хук вызывается после каждого выполнения команды (успех или ошибка).

    Аргументы:
        func: Функция хука

    Пример:
        @app.after_command()
        async def track_usage(ctx: Context, result, error):
            if error:
                print(f"Команда {ctx.command.name} упала: {error}")
            else:
                print(f"Команда {ctx.command.name} выполнена")
    """

    def decorator(f: Handler) -> Handler:
        f.__vkflow_after_command__ = True
        return f

    if func is not None:
        return decorator(func)
    return decorator
