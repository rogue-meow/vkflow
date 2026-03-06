"""
Тесты для форматирования сообщений
"""

from vkflow.formatting import (
    FormatSegment,
    MarkdownParser,
    format_message,
)


class TestFormatSegment:
    def test_format_segment_creation(self):
        """Тест создания сегмента форматирования"""
        segment = FormatSegment(type="bold", offset=0, length=4)
        assert segment.type == "bold"
        assert segment.offset == 0
        assert segment.length == 4

    def test_format_segment_with_data(self):
        """Тест создания сегмента с дополнительными данными"""
        segment = FormatSegment(type="url", offset=0, length=4, data={"url": "https://vk.com"})
        result = segment.as_dict()
        assert result["type"] == "url"
        assert result["url"] == "https://vk.com"


class TestMarkdownParser:
    def test_bold_text(self):
        """Тест парсинга жирного текста"""
        text = "Привет, **мир**!"
        plain_text, format_data = MarkdownParser.parse(text)

        assert plain_text == "Привет, мир!"
        assert format_data["version"] == 1
        assert len(format_data["items"]) == 1
        assert format_data["items"][0]["type"] == "bold"
        assert format_data["items"][0]["offset"] == 8
        assert format_data["items"][0]["length"] == 3

    def test_italic_text(self):
        """Тест парсинга курсива"""
        text = "Это *курсив*"
        plain_text, format_data = MarkdownParser.parse(text)

        assert plain_text == "Это курсив"
        assert len(format_data["items"]) == 1
        assert format_data["items"][0]["type"] == "italic"

    def test_underline_text(self):
        """Тест парсинга подчеркнутого текста"""
        text = "Это __подчеркнуто__"
        plain_text, format_data = MarkdownParser.parse(text)

        assert plain_text == "Это подчеркнуто"
        assert len(format_data["items"]) == 1
        assert format_data["items"][0]["type"] == "underline"

    def test_link(self):
        """Тест парсинга ссылок"""
        text = "Посмотри [это](https://vk.com)!"
        plain_text, format_data = MarkdownParser.parse(text)

        assert plain_text == "Посмотри это!"
        assert len(format_data["items"]) == 1
        assert format_data["items"][0]["type"] == "url"
        assert format_data["items"][0]["url"] == "https://vk.com"

    def test_mixed_formatting(self):
        """Тест смешанного форматирования"""
        text = "**Жирный** и *курсив* и __подчеркнутый__"
        plain_text, format_data = MarkdownParser.parse(text)

        assert plain_text == "Жирный и курсив и подчеркнутый"
        assert len(format_data["items"]) == 3

        # Проверяем типы
        types = [item["type"] for item in format_data["items"]]
        assert "bold" in types
        assert "italic" in types
        assert "underline" in types

    def test_no_formatting(self):
        """Тест текста без форматирования"""
        text = "Обычный текст"
        plain_text, format_data = MarkdownParser.parse(text)

        assert plain_text == "Обычный текст"
        assert len(format_data["items"]) == 0

    def test_empty_text(self):
        """Тест пустого текста"""
        text = ""
        plain_text, format_data = MarkdownParser.parse(text)

        assert plain_text == ""
        assert len(format_data["items"]) == 0

    def test_multiple_bold_segments(self):
        """Тест нескольких жирных сегментов"""
        text = "**Первый** и **второй**"
        plain_text, format_data = MarkdownParser.parse(text)

        assert plain_text == "Первый и второй"
        assert len(format_data["items"]) == 2
        assert all(item["type"] == "bold" for item in format_data["items"])

    def test_cyrillic_offset_calculation(self):
        """Тест правильного расчета offset для кириллицы"""
        text = "Текст **жирный**"
        plain_text, format_data = MarkdownParser.parse(text)

        assert plain_text == "Текст жирный"
        assert format_data["items"][0]["offset"] == 6

    def test_emoji_with_formatting(self):
        """Тест форматирования с эмодзи"""
        text = "Привет **😊 мир**!"
        plain_text, format_data = MarkdownParser.parse(text)

        assert plain_text == "Привет 😊 мир!"
        assert len(format_data["items"]) == 1
        assert format_data["items"][0]["type"] == "bold"


class TestFormatMessage:
    def test_format_message_with_bold(self):
        """Тест format_message с жирным текстом"""
        plain_text, format_data = format_message("**Привет**")

        assert plain_text == "Привет"
        assert format_data is not None
        assert format_data["version"] == 1
        assert len(format_data["items"]) == 1

    def test_format_message_without_formatting(self):
        """Тест format_message без форматирования"""
        plain_text, format_data = format_message("Обычный текст")

        assert plain_text == "Обычный текст"
        assert format_data is None

    def test_format_message_none(self):
        """Тест format_message с None"""
        plain_text, format_data = format_message(None)

        assert plain_text is None
        assert format_data is None

    def test_complex_message(self):
        """Тест сложного сообщения"""
        text = "**Заголовок**\n\nЭто *важный* текст с [ссылкой](https://vk.com) и __подчеркиванием__."
        plain_text, format_data = format_message(text)

        assert plain_text == "Заголовок\n\nЭто важный текст с ссылкой и подчеркиванием."
        assert format_data is not None
        assert len(format_data["items"]) == 4

    def test_triple_asterisk_bold_italic(self):
        """Тест жирного + курсива с тройными звездочками"""
        text = "***Жирный и курсив***"
        plain_text, format_data = format_message(text)

        assert plain_text == "Жирный и курсив"
        assert format_data is not None
        assert len(format_data["items"]) == 2

        types = [item["type"] for item in format_data["items"]]
        assert "bold" in types
        assert "italic" in types

    def test_combined_bold_italic(self):
        """Тест комбинированного форматирования ***жирный** курсив*"""
        text = "***Привет, как** дела?*"
        plain_text, format_data = format_message(text)

        assert plain_text == "Привет, как дела?"
        assert format_data is not None
        assert len(format_data["items"]) == 2

        # bold for "Привет, как" (offset 0, length 11)
        assert format_data["items"][0]["type"] == "bold"
        assert format_data["items"][0]["offset"] == 0
        assert format_data["items"][0]["length"] == 11
        # italic for the whole "Привет, как дела?" (offset 0, length 17)
        assert format_data["items"][1]["type"] == "italic"
        assert format_data["items"][1]["offset"] == 0


