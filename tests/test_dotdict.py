import copy
import pytest

from vkflow.utils.dotdict import DotDict, wrap_response


class TestDotDict:
    """Тесты для класса DotDict."""

    def test_isinstance_dict(self):
        """DotDict должен проходить проверку isinstance(obj, dict)."""
        d = DotDict({"key": "value"})
        assert isinstance(d, dict)

    def test_getattr(self):
        """Доступ к ключам через точку."""
        d = DotDict({"name": "Alice", "age": 25})
        assert d.name == "Alice"
        assert d.age == 25

    def test_getitem(self):
        """Доступ к ключам через квадратные скобки."""
        d = DotDict({"name": "Bob"})
        assert d["name"] == "Bob"

    def test_setattr(self):
        """Установка значений через точку."""
        d = DotDict()
        d.city = "Moscow"
        assert d.city == "Moscow"
        assert d["city"] == "Moscow"

    def test_setitem(self):
        """Установка значений через квадратные скобки."""
        d = DotDict()
        d["country"] = "Russia"
        assert d.country == "Russia"

    def test_delattr(self):
        """Удаление через точку."""
        d = DotDict({"key": "value"})
        del d.key
        assert "key" not in d

    def test_delitem(self):
        """Удаление через квадратные скобки."""
        d = DotDict({"key": "value"})
        del d["key"]
        with pytest.raises(AttributeError):
            _ = d.key

    def test_nested_dict(self):
        """Вложенные словари должны автоматически оборачиваться."""
        d = DotDict({"user": {"name": "Alice", "profile": {"age": 25}}})
        assert isinstance(d.user, DotDict)
        assert isinstance(d.user.profile, DotDict)
        assert d.user.name == "Alice"
        assert d.user.profile.age == 25

    def test_nested_list_with_dicts(self):
        """Словари в списках должны оборачиваться."""
        d = DotDict({"users": [{"name": "Alice"}, {"name": "Bob"}]})
        assert isinstance(d.users, list)
        assert isinstance(d.users[0], DotDict)
        assert d.users[0].name == "Alice"
        assert d.users[1].name == "Bob"

    def test_set_nested_dict(self):
        """Присваивание словаря должно его оборачивать."""
        d = DotDict()
        d.user = {"name": "Charlie"}
        assert isinstance(d.user, DotDict)
        assert d.user.name == "Charlie"

    def test_attribute_error(self):
        """Несуществующий ключ должен вызывать AttributeError."""
        d = DotDict({"key": "value"})
        with pytest.raises(AttributeError):
            _ = d.nonexistent

    def test_get_with_default(self):
        """Метод get() должен возвращать default для отсутствующих ключей."""
        d = DotDict({"key": "value"})
        assert d.get("key") == "value"
        assert d.get("missing") is None
        assert d.get("missing", "default") == "default"

    def test_update(self):
        """Метод update() должен оборачивать новые значения."""
        d = DotDict({"a": 1})
        d.update({"b": {"nested": True}})
        assert d.a == 1
        assert isinstance(d.b, DotDict)
        assert d.b.nested is True

    def test_setdefault(self):
        """Метод setdefault() должен работать корректно."""
        d = DotDict({"existing": "value"})
        assert d.setdefault("existing", "other") == "value"
        assert d.setdefault("new", {"nested": True}).nested is True

    def test_copy(self):
        """Копирование должно возвращать DotDict."""
        d = DotDict({"key": "value"})
        d_copy = d.copy()
        assert isinstance(d_copy, DotDict)
        assert d_copy.key == "value"

    def test_deepcopy(self):
        """Глубокое копирование должно работать."""
        d = DotDict({"user": {"name": "Alice"}})
        d_copy = copy.deepcopy(d)
        d_copy.user.name = "Bob"
        assert d.user.name == "Alice"  # Оригинал не изменился

    def test_to_dict(self):
        """Метод to_dict() должен возвращать обычный dict."""
        d = DotDict({"user": {"name": "Alice", "friends": [{"name": "Bob"}]}})
        result = d.to_dict()
        assert type(result) is dict
        assert type(result["user"]) is dict
        assert type(result["user"]["friends"][0]) is dict

    def test_repr(self):
        """Repr должен показывать имя класса."""
        d = DotDict({"key": "value"})
        assert "DotDict" in repr(d)

    def test_kwargs_init(self):
        """Инициализация через kwargs."""
        d = DotDict(name="Alice", age=25)
        assert d.name == "Alice"
        assert d.age == 25

    def test_mixed_init(self):
        """Инициализация через dict и kwargs."""
        d = DotDict({"a": 1}, b=2)
        assert d.a == 1
        assert d.b == 2

    def test_items_key_priority(self):
        """Ключ 'items' должен иметь приоритет над методом dict.items()."""
        d = DotDict({"items": [1, 2, 3], "count": 3})
        assert d.items == [1, 2, 3]
        # Для доступа к методу items() используем dict_items()
        assert list(d.dict_items()) == [("items", [1, 2, 3]), ("count", 3)]

    def test_keys_key_priority(self):
        """Ключ 'keys' должен иметь приоритет над методом dict.keys()."""
        d = DotDict({"keys": ["a", "b"], "value": 1})
        assert d.keys == ["a", "b"]
        assert list(d.dict_keys()) == ["keys", "value"]

    def test_values_key_priority(self):
        """Ключ 'values' должен иметь приоритет над методом dict.values()."""
        d = DotDict({"values": [10, 20], "name": "test"})
        assert d.values == [10, 20]
        assert list(d.dict_values()) == [[10, 20], "test"]

    def test_dict_methods_without_conflict(self):
        """Методы dict должны работать когда нет конфликта ключей."""
        d = DotDict({"name": "Alice", "age": 25})
        assert list(d.keys()) == ["name", "age"]
        assert list(d.values()) == ["Alice", 25]
        assert list(d.items()) == [("name", "Alice"), ("age", 25)]

    def test_iteration(self):
        """Итерация по ключам должна работать."""
        d = DotDict({"a": 1, "b": 2})
        keys = list(d)
        assert keys == ["a", "b"]

    def test_len(self):
        """len() должен работать."""
        d = DotDict({"a": 1, "b": 2, "c": 3})
        assert len(d) == 3

    def test_in_operator(self):
        """Оператор in должен работать."""
        d = DotDict({"key": "value"})
        assert "key" in d
        assert "missing" not in d


