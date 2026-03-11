"""
Тесты для системы экспериментальных флагов
"""

import asyncio
import sys
import warnings

import pytest

from vkflow.app.experimental import ExperimentalFeature, validate_experiments


def test_validate_known_feature_enabled():
    """Известный флаг включается корректно"""
    result = validate_experiments({"eager_task_factory": True})
    assert result[ExperimentalFeature.EAGER_TASK_FACTORY] is True


def test_validate_known_feature_disabled():
    """Известный флаг можно явно отключить"""
    result = validate_experiments({"eager_task_factory": False})
    assert result[ExperimentalFeature.EAGER_TASK_FACTORY] is False


def test_validate_unknown_feature_warns():
    """Неизвестный ключ вызывает предупреждение и пропускается"""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = validate_experiments({"nonexistent_flag": True})

    assert len(w) == 1
    assert "Unknown experimental feature" in str(w[0].message)
    assert ExperimentalFeature.EAGER_TASK_FACTORY not in result


def test_validate_empty_dict():
    """Пустой словарь возвращает пустой результат"""
    result = validate_experiments({})
    assert result == {}


@pytest.mark.skipif(
    sys.version_info >= (3, 12),
    reason="Тест для Python < 3.12",
)
def test_validate_eager_warns_on_old_python():
    """eager_task_factory на Python < 3.12 выдаёт предупреждение и отключается"""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = validate_experiments({"eager_task_factory": True})

    assert result[ExperimentalFeature.EAGER_TASK_FACTORY] is False
    assert len(w) == 1
    assert "requires Python 3.12+" in str(w[0].message)


def test_experimental_feature_enum_values():
    """StrEnum содержит ожидаемые значения"""
    assert ExperimentalFeature.EAGER_TASK_FACTORY == "eager_task_factory"
    assert ExperimentalFeature("eager_task_factory") is ExperimentalFeature.EAGER_TASK_FACTORY


def test_validate_multiple_features():
    """Несколько флагов обрабатываются за один вызов"""
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        result = validate_experiments(
            {
                "eager_task_factory": True,
                "unknown_one": False,
            }
        )

    assert ExperimentalFeature.EAGER_TASK_FACTORY in result


def test_app_has_experiment_method():
    """App.has_experiment возвращает состояние флага"""
    from vkflow.app.bot import App

    app = App(experimental={"eager_task_factory": False})
    assert app.has_experiment("eager_task_factory") is False
    assert app.has_experiment(ExperimentalFeature.EAGER_TASK_FACTORY) is False


def test_app_has_experiment_default_false():
    """has_experiment возвращает False для невключённых флагов"""
    from vkflow.app.bot import App

    app = App()
    assert app.has_experiment("eager_task_factory") is False


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="eager_task_factory доступна только на Python 3.12+",
)
def test_apply_loop_experiments_sets_factory():
    """_apply_loop_experiments устанавливает eager_task_factory на loop"""
    from vkflow.app.bot import App

    app = App(experimental={"eager_task_factory": True})
    loop = asyncio.new_event_loop()

    try:
        app._apply_loop_experiments(loop)
        assert loop.get_task_factory() is asyncio.eager_task_factory
    finally:
        loop.close()


def test_apply_loop_experiments_noop_when_disabled():
    """_apply_loop_experiments не трогает loop при выключенном флаге"""
    from vkflow.app.bot import App

    app = App(experimental={"eager_task_factory": False})
    loop = asyncio.new_event_loop()

    try:
        app._apply_loop_experiments(loop)
        assert loop.get_task_factory() is None
    finally:
        loop.close()


def test_apply_loop_experiments_noop_when_empty():
    """_apply_loop_experiments не трогает loop без experimental"""
    from vkflow.app.bot import App

    app = App()
    loop = asyncio.new_event_loop()

    try:
        app._apply_loop_experiments(loop)
        assert loop.get_task_factory() is None
    finally:
        loop.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
