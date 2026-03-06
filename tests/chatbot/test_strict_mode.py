"""
Tests for strict mode and async create in AutoConverterCutter.
"""

import pytest
from typing import Annotated, ClassVar
from unittest.mock import MagicMock

from vkflow.commands.parsing.cutters import (
    AutoConverterCutter,
    OptionalCutter,
    Strict,
    _NonStrictParsingError,
)
from vkflow.exceptions import BadArgumentError


# ============== Test Classes ==============


class HexColorSimple:
    """A simple color parser with value only."""

    def __init__(self, value: str):
        if not value.startswith("#") or len(value) != 7:
            raise ValueError(f"Invalid hex color: {value}")
        self.color = value


class HexColorWithCtx:
    """A color parser that accepts ctx and value."""

    def __init__(self, ctx, value: str):
        self.ctx = ctx
        if not value.startswith("#") or len(value) != 7:
            raise ValueError(f"Invalid hex color: {value}")
        self.color = value


class HexColorNonStrict:
    """A non-strict color parser with class attribute."""

    __strict__ = False
    __consume_on_error__ = True

    def __init__(self, value: str):
        if not value.startswith("#") or len(value) != 7:
            raise ValueError(f"Invalid hex color: {value}")
        self.color = value


class HexColorAsyncCreate:
    """A color parser with async create classmethod."""

    def __init__(self, ctx, value: str):
        self.ctx = ctx
        self.color = value
        self.validated = False

    @classmethod
    async def create(cls, ctx, value: str):
        if not value.startswith("#") or len(value) != 7:
            raise ValueError(f"Invalid hex color: {value}")
        instance = cls(ctx, value)
        instance.validated = True
        return instance


class HexColorAsyncCreateValueOnly:
    """Async create that only accepts value."""

    def __init__(self):
        self.color = None

    @classmethod
    async def create(cls, value: str):
        if not value.startswith("#") or len(value) != 7:
            raise ValueError(f"Invalid hex color: {value}")
        instance = cls()
        instance.color = value
        return instance


class HexColorAsyncCreateCtxOnly:
    """Async create that only accepts ctx."""

    def __init__(self):
        self.ctx = None

    @classmethod
    async def create(cls, ctx):
        instance = cls()
        instance.ctx = ctx
        return instance


class HexColorAsyncCreateNoParams:
    """Async create with no params (just cls)."""

    def __init__(self):
        self.created = False

    @classmethod
    async def create(cls):
        instance = cls()
        instance.created = True
        return instance


class HexColorStrictExplicit:
    """Explicitly strict color parser."""

    __strict__ = True

    def __init__(self, value: str):
        if not value.startswith("#") or len(value) != 7:
            raise ValueError(f"Invalid hex color: {value}")
        self.color = value


# ============== Tests ==============


class TestStrictAnnotation:
    """Tests for Strict annotation."""

    def test_strict_default_is_true(self):
        """Strict annotation defaults to True."""
        strict = Strict()
        assert strict.value is True

    def test_strict_can_be_set_to_false(self):
        """Strict annotation can be set to False."""
        strict = Strict(False)
        assert strict.value is False

    def test_strict_is_frozen(self):
        """Strict annotation is immutable."""
        strict = Strict(False)
        with pytest.raises(AttributeError):
            strict.value = True


class TestAutoConverterCutterDefaults:
    """Tests for AutoConverterCutter default values."""

    def test_default_strict_is_false(self):
        """Default strict mode is False (non-strict by default)."""
        cutter = AutoConverterCutter(HexColorSimple)
        assert cutter.strict is False

    def test_class_strict_attribute_true(self):
        """Class __strict__ = True is respected."""
        cutter = AutoConverterCutter(HexColorStrictExplicit)
        assert cutter.strict is True

    def test_class_strict_attribute_false(self):
        """Class __strict__ = False is respected."""
        cutter = AutoConverterCutter(HexColorNonStrict)
        assert cutter.strict is False

    def test_explicit_strict_overrides_class(self):
        """Explicit strict parameter overrides class attribute."""
        # Class has __strict__ = False, but we pass strict=True
        cutter = AutoConverterCutter(HexColorNonStrict, strict=True)
        assert cutter.strict is True

        # Class has no __strict__ (defaults to False), but we pass strict=True
        cutter = AutoConverterCutter(HexColorSimple, strict=True)
        assert cutter.strict is True

    def test_consume_on_error_default_is_false(self):
        """Default consume_on_error is False."""
        cutter = AutoConverterCutter(HexColorSimple)
        assert cutter.consume_on_error is False


