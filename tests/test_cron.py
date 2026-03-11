from __future__ import annotations

import datetime

import pytest

from vkflow.commands.cron import next_cron_time, validate_cron, _parse_field, _parse_cron


# ─── validate_cron ───


def test_validate_cron_valid():
    """Корректные cron-выражения проходят валидацию."""
    assert validate_cron("* * * * *") is True
    assert validate_cron("0 9 * * mon-fri") is True
    assert validate_cron("*/5 * * * *") is True
    assert validate_cron("0 0 1 1 *") is True


def test_validate_cron_invalid():
    """Некорректные выражения не проходят валидацию."""
    assert validate_cron("") is False
    assert validate_cron("* * *") is False
    assert validate_cron("60 * * * *") is False
    assert validate_cron("* 25 * * *") is False
    assert validate_cron("* * * 13 *") is False


# ─── _parse_field ───


def test_parse_field_wildcard():
    """Звёздочка раскрывается в полный диапазон."""
    result = _parse_field("*", 0, 59)
    assert result == set(range(60))


def test_parse_field_single_value():
    """Одиночное значение."""
    assert _parse_field("5", 0, 59) == {5}


def test_parse_field_range():
    """Диапазон значений."""
    assert _parse_field("1-5", 0, 59) == {1, 2, 3, 4, 5}


def test_parse_field_step():
    """Шаг по всему диапазону."""
    assert _parse_field("*/15", 0, 59) == {0, 15, 30, 45}


def test_parse_field_range_with_step():
    """Шаг по поддиапазону."""
    assert _parse_field("1-10/3", 0, 59) == {1, 4, 7, 10}


def test_parse_field_list():
    """Список значений через запятую."""
    assert _parse_field("1,3,5", 0, 59) == {1, 3, 5}


def test_parse_field_complex():
    """Комбинация списка, диапазона и шага."""
    assert _parse_field("1,10-12,*/20", 0, 59) == {0, 1, 10, 11, 12, 20, 40}


def test_parse_field_value_out_of_range():
    """Значение вне допустимого диапазона вызывает ошибку."""
    with pytest.raises(ValueError, match="вне допустимого"):
        _parse_field("60", 0, 59)


def test_parse_field_range_out_of_bounds():
    """Диапазон вне границ вызывает ошибку."""
    with pytest.raises(ValueError, match="вне допустимого"):
        _parse_field("0-32", 1, 31)


def test_parse_field_zero_step():
    """Нулевой шаг вызывает ошибку."""
    with pytest.raises(ValueError, match="Шаг должен быть > 0"):
        _parse_field("*/0", 0, 59)


# ─── _parse_cron ───


def test_parse_cron_every_minute():
    """Каждую минуту."""
    mins, hrs, days, mons, wdays = _parse_cron("* * * * *")
    assert mins == set(range(60))
    assert hrs == set(range(24))
    assert days == set(range(1, 32))
    assert mons == set(range(1, 13))
    assert wdays == set(range(7))


def test_parse_cron_specific():
    """Конкретное расписание: 9:30 каждый понедельник."""
    mins, hrs, _days, _mons, wdays = _parse_cron("30 9 * * mon")
    assert mins == {30}
    assert hrs == {9}
    assert wdays == {0}


def test_parse_cron_month_names():
    """Имена месяцев заменяются на числа."""
    _, _, _, mons, _ = _parse_cron("0 0 1 jan,mar,dec *")
    assert mons == {1, 3, 12}


def test_parse_cron_wrong_field_count():
    """Неверное число полей вызывает ошибку."""
    with pytest.raises(ValueError, match="5 полей"):
        _parse_cron("* * *")


# ─── next_cron_time ───


def test_next_cron_time_every_minute():
    """Следующая минута от заданного времени."""
    after = datetime.datetime(2025, 6, 15, 10, 30, 0, tzinfo=datetime.UTC)
    result = next_cron_time("* * * * *", after)
    assert result == datetime.datetime(2025, 6, 15, 10, 31, 0, tzinfo=datetime.UTC)


def test_next_cron_time_specific_minute():
    """Конкретная минута — ближайшая следующая."""
    after = datetime.datetime(2025, 6, 15, 10, 14, 0, tzinfo=datetime.UTC)
    result = next_cron_time("30 * * * *", after)
    assert result == datetime.datetime(2025, 6, 15, 10, 30, 0, tzinfo=datetime.UTC)


