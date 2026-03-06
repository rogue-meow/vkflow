from __future__ import annotations

import typing
import inspect
import dataclasses

from vkflow.base.filter import BaseFilter
from vkflow.exceptions import CommandError, StopCurrentHandlingError
from vkflow.utils.cache import APICache, CacheConfig

if typing.TYPE_CHECKING:
    from vkflow.app.storages import NewMessage

    from .context import Context
    from .cooldowns import BucketType

    CheckFunction = typing.Callable[[Context | NewMessage], typing.Awaitable[bool] | bool]


__all__ = (
    "CheckFailureError",
    "check",
    "check_any",
    "cooldown",
    "dm_only",
    "guild_only",
    "is_admin",
    "is_group_chat",
    "is_owner",
    "is_private_message",
    "max_concurrency",
)


@dataclasses.dataclass
class CheckFailureError(CommandError):
    """
    Исключение при провале проверки команды
    """

    check: Check
    message: str | None = None
    delete_after: int | float | None = None


CheckFailure = CheckFailureError


@dataclasses.dataclass
class Check(BaseFilter):
    """
    Проверка, которую можно применить к командам через декораторы

    Пример:
        def is_admin():
            async def predicate(ctx):
                admin_ids = [123456, 789012]
                return ctx.author in admin_ids
            return check(predicate)

        @commands.command()
        @is_admin()
        async def admin_command(ctx: commands.Context):
            await ctx.send("You are an admin!")
    """

    predicate: CheckFunction
    error_message: str | None = None
    delete_after: int | float | None = None

    async def make_decision(self, ctx: NewMessage, **kwargs):
        """Выполнить предикат проверки"""
        from .context import Context
        from .cooldowns import OnCooldownError

        check_ctx = Context.from_message(ctx) if not isinstance(ctx, Context) else ctx

        try:
            if inspect.iscoroutinefunction(self.predicate):
                result = await self.predicate(check_ctx)
            else:
                result = self.predicate(check_ctx)

            if not result:
                if self.error_message:
                    await check_ctx.send(self.error_message, delete_after=self.delete_after)
                raise StopCurrentHandlingError()

        except StopCurrentHandlingError:
            raise

        except OnCooldownError as e:
            e._ctx = check_ctx
            raise StopCurrentHandlingError() from e

        except CheckFailureError as e:
            if e.message:
                da = e.delete_after if e.delete_after is not None else self.delete_after
                await check_ctx.send(e.message, delete_after=da)

            raise StopCurrentHandlingError() from e

        except Exception as e:
            if self.error_message:
                await check_ctx.send(self.error_message, delete_after=self.delete_after)
            raise StopCurrentHandlingError() from e

    def __call__(self, func_or_command):
        """Позволяет использовать Check как декоратор"""
        from .core import Command

        if isinstance(func_or_command, Command):
            if func_or_command.filter is None:
                func_or_command.filter = self
            else:
                func_or_command.filter = func_or_command.filter & self

            return func_or_command

        if not hasattr(func_or_command, "__vkflow_checks__"):
            func_or_command.__vkflow_checks__ = []

        func_or_command.__vkflow_checks__.append(self)
        return func_or_command


def check(
    predicate: CheckFunction,
    *,
    error_message: str | None = None,
    delete_after: int | float | None = None,
) -> Check:
    """
    Создать проверку из функции-предиката

    Args:
        predicate: Функция (синхронная или асинхронная), принимающая Context и возвращающая bool
        error_message: Необязательное сообщение об ошибке при провале проверки (отправляется пользователю)
        delete_after: Удалить сообщение об ошибке через указанное количество секунд.
            Если None -сообщение не удаляется автоматически.

    Returns:
        Экземпляр Check

    Пример:
        def is_owner():
            async def predicate(ctx):
                return ctx.author == OWNER_ID
            return check(predicate, error_message="Только владелец может это использовать!")

        def is_premium():
            def predicate(ctx):
                return ctx.author in PREMIUM_IDS
            return check(predicate, error_message="Только для премиум-пользователей!", delete_after=10)

        is_not_bot = lambda: check(
            lambda ctx: ctx.author > 0,
            error_message="Боты не могут это использовать!"
        )

        @commands.command()
        @is_owner()
        async def secret(ctx: commands.Context):
            await ctx.send("Секретная команда!")
    """
    return Check(predicate=predicate, error_message=error_message, delete_after=delete_after)