class TestWrapResponse:
    """Тесты для функции wrap_response."""

    def test_wrap_dict(self):
        """Словарь должен оборачиваться в DotDict."""
        result = wrap_response({"key": "value"})
        assert isinstance(result, DotDict)
        assert result.key == "value"

    def test_wrap_list_of_dicts(self):
        """Список словарей должен оборачиваться."""
        result = wrap_response([{"name": "Alice"}, {"name": "Bob"}])
        assert isinstance(result, list)
        assert isinstance(result[0], DotDict)
        assert result[0].name == "Alice"

    def test_wrap_primitive(self):
        """Примитивы должны возвращаться как есть."""
        assert wrap_response("string") == "string"
        assert wrap_response(123) == 123
        assert wrap_response(None) is None

    def test_wrap_nested(self):
        """Вложенные структуры должны обрабатываться."""
        data = {
            "items": [
                {"id": 1, "user": {"name": "Alice"}},
                {"id": 2, "user": {"name": "Bob"}},
            ],
            "count": 2,
        }
        result = wrap_response(data)
        assert result.count == 2
        assert result.items[0].user.name == "Alice"


class TestDotDictWithVKResponse:
    """Тесты эмулирующие реальные ответы VK API."""

    def test_users_get_response(self):
        """Эмуляция ответа users.get."""
        response = wrap_response(
            [
                {
                    "id": 1,
                    "first_name": "Павел",
                    "last_name": "Дуров",
                    "can_access_closed": True,
                    "is_closed": False,
                }
            ]
        )
        assert response[0].id == 1
        assert response[0].first_name == "Павел"
        assert response[0].is_closed is False

    def test_messages_get_history_response(self):
        """Эмуляция ответа messages.getHistory."""
        response = wrap_response(
            {
                "count": 2,
                "items": [
                    {
                        "id": 100,
                        "from_id": 1,
                        "text": "Привет!",
                        "attachments": [],
                    },
                    {
                        "id": 99,
                        "from_id": 2,
                        "text": "Как дела?",
                        "attachments": [{"type": "photo", "photo": {"id": 123}}],
                    },
                ],
            }
        )
        assert response.count == 2
        assert response.items[0].text == "Привет!"
        assert response.items[1].attachments[0].type == "photo"
        assert response.items[1].attachments[0].photo.id == 123

    def test_groups_get_by_id_response(self):
        """Эмуляция ответа groups.getById."""
        response = wrap_response(
            {
                "groups": [
                    {
                        "id": 1,
                        "name": "VK API",
                        "screen_name": "apiclub",
                        "is_closed": 0,
                        "type": "page",
                    }
                ]
            }
        )
        assert response.groups[0].name == "VK API"
        assert response.groups[0].screen_name == "apiclub"
