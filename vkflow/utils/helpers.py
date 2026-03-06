import random
import typing


def get_origin_typing(type: typing.Any) -> typing.Any:
    """
    Возвращает origin дженерик-типа, если он параметризован.
    Иначе возвращает тип как есть.
    """
    if typing.get_args(type):
        return typing.get_origin(type)
    return type


def random_id(side: int = 2**31 - 1) -> int:
    """
    Случайное число в диапазоне +-`side`.
    Используется для API метода `messages.send`.
    """
    return random.randint(-side, +side)


def peer(chat_id: int = 0) -> int:
    """Конвертирует chat_id в peer_id (chat_id + 2_000_000_000)."""
    return 2_000_000_000 + chat_id