def check_any(
    *checks: Check,
    error_message: str | None = "Ни одна из проверок не пройдена",
    delete_after: int | float | None = None,
) -> Check:
    """
    Объединить несколько проверок логикой ИЛИ

    Хотя бы одна проверка должна пройти для выполнения команды

    Args:
        *checks: Объекты Check для объединения
        error_message: Сообщение при провале всех проверок.
            По умолчанию "Ни одна из проверок не пройдена".
        delete_after: Удалить сообщение об ошибке через указанное количество секунд.

    Returns:
        Экземпляр Check

    Пример:
        @commands.command()
        @check_any(is_owner(), is_admin(), error_message="Нужны права владельца или админа!")
        async def manage(ctx: commands.Context):
            await ctx.send("Вы владелец или админ!")
    """

    async def predicate(ctx: Context) -> bool:
        for check_obj in checks:
            try:
                if inspect.iscoroutinefunction(check_obj.predicate):
                    result = await check_obj.predicate(ctx)
                else:
                    result = check_obj.predicate(ctx)
                if result:
                    return True
            except Exception:
                continue
        return False

    return check(predicate, error_message=error_message, delete_after=delete_after)


_owner_cache = APICache(CacheConfig(ttl=600, max_size=100))


def is_owner(*, delete_after: int | float | None = None) -> Check:
    """
    Проверка, является ли автор сообщения владельцем или администратором группы.

    Определяет group_id автоматически из токена бота и проверяет
    роль автора через groups.getMembers (role: creator, administrator).
    Результат кэшируется на 10 минут.

    Работает только с групповым токеном. С пользовательским -всегда False.

    Args:
        delete_after: Удалить сообщение об ошибке через указанное количество секунд.

    Returns:
        Экземпляр Check

    Пример:
        @commands.command()
        @is_owner()
        async def owner_cmd(ctx: commands.Context):
            await ctx.send("Команда владельца!")

        @commands.command()
        @is_owner(delete_after=5)
        async def owner_cmd(ctx: commands.Context):
            await ctx.send("Команда владельца!")
    """

    async def predicate(ctx: Context) -> bool:
        from vkflow.api import TokenOwner

        token_owner, owner = await ctx.api.define_token_owner()
        if token_owner != TokenOwner.GROUP:
            return False

        group_id = owner.id
        cache_key = str(group_id)
        cached = await _owner_cache.get(cache_key)

        if cached is not None:
            return ctx.author in cached

        response = await ctx.api.method(
            "groups.get_members",
            group_id=group_id,
            filter="managers",
        )

        owner_ids: set[int] = set()
        for member in response.get("items", []):
            if member.get("role") in ("creator", "administrator"):
                owner_ids.add(member["id"])

        await _owner_cache.set(cache_key, owner_ids)
        return ctx.author in owner_ids

    return check(
        predicate,
        error_message="Только владелец может использовать эту команду!",
        delete_after=delete_after,
    )


_admin_cache = APICache(CacheConfig(ttl=300, max_size=500))


def is_admin(*, delete_after: int | float | None = None) -> Check:
    """
    Проверка, является ли автор сообщения администратором чата.

    Проверяет через messages.getConversationMembers (is_admin / is_owner).
    Результат кэшируется на 5 минут.

    В личных сообщениях -всегда False.

    Args:
        delete_after: Удалить сообщение об ошибке через указанное количество секунд.

    Returns:
        Экземпляр Check

    Пример:
        @commands.command()
        @is_admin()
        async def admin_cmd(ctx: commands.Context):
            await ctx.send("Команда для админов!")

        @commands.command()
        @is_admin(delete_after=10)
        async def admin_cmd(ctx: commands.Context):
            await ctx.send("Команда для админов!")
    """

    async def predicate(ctx: Context) -> bool:
        if ctx.peer_id <= 2000000000:
            return False

        cache_key = str(ctx.peer_id)
        cached = await _admin_cache.get(cache_key)

        if cached is not None:
            return ctx.author in cached

        response = await ctx.api.messages.get_conversation_members(
            peer_id=ctx.peer_id,
            extended=False,
        )

        admin_ids: set[int] = set()
        for item in response.get("items", []):
            if item.get("is_admin") or item.get("is_owner"):
                admin_ids.add(item["member_id"])

        await _admin_cache.set(cache_key, admin_ids)
        return ctx.author in admin_ids

    return check(
        predicate,
        error_message="Вы должны быть администратором, чтобы использовать эту команду!",
        delete_after=delete_after,
    )


