"""
Tests for validators module.
"""

import pytest
from typing import ClassVar

from vkflow.commands.parsing.validators import (
    Validator,
    Range,
    MinLength,
    MaxLength,
    Regex,
    Between,
)
from vkflow.commands.parsing.cutters import ValidatingCutter, IntegerCutter, WordCutter
from vkflow.exceptions import BadArgumentError


class TestValidator:
    """Tests for base Validator class."""

    def test_validate_returns_value(self):
        """Base validator should return value unchanged."""
        v = Validator()
        assert v.validate(42) == 42
        assert v.validate("hello") == "hello"
        assert v.validate([1, 2, 3]) == [1, 2, 3]

    def test_description_empty(self):
        """Base validator description should be empty."""
        v = Validator()
        assert v.description() == ""


class TestRange:
    """Tests for Range validator."""

    def test_valid_int_in_range(self):
        """Integer within range should pass."""
        v = Range(min=1, max=100)
        assert v.validate(50) == 50
        assert v.validate(1) == 1
        assert v.validate(100) == 100

    def test_valid_float_in_range(self):
        """Float within range should pass."""
        v = Range(min=0.0, max=1.0)
        assert v.validate(0.5) == 0.5
        assert v.validate(0.0) == 0.0
        assert v.validate(1.0) == 1.0

    def test_value_below_min(self):
        """Value below min should raise ValueError."""
        v = Range(min=1, max=100)
        with pytest.raises(ValueError) as exc_info:
            v.validate(0)
        assert "диапазоне" in str(exc_info.value)

    def test_value_above_max(self):
        """Value above max should raise ValueError."""
        v = Range(min=1, max=100)
        with pytest.raises(ValueError) as exc_info:
            v.validate(101)
        assert "диапазоне" in str(exc_info.value)

    def test_description(self):
        """Description should include min and max."""
        v = Range(min=1, max=100)
        desc = v.description()
        assert "1" in desc
        assert "100" in desc


class TestMinLength:
    """Tests for MinLength validator."""

    def test_valid_length(self):
        """String with sufficient length should pass."""
        v = MinLength(length=3)
        assert v.validate("hello") == "hello"
        assert v.validate("abc") == "abc"

    def test_too_short(self):
        """String shorter than min should raise ValueError."""
        v = MinLength(length=3)
        with pytest.raises(ValueError) as exc_info:
            v.validate("ab")
        assert "Минимальная длина" in str(exc_info.value)

    def test_empty_string(self):
        """Empty string with min length > 0 should fail."""
        v = MinLength(length=1)
        with pytest.raises(ValueError):
            v.validate("")

    def test_description(self):
        """Description should include length."""
        v = MinLength(length=5)
        desc = v.description()
        assert "5" in desc
        assert "минимум" in desc


class TestMaxLength:
    """Tests for MaxLength validator."""

    def test_valid_length(self):
        """String within max length should pass."""
        v = MaxLength(length=10)
        assert v.validate("hello") == "hello"
        assert v.validate("") == ""

    def test_too_long(self):
        """String longer than max should raise ValueError."""
        v = MaxLength(length=5)
        with pytest.raises(ValueError) as exc_info:
            v.validate("toolongstring")
        assert "Максимальная длина" in str(exc_info.value)

    def test_exact_length(self):
        """String exactly at max length should pass."""
        v = MaxLength(length=5)
        assert v.validate("hello") == "hello"

    def test_description(self):
        """Description should include length."""
        v = MaxLength(length=20)
        desc = v.description()
        assert "20" in desc
        assert "максимум" in desc


class TestRegex:
    """Tests for Regex validator."""

    def test_valid_match(self):
        """String matching pattern should pass."""
        v = Regex(pattern=r"^[a-zA-Z]+$")
        assert v.validate("hello") == "hello"
        assert v.validate("ABC") == "ABC"

    def test_no_match(self):
        """String not matching pattern should raise ValueError."""
        v = Regex(pattern=r"^[a-zA-Z]+$")
        with pytest.raises(ValueError) as exc_info:
            v.validate("hello123")
        assert "паттерн" in str(exc_info.value).lower() or "pattern" in str(exc_info.value).lower()

    def test_custom_message(self):
        """Custom error message should be used."""
        v = Regex(pattern=r"^\d+$", message="Только цифры!")
        with pytest.raises(ValueError) as exc_info:
            v.validate("abc")
        assert "Только цифры!" in str(exc_info.value)

    def test_description_with_custom_message(self):
        """Description should use custom message if provided."""
        v = Regex(pattern=r"^\d+$", message="Только цифры!")
        assert v.description() == "Только цифры!"

    def test_description_without_custom_message(self):
        """Description should include pattern if no custom message."""
        v = Regex(pattern=r"^\d+$")
        desc = v.description()
        assert r"^\d+$" in desc


