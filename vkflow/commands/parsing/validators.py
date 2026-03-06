"""
Validators for command arguments.

This module provides Annotated-style validators for command arguments.
Validators are applied after the cutter has parsed the argument value.

Usage:
    from typing import Annotated
    from vkflow import Range, MinLength, MaxLength, Regex, Between
    from vkflow import commands

    class MyCog(commands.Cog):
        @commands.command(name="roll")
        async def roll(self, ctx, sides: Annotated[int, Range(1, 100)] = 6):
            import random
            result = random.randint(1, sides)
            await ctx.reply(f"Выпало: {result}")

        @commands.command(name="nick")
        async def nick(self, ctx, name: Annotated[str, MinLength(3), MaxLength(20)]):
            await ctx.reply(f"Ник установлен: {name}")

        @commands.command(name="poll")
        async def poll(self, ctx, question: str, *, options: Annotated[commands.Greedy[str], Between(2, 10)]):
            await ctx.reply(f"Голосование: {question}\\nВарианты: {', '.join(options)}")
"""

from __future__ import annotations

import re
import dataclasses
import typing


@dataclasses.dataclass
class Validator:
    """
    Base class for Annotated validators.

    Subclasses should override `validate` and `description` methods.
    """

    def validate(self, value: typing.Any) -> typing.Any:
        """
        Validate the value.

        Args:
            value: The value to validate

        Returns:
            The validated value (possibly transformed)

        Raises:
            ValueError: If validation fails
        """
        return value

    def description(self) -> str:
        """
        Get a description of this validator for error messages.

        Returns:
            Description string
        """
        return ""


@dataclasses.dataclass
class Range(Validator):
    """
    Range constraint for int/float values.

    Usage:
        Annotated[int, Range(1, 100)]
        Annotated[float, Range(0.0, 1.0)]
    """

    min: int | float
    max: int | float

    def validate(self, value: int | float) -> int | float:
        if not (self.min <= value <= self.max):
            raise ValueError(f"Значение должно быть в диапазоне [{self.min}, {self.max}]")
        return value

    def description(self) -> str:
        return f"от {self.min} до {self.max}"


@dataclasses.dataclass
class MinLength(Validator):
    """
    Minimum length constraint for strings.

    Usage:
        Annotated[str, MinLength(3)]
    """

    length: int

    def validate(self, value: str) -> str:
        if len(value) < self.length:
            raise ValueError(f"Минимальная длина: {self.length} символов")
        return value

    def description(self) -> str:
        return f"минимум {self.length} символов"


@dataclasses.dataclass
class MaxLength(Validator):
    """
    Maximum length constraint for strings.

    Usage:
        Annotated[str, MaxLength(20)]
    """

    length: int

    def validate(self, value: str) -> str:
        if len(value) > self.length:
            raise ValueError(f"Максимальная длина: {self.length} символов")
        return value

    def description(self) -> str:
        return f"максимум {self.length} символов"


@dataclasses.dataclass
class Regex(Validator):
    """
    Regex pattern constraint for strings.

    Usage:
        Annotated[str, Regex(r"^[a-zA-Z]+$")]
        Annotated[str, Regex(r"^[a-zA-Z]+$", message="Только буквы")]
    """

    pattern: str
    message: str | None = None

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    def validate(self, value: str) -> str:
        if not self._compiled.match(value):
            msg = self.message or f"Значение не соответствует паттерну: {self.pattern}"
            raise ValueError(msg)
        return value

    def description(self) -> str:
        return self.message or f"паттерн: {self.pattern}"


@dataclasses.dataclass
class Between(Validator):
    """
    Element count constraint for Greedy lists.

    Usage:
        Annotated[Greedy[str], Between(2, 10)]
    """

    min: int
    max: int

    def validate(self, value: list) -> list:
        if len(value) < self.min:
            raise ValueError(f"Минимум {self.min} элементов")
        if len(value) > self.max:
            raise ValueError(f"Максимум {self.max} элементов")
        return value

    def description(self) -> str:
        return f"от {self.min} до {self.max} элементов"


class Transform(Validator):
    """
    Трансформирующий валидатор - применяет функции к значению последовательно.

    Поддерживает одну или несколько функций (цепочка):
        Annotated[str, Transform(str.lower)]
        Annotated[str, Transform(str.strip, str.lower)]
        Annotated[int, Transform(abs)]
    """

    def __init__(self, *funcs: typing.Callable[[typing.Any], typing.Any]):
        if not funcs:
            raise ValueError("Transform требует хотя бы одну функцию")
        self._funcs = funcs

    def validate(self, value: typing.Any) -> typing.Any:
        for func in self._funcs:
            try:
                value = func(value)
            except Exception as e:
                name = getattr(func, "__name__", str(func))
                raise ValueError(f"Трансформация {name} не удалась: {e}") from e
        return value

    def description(self) -> str:
        names = [getattr(f, "__name__", str(f)) for f in self._funcs]
        return f"transform: {' → '.join(names)}"


@dataclasses.dataclass
class OneOf(Validator):
    """
    Валидатор допустимых значений.

    Проверяет, что значение входит в список разрешённых.

    Usage:
        Annotated[str, OneOf("rock", "paper", "scissors")]
        Annotated[int, OneOf(1, 2, 3, 5, 8, 13)]
    """

    allowed: tuple

    def __init__(self, *values):
        self.allowed = values

    def validate(self, value: typing.Any) -> typing.Any:
        if value not in self.allowed:
            formatted = ", ".join(repr(v) for v in self.allowed)
            raise ValueError(f"Допустимые значения: {formatted}")
        return value

    def description(self) -> str:
        return f"одно из: {', '.join(repr(v) for v in self.allowed)}"


__all__ = [
    "Between",
    "MaxLength",
    "MinLength",
    "OneOf",
    "Range",
    "Regex",
    "Transform",
    "Validator",
]