class TestVKMentions:
    """Тесты для VK-упоминаний [id123|text] и [club123|text]"""

    def test_mention_preserves_text(self):
        """Тест что упоминание сохраняется в тексте"""
        text = "[id123|Имя] привет"
        plain_text, format_data = MarkdownParser.parse(text)

        assert plain_text == "[id123|Имя] привет"
        assert len(format_data["items"]) == 0

    def test_mention_offset_calculation(self):
        """Тест что offset вычисляется по полному тексту упоминания"""
        text = "[id123|Имя] **привет**"
        plain_text, format_data = MarkdownParser.parse(text)

        assert plain_text == "[id123|Имя] привет"
        assert len(format_data["items"]) == 1
        assert format_data["items"][0]["type"] == "bold"
        # VK counts offsets by FULL text including [id...|]
        # offset = len("[id123|Имя] ") = 12
        assert format_data["items"][0]["offset"] == 12
        assert format_data["items"][0]["length"] == 6  # "привет"

    def test_multiple_mentions_offset(self):
        """Тест offset с несколькими упоминаниями"""
        text = "[id1|А] и [id2|Б] **тест**"
        _, format_data = MarkdownParser.parse(text)

        assert len(format_data["items"]) == 1
        # VK counts by full text: "[id1|А] и [id2|Б] "
        # offset = len("[id1|А] и [id2|Б] ") = 18
        assert format_data["items"][0]["offset"] == 18
        assert format_data["items"][0]["length"] == 4

    def test_club_mention(self):
        """Тест упоминания группы [club123|text]"""
        text = "[club123|Группа] **важно**"
        plain_text, format_data = MarkdownParser.parse(text)

        assert "[club123|Группа]" in plain_text
        # offset = len("[club123|Группа] ") = 17
        assert format_data["items"][0]["offset"] == 17

    def test_public_mention(self):
        """Тест упоминания паблика [public123|text]"""
        text = "[public123|Паблик] **тест**"
        plain_text, format_data = MarkdownParser.parse(text)

        assert "[public123|Паблик]" in plain_text
        # offset = len("[public123|Паблик] ") = 19
        assert format_data["items"][0]["offset"] == 19

    def test_complex_message_with_mentions(self):
        """Тест сложного сообщения с упоминаниями"""
        text = """[id1058738053|Пользователю] выдан варн **(3/3)**
Причина: __мя-мя-мяв__

**Внимание!** У [id1058738053|пользователя] достигнут лимит варнов __(3/3)__"""

        plain_text, format_data = MarkdownParser.parse(text)

        # Проверяем что упоминания сохранены
        assert "[id1058738053|Пользователю]" in plain_text
        assert "[id1058738053|пользователя]" in plain_text

        # Проверяем offset'ы (по полному тексту)
        items = format_data["items"]
        assert len(items) == 4

        # Первый bold: (3/3) после "[id1058738053|Пользователю] выдан варн "
        # offset = len("[id1058738053|Пользователю] выдан варн ") = 39
        assert items[0]["type"] == "bold"
        assert items[0]["offset"] == 39
        assert items[0]["length"] == 5

        # Второй underline: мя-мя-мяв
        assert items[1]["type"] == "underline"
        assert items[1]["length"] == 9

        # Третий bold: Внимание!
        assert items[2]["type"] == "bold"
        assert items[2]["length"] == 9

        # Четвертый underline: (3/3)
        assert items[3]["type"] == "underline"
        assert items[3]["length"] == 5

    def test_invalid_mention_not_parsed(self):
        """Тест что невалидные упоминания не парсятся как mention"""
        # Нет | разделителя
        text = "[id123] **тест**"
        plain_text, _ = MarkdownParser.parse(text)
        assert plain_text == "[id123] тест"

        # Нет цифр после id
        text = "[idabc|текст] **тест**"
        plain_text, _ = MarkdownParser.parse(text)
        assert plain_text == "[idabc|текст] тест"

        # Неизвестный префикс
        text = "[user123|текст] **тест**"
        plain_text, _ = MarkdownParser.parse(text)
        assert plain_text == "[user123|текст] тест"

    def test_mention_protects_inner_markdown(self):
        """Тест что markdown внутри упоминания не парсится"""
        # Если бы внутри упоминания был *, он не должен парситься как italic
        text = "[id123|Имя*Фамилия] **тест**"
        plain_text, format_data = MarkdownParser.parse(text)

        assert plain_text == "[id123|Имя*Фамилия] тест"
        # Только один сегмент - bold для "тест"
        assert len(format_data["items"]) == 1
        assert format_data["items"][0]["type"] == "bold"
