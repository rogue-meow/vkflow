from __future__ import annotations

import typing
import dataclasses

from enum import IntEnum


FormatType: typing.TypeAlias = typing.Literal[
    "bold",
    "italic",
    "underline",
    "url",
]


def _get_vk_length(string: str) -> int:
    return len(string.encode("utf-16-le")) // 2


class TokenType(IntEnum):
    TEXT = 0
    BOLD = 1
    ITALIC = 2
    UNDER = 3
    LINK = 4
    STAR3 = 5
    MENTION = 6


@dataclasses.dataclass(frozen=True, slots=True)
class FormatSegment:
    type: FormatType

    offset: int
    length: int

    data: dict[str, typing.Any] | None = None

    def as_dict(self) -> dict[str, typing.Any]:
        result = {
            "type": self.type,
            "offset": self.offset,
            "length": self.length,
        }

        if self.data:
            result.update(self.data)
        return result


class TextBuilder:
    __slots__ = ("_buffer", "_current_offset", "segments")

    def __init__(self) -> None:
        self._buffer: list[str] = []
        self._current_offset: int = 0

        self.segments: list[FormatSegment] = []

    def append(self, text: str) -> None:
        if not text:
            return

        self._buffer.append(text)
        self._current_offset += _get_vk_length(text)

    def append_as_single_char(self, text: str) -> None:
        """
        Append text to buffer but count it as 1 character for offset.
        Used for VK mentions which are counted as 1 character for format offsets.
        """
        if not text:
            return

        self._buffer.append(text)
        self._current_offset += 1

    def add_segment(
        self, seg_type: FormatType, start_offset: int, end_offset: int, data: dict | None = None
    ) -> None:
        length = end_offset - start_offset

        if length > 0:
            self.segments.append(FormatSegment(seg_type, start_offset, length, data))

    def get_text(self) -> str:
        return "".join(self._buffer)

    @property
    def current_offset(self) -> int:
        return self._current_offset


@dataclasses.dataclass(slots=True)
class Token:
    type: TokenType
    start: int
    length: int
    raw: str


