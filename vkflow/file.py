"""
Модуль для работы с файлами, которые могут быть загружены в VK
"""

from __future__ import annotations

import io
import mimetypes
import os
import typing
from pathlib import Path

if typing.TYPE_CHECKING:  # pragma: no cover
    FileSource: typing.TypeAlias = str | bytes | io.BytesIO | os.PathLike | Path


class File:
    """
    Класс для работы с файлами, которые могут быть загружены в VK.

    Поддерживает различные источники файлов:
    - Путь к файлу (str или PathLike)
    - URL (str начинающийся с http:// или https://)
    - Сырые байты (bytes)
    - IO-объект (BytesIO)

    Attributes:
        source: Источник файла (путь, URL, байты, или IO-объект)
        type: Тип загрузки ('photo', 'doc', 'video', 'audio_message', 'graffiti')
        filename: Имя файла (опционально)
        title: Название файла для отображения (опционально)
        tags: Теги для файла (опционально)

    Examples:
        >>> # Загрузка фотографии из файла
        >>> file = File("photo.jpg", type="photo")
        >>>
        >>> # Загрузка документа с кастомным именем
        >>> file = File("document.pdf", type="doc", filename="my_doc.pdf")
        >>>
        >>> # Загрузка голосового сообщения
        >>> file = File(audio_bytes, type="audio_message", filename="voice.ogg")
        >>>
        >>> # Загрузка фотографии по URL
        >>> file = File("https://example.com/image.jpg", type="photo")
        >>>
        >>> # Автоматическое определение типа по расширению
        >>> file = File("image.png")  # type будет определен как "photo"
        >>> file = File("document.pdf")  # type будет определен как "doc"
    """

    def __init__(
        self,
        source: FileSource,
        *,
        type: typing.Literal["photo", "doc", "video", "audio_message", "graffiti"] | None = None,
        filename: str | None = None,
        title: str | None = None,
        tags: str | None = None,
    ):
        """
        Инициализирует объект File.

        Args:
            source: Источник файла (путь, URL, байты, IO-объект)
            type: Тип загрузки. Если не указан, определяется автоматически
            filename: Имя файла (если не указано, определяется из source)
            title: Название для отображения
            tags: Теги для файла
        """
        self.source = source
        self.filename = filename or self._extract_filename()
        self.title = title
        self.tags = tags

        if type is None:
            self.type = self._detect_type()
        else:
            self.type = type

    def _extract_filename(self) -> str | None:
        """Извлекает имя файла из source"""
        if isinstance(self.source, (str, os.PathLike)):
            path_str = str(self.source)
            if path_str.startswith(("http://", "https://")):
                return path_str.split("/")[-1].split("?")[0] or None
            return Path(path_str).name
        return None

    def _detect_type(self) -> str:
        """
        Автоматически определяет тип файла на основе расширения или MIME-типа.

        Returns:
            Тип файла: 'photo', 'doc', 'video', 'audio_message', или 'graffiti'
        """
        if not self.filename:
            return "doc"

        ext = Path(self.filename).suffix.lower()
        _mime_type, _ = mimetypes.guess_type(self.filename)

        if ext == ".png" and self.filename.startswith("graffiti"):
            return "graffiti"
        if ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}:
            return "photo"
        if ext in {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}:
            return "video"
        if ext in {".ogg", ".opus"}:
            return "audio_message"
        return "doc"

    def is_url(self) -> bool:
        """Проверяет, является ли source URL"""
        return isinstance(self.source, str) and self.source.startswith(("http://", "https://"))

    def is_path(self) -> bool:
        """Проверяет, является ли source путем к файлу"""
        return isinstance(self.source, (str, os.PathLike, Path)) and not self.is_url()

    def is_bytes(self) -> bool:
        """Проверяет, является ли source байтами"""
        return isinstance(self.source, bytes)

    def is_io(self) -> bool:
        """Проверяет, является ли source IO-объектом"""
        return isinstance(self.source, io.BytesIO)

    def __repr__(self):
        return (
            f"<File type={self.type!r} filename={self.filename!r} source_type={type(self.source).__name__}>"
        )
