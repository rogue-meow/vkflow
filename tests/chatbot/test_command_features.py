"""
Тесты для новых фич команд:
1. Значения по умолчанию для аргументов
2. Обработка ошибок через @command.on_error
"""

import contextlib

import pytest
import inspect
from vkflow.commands.command import Command
from vkflow.commands.parsing.adapters import resolve_typing


def test_default_value_creates_optional():
    """Проверяет, что параметр с default=None становится опциональным"""

    async def test_func(value: int | None = None):
        pass

    sig = inspect.signature(test_func)
    param = sig.parameters["value"]
    result = resolve_typing(param)

    # Проверяем, что создан OptionalCutter
    from vkflow.commands.parsing.cutters import OptionalCutter

    assert isinstance(result.cutter, OptionalCutter)
    assert result.argument_settings.default is None


def test_default_value_non_none():
    """Проверяет, что параметр с default=10 становится опциональным"""

    async def test_func(value: int = 10):
        pass

    sig = inspect.signature(test_func)
    param = sig.parameters["value"]
    result = resolve_typing(param)

    # Проверяем, что создан OptionalCutter
    from vkflow.commands.parsing.cutters import OptionalCutter

    assert isinstance(result.cutter, OptionalCutter)
    assert result.argument_settings.default == 10


def test_no_default_not_optional():
    """Проверяет, что параметр без default НЕ становится опциональным"""

    async def test_func(value: int):
        pass

    sig = inspect.signature(test_func)
    param = sig.parameters["value"]
    result = resolve_typing(param)

    # Проверяем, что НЕ создан OptionalCutter
    from vkflow.commands.parsing.cutters import OptionalCutter, IntegerCutter

    assert not isinstance(result.cutter, OptionalCutter)
    assert isinstance(result.cutter, IntegerCutter)


def test_command_has_error_handler_attributes():
    """Проверяет, что команда имеет атрибуты для error handlers"""

    async def test_handler():
        pass

    cmd = Command(handler=test_handler, names=["test"])

    assert hasattr(cmd, "_error_handlers")
    assert isinstance(cmd._error_handlers, list)
    assert len(cmd._error_handlers) == 0


def test_on_error_decorator():
    """Проверяет, что декоратор on_error регистрирует обработчик"""

    async def test_handler():
        pass

    cmd = Command(handler=test_handler, names=["test"])

    async def error_handler(ctx, error):
        pass

    # Используем декоратор
    decorator = cmd.on_error()
    result = decorator(error_handler)

    assert len(cmd._error_handlers) == 1
    assert cmd._error_handlers[0][0] is error_handler
    assert cmd._error_handlers[0][1] is None  # catch-all handler
    assert result is error_handler


def test_on_error_with_types():
    """Проверяет, что декоратор on_error принимает типы ошибок"""

    async def test_handler():
        pass

    cmd = Command(handler=test_handler, names=["test"])

    async def error_handler(ctx, error):
        pass

    # Используем декоратор с типами
    decorator = cmd.on_error(ValueError, TypeError)
    result = decorator(error_handler)

    assert len(cmd._error_handlers) == 1
    assert cmd._error_handlers[0][0] is error_handler
    assert cmd._error_handlers[0][1] == (ValueError, TypeError)
    assert result is error_handler


@pytest.mark.asyncio
async def test_error_handler_called():
    """Проверяет, что error handler вызывается при ошибке"""
    import unittest.mock

    error_handled = False
    caught_error = None

    async def test_handler():
        raise ValueError("Test error")

    cmd = Command(handler=test_handler, names=["test"])

    async def error_handler(error):
        nonlocal error_handled, caught_error
        error_handled = True
        caught_error = error

    cmd.on_error(ValueError)(error_handler)

    # Создаем мок для ctx (spec=[] чтобы не было ложных атрибутов вроде app)
    mock_ctx = unittest.mock.Mock(spec=[])

    # Вызываем handler через _call_handler
    with contextlib.suppress(Exception):
        await cmd._call_handler(mock_ctx, {})

    # Проверяем, что error handler был вызван
    assert error_handled
    assert isinstance(caught_error, ValueError)
    assert str(caught_error) == "Test error"


