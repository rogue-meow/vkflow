"""
Тесты для фич Блока 4: новая функциональность и гибкость.
"""

import asyncio
import enum
import pytest

from vkflow.commands.parsing.cutters import (
    BoolCutter,
    BoolValues,
    DictCutter,
    EnumCutter,
    ValidatingCutter,
    WordCutter,
    _extract_named_value,
)
from vkflow.commands.parsing.validators import (
    OneOf,
    Transform,
    Validator,
)
from vkflow.exceptions import BadArgumentError


# ============================================================
# 2.4: Async валидаторы в ValidatingCutter
# ============================================================


class TestAsyncValidators:
    """Тесты поддержки async валидаторов."""

    @pytest.mark.asyncio
    async def test_async_validator(self):
        """Async validator должен корректно применяться."""

        class AsyncUpperValidator(Validator):
            async def validate(self, value):
                await asyncio.sleep(0)  # имитация async
                return value.upper()

            def description(self):
                return "async upper"

        inner = WordCutter()
        cutter = ValidatingCutter(inner, [AsyncUpperValidator()])
        result = await cutter.cut_part(None, "hello")
        assert result.parsed_part == "HELLO"

    @pytest.mark.asyncio
    async def test_mixed_sync_async_validators(self):
        """Смешанные sync и async валидаторы."""

        class AsyncValidator(Validator):
            async def validate(self, value):
                return value + "_async"

            def description(self):
                return ""

        class SyncValidator(Validator):
            def validate(self, value):
                return value + "_sync"

            def description(self):
                return ""

        inner = WordCutter()
        cutter = ValidatingCutter(inner, [SyncValidator(), AsyncValidator()])
        result = await cutter.cut_part(None, "test")
        assert result.parsed_part == "test_sync_async"


# ============================================================
# 3.3: Escaped кавычки в _extract_named_value
# ============================================================


class TestExtractNamedValue:
    """Тесты экранирования кавычек."""

    def test_simple_quoted(self):
        value, _ = _extract_named_value('"hello world"')
        assert value == "hello world"

    def test_escaped_quote(self):
        value, _ = _extract_named_value(r'"hello \"world\""')
        assert value == 'hello "world"'

    def test_escaped_backslash(self):
        value, _ = _extract_named_value(r'"hello \\"')
        assert value == "hello \\"

    def test_single_quoted(self):
        value, _ = _extract_named_value("'hello world'")
        assert value == "hello world"

    def test_escaped_single_quote(self):
        value, _ = _extract_named_value(r"'it\'s fine'")
        assert value == "it's fine"

    def test_unquoted(self):
        value, rest = _extract_named_value("hello world")
        assert value == "hello"
        assert rest == "world"

    def test_empty(self):
        value, rest = _extract_named_value("")
        assert value == ""
        assert rest == ""

    def test_rest_after_quoted(self):
        value, rest = _extract_named_value('"hello" остаток')
        assert value == "hello"
        assert rest == " остаток"


# ============================================================
# 3.4: Escaped кавычки в DictCutter
# ============================================================


class TestDictCutterEscapedQuotes:
    """Тесты экранирования кавычек в DictCutter."""

    @pytest.mark.asyncio
    async def test_escaped_quotes_in_value(self):
        cutter = DictCutter(WordCutter())
        result = await cutter.cut_part(None, r'key="hello \"world\""')
        assert result.parsed_part == {"key": 'hello "world"'}

    @pytest.mark.asyncio
    async def test_escaped_backslash_in_value(self):
        cutter = DictCutter(WordCutter())
        result = await cutter.cut_part(None, r'key="path\\to"')
        assert result.parsed_part == {"key": "path\\to"}

    @pytest.mark.asyncio
    async def test_simple_quoted_value(self):
        cutter = DictCutter(WordCutter())
        result = await cutter.cut_part(None, 'key="hello world"')
        assert result.parsed_part == {"key": "hello world"}


# ============================================================
# 5.2: BoolValues через Annotated
# ============================================================


