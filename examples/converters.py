"""
Примеры конвертеров аргументов команд.

Демонстрирует:
- Кастомный Cutter (низкоуровневый парсинг)
- Класс Converter (высокоуровневый конвертер)
- Сырой класс с classmethod async create / синхронным __init__
- Встроенные конвертеры (User, Group, Mention)
- Greedy[T] для жадного потребления
- Annotated с NameCase, Strict, Between
- Enum и Dict каттеры
- Flag и Named аргументы
"""

import re

from typing import Annotated
from enum import Enum

import vkflow

from vkflow import commands
from vkflow.commands.parsing.cutter import (
    Cutter,
    CutterParsingResponse,
    cut_part_via_regex,
)

from vkflow.commands.parsing.converters import Converter, ConversionError
from vkflow.commands.parsing.cutters import NameCase, Strict, Flag, Named
from vkflow.commands.parsing.validators import Range, Between


app = vkflow.App(prefixes=["!"])


# =============================================
# 1. Кастомный Cutter (низкоуровневый)
# =============================================


class HexColorCutter(Cutter):
    """Каттер для HEX-цветов (#RRGGBB)"""

    _pattern = re.compile(r"#[0-9a-fA-F]{6}")

    async def cut_part(self, ctx, arguments_string: str) -> CutterParsingResponse:
        return cut_part_via_regex(
            self._pattern,
            arguments_string,
            error_description="Ожидается HEX-цвет в формате #RRGGBB",
        )

    def gen_doc(self) -> str:
        return "HEX-цвет (<code>#RRGGBB</code>)"


# Регистрируем каттер для автоматического использования по типу
class HexColor(str):
    """Тип для HEX-цвета, автоматически парсится через HexColorCutter"""


# Регистрируем каттер в реестре
vkflow.register_cutter(HexColor, HexColorCutter())


@app.command()
async def setcolor(ctx: commands.Context, color: HexColor):
    """Установить цвет: !setcolor #FF5733"""
    await ctx.send(f"Цвет установлен: {color}")


# =============================================
# 2. Converter (высокоуровневый)
# =============================================


class TimeConverter(Converter):
    """Конвертер для времени в формате ЧЧ:ММ"""

    async def convert(self, ctx: commands.Context, argument: str):
        parts = argument.split(":")

        if len(parts) != 2:
            raise ConversionError(self.__class__, argument, "Формат: ЧЧ:ММ")

        try:
            hours, minutes = int(parts[0]), int(parts[1])

            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise ValueError

            return {"hours": hours, "minutes": minutes}
        except ValueError:
            raise ConversionError(self.__class__, argument, "Некорректное время")


@app.command()
async def alarm(ctx: commands.Context, time: TimeConverter):
    """Установить будильник: !alarm 08:30"""
    await ctx.send(f"Будильник установлен на {time['hours']:02d}:{time['minutes']:02d}")


# =============================================
# 3. Сырой класс с __init__ (синхронный)
# =============================================


class Percentage:
    """
    Класс, автоматически конвертируемый из строки.
    Фреймворк вызывает __init__(ctx, value) при парсинге.
    """

    def __init__(self, ctx, value: str):
        value = value.rstrip("%")

        try:
            self.value = float(value)
        except ValueError:
            raise ValueError(f"'{value}' не является числом")

        if not (0 <= self.value <= 100):
            raise ValueError("Процент должен быть от 0 до 100")

    def __repr__(self):
        return f"{self.value}%"


@app.command()
async def progress(ctx: commands.Context, percent: Percentage):
    """Показать прогресс: !progress 75%"""
    bars = int(percent.value / 10)
    bar = "█" * bars + "░" * (10 - bars)

    await ctx.send(f"Прогресс: [{bar}] {percent}")


# =============================================
# 4. Сырой класс с async create (classmethod)
# =============================================


