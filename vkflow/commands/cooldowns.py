"""
Система cooldown для vkflow.commands
"""

from __future__ import annotations

import asyncio
import enum
import time
import typing
import inspect
from datetime import timedelta

from vkflow.exceptions import CommandError

if typing.TYPE_CHECKING:
    from .context import Context


__all__ = (
    "BucketType",
    "Cooldown",
    "CooldownMapping",
    "MaxConcurrency",
    "MaxConcurrencyMapping",
    "MaxConcurrencyReachedError",
    "OnCooldownError",
    "dynamic_cooldown",
)


class BucketType(enum.Enum):
    """
    Перечисление типов бакетов для cooldown.

    Каждый тип определяет, как отслеживаются cooldown:
    - DEFAULT: Глобальный cooldown для всех пользователей и чатов
    - USER: Cooldown на пользователя (один пользователь во всех чатах)
    - CHAT: Cooldown на чат (один peer_id)
    - MEMBER: Cooldown на участника (комбинация пользователя и чата)

    Пример:
        @commands.cooldown(rate=3, per=60, type=commands.BucketType.USER)
        async def spam_cmd(ctx: commands.Context):
            await ctx.send("Команда выполнена!")
    """

    DEFAULT = 0
    USER = 1
    CHAT = 2
    MEMBER = 3


class OnCooldownError(CommandError):
    """
    Исключение, возникающее когда команда находится на cooldown.

    Атрибуты:
        cooldown: Экземпляр Cooldown
        retry_after: Секунды до истечения cooldown
        type: Тип BucketType

    Пример:
        try:
            pass
        except OnCooldownError as e:
            await ctx.send(f"Попробуйте снова через {e.retry_after:.1f} секунд")
    """

    def __init__(self, cooldown: Cooldown, retry_after: float, type: BucketType):
        self.cooldown = cooldown
        self.retry_after = retry_after
        self.type = type
        super().__init__(f"Команда на cooldown. Повторите через {retry_after:.2f}с")


OnCooldown = OnCooldownError


class Cooldown:
    """
    Представляет cooldown с ограничением частоты использования.

    Атрибуты:
        rate: Количество разрешённых использований
        per: Временной период (в секундах)

    Пример:
        # Разрешить 3 использования за 60 секунд
        cooldown = Cooldown(rate=3, per=60)

        # Разрешить 1 использование за 30 секунд
        cooldown = Cooldown(rate=1, per=30)
    """

    __slots__ = ("_last", "_tokens", "_window", "per", "rate")

    def __init__(self, rate: int, per: float | int | timedelta):
        """
        Инициализация Cooldown.

        Args:
            rate: Количество раз, сколько команда может быть использована
            per: Временной период в секундах (int/float) или timedelta
        """
        self.rate = int(rate)

        if isinstance(per, timedelta):
            self.per = per.total_seconds()
        else:
            self.per = float(per)

        self._window = 0.0
        self._tokens = self.rate
        self._last = 0.0

    def get_tokens(self, current: float | None = None) -> int:
        """
        Получить количество доступных токенов.

        Args:
            current: Текущая метка времени (по умолчанию time.time())

        Returns:
            Количество доступных токенов
        """
        if current is None:
            current = time.time()

        if current > self._window + self.per:
            self._tokens = self.rate
            self._window = current

        return self._tokens

    def get_retry_after(self, current: float | None = None) -> float:
        """
        Получить время до истечения cooldown.

        Args:
            current: Текущая метка времени (по умолчанию time.time())

        Returns:
            Секунды до истечения cooldown (0 если cooldown не активен)
        """
        if current is None:
            current = time.time()

        tokens = self.get_tokens(current)

        if tokens == 0:
            return self.per - (current - self._window)

        return 0.0

    def update_rate_limit(self, current: float | None = None) -> float | None:
        """
        Обновить ограничение частоты и вернуть retry_after, если cooldown активен.

        Args:
            current: Текущая метка времени (по умолчанию time.time())

        Returns:
            None если cooldown не активен, иначе секунды до истечения cooldown
        """
        if current is None:
            current = time.time()

        self._last = current

        self.get_tokens(current)

        if self._tokens > 0:
            self._tokens -= 1
            if self._tokens == 0:
                self._window = current
            return None

        return self.per - (current - self._window)

    def reset(self):
        """Сбросить состояние cooldown."""
        self._tokens = self.rate
        self._window = 0.0
        self._last = 0.0

    def copy(self) -> Cooldown:
        """Создать копию этого cooldown."""
        return Cooldown(self.rate, self.per)

    def __repr__(self):
        return f"<Cooldown rate={self.rate} per={self.per}>"


