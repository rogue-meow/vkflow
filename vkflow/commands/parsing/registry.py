"""
Registry for custom cutters.

Allows registering custom cutters for arbitrary types that will be
automatically resolved during command argument parsing.

Example:
    from vkflow import register_cutter
    from vkflow.commands.parsing.cutter import Cutter, CutterParsingResponse

    class Color:
        def __init__(self, r: int, g: int, b: int):
            self.r, self.g, self.b = r, g, b

    @register_cutter(Color)
    class ColorCutter(Cutter):
        async def cut_part(self, ctx, arguments_string):
            # Parse "#FF0000" or "255,0,0"
            ...

        def gen_doc(self):
            return "color in hex (#FF0000) or RGB (255,0,0) format"

    # Now works automatically:
    @command(names=["setcolor"])
    async def setcolor(ctx, color: Color):
        ...
"""

from __future__ import annotations

import typing
import inspect

if typing.TYPE_CHECKING:
    from vkflow.commands.parsing.cutter import Cutter


_cutter_registry: dict[type, type[Cutter]] = {}


def _validate_cutter_class(cls: type) -> None:
    """Проверить, что cls является подклассом Cutter."""
    from vkflow.commands.parsing.cutter import Cutter

    if not (inspect.isclass(cls) and issubclass(cls, Cutter)):
        raise TypeError(
            f"Ожидался подкласс Cutter, получен {cls!r}. "
            f"Зарегистрированный каттер должен наследоваться от Cutter."
        )


def register_cutter(
    type_class: type,
    cutter_class: type[Cutter] | None = None,
) -> type[Cutter] | typing.Callable[[type[Cutter]], type[Cutter]]:
    """
    Зарегистрировать пользовательский каттер для типа.

    Можно использовать как декоратор или как функцию.

    Пример как декоратор:
        @register_cutter(Color)
        class ColorCutter(Cutter):
            ...

    Пример как функция:
        register_cutter(Color, ColorCutter)

    Аргументы:
        type_class: Тип, для которого регистрируется каттер
        cutter_class: Класс каттера (опционально, если используется как декоратор)

    Возвращает:
        Класс каттера (при вызове как функция) или декоратор

    Raises:
        TypeError: Если cutter_class не является подклассом Cutter
    """
    if cutter_class is not None:
        _validate_cutter_class(cutter_class)
        _cutter_registry[type_class] = cutter_class
        return cutter_class

    def decorator(cls: type[Cutter]) -> type[Cutter]:
        _validate_cutter_class(cls)
        _cutter_registry[type_class] = cls
        return cls

    return decorator


def unregister_cutter(type_class: type) -> type[Cutter] | None:
    """
    Unregister a custom cutter for a type.

    Arguments:
        type_class: The type to unregister

    Returns:
        The previously registered cutter class, or None if not found
    """
    return _cutter_registry.pop(type_class, None)


def get_registered_cutter(type_class: type) -> type[Cutter] | None:
    """
    Get the registered cutter for a type.

    Performs exact match first, then checks MRO (base classes)
    so that registering a cutter for a base class covers subclasses.

    Arguments:
        type_class: The type to look up

    Returns:
        The registered cutter class, or None if not found
    """
    result = _cutter_registry.get(type_class)
    if result is not None:
        return result

    if hasattr(type_class, "__mro__"):
        for base in type_class.__mro__[1:]:
            result = _cutter_registry.get(base)
            if result is not None:
                return result

    return None


def get_all_registered_cutters() -> dict[type, type[Cutter]]:
    """
    Get a copy of all registered cutters.

    Returns:
        A dictionary mapping types to their cutter classes
    """
    return _cutter_registry.copy()


def clear_registry() -> None:
    """
    Clear all registered cutters.

    Useful for testing.
    """
    _cutter_registry.clear()
