"""
Утилита для унифицированного вызова функций с инъекцией параметров по имени.

Используется для хуков, обработчиков ошибок, middleware и других
callback-функций, которые принимают произвольный набор параметров.
"""

from __future__ import annotations

import typing
import inspect
import functools


_SKIP_PARAMS = frozenset(("self", "cls"))


@functools.lru_cache(maxsize=256)
def _cached_signature(func: typing.Callable) -> inspect.Signature:
    return inspect.signature(func)


def _get_params(func: typing.Callable) -> list[inspect.Parameter]:
    """Получить параметры функции (без self/cls)."""
    sig = _cached_signature(func)
    return [p for p in sig.parameters.values() if p.name not in _SKIP_PARAMS]


async def inject_and_call(
    func: typing.Callable,
    available: dict[str, typing.Any],
) -> typing.Any:
    """
    Вызвать функцию, инъецируя параметры из available по имени.

    Анализирует сигнатуру func и передаёт только те аргументы,
    которые запрошены в сигнатуре и доступны в available.

    Если функция принимает **kwargs -все оставшиеся ключи из available,
    не занятые явными параметрами, передаются через kwargs.

    Если обязательный параметр (без значения по умолчанию) не найден
    в available -бросает TypeError с понятным сообщением.
    """
    params = _get_params(func)

    kwargs: dict[str, typing.Any] = {}
    has_var_keyword = False
    explicit_names: set[str] = set()

    for p in params:
        if p.kind == inspect.Parameter.VAR_KEYWORD:
            has_var_keyword = True
            continue

        if p.kind == inspect.Parameter.VAR_POSITIONAL:
            continue

        explicit_names.add(p.name)

        if p.name in available:
            kwargs[p.name] = available[p.name]
        elif p.default is inspect.Parameter.empty:
            raise TypeError(
                f"{getattr(func, '__qualname__', func)!r} requires parameter "
                f"'{p.name}', but it was not found in available keys: "
                f"{set(available)}"
            )

    if has_var_keyword:
        kwargs.update({key: value for key, value in available.items() if key not in explicit_names})

    result = func(**kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result