class CooldownMapping:
    """
    Управляет cooldown для разных типов бакетов.

    Этот класс отслеживает состояния cooldown для разных пользователей/чатов/участников
    на основе типа бакета.

    Пример:
        mapping = CooldownMapping(
            cooldown=Cooldown(rate=3, per=60),
            type=BucketType.USER
        )

        bucket = mapping.get_bucket(ctx)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            raise OnCooldownError(bucket, retry_after, mapping.type)
    """

    def __init__(self, cooldown: Cooldown, type: BucketType):
        """
        Инициализация CooldownMapping.

        Args:
            cooldown: Базовый экземпляр Cooldown
            type: Используемый BucketType
        """
        self._cooldown = cooldown
        self._type = type
        self._cache: dict[typing.Any, Cooldown] = {}
        self._cleanup_threshold = 100
        self._lock = asyncio.Lock()

    @property
    def type(self) -> BucketType:
        """Тип бакета."""
        return self._type

    def _bucket_key(self, ctx: Context) -> typing.Any:
        """
        Сгенерировать ключ бакета на основе типа бакета.

        Args:
            ctx: Контекст команды

        Returns:
            Ключ бакета
        """
        if self._type == BucketType.DEFAULT:
            return 0
        if self._type == BucketType.USER:
            return ctx.author
        if self._type == BucketType.CHAT:
            return ctx.peer_id
        if self._type == BucketType.MEMBER:
            return (ctx.author, ctx.peer_id)
        return 0

    def get_bucket(self, ctx: Context, current: float | None = None) -> Cooldown:
        """
        Получить бакет cooldown для данного контекста.

        Args:
            ctx: Контекст команды
            current: Текущая метка времени (по умолчанию time.time())

        Returns:
            Экземпляр Cooldown для этого бакета
        """
        key = self._bucket_key(ctx)

        if key not in self._cache:
            bucket = self._cooldown.copy()
            if current:
                bucket._last = current
            self._cache[key] = bucket

        return self._cache[key]

    def _cleanup_expired(self) -> None:
        """Удалить истёкшие записи из кэша (TTL = cooldown.per * 2)."""
        if len(self._cache) < self._cleanup_threshold:
            return
        now = time.time()
        ttl = self._cooldown.per * 2
        expired = [
            key
            for key, bucket in self._cache.items()
            if now - bucket._last > ttl and bucket._tokens == bucket.rate
        ]
        for key in expired:
            del self._cache[key]

    async def acquire(self, ctx: Context) -> float | None:
        """
        Занять использование кулдауна.

        Args:
            ctx: Контекст команды

        Returns:
            None если успешно, иначе секунды до истечения кулдауна
        """
        async with self._lock:
            self._cleanup_expired()
            bucket = self.get_bucket(ctx)
            return bucket.update_rate_limit()

    def reset(
        self,
        ctx: Context | None = None,
        *,
        user: int | None = None,
        chat: int | None = None,
    ):
        """
        Сбросить cooldown.

        Args:
            ctx: Контекст для сброса. Если None и нет других аргументов, сбрасываются все бакеты
            user: ID пользователя для сброса cooldown (только для типов USER/MEMBER)
            chat: ID чата/peer для сброса cooldown (только для типов CHAT/MEMBER)

        Примеры:
            # Сбросить все cooldown
            mapping.reset()

            # Сбросить для конкретного пользователя
            mapping.reset(user=123456)

            # Сбросить для конкретного чата
            mapping.reset(chat=2000000001)

            # Сбросить для конкретного участника (пользователь в чате)
            mapping.reset(user=123456, chat=2000000001)

            # Сбросить из контекста
            mapping.reset(ctx)
        """
        if ctx is None and user is None and chat is None:
            self._cache.clear()
            return

        if ctx is not None:
            key = self._bucket_key(ctx)
        elif self._type == BucketType.DEFAULT:
            key = 0
        elif self._type == BucketType.USER:
            if user is None:
                return
            key = user
        elif self._type == BucketType.CHAT:
            if chat is None:
                return
            key = chat
        elif self._type == BucketType.MEMBER:
            if user is None or chat is None:
                return
            key = (user, chat)
        else:
            key = 0

        if key in self._cache:
            self._cache[key].reset()

    def __repr__(self):
        return f"<CooldownMapping cooldown={self._cooldown} type={self._type}>"