class TestBoolValues:
    """Тесты кастомных значений для BoolCutter."""

    @pytest.mark.asyncio
    async def test_custom_true_values(self):
        bv = BoolValues(true=["включить", "запустить"], false=["выключить", "остановить"])
        cutter = BoolCutter(bv)
        result = await cutter.cut_part(None, "включить")
        assert result.parsed_part is True

    @pytest.mark.asyncio
    async def test_custom_false_values(self):
        bv = BoolValues(true=["включить"], false=["выключить"])
        cutter = BoolCutter(bv)
        result = await cutter.cut_part(None, "выключить")
        assert result.parsed_part is False

    @pytest.mark.asyncio
    async def test_custom_values_reject_default(self):
        """Стандартные значения НЕ должны работать при кастомных."""
        bv = BoolValues(true=["включить"], false=["выключить"])
        cutter = BoolCutter(bv)
        with pytest.raises(BadArgumentError):
            await cutter.cut_part(None, "да")

    @pytest.mark.asyncio
    async def test_default_values_without_bool_values(self):
        """Без BoolValues должны работать стандартные значения."""
        cutter = BoolCutter()
        result = await cutter.cut_part(None, "да")
        assert result.parsed_part is True

    @pytest.mark.asyncio
    async def test_case_insensitive(self):
        """BoolCutter должен быть регистронезависимым."""
        cutter = BoolCutter()
        result = await cutter.cut_part(None, "YES")
        assert result.parsed_part is True

        result = await cutter.cut_part(None, "No")
        assert result.parsed_part is False

    @pytest.mark.asyncio
    async def test_gen_doc_custom(self):
        bv = BoolValues(true=["вкл"], false=["выкл"])
        cutter = BoolCutter(bv)
        doc = cutter.gen_doc()
        assert "вкл" in doc
        assert "выкл" in doc


# ============================================================
# 5.3: EnumCutter multi-word values
# ============================================================


class TestEnumCutterMultiWord:
    """Тесты multi-word значений в EnumCutter."""

    class Action(enum.Enum):
        BAN = "бан"
        TEMP_BAN = "временный бан"
        MUTE = "мут"

    @pytest.mark.asyncio
    async def test_single_word_value(self):
        cutter = EnumCutter(self.Action)
        result = await cutter.cut_part(None, "бан остальной текст")
        assert result.parsed_part == self.Action.BAN
        assert result.new_arguments_string == " остальной текст"

    @pytest.mark.asyncio
    async def test_multi_word_value(self):
        cutter = EnumCutter(self.Action)
        result = await cutter.cut_part(None, "временный бан остальной текст")
        assert result.parsed_part == self.Action.TEMP_BAN
        assert result.new_arguments_string == " остальной текст"

    @pytest.mark.asyncio
    async def test_multi_word_priority(self):
        """Multi-word значение должно матчиться раньше single-word."""
        # "временный бан" должен матчиться целиком, а не только "бан"
        cutter = EnumCutter(self.Action)
        result = await cutter.cut_part(None, "временный бан")
        assert result.parsed_part == self.Action.TEMP_BAN

    @pytest.mark.asyncio
    async def test_name_match(self):
        """Enum name тоже должен работать."""
        cutter = EnumCutter(self.Action)
        result = await cutter.cut_part(None, "BAN")
        assert result.parsed_part == self.Action.BAN

    @pytest.mark.asyncio
    async def test_case_insensitive(self):
        cutter = EnumCutter(self.Action)
        result = await cutter.cut_part(None, "Мут")
        assert result.parsed_part == self.Action.MUTE

    @pytest.mark.asyncio
    async def test_no_match(self):
        cutter = EnumCutter(self.Action)
        with pytest.raises(BadArgumentError):
            await cutter.cut_part(None, "неизвестно")


# ============================================================
# 5.5: Transform цепочки
# ============================================================


class TestTransformChain:
    """Тесты цепочек Transform."""

    def test_single_func(self):
        t = Transform(str.upper)
        assert t.validate("hello") == "HELLO"

    def test_chain(self):
        t = Transform(str.strip, str.upper)
        assert t.validate("  hello  ") == "HELLO"

    def test_chain_with_abs(self):
        t = Transform(abs)
        assert t.validate(-42) == 42

    def test_chain_description(self):
        t = Transform(str.strip, str.lower)
        desc = t.description()
        assert "strip" in desc
        assert "lower" in desc
        assert "→" in desc

    def test_chain_error(self):
        t = Transform(int)
        with pytest.raises(ValueError, match="Трансформация"):
            t.validate("not_a_number")

    def test_no_funcs_raises(self):
        with pytest.raises(ValueError, match="хотя бы одну функцию"):
            Transform()