class TestAutoConverterCutterAsyncCreate:
    """Tests for async create classmethod detection."""

    def test_detects_async_create(self):
        """Detects async create classmethod."""
        cutter = AutoConverterCutter(HexColorAsyncCreate)
        assert cutter._has_async_create is True

    def test_no_async_create(self):
        """No async create when not present."""
        cutter = AutoConverterCutter(HexColorSimple)
        assert cutter._has_async_create is False

    def test_async_create_params_ctx_and_value(self):
        """Async create with both ctx and value."""
        cutter = AutoConverterCutter(HexColorAsyncCreate)
        assert cutter._accepts_ctx is True
        assert cutter._accepts_value is True

    def test_async_create_params_value_only(self):
        """Async create with value only."""
        cutter = AutoConverterCutter(HexColorAsyncCreateValueOnly)
        assert cutter._accepts_ctx is False
        assert cutter._accepts_value is True

    def test_async_create_params_ctx_only(self):
        """Async create with ctx only."""
        cutter = AutoConverterCutter(HexColorAsyncCreateCtxOnly)
        assert cutter._accepts_ctx is True
        assert cutter._accepts_value is False

    def test_async_create_no_params(self):
        """Async create with no params."""
        cutter = AutoConverterCutter(HexColorAsyncCreateNoParams)
        assert cutter._accepts_ctx is False
        assert cutter._accepts_value is False


class TestAutoConverterCutterInitParams:
    """Tests for __init__ parameter detection."""

    def test_init_value_only(self):
        """Init with value only."""
        cutter = AutoConverterCutter(HexColorSimple)
        assert cutter._accepts_ctx is False
        assert cutter._accepts_value is True

    def test_init_ctx_and_value(self):
        """Init with ctx and value."""
        cutter = AutoConverterCutter(HexColorWithCtx)
        assert cutter._accepts_ctx is True
        assert cutter._accepts_value is True


class TestAutoConverterCutterParsing:
    """Tests for AutoConverterCutter parsing behavior."""

    @pytest.fixture
    def mock_ctx(self):
        ctx = MagicMock()
        ctx.api = MagicMock()
        return ctx

    @pytest.mark.asyncio
    async def test_simple_parsing(self, mock_ctx):
        """Simple class parses correctly."""
        cutter = AutoConverterCutter(HexColorSimple)
        result = await cutter.cut_part(mock_ctx, "#FF0000 extra")

        assert result.parsed_part.color == "#FF0000"
        assert result.new_arguments_string == "extra"

    @pytest.mark.asyncio
    async def test_parsing_with_ctx(self, mock_ctx):
        """Class with ctx receives context."""
        cutter = AutoConverterCutter(HexColorWithCtx)
        result = await cutter.cut_part(mock_ctx, "#FF0000")

        assert result.parsed_part.color == "#FF0000"
        assert result.parsed_part.ctx is mock_ctx

    @pytest.mark.asyncio
    async def test_async_create_is_used(self, mock_ctx):
        """Async create classmethod is used when present."""
        cutter = AutoConverterCutter(HexColorAsyncCreate)
        result = await cutter.cut_part(mock_ctx, "#FF0000")

        assert result.parsed_part.color == "#FF0000"
        assert result.parsed_part.validated is True
        assert result.parsed_part.ctx is mock_ctx

    @pytest.mark.asyncio
    async def test_async_create_value_only(self, mock_ctx):
        """Async create with value only works."""
        cutter = AutoConverterCutter(HexColorAsyncCreateValueOnly)
        result = await cutter.cut_part(mock_ctx, "#00FF00")

        assert result.parsed_part.color == "#00FF00"

    @pytest.mark.asyncio
    async def test_async_create_ctx_only(self, mock_ctx):
        """Async create with ctx only works."""
        cutter = AutoConverterCutter(HexColorAsyncCreateCtxOnly)
        result = await cutter.cut_part(mock_ctx, "ignored_value")

        assert result.parsed_part.ctx is mock_ctx

    @pytest.mark.asyncio
    async def test_async_create_no_params(self, mock_ctx):
        """Async create with no params works."""
        cutter = AutoConverterCutter(HexColorAsyncCreateNoParams)
        result = await cutter.cut_part(mock_ctx, "ignored_value")

        assert result.parsed_part.created is True

    @pytest.mark.asyncio
    async def test_non_strict_mode_default(self, mock_ctx):
        """Non-strict mode (default) raises _NonStrictParsingError."""
        cutter = AutoConverterCutter(HexColorSimple)  # strict=False by default

        with pytest.raises(_NonStrictParsingError) as exc_info:
            await cutter.cut_part(mock_ctx, "invalid")

        error = exc_info.value
        assert error.consume is False  # consume_on_error=False by default

    @pytest.mark.asyncio
    async def test_strict_mode_raises_bad_argument(self, mock_ctx):
        """Strict mode raises BadArgumentError."""
        cutter = AutoConverterCutter(HexColorStrictExplicit)

        with pytest.raises(BadArgumentError):
            await cutter.cut_part(mock_ctx, "invalid")