class TestBetween:
    """Tests for Between validator (Greedy constraints)."""

    def test_valid_count(self):
        """List with valid count should pass."""
        v = Between(min=2, max=5)
        assert v.validate([1, 2]) == [1, 2]
        assert v.validate([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]

    def test_too_few_items(self):
        """List with too few items should raise ValueError."""
        v = Between(min=2, max=5)
        with pytest.raises(ValueError) as exc_info:
            v.validate([1])
        assert "Минимум" in str(exc_info.value)

    def test_too_many_items(self):
        """List with too many items should raise ValueError."""
        v = Between(min=2, max=5)
        with pytest.raises(ValueError) as exc_info:
            v.validate([1, 2, 3, 4, 5, 6])
        assert "Максимум" in str(exc_info.value)

    def test_empty_list(self):
        """Empty list with min > 0 should fail."""
        v = Between(min=1, max=10)
        with pytest.raises(ValueError):
            v.validate([])

    def test_description(self):
        """Description should include min and max."""
        v = Between(min=2, max=10)
        desc = v.description()
        assert "2" in desc
        assert "10" in desc
        assert "элементов" in desc


class TestValidatingCutter:
    """Tests for ValidatingCutter wrapper."""

    @pytest.fixture
    def mock_ctx(self):
        """Create a mock NewMessage context."""

        class MockMessage:
            text = "test"
            is_cropped = False
            reply_message = None
            fwd_messages: ClassVar[list] = []
            attachments: ClassVar[list] = []

        class MockCtx:
            msg = MockMessage()
            api = None
            argument_processing_payload: ClassVar[dict] = {}

        return MockCtx()

    @pytest.mark.asyncio
    async def test_valid_value_passes(self, mock_ctx):
        """Valid value should pass through validators."""
        inner = IntegerCutter()
        validators = [Range(min=1, max=100)]
        cutter = ValidatingCutter(inner, validators)

        result = await cutter.cut_part(mock_ctx, "50")
        assert result.parsed_part == 50

    @pytest.mark.asyncio
    async def test_invalid_value_raises(self, mock_ctx):
        """Invalid value should raise BadArgumentError."""
        inner = IntegerCutter()
        validators = [Range(min=1, max=100)]
        cutter = ValidatingCutter(inner, validators)

        with pytest.raises(BadArgumentError):
            await cutter.cut_part(mock_ctx, "200")

    @pytest.mark.asyncio
    async def test_multiple_validators(self, mock_ctx):
        """Multiple validators should all be applied."""
        inner = WordCutter()
        validators = [MinLength(length=3), MaxLength(length=10)]
        cutter = ValidatingCutter(inner, validators)

        # Valid
        result = await cutter.cut_part(mock_ctx, "hello")
        assert result.parsed_part == "hello"

        # Too short
        with pytest.raises(BadArgumentError):
            await cutter.cut_part(mock_ctx, "ab")

        # Too long
        with pytest.raises(BadArgumentError):
            await cutter.cut_part(mock_ctx, "verylongstring")

    def test_gen_doc_with_constraints(self):
        """Documentation should include validator constraints."""
        inner = IntegerCutter()
        validators = [Range(min=1, max=100)]
        cutter = ValidatingCutter(inner, validators)

        doc = cutter.gen_doc()
        assert "1" in doc
        assert "100" in doc

    def test_gen_doc_multiple_validators(self):
        """Documentation should include all validator descriptions."""
        inner = WordCutter()
        validators = [MinLength(length=3), MaxLength(length=10)]
        cutter = ValidatingCutter(inner, validators)

        doc = cutter.gen_doc()
        assert "3" in doc
        assert "10" in doc


class TestCombinedValidators:
    """Tests for combining multiple validators."""

    def test_minlength_and_maxlength(self):
        """MinLength and MaxLength should work together."""
        validators = [MinLength(length=3), MaxLength(length=10)]

        # Valid
        value = "hello"
        for v in validators:
            value = v.validate(value)
        assert value == "hello"

        # Too short
        with pytest.raises(ValueError):
            value = "ab"
            for v in validators:
                value = v.validate(value)

        # Too long
        with pytest.raises(ValueError):
            value = "verylongstring"
            for v in validators:
                value = v.validate(value)

    def test_minlength_maxlength_regex(self):
        """Three validators should work together."""
        validators = [MinLength(length=3), MaxLength(length=20), Regex(pattern=r"^[a-zA-Z]+$")]

        # Valid
        value = "hello"
        for v in validators:
            value = v.validate(value)
        assert value == "hello"

        # Invalid (contains numbers)
        with pytest.raises(ValueError):
            value = "hello123"
            for v in validators:
                value = v.validate(value)
