"""
Тесты для SQLiteStorage (FSM)
"""

import time
import warnings

import pytest
import pytest_asyncio

from vkflow.app.fsm.storage.sqlite import SQLiteStorage


@pytest_asyncio.fixture
async def storage():
    s = SQLiteStorage(":memory:")
    yield s
    await s.close()


@pytest_asyncio.fixture
async def storage_ttl():
    s = SQLiteStorage(":memory:", ttl=1.0)
    yield s
    await s.close()


KEY = "fsm:123:456"


@pytest.mark.asyncio
async def test_get_state_empty(storage):
    """Пустое хранилище возвращает None"""
    assert await storage.get_state(KEY) is None


@pytest.mark.asyncio
async def test_set_and_get_state(storage):
    """set_state сохраняет, get_state возвращает"""
    await storage.set_state(KEY, "OrderStates:waiting_name")
    assert await storage.get_state(KEY) == "OrderStates:waiting_name"


@pytest.mark.asyncio
async def test_delete_state(storage):
    """delete_state убирает состояние"""
    await storage.set_state(KEY, "some_state")
    await storage.delete_state(KEY)
    assert await storage.get_state(KEY) is None


@pytest.mark.asyncio
async def test_get_data_empty(storage):
    """Пустое хранилище возвращает пустой dict"""
    assert await storage.get_data(KEY) == {}


@pytest.mark.asyncio
async def test_set_and_get_data(storage):
    """set_data сохраняет, get_data возвращает"""
    await storage.set_data(KEY, {"name": "Test", "age": 25})
    data = await storage.get_data(KEY)
    assert data == {"name": "Test", "age": 25}


@pytest.mark.asyncio
async def test_update_data(storage):
    """update_data мержит данные и возвращает полный dict"""
    await storage.set_data(KEY, {"name": "Test"})
    result = await storage.update_data(KEY, age=25)
    assert result == {"name": "Test", "age": 25}


@pytest.mark.asyncio
async def test_update_data_empty(storage):
    """update_data на пустом ключе создаёт данные"""
    result = await storage.update_data(KEY, name="Test")
    assert result == {"name": "Test"}


@pytest.mark.asyncio
async def test_delete_data(storage):
    """delete_data очищает данные"""
    await storage.set_data(KEY, {"name": "Test"})
    await storage.delete_data(KEY)
    assert await storage.get_data(KEY) == {}


@pytest.mark.asyncio
async def test_clear(storage):
    """clear удаляет и состояние и данные"""
    await storage.set_state(KEY, "some_state")
    await storage.set_data(KEY, {"name": "Test"})
    await storage.clear(KEY)
    assert await storage.get_state(KEY) is None
    assert await storage.get_data(KEY) == {}


@pytest.mark.asyncio
async def test_state_overwrite(storage):
    """Повторный set_state перезаписывает состояние"""
    await storage.set_state(KEY, "state1")
    await storage.set_state(KEY, "state2")
    assert await storage.get_state(KEY) == "state2"


@pytest.mark.asyncio
async def test_data_overwrite(storage):
    """set_data полностью заменяет данные"""
    await storage.set_data(KEY, {"a": 1, "b": 2})
    await storage.set_data(KEY, {"c": 3})
    assert await storage.get_data(KEY) == {"c": 3}


@pytest.mark.asyncio
async def test_multiple_keys(storage):
    """Разные ключи изолированы друг от друга"""
    key1, key2 = "fsm:1:100", "fsm:2:200"
    await storage.set_state(key1, "state_a")
    await storage.set_state(key2, "state_b")
    await storage.set_data(key1, {"x": 1})
    await storage.set_data(key2, {"y": 2})

    assert await storage.get_state(key1) == "state_a"
    assert await storage.get_state(key2) == "state_b"
    assert await storage.get_data(key1) == {"x": 1}
    assert await storage.get_data(key2) == {"y": 2}


@pytest.mark.asyncio
async def test_get_states_count(storage):
    """get_states_count считает только активные состояния"""
    assert await storage.get_states_count() == 0
    await storage.set_state("fsm:1:1", "s1")
    await storage.set_state("fsm:2:2", "s2")
    assert await storage.get_states_count() == 2
    await storage.delete_state("fsm:1:1")
    assert await storage.get_states_count() == 1