def dynamic_cooldown(
    func: typing.Callable[[Context], Cooldown | None],
    *,
    type: BucketType | None = None,
    delete_after: int | float | None = None,
):
    """
    Декоратор для создания динамических кулдаунов.

    Функция получает контекст и должна вернуть экземпляр Cooldown
    или None для пропуска кулдауна.

    Args:
        func: Функция (sync или async), принимающая Context и возвращающая Cooldown или None
        type: BucketType (USER, CHAT, MEMBER, DEFAULT). По умолчанию USER
        delete_after: Удалить сообщение об ошибке через указанное количество секунд.

    Returns:
        Check декоратор

    Пример:
        def my_cooldown(ctx: commands.Context):
            if ctx.author in PREMIUM_USERS:
                return commands.Cooldown(rate=10, per=60)
            return commands.Cooldown(rate=3, per=60)

        @commands.command()
        @commands.dynamic_cooldown(my_cooldown, type=BucketType.USER)
        async def test(ctx: commands.Context):
            await ctx.send("Test!")
    """
    bucket_type = type if type is not None else BucketType.USER
    _dynamic_cache: dict[int, CooldownMapping] = {}

    async def predicate(ctx: Context) -> bool:
        if inspect.iscoroutinefunction(func):
            cooldown_obj = await func(ctx)
        else:
            cooldown_obj = func(ctx)

        if cooldown_obj is None:
            return True

        ctx_key = id(ctx.command) if hasattr(ctx, "command") else 0

        if ctx_key not in _dynamic_cache:
            _dynamic_cache[ctx_key] = CooldownMapping(
                cooldown=cooldown_obj,
                type=bucket_type,
            )
        else:
            mapping = _dynamic_cache[ctx_key]
            if mapping._cooldown.rate != cooldown_obj.rate or mapping._cooldown.per != cooldown_obj.per:
                mapping._cooldown = cooldown_obj

        mapping = _dynamic_cache[ctx_key]
        retry_after = await mapping.acquire(ctx)

        if retry_after is not None:
            raise OnCooldownError(mapping._cooldown, retry_after, mapping.type)

        return True

    from .checks import check

    return check(predicate, error_message=None, delete_after=delete_after)


class MaxConcurrencyReachedError(CommandError):
    """
    Исключение, возникающее при достижении лимита одновременного выполнения.

    Атрибуты:
        number: Максимально допустимое количество одновременных выполнений
        per: Тип BucketType
        current: Текущее количество активных выполнений

    Пример:
        try:
            pass
        except MaxConcurrencyReachedError as e:
            await ctx.send(f"Максимум {e.number} одновременных использований. Сейчас: {e.current}")
    """

    def __init__(self, number: int, per: BucketType, current: int = 0):
        self.number = number
        self.per = per
        self.current = current
        super().__init__(f"Достигнут лимит одновременного выполнения: {current}/{number} для {per.name}")


MaxConcurrencyReached = MaxConcurrencyReachedError


