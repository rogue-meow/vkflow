import json

from vkflow.json_parsers import json_parser_policy

try:
    import pygments.lexers
    import pygments.formatters

    _has_pygments = True
except ImportError:
    _has_pygments = False


def pretty_view(mapping: dict, /) -> str:
    """
    Форматирует словарь в читабельную JSON-строку
    с подсветкой синтаксиса (если установлен pygments).

    Arguments:
        mapping: Словарь для форматирования

    Returns:
        Отформатированная строка с подсветкой синтаксиса
        или без неё, если pygments не установлен
    """
    dumped = json.dumps(
        json.loads(json_parser_policy.dumps(mapping)),
        indent=4,
        ensure_ascii=False,
    )

    if _has_pygments:
        return pygments.highlight(
            dumped,
            pygments.lexers.JsonLexer(),
            pygments.formatters.TerminalFormatter(bg="light"),
        )

    return dumped