class RichUser:
    """
    Класс с асинхронным созданием.
    Фреймворк обнаруживает classmethod `create` и вызывает его.
    """

    def __init__(self, user_id: int, name: str, online: bool):
        self.user_id = user_id

        self.name = name
        self.online = online

    @classmethod
    async def create(cls, ctx, value: str):
        """Асинхронная фабрика - вызывается фреймворком"""
        try:
            user_id = int(value)
        except ValueError:
            raise ValueError(f"'{value}' не является ID пользователя")

        users = await ctx.api.users.get(user_ids=[user_id], fields=["online"])

        if not users:
            raise ValueError(f"Пользователь {user_id} не найден")

        user = users[0]

        return cls(
            user_id=user["id"],
            name=f"{user['first_name']} {user['last_name']}",
            online=bool(user.get("online", 0)),
        )


@app.command()
async def userinfo(ctx: commands.Context, user: RichUser):
    """Информация о пользователе: !userinfo 1"""
    status = "онлайн" if user.online else "оффлайн"
    await ctx.send(f"{user.name} (ID: {user.user_id}) - {status}")


# =============================================
# 5. Встроенные конвертеры
# =============================================


# User - автоматически резолвится из упоминания, ID или короткого имени
@app.command()
async def profile(ctx: commands.Context, target: vkflow.User):
    """Профиль пользователя: !profile [id1|Павел] или !profile 1"""
    await ctx.send(f"Имя: {target.first_name} {target.last_name}")


# User с падежом через Annotated + NameCase
@app.command()
async def pat(ctx: commands.Context, target: Annotated[vkflow.User, NameCase("acc")]):
    """Погладить: !pat [id1|Павел]"""
    await ctx.send(f"Погладил {target.mention()}")


# Greedy[User] - жадно потребляет всех пользователей
@app.command()
async def invite(ctx: commands.Context, users: commands.Greedy[vkflow.User]):
    """Пригласить пользователей: !invite @user1 @user2 @user3"""
    if not users:
        return "Укажите хотя бы одного пользователя!"

    names = ", ".join(u.first_name for u in users)
    await ctx.send(f"Приглашены: {names}")


# =============================================
# 6. Enum каттер
# =============================================


class GameMode(Enum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


@app.command()
async def play(ctx: commands.Context, mode: GameMode):
    """Начать игру: !play easy"""
    await ctx.send(f"Режим: {mode.value}")


# =============================================
# 7. Валидаторы: Range, Between
# =============================================


@app.command()
async def roll(ctx: commands.Context, sides: Annotated[int, Range(1, 100)]):
    """Бросить кубик: !roll 20"""
    import random

    result = random.randint(1, sides)
    await ctx.send(f"Выпало: {result} (d{sides})")


@app.command()
async def rate(ctx: commands.Context, score: Annotated[int, Between(1, 10)]):
    """Оценить: !rate 8"""
    await ctx.send(f"Оценка: {'⭐' * score}")


# =============================================
# 8. Flag и Named аргументы
# =============================================


@app.command()
async def search(
    ctx: commands.Context,
    query: str,
    verbose: Annotated[bool, Flag("--verbose", "-v")] = False,
    limit: Annotated[int, Named("--limit", "-l")] = 10,
):
    """Поиск: !search котики --verbose --limit 5"""
    await ctx.send(f"Поиск: {query}\nПодробный: {'да' if verbose else 'нет'}\nЛимит: {limit}")


# =============================================
# 9. Strict-режим через Annotated
# =============================================


class Temperature:
    """Температура с нестрогим парсингом"""

    __strict__ = False  # При ошибке вернёт default, а не отменит команду

    def __init__(self, ctx, value: str):
        value = value.rstrip("°CcСс")
        self.celsius = float(value)

    def __repr__(self):
        return f"{self.celsius}°C"


@app.command()
async def weather(ctx: commands.Context, temp: Temperature = None):
    """Погода: !weather 25°C или !weather (без аргумента)"""
    if temp is None:
        await ctx.send("Температура не указана")
    else:
        await ctx.send(f"Температура: {temp}")


# Можно переопределить strict через Annotated:
@app.command()
async def weather_strict(
    ctx: commands.Context,
    temp: Annotated[Temperature, Strict(True)],
):
    """Строгий вариант: !weather_strict 25 (ошибка при невалидном значении)"""
    await ctx.send(f"Температура: {temp}")


# =============================================
# Запуск
# =============================================

app.run("$VK_TOKEN")
