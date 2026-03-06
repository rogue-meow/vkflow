from __future__ import annotations

import typing


class DotDict(dict):
    """
    Словарь с поддержкой доступа к ключам через атрибуты (точку).

    Позволяет обращаться к ключам как через `obj["key"]`, так и через `obj.key`.
    При этом `isinstance(obj, dict)` возвращает `True`.

    Вложенные словари автоматически оборачиваются в `DotDict`,
    а списки с вложенными словарями также обрабатываются рекурсивно.

    Examples:
        ```python
        data = DotDict({"user": {"name": "Alice", "age": 25}})
        data.user.name   # 'Alice'
        data["user"]["age"]  # 25
        data.user.city = "Moscow"
        data.user.city   # 'Moscow'
        isinstance(data, dict)  # True
        ```
    """

    def __init__(self, data: dict[str, typing.Any] | None = None, **kwargs: typing.Any) -> None:
        if data is None:
            data = {}
        data.update(kwargs)

        for key, value in data.items():
            data[key] = self._wrap(value)

        super().__init__(data)

    @classmethod
    def _wrap(cls, value: typing.Any) -> typing.Any:
        if isinstance(value, dict) and not isinstance(value, DotDict):
            return cls(value)
        if isinstance(value, list):
            return [cls._wrap(item) for item in value]
        return value

    def __getattribute__(self, key: str) -> typing.Any:
        if key.startswith("_"):
            return super().__getattribute__(key)

        try:
            if key in self:
                return self[key]
        except (TypeError, RecursionError):
            pass

        return super().__getattribute__(key)

    def __setattr__(self, key: str, value: typing.Any) -> None:
        self[key] = self._wrap(value)

    def __delattr__(self, key: str) -> None:
        try:
            del self[key]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{key}'") from None

    def __repr__(self) -> str:
        return f"{type(self).__name__}({super().__repr__()})"

    def dict_keys(self):
        """Аналог dict.keys() -используется когда в словаре есть ключ "keys"."""
        return dict.keys(self)

    def dict_values(self):
        """Аналог dict.values() -используется когда в словаре есть ключ "values"."""
        return dict.values(self)

    def dict_items(self):
        """Аналог dict.items() -используется когда в словаре есть ключ "items"."""
        return dict.items(self)

    def to_dict(self) -> dict[str, typing.Any]:
        result = {}
        for key, value in self.items():
            if isinstance(value, DotDict):
                result[key] = value.to_dict()
            elif isinstance(value, list):
                result[key] = [item.to_dict() if isinstance(item, DotDict) else item for item in value]
            else:
                result[key] = value
        return result

    def get(self, key: str, default: typing.Any = None) -> typing.Any:
        try:
            return self[key]
        except KeyError:
            return default

    def update(self, other: dict[str, typing.Any] | None = None, **kwargs: typing.Any) -> None:
        if other:
            for key, value in other.items():
                self[key] = self._wrap(value)
        for key, value in kwargs.items():
            self[key] = self._wrap(value)

    def setdefault(self, key: str, default: typing.Any = None) -> typing.Any:
        if key not in self:
            self[key] = self._wrap(default)
        return self[key]

    def copy(self) -> DotDict:
        return type(self)(dict.copy(self))

    def __copy__(self) -> DotDict:
        return self.copy()

    def __deepcopy__(self, memo: dict) -> DotDict:
        import copy

        return type(self)(copy.deepcopy(dict(self), memo))


def wrap_response(data: typing.Any) -> typing.Any:
    """
    Оборачивает ответ API в DotDict.

    Если data является словарём -возвращает DotDict.
    Если data является списком -рекурсивно обрабатывает элементы.
    Иначе -возвращает данные как есть.
    """
    if isinstance(data, dict):
        return DotDict(data)
    if isinstance(data, list):
        return [wrap_response(item) for item in data]
    return data