class MaxConcurrency:
    """
    Представляет лимит одновременного выполнения.

    Ограничивает количество одновременных выполнений команды на основе типа бакета.

    Атрибуты:
        number: Максимальное количество одновременных выполнений
        per: BucketType, к которому применяется лимит

    Пример:
        max_conc = MaxConcurrency(number=2, per=BucketType.CHAT)
    """

    __slots__ = ("number", "per")

    def __init__(self, number: int, per: BucketType):
        """
        Инициализация MaxConcurrency.

        Args:
            number: Максимальное количество одновременных выполнений
            per: BucketType, к которому применяется лимит
        """
        self.number = int(number)
        self.per = per

    def __repr__(self):
        return f"<MaxConcurrency number={self.number} per={self.per}>"


class MaxConcurrencyMapping:
    """
    Управляет лимитами одновременного выполнения для разных типов бакетов.

    Отслеживает активные выполнения для разных пользователей/чатов/участников
    на основе типа бакета, используя asyncio.Semaphore.

    Семафор -единственный источник истины для отслеживания занятых слотов.
    Это гарантирует отсутствие утечек счётчика при отмене корутин.

    Пример:
        mapping = MaxConcurrencyMapping(
            max_concurrency=MaxConcurrency(number=2, per=BucketType.CHAT)
        )

        async with mapping(ctx):
            await do_work()
    """

    def __init__(self, max_concurrency: MaxConcurrency):
        self._max_concurrency = max_concurrency
        self._semaphores: dict[typing.Any, asyncio.Semaphore] = {}

    @property
    def number(self) -> int:
        """Максимальное количество одновременных выполнений."""
        return self._max_concurrency.number

    @property
    def per(self) -> BucketType:
        """Тип бакета."""
        return self._max_concurrency.per

    def _bucket_key(self, ctx: Context) -> typing.Any:
        """Сгенерировать ключ бакета на основе типа."""
        if self.per == BucketType.DEFAULT:
            return 0
        if self.per == BucketType.USER:
            return ctx.author
        if self.per == BucketType.CHAT:
            return ctx.peer_id
        if self.per == BucketType.MEMBER:
            return (ctx.author, ctx.peer_id)
        return 0

    def _get_semaphore(self, key: typing.Any) -> asyncio.Semaphore:
        """Получить или создать семафор для ключа."""
        if key not in self._semaphores:
            self._semaphores[key] = asyncio.Semaphore(self.number)
        return self._semaphores[key]

    def _get_active_count(self, key: typing.Any) -> int:
        """Получить количество активных выполнений из семафора."""
        if key not in self._semaphores:
            return 0
        semaphore = self._semaphores[key]
        return self.number - semaphore._value

    async def acquire(self, ctx: Context) -> bool:
        """
        Попытка занять слот для выполнения.

        Использует только семафор для отслеживания -нет отдельного счётчика,
        поэтому отмена корутины не приводит к утечке.

        Raises:
            MaxConcurrencyReachedError: Если лимит достигнут
        """
        key = self._bucket_key(ctx)
        semaphore = self._get_semaphore(key)

        if semaphore.locked():
            current = self._get_active_count(key)
            raise MaxConcurrencyReachedError(self.number, self.per, current)

        acquired = False
        try:
            acquired = semaphore._value > 0
            if not acquired:
                current = self._get_active_count(key)
                raise MaxConcurrencyReachedError(self.number, self.per, current)
            await semaphore.acquire()
            return True
        except MaxConcurrencyReachedError:
            raise

    def release(self, ctx: Context):
        """Освободить слот после выполнения."""
        key = self._bucket_key(ctx)
        if key in self._semaphores:
            self._semaphores[key].release()

    class _AcquireContext:
        """Контекстный менеджер для захвата/освобождения семафора."""

        def __init__(self, mapping: MaxConcurrencyMapping, ctx: Context):
            self.mapping = mapping
            self.ctx = ctx
            self._acquired = False

        async def __aenter__(self):
            await self.mapping.acquire(self.ctx)
            self._acquired = True
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            if self._acquired:
                self.mapping.release(self.ctx)
            return False

    def __call__(self, ctx: Context):
        """Создать контекстный менеджер для этого маппинга."""
        return self._AcquireContext(self, ctx)

    def __repr__(self):
        return f"<MaxConcurrencyMapping max_concurrency={self._max_concurrency}>"
