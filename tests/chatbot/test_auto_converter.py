"""Tests for AutoConverterCutter."""

import pytest
from unittest.mock import MagicMock

from vkflow.commands.parsing.cutters import AutoConverterCutter, _NonStrictParsingError
from vkflow.commands.parsing.adapters import _resolve_cutter, _is_auto_convertible
from vkflow.commands.parsing.cutter import Argument
from vkflow.exceptions import BadArgumentError


class HexColor:
    """A color in hexadecimal format."""

    def __init__(self, ctx, value: str):
        self.ctx = ctx
        self.color = self._parse_hex(value)

    def _parse_hex(self, value: str) -> str:
        value = value.strip()

        hex_part = value[1:] if value.startswith("#") else value

        if len(hex_part) == 3:
            hex_part = "".join(c * 2 for c in hex_part)

        if len(hex_part) == 6 and all(c in "0123456789abcdefABCDEF" for c in hex_part):
            return f"#{hex_part.lower()}"

        raise ValueError(f"Invalid hex color: {value}")

    def __repr__(self):
        return f"HexColor({self.color})"


class SimpleValue:
    """A simple value without context."""

    def __init__(self, value: str):
        self.value = value.upper()


class PositiveInt:
    """A positive integer."""

    def __init__(self, value: str):
        num = int(value)
        if num <= 0:
            raise ValueError("Must be positive")
        self.value = num


class NoParamsClass:
    """Class with no __init__ params."""

    def __init__(self):
        pass


class TooManyParamsClass:
    """Class with too many required params."""

    def __init__(self, a, b, c, d):
        pass


class TestIsAutoConvertible:
    def test_class_with_ctx_and_value(self):
        assert _is_auto_convertible(HexColor) is True

    def test_class_with_value_only(self):
        assert _is_auto_convertible(SimpleValue) is True

    def test_class_with_no_params(self):
        assert _is_auto_convertible(NoParamsClass) is False

    def test_class_with_many_params_is_convertible(self):
        # Classes with many params are now auto-convertible
        # (they just won't receive all expected params)
        assert _is_auto_convertible(TooManyParamsClass) is True

    def test_builtin_types_not_convertible(self):
        assert _is_auto_convertible(int) is False
        assert _is_auto_convertible(str) is False