def is_private_message(*, delete_after: int | float | None = None) -> Check:
    """
    Проверка, что сообщение из личного чата

    Args:
        delete_after: Удалить сообщение об ошибке через указанное количество секунд.

    Returns:
        Экземпляр Check

    Пример:
        @commands.command()
        @is_private_message()
        async def private_cmd(ctx: commands.Context):
            await ctx.send("Это личное сообщение!")
    """

    async def predicate(ctx: Context) -> bool:
        return ctx.peer_id == ctx.author

    return check(
        predicate,
        error_message="Эта команда доступна только в личных сообщениях!",
        delete_after=delete_after,
    )


dm_only = is_private_message


def is_group_chat(*, delete_after: int | float | None = None) -> Check:
    """
    Проверка, что сообщение из группового чата

    Args:
        delete_after: Удалить сообщение об ошибке через указанное количество секунд.

    Returns:
        Экземпляр Check

    Пример:
        @commands.command()
        @is_group_chat()
        async def group_cmd(ctx: commands.Context):
            await ctx.send("Это групповой чат!")
    """

    async def predicate(ctx: Context) -> bool:
        return ctx.peer_id != ctx.author and ctx.peer_id > 2000000000

    return check(
        predicate, error_message="Эта команда доступна только в групповых чатах!", delete_after=delete_after
    )


guild_only = is_group_chat


def cooldown(
    rate: int, per: float | int, type: BucketType | None = None, *, delete_after: int | float | None = None
) -> Check:
    """
    Применить cooldown к команде.

    Args:
        rate: Количество раз, сколько команда может быть использована
        per: Временной период в секундах (int/float/timedelta)
        type: BucketType (DEFAULT, USER, CHAT, MEMBER)
        delete_after: Удалить сообщение об ошибке через указанное количество секунд.

    Returns:
        Экземпляр Check

    Пример:
        from vkflow.commands import BucketType

        @commands.command()
        @commands.cooldown(rate=3, per=60.0, type=BucketType.USER)
        async def spam_cmd(ctx: commands.Context):
            await ctx.send("Спам!")

        @commands.command()
        @commands.cooldown(rate=1, per=30, type=BucketType.MEMBER)
        async def limited(ctx: commands.Context):
            await ctx.send("Ограниченная команда!")
    """
    from .cooldowns import BucketType, Cooldown, CooldownMapping, OnCooldownError

    if type is None:
        type = BucketType.USER

    mapping = CooldownMapping(cooldown=Cooldown(rate=rate, per=per), type=type)

    async def predicate(ctx: Context) -> bool:
        retry_after = await mapping.acquire(ctx)

        if retry_after is not None:
            raise OnCooldownError(mapping._cooldown, retry_after, mapping.type)

        return True

    check_obj = check(predicate, error_message=None, delete_after=delete_after)
    check_obj._cooldown_mapping = mapping

    return check_obj


def max_concurrency(number: int, per: BucketType | None = None) -> typing.Callable:
    """
    Ограничить количество одновременных выполнений команды.

    Args:
        number: Максимальное количество одновременных выполнений
        per: BucketType (DEFAULT, USER, CHAT, MEMBER)

    Returns:
        Функция-декоратор

    Пример:
        from vkflow.commands import BucketType

        @commands.command()
        @commands.max_concurrency(2, BucketType.CHAT)
        async def heavy(ctx: commands.Context):
            await asyncio.sleep(10)
            await ctx.send("Готово!")

        @commands.command()
        @commands.max_concurrency(1, BucketType.USER)
        async def unique(ctx: commands.Context):
            await ctx.send("Выполняется!")
    """
    from .cooldowns import BucketType, MaxConcurrency, MaxConcurrencyMapping

    if per is None:
        per = BucketType.DEFAULT

    mapping = MaxConcurrencyMapping(max_concurrency=MaxConcurrency(number=number, per=per))

    def decorator(func):
        func.__max_concurrency__ = mapping
        return func

    return decorator