@pytest.mark.asyncio
async def test_get_keys(storage):
    """get_keys возвращает ключи с активными состояниями"""
    await storage.set_state("fsm:1:1", "s1")
    await storage.set_state("fsm:2:2", "s2")
    keys = await storage.get_keys()
    assert sorted(keys) == ["fsm:1:1", "fsm:2:2"]


@pytest.mark.asyncio
async def test_get_keys_excludes_deleted(storage):
    """get_keys не включает ключи без состояния"""
    await storage.set_state(KEY, "s1")
    await storage.delete_state(KEY)
    assert await storage.get_keys() == []


@pytest.mark.asyncio
async def test_ttl_state_expired(storage_ttl, monkeypatch):
    """Просроченное состояние возвращает None"""
    await storage_ttl.set_state(KEY, "some_state")
    original = time.time()
    monkeypatch.setattr(time, "time", lambda: original + 2.0)
    assert await storage_ttl.get_state(KEY) is None


@pytest.mark.asyncio
async def test_ttl_data_expired(storage_ttl, monkeypatch):
    """Просроченные данные возвращают пустой dict"""
    await storage_ttl.set_data(KEY, {"name": "Test"})
    original = time.time()
    monkeypatch.setattr(time, "time", lambda: original + 2.0)
    assert await storage_ttl.get_data(KEY) == {}


@pytest.mark.asyncio
async def test_ttl_state_not_expired(storage_ttl):
    """Непросроченное состояние возвращается нормально"""
    await storage_ttl.set_state(KEY, "some_state")
    assert await storage_ttl.get_state(KEY) == "some_state"


@pytest.mark.asyncio
async def test_cleanup_removes_expired(storage_ttl, monkeypatch):
    """cleanup удаляет просроченные записи"""
    await storage_ttl.set_state("fsm:1:1", "s1")
    await storage_ttl.set_state("fsm:2:2", "s2")
    original = time.time()
    monkeypatch.setattr(time, "time", lambda: original + 2.0)
    removed = await storage_ttl.cleanup()
    assert removed == 2
    assert await storage_ttl.get_states_count() == 0


@pytest.mark.asyncio
async def test_cleanup_no_ttl(storage):
    """cleanup без TTL возвращает 0"""
    await storage.set_state(KEY, "state")
    assert await storage.cleanup() == 0


@pytest.mark.asyncio
async def test_close_and_reopen():
    """После close повторный доступ пересоздаёт соединение"""
    storage = SQLiteStorage(":memory:")
    await storage.set_state(KEY, "state")
    await storage.close()
    assert storage._connection is None


@pytest.mark.asyncio
async def test_context_manager():
    """async with автоматически закрывает соединение"""
    async with SQLiteStorage(":memory:") as storage:
        await storage.set_state(KEY, "state")
        assert await storage.get_state(KEY) == "state"
    assert storage._connection is None


@pytest.mark.asyncio
async def test_set_data_without_state(storage):
    """Данные можно сохранить без установки состояния"""
    await storage.set_data(KEY, {"key": "value"})
    assert await storage.get_state(KEY) is None
    assert await storage.get_data(KEY) == {"key": "value"}


@pytest.mark.asyncio
async def test_state_and_data_independent(storage):
    """delete_state не удаляет данные и наоборот"""
    await storage.set_state(KEY, "state")
    await storage.set_data(KEY, {"key": "value"})

    await storage.delete_state(KEY)
    assert await storage.get_state(KEY) is None
    assert await storage.get_data(KEY) == {"key": "value"}


@pytest.mark.asyncio
async def test_sync_fallback(monkeypatch):
    """Fallback на синхронный sqlite3 при отсутствии aiosqlite"""
    import vkflow.app.fsm.storage.sqlite as sqlite_mod

    monkeypatch.setattr(sqlite_mod, "_HAS_AIOSQLITE", False)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        s = SQLiteStorage(":memory:")
        assert len(w) == 1
        assert "aiosqlite не установлен" in str(w[0].message)

    await s.set_state(KEY, "test_state")
    assert await s.get_state(KEY) == "test_state"

    await s.set_data(KEY, {"x": 42})
    assert await s.get_data(KEY) == {"x": 42}

    await s.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