# ============================================================
# 5.6: OneOf валидатор
# ============================================================


class TestOneOf:
    """Тесты для OneOf валидатора."""

    def test_valid_value(self):
        v = OneOf("rock", "paper", "scissors")
        assert v.validate("rock") == "rock"
        assert v.validate("paper") == "paper"

    def test_invalid_value(self):
        v = OneOf("rock", "paper", "scissors")
        with pytest.raises(ValueError, match="Допустимые значения"):
            v.validate("fire")

    def test_int_values(self):
        v = OneOf(1, 2, 3, 5, 8, 13)
        assert v.validate(5) == 5
        with pytest.raises(ValueError):
            v.validate(4)

    def test_description(self):
        v = OneOf("a", "b", "c")
        desc = v.description()
        assert "'a'" in desc
        assert "'b'" in desc
        assert "'c'" in desc


# ============================================================
# MaxConcurrencyMapping: нет утечки семафора
# ============================================================


class TestMaxConcurrencyNoLeak:
    """Тесты что MaxConcurrencyMapping не утекает."""

    @pytest.mark.asyncio
    async def test_acquire_release_cycle(self):
        from vkflow.commands.cooldowns import (
            MaxConcurrency,
            MaxConcurrencyMapping,
            BucketType,
        )

        mc = MaxConcurrency(number=2, per=BucketType.DEFAULT)
        mapping = MaxConcurrencyMapping(mc)

        class FakeCtx:
            author = 123
            peer_id = 456

        ctx = FakeCtx()

        # Занимаем 2 слота
        await mapping.acquire(ctx)
        await mapping.acquire(ctx)

        # 3-й должен упасть
        from vkflow.commands.cooldowns import MaxConcurrencyReachedError

        with pytest.raises(MaxConcurrencyReachedError):
            await mapping.acquire(ctx)

        # Освобождаем 1
        mapping.release(ctx)

        # Теперь 3-й должен пройти
        await mapping.acquire(ctx)

        # Освобождаем все
        mapping.release(ctx)
        mapping.release(ctx)

        # Снова 2 слота доступны
        await mapping.acquire(ctx)
        await mapping.acquire(ctx)
        mapping.release(ctx)
        mapping.release(ctx)

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        from vkflow.commands.cooldowns import (
            MaxConcurrency,
            MaxConcurrencyMapping,
            BucketType,
        )

        mc = MaxConcurrency(number=1, per=BucketType.DEFAULT)
        mapping = MaxConcurrencyMapping(mc)

        class FakeCtx:
            author = 1
            peer_id = 1

        ctx = FakeCtx()

        # Context manager должен освободить слот
        async with mapping(ctx):
            pass

        # Слот снова доступен
        async with mapping(ctx):
            pass


# ============================================================
# Cog.walk_commands с Group
# ============================================================


class TestWalkCommandsWithGroup:
    """Тесты для walk_commands с вложенными Group."""

    def test_walk_commands_includes_subcommands(self):
        from vkflow.commands.core import Command, Group
        from vkflow.commands.context import Context

        async def handler1(ctx: Context):
            pass

        async def handler2(ctx: Context):
            pass

        async def handler3(ctx: Context):
            pass

        group = Group(handler1, name="config")
        cmd1 = Command(handler2, name="show")
        cmd2 = Command(handler3, name="set")
        group.add_command(cmd1)
        group.add_command(cmd2)

        all_commands = list(group.walk_commands())

        assert cmd1 in all_commands
        assert cmd2 in all_commands

    def test_walk_commands_nested_groups(self):
        from vkflow.commands.core import Command, Group
        from vkflow.commands.context import Context

        async def h(ctx: Context):
            pass

        outer = Group(h, name="admin")
        inner = Group(h, name="config")
        cmd = Command(h, name="show")

        inner.add_command(cmd)
        outer.add_command(inner)

        all_commands = list(outer.walk_commands())
        assert inner in all_commands
        assert cmd in all_commands