def test_next_cron_time_next_hour():
    """Минута уже прошла — переход на следующий час."""
    after = datetime.datetime(2025, 6, 15, 10, 45, 0, tzinfo=datetime.UTC)
    result = next_cron_time("30 * * * *", after)
    assert result == datetime.datetime(2025, 6, 15, 11, 30, 0, tzinfo=datetime.UTC)


def test_next_cron_time_specific_hour():
    """Конкретный час — переход на следующий день."""
    after = datetime.datetime(2025, 6, 15, 10, 0, 0, tzinfo=datetime.UTC)
    result = next_cron_time("0 9 * * *", after)
    assert result == datetime.datetime(2025, 6, 16, 9, 0, 0, tzinfo=datetime.UTC)


def test_next_cron_time_same_hour_future_minute():
    """Тот же час, минута ещё впереди."""
    after = datetime.datetime(2025, 6, 15, 9, 0, 0, tzinfo=datetime.UTC)
    result = next_cron_time("30 9 * * *", after)
    assert result == datetime.datetime(2025, 6, 15, 9, 30, 0, tzinfo=datetime.UTC)


def test_next_cron_time_weekday_filter():
    """Фильтрация по дню недели (понедельник)."""
    after = datetime.datetime(2025, 6, 15, 0, 0, 0, tzinfo=datetime.UTC)  # воскресенье
    result = next_cron_time("0 9 * * mon", after)
    assert result == datetime.datetime(2025, 6, 16, 9, 0, 0, tzinfo=datetime.UTC)
    assert result.weekday() == 0


def test_next_cron_time_month_skip():
    """Переход через месяц если текущий не подходит."""
    after = datetime.datetime(2025, 6, 15, 0, 0, 0, tzinfo=datetime.UTC)
    result = next_cron_time("0 0 1 dec *", after)
    assert result == datetime.datetime(2025, 12, 1, 0, 0, 0, tzinfo=datetime.UTC)


def test_next_cron_time_year_wrap():
    """Переход через год."""
    after = datetime.datetime(2025, 12, 31, 23, 59, 0, tzinfo=datetime.UTC)
    result = next_cron_time("0 0 1 jan *", after)
    assert result == datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)


def test_next_cron_time_step_minutes():
    """Каждые 15 минут."""
    after = datetime.datetime(2025, 6, 15, 10, 16, 0, tzinfo=datetime.UTC)
    result = next_cron_time("*/15 * * * *", after)
    assert result == datetime.datetime(2025, 6, 15, 10, 30, 0, tzinfo=datetime.UTC)


def test_next_cron_time_complex_expression():
    """Сложное выражение: 9:00 и 18:00 в будни."""
    after = datetime.datetime(2025, 6, 13, 18, 0, 0, tzinfo=datetime.UTC)  # пятница 18:00
    result = next_cron_time("0 9,18 * * mon-fri", after)
    assert result == datetime.datetime(2025, 6, 16, 9, 0, 0, tzinfo=datetime.UTC)
    assert result.weekday() == 0


def test_next_cron_time_naive_datetime():
    """Наивный datetime трактуется как UTC."""
    after = datetime.datetime(2025, 6, 15, 10, 30, 0)
    result = next_cron_time("* * * * *", after)
    assert result.tzinfo == datetime.UTC
    assert result == datetime.datetime(2025, 6, 15, 10, 31, 0, tzinfo=datetime.UTC)


def test_next_cron_time_default_after():
    """Без указания after — от текущего времени."""
    result = next_cron_time("* * * * *")
    now = datetime.datetime.now(datetime.UTC)
    assert result > now - datetime.timedelta(seconds=1)
    assert result <= now + datetime.timedelta(minutes=2)


def test_next_cron_time_day_31():
    """День 31 — пропуск месяцев с меньшим числом дней."""
    after = datetime.datetime(2025, 6, 30, 0, 0, 0, tzinfo=datetime.UTC)
    result = next_cron_time("0 0 31 * *", after)
    assert result.day == 31
    assert result == datetime.datetime(2025, 7, 31, 0, 0, 0, tzinfo=datetime.UTC)


def test_next_cron_time_feb_29_leap_year():
    """29 февраля — только в високосный год."""
    after = datetime.datetime(2027, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)
    result = next_cron_time("0 0 29 feb *", after)
    assert result == datetime.datetime(2028, 2, 29, 0, 0, 0, tzinfo=datetime.UTC)
