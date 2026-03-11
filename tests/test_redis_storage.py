"""Тесты для RedisStorage (FSM)"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import pytest_asyncio

from vkflow.app.fsm.storage.redis import RedisStorage


class FakeRedis:
    """Имитация redis.asyncio.Redis на основе словаря."""

    def __init__(self):
        self._store: dict[str, dict[str, str]] = {}
        self._ttls: dict[str, int] = {}

    async def hget(self, name, key):
        h = self._store.get(name if isinstance(name, str) else name.decode())
        if h is None:
            return None
        val = h.get(key)
        if val is None:
            return None
        return val.encode()

    async def hset(self, name, key, value):
        name = name if isinstance(name, str) else name.decode()
        if name not in self._store:
            self._store[name] = {}
        self._store[name][key] = value if isinstance(value, str) else value.decode()

    async def hdel(self, name, *keys):
        name = name if isinstance(name, str) else name.decode()
        h = self._store.get(name)
        if h is None:
            return 0
        removed = 0
        for key in keys:
            if key in h:
                del h[key]
                removed += 1
        return removed

    async def hexists(self, name, key):
        name = name if isinstance(name, str) else name.decode()
        h = self._store.get(name)
        return h is not None and key in h

    async def expire(self, name, ttl):
        name = name if isinstance(name, str) else name.decode()
        self._ttls[name] = ttl
        return True

    async def scan_iter(self, match=None):
        pattern_prefix = match.rstrip("*") if match else ""
        for key in list(self._store):
            if key.startswith(pattern_prefix):
                yield key.encode()

    async def aclose(self):
        self._store.clear()


@pytest_asyncio.fixture
async def fake_redis():
    return FakeRedis()


@pytest_asyncio.fixture
async def storage(fake_redis):
    s = RedisStorage(client=fake_redis)
    yield s
    await s.close()


@pytest_asyncio.fixture
async def storage_ttl(fake_redis):
    s = RedisStorage(client=fake_redis, ttl=3600)
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
async def test_ttl_applied_on_set_state(storage_ttl, fake_redis):
    """set_state устанавливает TTL через EXPIRE"""
    await storage_ttl.set_state(KEY, "some_state")
    redis_key = f"vkflow:fsm:{KEY}"
    assert fake_redis._ttls.get(redis_key) == 3600


@pytest.mark.asyncio
async def test_ttl_applied_on_set_data(storage_ttl, fake_redis):
    """set_data устанавливает TTL через EXPIRE"""
    await storage_ttl.set_data(KEY, {"name": "Test"})
    redis_key = f"vkflow:fsm:{KEY}"
    assert fake_redis._ttls.get(redis_key) == 3600


@pytest.mark.asyncio
async def test_no_ttl_without_config(storage, fake_redis):
    """Без TTL EXPIRE не вызывается"""
    await storage.set_state(KEY, "state")
    redis_key = f"vkflow:fsm:{KEY}"
    assert redis_key not in fake_redis._ttls


@pytest.mark.asyncio
async def test_custom_prefix():
    """Кастомный префикс используется в ключах"""
    fake = FakeRedis()
    s = RedisStorage(client=fake, prefix="mybot:")
    await s.set_state("user:1", "state1")
    assert "mybot:user:1" in fake._store
    await s.close()


@pytest.mark.asyncio
async def test_close_own_client():
    """close() закрывает соединение, созданное хранилищем"""
    fake = FakeRedis()
    s = RedisStorage.__new__(RedisStorage)
    s._url = "redis://localhost"
    s._ttl = None
    s._prefix = "vkflow:fsm:"
    s._client = fake
    s._owns_client = True
    await s.close()
    assert s._client is None


@pytest.mark.asyncio
async def test_close_external_client(fake_redis):
    """close() НЕ закрывает внешний клиент"""
    s = RedisStorage(client=fake_redis)
    await s.close()
    assert s._client is not None


@pytest.mark.asyncio
async def test_context_manager():
    """async with автоматически закрывает соединение"""
    fake = FakeRedis()
    s = RedisStorage.__new__(RedisStorage)
    s._url = "redis://localhost"
    s._ttl = None
    s._prefix = "vkflow:fsm:"
    s._client = fake
    s._owns_client = True

    async with s as storage:
        await storage.set_state(KEY, "state")
        assert await storage.get_state(KEY) == "state"
    assert s._client is None


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


def test_no_redis_raises():
    """При отсутствии redis выбрасывается RuntimeError"""
    with (
        patch("vkflow.app.fsm.storage.redis._HAS_REDIS", False),
        pytest.raises(RuntimeError, match="redis"),
    ):
        RedisStorage()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
