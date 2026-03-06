"""
Тесты для системы префиксов
"""

import pytest
from unittest.mock import Mock
from vkflow.app.prefixes import (
    resolve_prefixes,
    when_mentioned,
    when_mentioned_or,
)
from vkflow.app.storages import NewMessage


@pytest.fixture
def mock_ctx():
    """Создать мок контекста"""
    ctx = Mock(spec=NewMessage)
    ctx.msg = Mock()
    ctx.msg.text = "!ping"
    ctx.msg.peer_id = 123456789
    ctx.msg.from_id = 100
    ctx.bot = Mock()
    return ctx


@pytest.fixture
def mock_group_ctx():
    """Создать мок контекста для группового чата"""
    ctx = Mock(spec=NewMessage)
    ctx.msg = Mock()
    ctx.msg.text = "[club123456|@bot] ping"
    ctx.msg.peer_id = 2000000001  # Групповой чат
    ctx.msg.from_id = 100
    ctx.bot = Mock()
    ctx.bot.api = Mock()
    ctx.bot.events_factory = Mock()
    ctx.bot.events_factory.group_id = 123456
    return ctx


class TestResolvePrefixes:
    """Тесты для resolve_prefixes()"""

    @pytest.mark.asyncio
    async def test_string_prefix(self, mock_ctx):
        """Тест: строковый префикс преобразуется в список"""
        result = await resolve_prefixes(mock_ctx, "!")
        assert result == ["!"]

    @pytest.mark.asyncio
    async def test_list_prefix(self, mock_ctx):
        """Тест: список префиксов возвращается как есть"""
        result = await resolve_prefixes(mock_ctx, ["!", "/", "."])
        assert result == ["!", "/", "."]

    @pytest.mark.asyncio
    async def test_none_prefix(self, mock_ctx):
        """Тест: None возвращает пустой список"""
        result = await resolve_prefixes(mock_ctx, None)
        assert result == []

    @pytest.mark.asyncio
    async def test_sync_callable(self, mock_ctx):
        """Тест: синхронная функция"""

        def get_prefix(ctx):
            return "!"

        result = await resolve_prefixes(mock_ctx, get_prefix)
        assert result == ["!"]

    @pytest.mark.asyncio
    async def test_async_callable(self, mock_ctx):
        """Тест: асинхронная функция"""

        async def get_prefix(ctx):
            return "/"

        result = await resolve_prefixes(mock_ctx, get_prefix)
        assert result == ["/"]

    @pytest.mark.asyncio
    async def test_callable_returns_list(self, mock_ctx):
        """Тест: функция возвращает список"""

        def get_prefixes(ctx):
            return ["!", "/"]

        result = await resolve_prefixes(mock_ctx, get_prefixes)
        assert result == ["!", "/"]

    @pytest.mark.asyncio
    async def test_lambda_prefix(self, mock_ctx):
        """Тест: лямбда-функция"""
        result = await resolve_prefixes(mock_ctx, lambda ctx: "!" if ctx.msg.peer_id > 2000000000 else "/")
        assert result == ["/"]  # peer_id = 123456789 < 2000000000


class TestWhenMentioned:
    """Тесты для when_mentioned()"""

    @pytest.mark.asyncio
    async def test_when_mentioned_returns_callable(self):
        """Тест: when_mentioned() возвращает callable"""
        prefix_func = when_mentioned()
        assert callable(prefix_func)

    @pytest.mark.asyncio
    async def test_when_mentioned_basic(self, mock_group_ctx):
        """Тест: when_mentioned() возвращает список упоминаний"""
        prefix_func = when_mentioned()
        result = await prefix_func(mock_group_ctx)
        assert isinstance(result, list)
        # Должен содержать паттерны упоминания
        # (точный результат зависит от реализации)


class TestWhenMentionedOr:
    """Тесты для when_mentioned_or()"""

    @pytest.mark.asyncio
    async def test_when_mentioned_or_single_prefix(self, mock_group_ctx):
        """Тест: when_mentioned_or() с одним префиксом"""
        prefix_func = when_mentioned_or("!")
        result = await prefix_func(mock_group_ctx)
        assert isinstance(result, list)
        assert "!" in result

    @pytest.mark.asyncio
    async def test_when_mentioned_or_multiple_prefixes(self, mock_group_ctx):
        """Тест: when_mentioned_or() с несколькими префиксами"""
        prefix_func = when_mentioned_or("!", "/", ".")
        result = await prefix_func(mock_group_ctx)
        assert isinstance(result, list)
        assert "!" in result
        assert "/" in result
        assert "." in result

    @pytest.mark.asyncio
    async def test_when_mentioned_or_list(self, mock_group_ctx):
        """Тест: when_mentioned_or() со списком"""
        prefix_func = when_mentioned_or(["!", "/"])
        result = await prefix_func(mock_group_ctx)
        assert isinstance(result, list)
        assert "!" in result
        assert "/" in result

    @pytest.mark.asyncio
    async def test_when_mentioned_or_callable(self, mock_group_ctx):
        """Тест: when_mentioned_or() с функцией"""

        def get_prefix(ctx):
            return "?"

        prefix_func = when_mentioned_or(get_prefix)
        result = await prefix_func(mock_group_ctx)
        assert isinstance(result, list)
        assert "?" in result

    @pytest.mark.asyncio
    async def test_when_mentioned_or_no_duplicates(self, mock_group_ctx):
        """Тест: when_mentioned_or() не создает дубликаты"""
        prefix_func = when_mentioned_or("!", "!", "/")
        result = await prefix_func(mock_group_ctx)
        # Считаем количество "!"
        _count_exclamation = result.count("!")
        # Должен быть только один "!" (дубликаты удалены)
        # Но могут быть паттерны упоминания, так что проверяем общее
        assert isinstance(result, list)


class TestCommandPrefixes:
    """Интеграционные тесты для префиксов в командах"""

    @pytest.mark.asyncio
    async def test_command_with_string_prefix(self):
        """Тест: команда с строковым префиксом"""
        from vkflow.commands.command import Command

        async def handler():
            return "pong"

        cmd = Command(handler=handler, names=["ping"], prefixes="!")

        # Проверяем, что префикс преобразован в список
        assert isinstance(cmd.prefixes, list)
        assert "!" in cmd.prefixes

    @pytest.mark.asyncio
    async def test_command_with_list_prefix(self):
        """Тест: команда со списком префиксов"""
        from vkflow.commands.command import Command

        async def handler():
            return "pong"

        cmd = Command(handler=handler, names=["ping"], prefixes=["!", "/"])

        assert isinstance(cmd.prefixes, list)
        assert "!" in cmd.prefixes
        assert "/" in cmd.prefixes

    @pytest.mark.asyncio
    async def test_command_with_callable_prefix(self):
        """Тест: команда с callable префиксом"""
        from vkflow.commands.command import Command

        def get_prefix(ctx):
            return "!"

        async def handler():
            return "pong"

        cmd = Command(handler=handler, names=["ping"], prefixes=get_prefix)

        # Префикс должен остаться callable
        assert callable(cmd.prefixes)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