class TestOptionalCutterIntegration:
    """Tests for OptionalCutter with AutoConverterCutter."""

    @pytest.fixture
    def mock_ctx(self):
        ctx = MagicMock()
        ctx.api = MagicMock()
        return ctx

    @pytest.mark.asyncio
    async def test_non_strict_returns_default(self, mock_ctx):
        """Non-strict with invalid input returns default."""
        inner_cutter = AutoConverterCutter(HexColorSimple)
        optional_cutter = OptionalCutter(inner_cutter, default=None)

        result = await optional_cutter.cut_part(mock_ctx, "invalid next_arg")

        assert result.parsed_part is None
        # Text not consumed (consume_on_error=False by default)
        assert result.new_arguments_string == "invalid next_arg"

    @pytest.mark.asyncio
    async def test_non_strict_with_consume(self, mock_ctx):
        """Non-strict with consume_on_error=True removes text."""
        inner_cutter = AutoConverterCutter(HexColorNonStrict)
        optional_cutter = OptionalCutter(inner_cutter, default=None)

        result = await optional_cutter.cut_part(mock_ctx, "invalid next_arg")

        assert result.parsed_part is None
        # Text consumed
        assert result.new_arguments_string == "next_arg"

    @pytest.mark.asyncio
    async def test_valid_input_works(self, mock_ctx):
        """Valid input parses correctly."""
        inner_cutter = AutoConverterCutter(HexColorSimple)
        optional_cutter = OptionalCutter(inner_cutter, default=None)

        result = await optional_cutter.cut_part(mock_ctx, "#FF0000 next_arg")

        assert result.parsed_part.color == "#FF0000"
        assert result.new_arguments_string == "next_arg"


class TestAdaptersResolveStrict:
    """Tests for adapters.py resolve_typing with Strict annotation."""

    def test_strict_annotation_is_extracted(self):
        """Strict annotation is extracted from Annotated."""
        from vkflow.commands.parsing.adapters import _resolve_cutter
        from vkflow.commands.parsing.cutter import Argument
        import inspect

        # With Strict(True)
        cutter = _resolve_cutter(
            arg_name="color",
            arg_annotation=Annotated[HexColorSimple, Strict(True)],
            arg_settings=Argument(),
            arg_kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )

        assert isinstance(cutter, AutoConverterCutter)
        assert cutter.strict is True

    def test_default_strict_is_false(self):
        """Default strict is False without annotation."""
        from vkflow.commands.parsing.adapters import _resolve_cutter
        from vkflow.commands.parsing.cutter import Argument
        import inspect

        cutter = _resolve_cutter(
            arg_name="color",
            arg_annotation=HexColorSimple,
            arg_settings=Argument(),
            arg_kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )

        assert isinstance(cutter, AutoConverterCutter)
        assert cutter.strict is False


class TestIsAutoConvertible:
    """Tests for _is_auto_convertible function."""

    def test_class_with_value_only(self):
        """Class with __init__(self, value) is auto-convertible."""
        from vkflow.commands.parsing.adapters import _is_auto_convertible

        assert _is_auto_convertible(HexColorSimple) is True

    def test_class_with_ctx_and_value(self):
        """Class with __init__(self, ctx, value) is auto-convertible."""
        from vkflow.commands.parsing.adapters import _is_auto_convertible

        assert _is_auto_convertible(HexColorWithCtx) is True

    def test_class_with_async_create(self):
        """Class with async create() is auto-convertible."""
        from vkflow.commands.parsing.adapters import _is_auto_convertible

        assert _is_auto_convertible(HexColorAsyncCreate) is True

    def test_class_with_async_create_value_only(self):
        """Class with async create(cls, value) is auto-convertible."""
        from vkflow.commands.parsing.adapters import _is_auto_convertible

        assert _is_auto_convertible(HexColorAsyncCreateValueOnly) is True

    def test_class_with_async_create_no_params(self):
        """Class with async create(cls) is auto-convertible."""
        from vkflow.commands.parsing.adapters import _is_auto_convertible

        assert _is_auto_convertible(HexColorAsyncCreateNoParams) is True

    def test_builtin_int_not_convertible(self):
        """Built-in int is not auto-convertible."""
        from vkflow.commands.parsing.adapters import _is_auto_convertible

        assert _is_auto_convertible(int) is False

    def test_builtin_str_not_convertible(self):
        """Built-in str is not auto-convertible."""
        from vkflow.commands.parsing.adapters import _is_auto_convertible

        assert _is_auto_convertible(str) is False