class MarkdownParser:
    VERSION = 1

    @classmethod
    def parse(cls, text: str) -> tuple[str, dict[str, typing.Any]]:
        if not text:
            return text, {"version": cls.VERSION, "items": []}

        tokens = cls._tokenize(text)
        actions = cls._analyze_structure(text, tokens)

        builder = TextBuilder()
        cls._build(text, tokens, actions, builder)

        format_data = {"version": cls.VERSION, "items": [seg.as_dict() for seg in builder.segments]}

        return builder.get_text(), format_data

    @classmethod
    def _tokenize(cls, text: str) -> list[Token]:
        tokens = []

        i = 0
        length = len(text)

        while i < length:
            char = text[i]

            if char == "[":
                res = cls._try_parse_mention(text, i)

                if res:
                    tokens.append(Token(TokenType.MENTION, i, res, text[i : i + res]))
                    i += res
                    continue

                res = cls._try_parse_link(text, i)

                if res:
                    tokens.append(Token(TokenType.LINK, i, res, text[i : i + res]))
                    i += res

                    continue

            if char == "_" and i + 1 < length and text[i + 1] == "_":
                tokens.append(Token(TokenType.UNDER, i, 2, "__"))
                i += 2

                continue

            if char == "*":
                star_len = 1

                if i + 1 < length and text[i + 1] == "*":
                    star_len = 2

                    if i + 2 < length and text[i + 2] == "*":
                        star_len = 3

                if i + star_len < length and text[i + star_len] == "*":
                    tokens.append(Token(TokenType.TEXT, i, star_len + 1, "*" * (star_len + 1)))
                    i += star_len + 1

                    continue

                if star_len == 3:
                    tokens.append(Token(TokenType.STAR3, i, 3, "***"))
                elif star_len == 2:
                    tokens.append(Token(TokenType.BOLD, i, 2, "**"))
                else:
                    tokens.append(Token(TokenType.ITALIC, i, 1, "*"))

                i += star_len
                continue

            i += 1

        return tokens

    @classmethod
    def _analyze_structure(cls, text: str, tokens: list[Token]) -> dict[int, list[tuple[str, FormatType]]]:
        actions: dict[int, list[tuple[str, FormatType]]] = {i: [] for i in range(len(tokens))}

        stack_bold: list[int] = []
        stack_under: list[int] = []
        stack_italic: list[int] = []

        for i, token in enumerate(tokens):
            if token.type == TokenType.LINK or token.type == TokenType.MENTION:
                continue

            if token.type == TokenType.UNDER:
                if stack_under:
                    opener_idx = stack_under.pop()

                    actions[opener_idx].append(("open", "underline"))
                    actions[i].append(("close", "underline"))
                else:
                    stack_under.append(i)

            elif token.type == TokenType.BOLD:
                if stack_bold:
                    opener_idx = stack_bold.pop()

                    actions[opener_idx].append(("open", "bold"))
                    actions[i].append(("close", "bold"))
                else:
                    stack_bold.append(i)

            elif token.type == TokenType.ITALIC:
                prev_is_space = token.start > 0 and text[token.start - 1] == " "
                next_is_space = token.start + 1 < len(text) and text[token.start + 1] == " "

                if stack_italic and not prev_is_space:
                    opener_idx = stack_italic.pop()

                    actions[opener_idx].append(("open", "italic"))
                    actions[i].append(("close", "italic"))

                elif not next_is_space:
                    stack_italic.append(i)

            elif token.type == TokenType.STAR3:
                remaining_stars = 3

                if remaining_stars >= 2 and stack_bold:
                    opener_idx = stack_bold.pop()

                    actions[opener_idx].append(("open", "bold"))
                    actions[i].append(("close", "bold"))

                    remaining_stars -= 2

                prev_is_space = token.start > 0 and text[token.start - 1] == " "

                if remaining_stars >= 1 and stack_italic and not prev_is_space:
                    opener_idx = stack_italic.pop()

                    actions[opener_idx].append(("open", "italic"))
                    actions[i].append(("close", "italic"))

                    remaining_stars -= 1

                next_is_space = token.start + 3 < len(text) and text[token.start + 3] == " "

                if not next_is_space:
                    if remaining_stars == 3:
                        stack_bold.append(i)
                        stack_italic.append(i)

                    elif remaining_stars == 2:
                        stack_bold.append(i)

                    elif remaining_stars == 1:
                        stack_italic.append(i)

        return actions

    @classmethod
    def _build(cls, text: str, tokens: list[Token], actions_map: dict, builder: TextBuilder) -> None:
        last_idx = 0

        active_starts: dict[FormatType, int | None] = {"bold": None, "italic": None, "underline": None}

        for i, token in enumerate(tokens):
            if token.start > last_idx:
                builder.append(text[last_idx : token.start])

            last_idx = token.start + token.length
            token_actions = actions_map[i]

            if token.type == TokenType.MENTION:
                builder.append(token.raw)
                continue

            if token.type == TokenType.LINK:
                start = builder.current_offset

                close_sq = token.raw.find("]")
                visible_text = token.raw[1:close_sq]

                url_part = token.raw[close_sq + 1 :]
                url = url_part[1:-1]

                builder.append(visible_text)
                builder.add_segment("url", start, builder.current_offset, {"url": url})

                continue

            used_chars = 0

            closes = [a for a in token_actions if a[0] == "close"]
            opens = [a for a in token_actions if a[0] == "open"]

            for _, fmt_type in closes:
                if fmt_type == "bold":
                    used_chars += 2
                elif fmt_type == "italic":
                    used_chars += 1
                elif fmt_type == "underline":
                    used_chars += 2

                start_off = active_starts[fmt_type]

                if start_off is not None:
                    builder.add_segment(fmt_type, start_off, builder.current_offset)
                    active_starts[fmt_type] = None

            for _, fmt_type in opens:
                if fmt_type == "bold":
                    used_chars += 2
                elif fmt_type == "italic":
                    used_chars += 1
                elif fmt_type == "underline":
                    used_chars += 2

                active_starts[fmt_type] = builder.current_offset

            if token.type == TokenType.STAR3:
                total_chars = 3
            elif token.type == TokenType.BOLD or token.type == TokenType.UNDER:
                total_chars = 2
            else:
                total_chars = 1

            remaining = total_chars - used_chars

            if remaining > 0:
                raw_char = token.raw[0]
                builder.append(raw_char * remaining)

        if last_idx < len(text):
            builder.append(text[last_idx:])

    @classmethod
    def _try_parse_mention(cls, text: str, i: int) -> int | None:
        """
        Parse VK mentions: [id123|text], [club123|text], [public123|text]
        Returns length of the match or None if not a mention.
        """
        close_bracket = text.find("]", i + 1)

        if close_bracket == -1:
            return None

        content = text[i + 1 : close_bracket]

        if "|" not in content:
            return None

        pipe_pos = content.find("|")
        prefix_part = content[:pipe_pos]

        valid_prefixes = ("id", "club", "public")
        is_valid = False

        for prefix in valid_prefixes:
            if prefix_part.startswith(prefix):
                digits = prefix_part[len(prefix) :]
                if digits.isdigit() and len(digits) > 0:
                    is_valid = True
                    break

        if not is_valid:
            return None

        return close_bracket + 1 - i

    @classmethod
    def _try_parse_link(cls, text: str, i: int) -> int | None:
        close_bracket = text.find("]", i + 1)

        if close_bracket == -1:
            return None

        if not text[i + 1 : close_bracket]:
            return None

        if close_bracket + 1 >= len(text) or text[close_bracket + 1] != "(":
            return None

        close_paren = text.find(")", close_bracket + 2)

        if close_paren == -1:
            return None

        if not text[close_bracket + 2 : close_paren]:
            return None

        return close_paren + 1 - i


def format_message(text: str | None) -> tuple[str | None, dict[str, typing.Any] | None]:
    if text is None:
        return None, None

    plain_text, format_data = MarkdownParser.parse(text)

    if not format_data["items"]:
        return plain_text, None

    return plain_text, format_data


__all__ = (
    "FormatSegment",
    "MarkdownParser",
    "format_message",
)
