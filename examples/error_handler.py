"""
Пример обработки ошибок на всех уровнях.

Цепочка обработки ошибок (от наиболее к наименее специфичному):
1. Локальный @command.on_error() - обработчик конкретной команды
2. Cog.cog_command_error() - информационный (логирование), всегда вызывается
3. Cog.cog_command_fallback() - fallback для необработанных ошибок в коге
4. App.on_command_error() - информационный (логирование), всегда вызывается
5. App.on_command_error_fallback() - глобальный fallback

Также демонстрирует:
- on_error с фильтрацией по типу ошибки
- on_cooldown обработчик
- on_max_concurrency обработчик
- before_invoke / after_invoke хуки
- Обработка ArgumentParsingError (strict_mode)
"""

import asyncio

import vkflow

from vkflow import commands

from vkflow.commands import BucketType
from vkflow.exceptions import ArgumentParsingError


# =============================================
# Кастомные исключения
# =============================================


class InsufficientFunds(Exception):
    def __init__(self, balance: int, required: int):
        self.balance = balance
        self.required = required

        super().__init__(f"Недостаточно средств: {balance}/{required}")


class UserBanned(Exception):
    def __init__(self, reason: str):
        self.reason = reason

        super().__init__(f"Пользователь заблокирован: {reason}")


# =============================================
# App с глобальной обработкой ошибок
# =============================================


class MyApp(vkflow.App):
    async def on_command_error(self, ctx, error):
        """
        Уровень 4: Информационный обработчик.
        Вызывается ВСЕГДА при любой ошибке, независимо от других обработчиков.
        Используйте для логирования, метрик, уведомлений.
        """
        print(f"[LOG] Ошибка в команде: {type(error).__name__}: {error}")

    async def on_command_error_fallback(self, ctx, error):
        """
        Уровень 5: Глобальный fallback.
        Вызывается ТОЛЬКО если ни один другой обработчик не обработал ошибку.
        Если этот метод НЕ выбрасывает исключение - ошибка считается обработанной.
        """
        if isinstance(error, ArgumentParsingError):
            await ctx.reply(
                f"Неверные аргументы: {error.reason}\n"
                f"Использование: {ctx.clean_prefix}{ctx.command.name} {ctx.command.usage or ''}"
            )
        else:
            await ctx.reply(f"Произошла непредвиденная ошибка: {type(error).__name__}")


app = MyApp(prefixes=["!"])


# =============================================
# Уровень 1: Локальные обработчики @command.on_error()
# =============================================


@app.command()
async def pay(ctx: commands.Context, amount: int):
    """Оплата: !pay 100"""
    balance = 50  # Имитация

    if amount > balance:
        raise InsufficientFunds(balance, amount)
    await ctx.send(f"Оплачено: {amount}")


# Обработчик конкретного типа ошибки
@pay.on_error(InsufficientFunds)
async def on_pay_insufficient(ctx: commands.Context, error: InsufficientFunds):
    await ctx.send(f"Недостаточно средств!\nБаланс: {error.balance}\nТребуется: {error.required}")


@app.command()
async def risky(ctx: commands.Context):
    """Рискованная команда"""
    raise RuntimeError("Что-то пошло не так!")


# Универсальный обработчик (catch-all) - ловит все ошибки
@risky.on_error()
async def on_risky_error(ctx: commands.Context, error: Exception):
    await ctx.send(f"Команда /risky упала: {type(error).__name__}")


@app.command()
async def multi_error(ctx: commands.Context, action: str):
    """Команда с несколькими обработчиками"""
    if action == "ban":
        raise UserBanned("спам")
    if action == "pay":
        raise InsufficientFunds(10, 100)
    raise ValueError("Неизвестное действие")


# Несколько on_error для разных типов ошибок
@multi_error.on_error(UserBanned)
async def on_multi_banned(ctx: commands.Context, error: UserBanned):
    await ctx.send(f"Вы заблокированы: {error.reason}")


@multi_error.on_error(InsufficientFunds)
async def on_multi_funds(ctx: commands.Context, error: InsufficientFunds):
    await ctx.send(f"Мало денег: {error.balance}/{error.required}")


# Catch-all для остальных ошибок
@multi_error.on_error()
async def on_multi_other(ctx: commands.Context, error: Exception):
    await ctx.send(f"Другая ошибка: {error}")


# =============================================
# Cooldown и Max Concurrency обработчики
# =============================================


@app.command()
@commands.cooldown(rate=3, per=60, type=BucketType.USER)
async def spam(ctx: commands.Context):
    """Команда с кулдауном (3 раза в минуту)"""
    await ctx.send("Спам!")


@spam.on_cooldown()
async def on_spam_cooldown(ctx: commands.Context, remaining: float):
    await ctx.send(f"Подождите {remaining:.1f} сек.")


@app.command()
@commands.max_concurrency(2, BucketType.CHAT)
async def heavy(ctx: commands.Context):
    """Тяжёлая команда (макс. 2 одновременно в чате)"""
    await asyncio.sleep(10)
    await ctx.send("Готово!")


@heavy.on_max_concurrency()
async def on_heavy_concurrency(ctx: commands.Context, limit: int, current: int):
    await ctx.send(f"Слишком много выполнений: {current}/{limit}")


# =============================================
# Before/After Invoke хуки
# =============================================


@app.command()
async def guarded(ctx: commands.Context):
    """Команда с хуками"""
    await ctx.send("Основная логика!")


@guarded.before_invoke()
async def before_guarded(ctx: commands.Context):
    """Вызывается перед командой. Верните False для отмены."""
    print(f"[BEFORE] {ctx.command.name} от {ctx.author}")
    # return False  # Раскомментируйте для отмены команды


@guarded.after_invoke()
async def after_guarded(ctx: commands.Context, error):
    """Вызывается после команды (всегда, даже при ошибке)"""
    if error:
        print(f"[AFTER] Команда упала: {error}")
    else:
        print("[AFTER] Команда выполнена успешно")


# =============================================
# Уровни 2-3: Обработка ошибок в Cog
# =============================================


class ShopCog(commands.Cog):
    """Ког магазина с обработкой ошибок"""

    @commands.command()
    async def buy(self, ctx: commands.Context, item: str):
        """Купить предмет"""
        if item == "sword":
            raise InsufficientFunds(10, 100)
        await ctx.send(f"Куплено: {item}")

    @commands.command()
    async def sell(self, ctx: commands.Context, item: str):
        """Продать предмет"""
        raise ValueError(f"Предмет '{item}' нельзя продать")

    # Локальный обработчик для buy
    @buy.on_error(InsufficientFunds)
    async def on_buy_error(self, ctx: commands.Context, error: InsufficientFunds):
        await ctx.send(f"Не хватает золота: {error.balance}/{error.required}")

    async def cog_command_error(self, ctx, error):
        """
        Уровень 2: Информационный обработчик кога.
        Вызывается ВСЕГДА при ошибке в любой команде кога.
        НЕ влияет на дальнейшую обработку - только для логирования.
        """
        print(f"[COG LOG] Ошибка в {ctx.command.name}: {error}")

    async def cog_command_fallback(self, ctx, error):
        """
        Уровень 3: Fallback кога.
        Вызывается, если ни один on_error не обработал ошибку.
        Если завершается без raise - ошибка считается обработанной.
        """
        await ctx.send(f"Ошибка в магазине: {type(error).__name__}: {error}")


async def setup():
    await app.add_cog(ShopCog())


app.run_when_ready(setup)
app.run("$VK_TOKEN")