@pytest.mark.asyncio
async def test_error_handler_not_called_for_wrong_type():
    """Проверяет, что error handler НЕ вызывается для неподходящего типа ошибки"""
    import unittest.mock

    error_handled = False

    async def test_handler():
        raise TypeError("Test error")

    cmd = Command(handler=test_handler, names=["test"])

    async def error_handler(error):
        nonlocal error_handled
        error_handled = True

    # Регистрируем обработчик только для ValueError
    cmd.on_error(ValueError)(error_handler)

    mock_ctx = unittest.mock.Mock()

    # Должно выброситься исключение, т.к. TypeError не обрабатывается
    with pytest.raises(TypeError):
        await cmd._call_handler(mock_ctx, {})

    # Проверяем, что error handler НЕ был вызван
    assert not error_handled


def test_string_default_value():
    """Проверяет работу с дефолтными строковыми значениями"""

    async def test_func(name: str = "default"):
        pass

    sig = inspect.signature(test_func)
    param = sig.parameters["name"]
    result = resolve_typing(param)

    from vkflow.commands.parsing.cutters import OptionalCutter

    assert isinstance(result.cutter, OptionalCutter)
    assert result.argument_settings.default == "default"


def test_multiple_defaults():
    """Проверяет работу с несколькими параметрами с дефолтными значениями"""

    async def test_func(name: str = "user", age: int = 18, active: bool = True):
        pass

    sig = inspect.signature(test_func)

    # Проверяем каждый параметр
    from vkflow.commands.parsing.cutters import OptionalCutter

    param_name = sig.parameters["name"]
    result_name = resolve_typing(param_name)
    assert isinstance(result_name.cutter, OptionalCutter)
    assert result_name.argument_settings.default == "user"

    param_age = sig.parameters["age"]
    result_age = resolve_typing(param_age)
    assert isinstance(result_age.cutter, OptionalCutter)
    assert result_age.argument_settings.default == 18

    param_active = sig.parameters["active"]
    result_active = resolve_typing(param_active)
    assert isinstance(result_active.cutter, OptionalCutter)
    assert result_active.argument_settings.default is True


def test_error_handler_binding_in_cog():
    """Проверяет, что error handlers корректно bind'ятся при использовании в Cog"""

    # Создаем mock класс для имитации Cog
    class MockCog:
        pass

    async def test_handler(self):
        raise ValueError("Test error")

    async def error_handler(self, error):
        pass

    # Создаем команду
    cmd = Command(handler=test_handler, names=["test"])
    cmd.on_error(ValueError)(error_handler)

    # Проверяем, что error handler установлен
    assert len(cmd._error_handlers) == 1
    assert cmd._error_handlers[0][0] is error_handler

    # Создаем экземпляр Cog
    cog_instance = MockCog()

    # Получаем bound версию команды через descriptor protocol
    bound_cmd = cmd.__get__(cog_instance, MockCog)

    # Проверяем, что handler bound
    assert bound_cmd.handler != cmd.handler

    # Проверяем, что error_handler тоже bound
    assert len(bound_cmd._error_handlers) == 1
    assert bound_cmd._error_handlers[0][0] != cmd._error_handlers[0][0]
    assert hasattr(bound_cmd._error_handlers[0][0], "__self__")
    assert bound_cmd._error_handlers[0][0].__self__ is cog_instance


def test_multiple_error_handlers():
    """Проверяет, что можно зарегистрировать несколько error handlers для разных типов"""

    async def test_handler():
        pass

    cmd = Command(handler=test_handler, names=["test"])

    async def value_error_handler(ctx, error):
        pass

    async def type_error_handler(ctx, error):
        pass

    async def zero_div_handler(ctx, error):
        pass

    # Регистрируем несколько обработчиков
    cmd.on_error(ValueError)(value_error_handler)
    cmd.on_error(TypeError)(type_error_handler)
    cmd.on_error(ZeroDivisionError)(zero_div_handler)

    # Проверяем, что все зарегистрированы
    assert len(cmd._error_handlers) == 3
    assert cmd._error_handlers[0] == (value_error_handler, (ValueError,))
    assert cmd._error_handlers[1] == (type_error_handler, (TypeError,))
    assert cmd._error_handlers[2] == (zero_div_handler, (ZeroDivisionError,))