# ============== App.strict_mode Tests ==============


class TestArgumentParsingError:
    """Tests for ArgumentParsingError exception."""

    def test_basic_creation(self):
        """Test basic error creation."""
        from vkflow.exceptions import ArgumentParsingError

        mock_ctx = MagicMock()
        error = ArgumentParsingError(
            argument=None,
            remain_string="test",
            ctx=mock_ctx,
        )
        assert error.remain_string == "test"
        assert error.ctx is mock_ctx
        assert error.argument is None

    def test_with_original_error(self):
        """Test error with original BadArgumentError."""
        from vkflow.exceptions import ArgumentParsingError

        mock_ctx = MagicMock()
        original = BadArgumentError("Invalid number")

        error = ArgumentParsingError(
            argument=None,
            remain_string="abc",
            ctx=mock_ctx,
            original_error=original,
        )

        assert error.original_error is original
        assert "Invalid number" in str(error)

    def test_custom_reason(self):
        """Test error with custom reason."""
        from vkflow.exceptions import ArgumentParsingError

        mock_ctx = MagicMock()
        error = ArgumentParsingError(
            argument=None,
            remain_string="test",
            ctx=mock_ctx,
            reason="Custom error message",
        )

        assert str(error) == "Custom error message"

    def test_auto_reason_from_argument(self):
        """Test auto-generated reason from argument."""
        from vkflow.exceptions import ArgumentParsingError

        mock_ctx = MagicMock()
        mock_arg = MagicMock()
        mock_arg.argument_name = "count"

        error = ArgumentParsingError(
            argument=mock_arg,
            remain_string="test",
            ctx=mock_ctx,
        )

        assert "count" in str(error)


class TestAppStrictMode:
    """Tests for App strict_mode configuration."""

    def test_strict_mode_default_false(self):
        """strict_mode should be False by default."""
        from vkflow import App

        app = App(prefixes=["/"])
        assert app.strict_mode is False

    def test_strict_mode_can_be_enabled(self):
        """strict_mode can be set to True."""
        from vkflow import App

        app = App(prefixes=["/"], strict_mode=True)
        assert app.strict_mode is True

    def test_strict_mode_independent_of_debug(self):
        """strict_mode and debug are independent settings."""
        from vkflow import App

        # strict_mode=True, debug=False
        app1 = App(prefixes=["/"], strict_mode=True, debug=False)
        assert app1.strict_mode is True
        assert app1.debug is False

        # strict_mode=False, debug=True
        app2 = App(prefixes=["/"], strict_mode=False, debug=True)
        assert app2.strict_mode is False
        assert app2.debug is True

        # Both True
        app3 = App(prefixes=["/"], strict_mode=True, debug=True)
        assert app3.strict_mode is True
        assert app3.debug is True


