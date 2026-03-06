"""
Тесты для атрибута extra в командах
"""

import pytest
from vkflow import commands
from vkflow.commands.command import Command as BaseCommand


def test_base_command_has_extra_attribute():
    """Проверка, что базовая команда имеет атрибут extra"""

    async def handler():
        pass

    cmd = BaseCommand(handler=handler, names=["test"])
    assert hasattr(cmd, "extra")
    assert isinstance(cmd.extra, dict)
    assert cmd.extra == {}


def test_ext_command_has_extra_attribute():
    """Проверка, что команда из ext.commands имеет атрибут extra"""

    @commands.command()
    async def test_cmd(ctx: commands.Context):
        pass

    assert hasattr(test_cmd, "extra")
    assert isinstance(test_cmd.extra, dict)
    assert test_cmd.extra == {}


def test_extra_can_store_data():
    """Проверка, что в extra можно сохранять данные"""

    @commands.command()
    async def test_cmd(ctx: commands.Context):
        pass

    test_cmd.extra["key1"] = "value1"
    test_cmd.extra["key2"] = 42
    test_cmd.extra["key3"] = {"nested": "dict"}

    assert test_cmd.extra["key1"] == "value1"
    assert test_cmd.extra["key2"] == 42
    assert test_cmd.extra["key3"] == {"nested": "dict"}


def test_context_has_extra_property():
    """Проверка, что Context имеет свойство extra"""

    @commands.command()
    async def test_cmd(ctx: commands.Context):
        pass

    test_cmd.extra["test_key"] = "test_value"

    # Создаем мок для NewMessage
    from unittest.mock import Mock

    mock_message = Mock()

    # Создаем Context
    ctx = commands.Context.from_message(mock_message, command=test_cmd, prefix="/", invoked_with="test_cmd")

    assert hasattr(ctx, "extra")
    assert ctx.extra == test_cmd.extra
    assert ctx.extra["test_key"] == "test_value"


def test_context_extra_returns_empty_dict_without_command():
    """Проверка, что ctx.extra возвращает пустой словарь, если команда не установлена"""
    from unittest.mock import Mock

    mock_message = Mock()

    ctx = commands.Context.from_message(mock_message)

    assert ctx.extra == {}


def test_multiple_commands_have_separate_extra():
    """Проверка, что у разных команд отдельные словари extra"""

    @commands.command()
    async def cmd1(ctx: commands.Context):
        pass

    @commands.command()
    async def cmd2(ctx: commands.Context):
        pass

    cmd1.extra["key"] = "value1"
    cmd2.extra["key"] = "value2"

    assert cmd1.extra["key"] == "value1"
    assert cmd2.extra["key"] == "value2"


@pytest.mark.asyncio
async def test_extra_accessible_in_command_handler():
    """Проверка, что extra доступен внутри обработчика команды"""
    executed = False
    extra_value = None

    @commands.command()
    async def test_cmd(ctx: commands.Context):
        nonlocal executed, extra_value
        executed = True
        extra_value = ctx.extra.get("test_key")

    test_cmd.extra["test_key"] = "expected_value"

    # Создаем мок для NewMessage
    from unittest.mock import Mock

    mock_message = Mock()
    mock_message.msg = Mock()
    mock_message.msg.text = "test"
    mock_message.msg.from_id = 123
    mock_message.msg.peer_id = 456
    mock_message.bot = Mock()
    mock_message.api = Mock()

    # Создаем Context
    ctx = commands.Context.from_message(mock_message, command=test_cmd, prefix="/", invoked_with="test_cmd")

    # Вызываем обработчик
    await test_cmd.handler(ctx)

    assert executed
    assert extra_value == "expected_value"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