class TestAutoConverterCutter:
    @pytest.mark.asyncio
    async def test_parse_hex_color_with_hash(self):
        ctx = MagicMock()
        cutter = AutoConverterCutter(HexColor)

        result = await cutter.cut_part(ctx, "#FF0000 rest")

        assert isinstance(result.parsed_part, HexColor)
        assert result.parsed_part.color == "#ff0000"
        assert result.parsed_part.ctx is ctx
        assert result.new_arguments_string == "rest"

    @pytest.mark.asyncio
    async def test_parse_hex_color_without_hash(self):
        ctx = MagicMock()
        cutter = AutoConverterCutter(HexColor)

        result = await cutter.cut_part(ctx, "00FF00")

        assert result.parsed_part.color == "#00ff00"

    @pytest.mark.asyncio
    async def test_parse_hex_color_short_format(self):
        ctx = MagicMock()
        cutter = AutoConverterCutter(HexColor)

        result = await cutter.cut_part(ctx, "#F00")

        assert result.parsed_part.color == "#ff0000"

    @pytest.mark.asyncio
    async def test_invalid_hex_color_raises_non_strict_error(self):
        """Non-strict mode (default) raises _NonStrictParsingError."""
        ctx = MagicMock()
        cutter = AutoConverterCutter(HexColor)  # strict=False by default

        with pytest.raises(_NonStrictParsingError) as exc_info:
            await cutter.cut_part(ctx, "notacolor")

        assert "Invalid hex color" in str(exc_info.value.original_error)

    @pytest.mark.asyncio
    async def test_invalid_hex_color_strict_mode(self):
        """Strict mode raises BadArgumentError."""
        ctx = MagicMock()
        cutter = AutoConverterCutter(HexColor, strict=True)

        with pytest.raises(BadArgumentError) as exc_info:
            await cutter.cut_part(ctx, "notacolor")

        assert "Invalid hex color" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_parse_simple_value_without_ctx(self):
        ctx = MagicMock()
        cutter = AutoConverterCutter(SimpleValue)

        result = await cutter.cut_part(ctx, "hello world")

        assert isinstance(result.parsed_part, SimpleValue)
        assert result.parsed_part.value == "HELLO"
        assert result.new_arguments_string == "world"

    @pytest.mark.asyncio
    async def test_parse_positive_int(self):
        ctx = MagicMock()
        cutter = AutoConverterCutter(PositiveInt)

        result = await cutter.cut_part(ctx, "42 rest")

        assert result.parsed_part.value == 42

    @pytest.mark.asyncio
    async def test_parse_negative_int_raises_non_strict_error(self):
        """Non-strict mode (default) raises _NonStrictParsingError."""
        ctx = MagicMock()
        cutter = AutoConverterCutter(PositiveInt)  # strict=False by default

        with pytest.raises(_NonStrictParsingError) as exc_info:
            await cutter.cut_part(ctx, "-5")

        assert "Must be positive" in str(exc_info.value.original_error)

    @pytest.mark.asyncio
    async def test_parse_negative_int_strict_mode(self):
        """Strict mode raises BadArgumentError."""
        ctx = MagicMock()
        cutter = AutoConverterCutter(PositiveInt, strict=True)

        with pytest.raises(BadArgumentError) as exc_info:
            await cutter.cut_part(ctx, "-5")

        assert "Must be positive" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_string_raises_error(self):
        ctx = MagicMock()
        cutter = AutoConverterCutter(HexColor)

        with pytest.raises(BadArgumentError):
            await cutter.cut_part(ctx, "")

    @pytest.mark.asyncio
    async def test_whitespace_only_raises_error(self):
        ctx = MagicMock()
        cutter = AutoConverterCutter(HexColor)

        with pytest.raises(BadArgumentError):
            await cutter.cut_part(ctx, "   ")

    def test_gen_doc_uses_class_docstring(self):
        cutter = AutoConverterCutter(HexColor)
        doc = cutter.gen_doc()

        assert "HexColor" in doc
        assert "hexadecimal" in doc

    def test_gen_doc_without_docstring(self):
        class NoDocClass:
            def __init__(self, value: str):
                self.value = value

        cutter = AutoConverterCutter(NoDocClass)
        doc = cutter.gen_doc()

        assert "NoDocClass" in doc


class TestResolveAutoConverter:
    def test_resolve_custom_class_automatically(self):
        cutter = _resolve_cutter(
            arg_name="color",
            arg_annotation=HexColor,
            arg_settings=Argument(),
            arg_kind=None,
        )

        assert isinstance(cutter, AutoConverterCutter)
        assert cutter._target_class is HexColor

    def test_resolve_simple_class_without_ctx(self):
        cutter = _resolve_cutter(
            arg_name="val",
            arg_annotation=SimpleValue,
            arg_settings=Argument(),
            arg_kind=None,
        )

        assert isinstance(cutter, AutoConverterCutter)

    def test_builtin_types_not_auto_converted(self):
        from vkflow.commands.parsing.cutters import IntegerCutter

        cutter = _resolve_cutter(
            arg_name="num",
            arg_annotation=int,
            arg_settings=Argument(),
            arg_kind=None,
        )

        assert isinstance(cutter, IntegerCutter)


class TestOptionalAutoConverter:
    def test_resolve_optional_custom_class(self):
        from vkflow.commands.parsing.cutters import OptionalCutter

        cutter = _resolve_cutter(
            arg_name="color",
            arg_annotation=HexColor | None,
            arg_settings=Argument(default=None),
            arg_kind=None,
        )

        assert isinstance(cutter, OptionalCutter)

    @pytest.mark.asyncio
    async def test_optional_returns_none_on_error(self):

        cutter = _resolve_cutter(
            arg_name="color",
            arg_annotation=HexColor | None,
            arg_settings=Argument(default=None),
            arg_kind=None,
        )

        ctx = MagicMock()
        result = await cutter.cut_part(ctx, "notacolor rest")

        assert result.parsed_part is None

    @pytest.mark.asyncio
    async def test_optional_returns_value_on_success(self):
        cutter = _resolve_cutter(
            arg_name="color",
            arg_annotation=HexColor | None,
            arg_settings=Argument(default=None),
            arg_kind=None,
        )

        ctx = MagicMock()
        result = await cutter.cut_part(ctx, "#FF0000 rest")

        assert isinstance(result.parsed_part, HexColor)
        assert result.parsed_part.color == "#ff0000"