class TestCommandStrictModeIntegration:
    """Integration tests for Command with App.strict_mode."""

    @pytest.fixture
    def mock_ctx_strict(self):
        """Create a mock NewMessage context with strict_mode=True."""

        class MockMessage:
            text = "/test abc"
            is_cropped = False
            reply_message = None
            fwd_messages: ClassVar[list] = []
            attachments: ClassVar[list] = []

        class MockApp:
            debug = False
            strict_mode = True

            async def dispatch_event(self, *args, **kwargs):
                pass

        class MockBot:
            app = MockApp()

        class MockCtx:
            msg = MockMessage()
            bot = MockBot()
            app = MockBot().app
            api = None
            argument_processing_payload: ClassVar[dict] = {}

        return MockCtx()

    @pytest.fixture
    def mock_ctx_non_strict(self):
        """Create a mock context with strict_mode=False."""

        class MockMessage:
            text = "/test abc"
            is_cropped = False
            reply_message = None
            fwd_messages: ClassVar[list] = []
            attachments: ClassVar[list] = []

        class MockApp:
            debug = False
            strict_mode = False

            async def dispatch_event(self, *args, **kwargs):
                pass

        class MockBot:
            app = MockApp()

        class MockCtx:
            msg = MockMessage()
            bot = MockBot()
            app = MockBot().app
            api = None
            argument_processing_payload: ClassVar[dict] = {}

        return MockCtx()

    @pytest.mark.asyncio
    async def test_strict_mode_raises_on_invalid_argument(self, mock_ctx_strict):
        """In strict mode, invalid argument should raise ArgumentParsingError."""
        from vkflow.commands.command import Command
        from vkflow.exceptions import ArgumentParsingError
        from vkflow.app.storages import NewMessage

        async def handler(ctx: NewMessage, num: int):
            pass

        cmd = Command(
            handler=handler,
            names=["test"],
            prefixes=["/"],
        )

        # "abc" is not a valid int
        with pytest.raises(ArgumentParsingError) as exc_info:
            await cmd._make_arguments(mock_ctx_strict, "abc")

        assert exc_info.value.remain_string == "abc"

    @pytest.mark.asyncio
    async def test_non_strict_mode_returns_none(self, mock_ctx_non_strict):
        """In non-strict mode, invalid argument should return None."""
        from vkflow.commands.command import Command
        from vkflow.app.storages import NewMessage

        async def handler(ctx: NewMessage, num: int):
            pass

        cmd = Command(
            handler=handler,
            names=["test"],
            prefixes=["/"],
        )

        # "abc" is not a valid int - should return None, not raise
        result = await cmd._make_arguments(mock_ctx_non_strict, "abc")
        assert result is None

    @pytest.mark.asyncio
    async def test_strict_mode_raises_on_extra_text(self, mock_ctx_strict):
        """In strict mode, extra text after arguments should raise."""
        from vkflow.commands.command import Command
        from vkflow.exceptions import ArgumentParsingError
        from vkflow.app.storages import NewMessage

        async def handler(ctx: NewMessage, num: int):
            pass

        cmd = Command(
            handler=handler,
            names=["test"],
            prefixes=["/"],
        )

        # "123 extra" - "extra" is leftover text
        with pytest.raises(ArgumentParsingError) as exc_info:
            await cmd._make_arguments(mock_ctx_strict, "123 extra")

        assert "extra" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_strict_mode_valid_arguments_work(self, mock_ctx_strict):
        """In strict mode, valid arguments should work normally."""
        from vkflow.commands.command import Command
        from vkflow.app.storages import NewMessage

        async def handler(ctx: NewMessage, num: int):
            pass

        cmd = Command(
            handler=handler,
            names=["test"],
            prefixes=["/"],
        )

        result = await cmd._make_arguments(mock_ctx_strict, "42")
        assert result is not None
        assert result["num"] == 42


class TestStrictModeWithValidators:
    """Tests for App.strict_mode with validators."""

    @pytest.fixture
    def mock_ctx_strict(self):
        """Create a strict mode mock context."""

        class MockMessage:
            text = "/test 200"
            is_cropped = False
            reply_message = None
            fwd_messages: ClassVar[list] = []
            attachments: ClassVar[list] = []

        class MockApp:
            debug = False
            strict_mode = True

            async def dispatch_event(self, *args, **kwargs):
                pass

        class MockBot:
            app = MockApp()

        class MockCtx:
            msg = MockMessage()
            bot = MockBot()
            app = MockBot().app
            api = None
            argument_processing_payload: ClassVar[dict] = {}

        return MockCtx()

    @pytest.mark.asyncio
    async def test_validator_failure_raises_in_strict_mode(self, mock_ctx_strict):
        """Validator failure should raise ArgumentParsingError in strict mode."""
        from vkflow.commands.command import Command
        from vkflow.exceptions import ArgumentParsingError
        from vkflow.app.storages import NewMessage
        from vkflow import Range

        async def handler(ctx: NewMessage, num: Annotated[int, Range(1, 100)]):
            pass

        cmd = Command(
            handler=handler,
            names=["test"],
            prefixes=["/"],
        )

        # 200 is out of range [1, 100]
        with pytest.raises(ArgumentParsingError) as exc_info:
            await cmd._make_arguments(mock_ctx_strict, "200")

        # Check that the error contains range info
        assert "диапазоне" in str(exc_info.value) or "range" in str(exc_info.value).lower()
