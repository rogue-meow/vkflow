from __future__ import annotations

import enum
import sys
import warnings


class ExperimentalFeature(enum.StrEnum):
    """Доступные экспериментальные возможности."""

    EAGER_TASK_FACTORY = "eager_task_factory"


_FEATURE_MIN_PYTHON: dict[ExperimentalFeature, tuple[int, int]] = {
    ExperimentalFeature.EAGER_TASK_FACTORY: (3, 12),
}


def validate_experiments(
    raw: dict[str, bool],
) -> dict[ExperimentalFeature, bool]:
    """Валидация и нормализация словаря экспериментов.

    Неизвестные ключи вызывают предупреждение и пропускаются.
    Флаги, чьи требования к версии Python не выполнены,
    вызывают предупреждение и принудительно отключаются.
    """
    result: dict[ExperimentalFeature, bool] = {}

    for key, enabled in raw.items():
        try:
            feature = ExperimentalFeature(key)
        except ValueError:
            warnings.warn(
                f"Unknown experimental feature: {key!r}. "
                f"Available: {[f.value for f in ExperimentalFeature]}",
                stacklevel=3,
            )
            continue

        if enabled:
            min_ver = _FEATURE_MIN_PYTHON.get(feature)
            if min_ver is not None and sys.version_info < min_ver:
                ver_str = ".".join(map(str, min_ver))
                warnings.warn(
                    f"Experimental feature {key!r} requires Python {ver_str}+, "
                    f"current: {sys.version_info.major}.{sys.version_info.minor}. "
                    f"Flag ignored.",
                    stacklevel=3,
                )
                enabled = False

        result[feature] = enabled

    return result
