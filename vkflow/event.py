from vkflow.base.event import BaseEvent


class GroupEvent(BaseEvent[dict]):
    """
    Обертка над событием в группе
    """

    @property
    def type(self) -> str:
        return self._content["type"]

    @property
    def object(self) -> dict:
        return self._content["object"]

    @property
    def group_id(self) -> int:
        return self._content["group_id"]


class UserEvent(BaseEvent[list]):
    """
    Обертка над событием у пользователя
    """

    @property
    def type(self) -> int:
        return self._content[0]

    @property
    def object(self) -> list:
        return self._content