def test_multiple_error_handlers_with_catchall():
    """Проверяет, что можно комбинировать специфичные handlers с catch-all"""

    async def test_handler():
        pass

    cmd = Command(handler=test_handler, names=["test"])

    async def value_error_handler(ctx, error):
        pass

    async def catchall_handler(ctx, error):
        pass

    # Регистрируем специфичный и catch-all
    cmd.on_error(ValueError)(value_error_handler)
    cmd.on_error()(catchall_handler)

    # Проверяем, что оба зарегистрированы
    assert len(cmd._error_handlers) == 2
    assert cmd._error_handlers[0] == (value_error_handler, (ValueError,))
    assert cmd._error_handlers[1] == (catchall_handler, None)


def test_duplicate_catchall_raises_error():
    """Проверяет, что нельзя зарегистрировать два catch-all обработчика"""

    async def test_handler():
        pass

    cmd = Command(handler=test_handler, names=["test"])

    async def catchall_handler1(ctx, error):
        pass

    async def catchall_handler2(ctx, error):
        pass

    # Первый catch-all регистрируется успешно
    cmd.on_error()(catchall_handler1)

    # Второй catch-all должен вызвать ошибку
    with pytest.raises(ValueError, match="уже есть универсальный обработчик ошибок"):
        cmd.on_error()(catchall_handler2)


@pytest.mark.asyncio
async def test_multiple_handlers_called_correctly():
    """Проверяет, что вызывается правильный handler для каждого типа ошибки"""
    import unittest.mock

    value_error_handled = False
    type_error_handled = False
    catchall_handled = False

    async def test_handler_value():
        raise ValueError("Value error")

    async def test_handler_type():
        raise TypeError("Type error")

    async def test_handler_runtime():
        raise RuntimeError("Runtime error")

    # Создаем три команды для тестирования разных сценариев
    cmd_value = Command(handler=test_handler_value, names=["test1"])
    cmd_type = Command(handler=test_handler_type, names=["test2"])
    cmd_runtime = Command(handler=test_handler_runtime, names=["test3"])

    async def value_error_handler(error):
        nonlocal value_error_handled
        value_error_handled = True

    async def type_error_handler(error):
        nonlocal type_error_handled
        type_error_handled = True

    async def catchall_handler(error):
        nonlocal catchall_handled
        catchall_handled = True

    # Регистрируем обработчики для всех команд
    for cmd in [cmd_value, cmd_type, cmd_runtime]:
        cmd.on_error(ValueError)(value_error_handler)
        cmd.on_error(TypeError)(type_error_handler)
        cmd.on_error()(catchall_handler)

    mock_ctx = unittest.mock.Mock(spec=[])

    # Тест 1: ValueError должен вызвать value_error_handler
    value_error_handled = False
    await cmd_value._call_handler(mock_ctx, {})
    assert value_error_handled
    assert not type_error_handled
    assert not catchall_handled

    # Тест 2: TypeError должен вызвать type_error_handler
    value_error_handled = False
    type_error_handled = False
    catchall_handled = False
    await cmd_type._call_handler(mock_ctx, {})
    assert not value_error_handled
    assert type_error_handled
    assert not catchall_handled

    # Тест 3: RuntimeError должен вызвать catchall_handler
    value_error_handled = False
    type_error_handled = False
    catchall_handled = False
    await cmd_runtime._call_handler(mock_ctx, {})
    assert not value_error_handled
    assert not type_error_handled
    assert catchall_handled


@pytest.mark.asyncio
async def test_error_handler_with_multiple_exception_types():
    """Проверяет, что один handler может обрабатывать несколько типов ошибок"""
    import unittest.mock

    error_handled = False
    caught_error = None

    async def test_handler_value():
        raise ValueError("Value error")

    async def test_handler_type():
        raise TypeError("Type error")

    cmd_value = Command(handler=test_handler_value, names=["test1"])
    cmd_type = Command(handler=test_handler_type, names=["test2"])

    async def multi_type_handler(error):
        nonlocal error_handled, caught_error
        error_handled = True
        caught_error = error

    # Регистрируем один обработчик для двух типов ошибок
    cmd_value.on_error(ValueError, TypeError)(multi_type_handler)
    cmd_type.on_error(ValueError, TypeError)(multi_type_handler)

    mock_ctx = unittest.mock.Mock(spec=[])

    # Тест 1: ValueError
    error_handled = False
    await cmd_value._call_handler(mock_ctx, {})
    assert error_handled
    assert isinstance(caught_error, ValueError)

    # Тест 2: TypeError
    error_handled = False
    caught_error = None
    await cmd_type._call_handler(mock_ctx, {})
    assert error_handled
    assert isinstance(caught_error, TypeError)
