"""
Пример middleware (промежуточного ПО).

Демонстрирует:
- before_command / after_command хуки
- MiddlewarePriority для управления порядком
- Блокировка выполнения команды из middleware
- Логирование, авторизация, аналитика
"""

import time

import vkflow

from vkflow import commands
from vkflow.commands.middleware import (
    after_command,
    before_command,
)


app = vkflow.App(prefixes=["!"])

# Хранилище для аналитики
command_stats: dict[str, int] = {}
banned_users: set[int] = set()


# =============================================
# 1. Before Command - логирование
# =============================================


@before_command
async def log_command(ctx: commands.Context, command):
    """Логирует каждую вызванную команду"""
    cmd_name = command.name if command else "unknown"
    print(f"[LOG] Команда '{cmd_name}' от пользователя {ctx.author} в {ctx.peer_id}")


# Регистрируем хук в менеджере middleware приложения
app.middleware_manager.add_before_command_hook(log_command)


# =============================================
# 2. Before Command - блокировка забаненных
# =============================================


@before_command
async def check_banned(ctx: commands.Context):
    """Блокирует забаненных пользователей. Возврат False отменяет команду."""
    if ctx.author in banned_users:
        await ctx.send("Вы заблокированы!")
        return False


app.middleware_manager.add_before_command_hook(check_banned)


# =============================================
# 3. Before Command - замер времени
# =============================================


@before_command
async def start_timer(ctx: commands.Context):
    """Запоминает время начала выполнения"""
    ctx._start_time = time.monotonic()


app.middleware_manager.add_before_command_hook(start_timer)


# =============================================
# 4. After Command - аналитика и замер времени
# =============================================


@after_command
async def track_usage(ctx: commands.Context, command, error):
    """Собирает статистику использования команд"""
    cmd_name = command.name if command else "unknown"

    if cmd_name not in command_stats:
        command_stats[cmd_name] = 0
    command_stats[cmd_name] += 1

    elapsed = time.monotonic() - getattr(ctx, "_start_time", time.monotonic())

    if error:
        print(f"[STATS] '{cmd_name}' ОШИБКА за {elapsed:.3f}с: {error}")
    else:
        print(f"[STATS] '{cmd_name}' OK за {elapsed:.3f}с")


app.middleware_manager.add_after_command_hook(track_usage)


# =============================================
# 5. After Command - уведомление при ошибке
# =============================================


@after_command
async def notify_on_error(ctx: commands.Context, error):
    """Уведомляет админа об ошибках"""
    if error is not None:
        admin_id = 123456789
        bot = ctx.bot

        await bot.api.messages.send(
            peer_id=admin_id,
            message=f"Ошибка в команде: {type(error).__name__}: {error}",
            random_id=vkflow.random_id(),
        )


app.middleware_manager.add_after_command_hook(notify_on_error)


# =============================================
# Тестовые команды
# =============================================


@app.command()
async def hello(ctx: commands.Context):
    """Простая команда для теста middleware"""
    await ctx.send("Привет!")


@app.command()
async def stats(ctx: commands.Context):
    """Показать статистику команд"""
    if not command_stats:
        await ctx.send("Статистика пуста.")
        return

    text = "Статистика команд:\n"

    for cmd, count in sorted(command_stats.items(), key=lambda x: -x[1]):
        text += f"  {cmd}: {count} раз\n"

    await ctx.send(text)


@app.command()
async def ban(ctx: commands.Context, user_id: int):
    """Заблокировать пользователя: !ban 123"""
    banned_users.add(user_id)
    await ctx.send(f"Пользователь {user_id} заблокирован.")


@app.command()
async def unban(ctx: commands.Context, user_id: int):
    """Разблокировать пользователя: !unban 123"""
    banned_users.discard(user_id)
    await ctx.send(f"Пользователь {user_id} разблокирован.")


@app.command()
async def fail(ctx: commands.Context):
    """Команда, которая всегда падает (для теста after_command)"""
    raise RuntimeError("Тестовая ошибка!")


# =============================================
# Запуск
# =============================================

app.run("$VK_TOKEN")
