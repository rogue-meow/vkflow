"""Tests for custom cutter registry."""

import pytest

from vkflow import (
    Cutter,
    CutterParsingResponse,
    register_cutter,
    unregister_cutter,
    get_registered_cutter,
    get_all_registered_cutters,
    clear_registry,
)
from vkflow.commands.parsing.adapters import _resolve_cutter
from vkflow.commands.parsing.cutter import Argument


class Color:
    """Example custom type."""

    def __init__(self, r: int, g: int, b: int):
        self.r = r
        self.g = g
        self.b = b

    def __eq__(self, other):
        if not isinstance(other, Color):
            return False
        return self.r == other.r and self.g == other.g and self.b == other.b

    def __hash__(self):
        return hash((self.r, self.g, self.b))


class ColorCutter(Cutter):
    """Example custom cutter."""

    async def cut_part(self, ctx, arguments_string: str) -> CutterParsingResponse:
        arguments_string = arguments_string.lstrip()

        if arguments_string.startswith("#"):
            hex_color = arguments_string[1:7]
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return CutterParsingResponse(
                parsed_part=Color(r, g, b),
                new_arguments_string=arguments_string[7:],
            )

        parts = arguments_string.split(",", 2)
        if len(parts) >= 3:
            r = int(parts[0].strip())
            g = int(parts[1].strip())
            b_and_rest = parts[2].strip().split(maxsplit=1)
            b = int(b_and_rest[0])
            rest = b_and_rest[1] if len(b_and_rest) > 1 else ""
            return CutterParsingResponse(
                parsed_part=Color(r, g, b),
                new_arguments_string=rest,
            )

        from vkflow.exceptions import BadArgumentError

        raise BadArgumentError(self.gen_doc())

    def gen_doc(self) -> str:
        return "color in hex (#FF0000) or RGB (255,0,0) format"


@pytest.fixture(autouse=True)
def clean_registry():
    """Clean registry before and after each test."""
    clear_registry()
    yield
    clear_registry()


class TestCutterRegistry:
    def test_register_cutter_as_decorator(self):
        @register_cutter(Color)
        class TestColorCutter(ColorCutter):
            pass

        assert get_registered_cutter(Color) is TestColorCutter

    def test_register_cutter_as_function(self):
        register_cutter(Color, ColorCutter)
        assert get_registered_cutter(Color) is ColorCutter

    def test_unregister_cutter(self):
        register_cutter(Color, ColorCutter)
        removed = unregister_cutter(Color)

        assert removed is ColorCutter
        assert get_registered_cutter(Color) is None

    def test_unregister_nonexistent(self):
        removed = unregister_cutter(Color)
        assert removed is None

    def test_get_all_registered_cutters(self):
        register_cutter(Color, ColorCutter)

        all_cutters = get_all_registered_cutters()

        assert Color in all_cutters
        assert all_cutters[Color] is ColorCutter

    def test_get_all_registered_cutters_returns_copy(self):
        register_cutter(Color, ColorCutter)

        all_cutters = get_all_registered_cutters()
        all_cutters.clear()

        assert get_registered_cutter(Color) is ColorCutter

    def test_clear_registry(self):
        register_cutter(Color, ColorCutter)
        clear_registry()

        assert get_registered_cutter(Color) is None
        assert get_all_registered_cutters() == {}


class TestResolveCustomCutter:
    def test_resolve_registered_type(self):
        register_cutter(Color, ColorCutter)

        cutter = _resolve_cutter(
            arg_name="color",
            arg_annotation=Color,
            arg_settings=Argument(),
            arg_kind=None,
        )

        assert isinstance(cutter, ColorCutter)

    def test_registered_cutter_overrides_builtin(self):
        """Test that custom cutters override built-in types."""

        class CustomIntCutter(Cutter):
            async def cut_part(self, ctx, arguments_string: str) -> CutterParsingResponse:
                return CutterParsingResponse(
                    parsed_part=42,
                    new_arguments_string=arguments_string,
                )

            def gen_doc(self) -> str:
                return "always 42"

        register_cutter(int, CustomIntCutter)

        cutter = _resolve_cutter(
            arg_name="num",
            arg_annotation=int,
            arg_settings=Argument(),
            arg_kind=None,
        )

        assert isinstance(cutter, CustomIntCutter)


class TestColorCutter:
    @pytest.mark.asyncio
    async def test_parse_hex_color(self):
        cutter = ColorCutter()
        result = await cutter.cut_part(None, "#FF0000 rest")

        assert result.parsed_part == Color(255, 0, 0)
        assert result.new_arguments_string == " rest"

    @pytest.mark.asyncio
    async def test_parse_rgb_color(self):
        cutter = ColorCutter()
        result = await cutter.cut_part(None, "255, 128, 64 rest")

        assert result.parsed_part == Color(255, 128, 64)
        assert result.new_arguments_string == "rest"

    @pytest.mark.asyncio
    async def test_parse_invalid_color(self):
        from vkflow.exceptions import BadArgumentError

        cutter = ColorCutter()

        with pytest.raises(BadArgumentError):
            await cutter.cut_part(None, "invalid")
