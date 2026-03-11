# SPDX-License-Identifier: MIT
from __future__ import annotations

import datetime
import calendar

__all__ = ["next_cron_time", "validate_cron"]

_FIELD_RANGES: list[tuple[int, int]] = [
    (0, 59),  # minute
    (0, 23),  # hour
    (1, 31),  # day of month
    (1, 12),  # month
    (0, 6),  # day of week (0=Mon ... 6=Sun)
]

_WEEKDAY_MAP: dict[str, str] = {
    "mon": "0",
    "tue": "1",
    "wed": "2",
    "thu": "3",
    "fri": "4",
    "sat": "5",
    "sun": "6",
}

_MONTH_MAP: dict[str, str] = {
    "jan": "1",
    "feb": "2",
    "mar": "3",
    "apr": "4",
    "may": "5",
    "jun": "6",
    "jul": "7",
    "aug": "8",
    "sep": "9",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}


def _parse_field(field: str, lo: int, hi: int) -> set[int]:
    """Разбирает одно поле cron-выражения в набор допустимых значений."""
    result: set[int] = set()

    for part in field.split(","):
        if "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"Шаг должен быть > 0, получено: {step}")
        else:
            base = part
            step = 0

        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            s, e = base.split("-", 1)
            start, end = int(s), int(e)
            if start < lo or end > hi or start > end:
                raise ValueError(f"Диапазон {start}-{end} вне допустимого {lo}-{hi}")
        else:
            val = int(base)
            if val < lo or val > hi:
                raise ValueError(f"Значение {val} вне допустимого {lo}-{hi}")
            if step:
                start, end = val, hi
            else:
                result.add(val)
                continue

        if step:
            result.update(range(start, end + 1, step))
        else:
            result.update(range(start, end + 1))

    return result


def _preprocess(expr: str) -> list[str]:
    """Нормализует cron-выражение: разбивает на поля, заменяет имена."""
    fields = expr.strip().lower().split()
    if len(fields) != 5:
        raise ValueError(
            f"Cron-выражение должно содержать 5 полей "
            f"(minute hour day month weekday), получено {len(fields)}"
        )

    for name, val in _MONTH_MAP.items():
        fields[3] = fields[3].replace(name, val)

    for name, val in _WEEKDAY_MAP.items():
        fields[4] = fields[4].replace(name, val)

    return fields


def _parse_cron(expr: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    """Разбирает cron-выражение в кортеж из пяти наборов значений."""
    fields = _preprocess(expr)
    return tuple(  # type: ignore[return-value]
        _parse_field(f, lo, hi) for f, (lo, hi) in zip(fields, _FIELD_RANGES, strict=True)
    )


def validate_cron(expr: str) -> bool:
    """Проверяет корректность cron-выражения."""
    try:
        _parse_cron(expr)
    except (ValueError, IndexError):
        return False
    return True


def next_cron_time(
    expr: str,
    after: datetime.datetime | None = None,
    *,
    tz: datetime.tzinfo = datetime.UTC,
) -> datetime.datetime:
    """Вычисляет следующее время срабатывания для cron-выражения.

    Стандартный 5-полевой формат::

        ┌───────── минута (0-59)
        │ ┌─────── час (0-23)
        │ │ ┌───── день месяца (1-31)
        │ │ │ ┌─── месяц (1-12)
        │ │ │ │ ┌─ день недели (0=Пн ... 6=Вс)
        * * * * *

    Поддерживаются: ``*``, диапазоны (``1-5``), шаг (``*/5``, ``1-10/2``),
    списки (``1,3,5``), имена месяцев и дней недели.

    Args:
        expr: Cron-выражение.
        after: Момент, после которого искать. По умолчанию — текущее время.
        tz: Часовой пояс для результата.

    Returns:
        Следующий момент срабатывания.

    Raises:
        ValueError: Некорректное cron-выражение или невозможно найти совпадение.
    """
    minutes, hours, days, months, weekdays = _parse_cron(expr)

    if after is None:
        after = datetime.datetime.now(tz)
    elif after.tzinfo is None:
        after = after.replace(tzinfo=tz)

    dt = after.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

    for _ in range(366 * 24 * 60):
        if dt.month not in months:
            if dt.month == 12:
                dt = dt.replace(year=dt.year + 1, month=1, day=1, hour=0, minute=0)
            else:
                dt = dt.replace(month=dt.month + 1, day=1, hour=0, minute=0)
            continue

        max_day = calendar.monthrange(dt.year, dt.month)[1]
        if dt.day not in days or dt.day > max_day:
            dt += datetime.timedelta(days=1)
            dt = dt.replace(hour=0, minute=0)
            continue

        if dt.weekday() not in weekdays:
            dt += datetime.timedelta(days=1)
            dt = dt.replace(hour=0, minute=0)
            continue

        if dt.hour not in hours:
            dt += datetime.timedelta(hours=1)
            dt = dt.replace(minute=0)
            continue

        if dt.minute not in minutes:
            dt += datetime.timedelta(minutes=1)
            continue

        return dt

    raise ValueError(f"Не удалось найти следующее время для cron-выражения: {expr!r}")
