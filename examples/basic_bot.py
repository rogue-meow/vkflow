"""
Базовый пример создания бота с помощью vkflow.App.

Демонстрирует:
- Создание приложения App
- Регистрация команд
- Команды с аргументами
- Алиасы и префиксы
- Подкоманды (Group)
- ctx.send / ctx.reply
- Запуск бота
"""

import vkflow

from vkflow import commands


# Создаём приложение с префиксом "/"
app = vkflow.App(prefixes=["/", "!"])


# --- Простая команда ---
@app.command()
async def hello(ctx: commands.Context):
    """Простое приветствие"""
    await ctx.send("Привет!")


# --- Команда с аргументами ---
@app.command()
async def greet(ctx: commands.Context, name: str):
    """Поприветствовать кого-то по имени"""
    await ctx.reply(f"Привет, {name}!")


# --- Команда с несколькими аргументами ---
@app.command()
async def add(ctx: commands.Context, a: int, b: int):
    """Сложить два числа"""
    await ctx.send(f"{a} + {b} = {a + b}")


# --- Команда с алиасами ---
@app.command(aliases=["hi", "yo"])
async def hey(ctx: commands.Context):
    """Поздороваться (имя: hey, алиасы: hi, yo)"""
    await ctx.send("Йо!")


# --- Команда с описанием и usage ---
@app.command(
    name="calc",
    aliases=["c"],
    help="Калькулятор",
    brief="Быстрый калькулятор",
    usage="<a> <оператор> <b>",
)
async def calculator(ctx: commands.Context, a: float, op: str, b: float):
    """Простой калькулятор"""
    ops = {"+": a + b, "-": a - b, "*": a * b, "/": a / b if b else 0}
    result = ops.get(op, "Неизвестный оператор")

    await ctx.send(f"Результат: {result}")


# --- Возврат строки как ответ ---
# Если команда возвращает строку, она автоматически отправляется как reply
@app.command()
async def ping(ctx: commands.Context):
    """Проверка бота"""
    return "Pong!"


# --- Подкоманды (Group) ---
@app.group()
async def config(ctx: commands.Context):
    """Настройки бота"""
    if not ctx.invoked_subcommand:
        await ctx.send("Доступные подкоманды: show, set")


@config.command()
async def show(ctx: commands.Context):
    """Показать настройки"""
    await ctx.send("Текущие настройки: ...")


@config.command()
async def set(ctx: commands.Context, key: str, value: str):
    """Установить настройку"""
    await ctx.send(f"Установлено: {key} = {value}")


# --- Информация об авторе ---
@app.command()
async def whoami(ctx: commands.Context):
    """Получить информацию о себе"""
    author = await ctx.fetch_author()
    await ctx.send(f"Ты - {author.mention()}")


# --- Запуск бота ---
app.run("$VK_TOKEN")
