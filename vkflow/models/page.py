from __future__ import annotations

import abc
import typing

from vkflow.base.wrapper import Wrapper
from vkflow.utils.media import get_user_registration_date

if typing.TYPE_CHECKING:  # pragma: no cover
    import aiohttp
    import datetime

    from vkflow.api import API


T = typing.TypeVar("T")

FieldsTypevar = typing.TypeVar("FieldsTypevar")
IDType: typing.TypeAlias = str | int


class Page(Wrapper, abc.ABC):
    _mention_prefix: str

    @property
    @abc.abstractmethod
    def fullname(self) -> str: ...

    @abc.abstractmethod
    def is_group(self) -> bool: ...

    @abc.abstractmethod
    def is_user(self) -> bool: ...

    @classmethod
    @abc.abstractmethod
    async def fetch_one(
        cls: type[T],
        api: API,
        id: IDType,
        /,
        *,
        fields: list[str] | None = None,
    ) -> T:
        pass

    @classmethod
    @abc.abstractmethod
    async def fetch_many(
        cls: type[T],
        api: API,
        /,
        *ids: IDType,
        fields: list[str] | None = None,
    ) -> list[T]:
        pass

    @property
    def id(self) -> int:
        return self.fields["id"]

    def mention(self, alias: str | None = None) -> str:
        """
        Создает упоминание пользователя либо с `alias` либо с его именем
        """
        if alias:
            updated_alias = format(self, alias)
            mention = f"[{self._mention_prefix}{self.id}|{updated_alias}]"
        else:
            mention = f"[{self._mention_prefix}{self.id}|{self.fullname}]"

        return mention

    def _extra_fields_to_format(self) -> dict:
        return {"fullname": self.fullname, "id": self.id}

    def __format__(self, format_spec) -> str:
        format_value = super().__format__(format_spec)

        if format_spec.startswith("@"):
            format_value = format_value[1:]
            return self.mention(format_value)

        return format_value

    def __repr__(self):
        return f"<vkflow.{self.__class__.__name__} fullname={self.fullname!r}>"


class Group(Page):
    _mention_prefix = "club"
    default_fields = ()

    @property
    def fullname(self) -> str:
        return self.fields["name"]

    def is_group(self) -> bool:
        return True

    def is_user(self) -> bool:
        return False

    @classmethod
    async def fetch_one(
        cls: type[Group],
        api: API,
        id: IDType,
        /,
        *,
        fields: list[str] | None = None,
    ) -> Group:
        response = await api.use_cache().method(
            "groups.get_by_id",
            group_id=id,
            fields=fields or cls.default_fields,
        )
        if isinstance(response, dict) and "groups" in response:
            return cls(response["groups"][0])
        return cls(response[0])

    @classmethod
    async def fetch_many(
        cls: type[Group],
        api: API,
        /,
        *ids: IDType,
        fields: list[str] | None = None,
    ) -> list[Group]:
        response = await api.use_cache().method(
            "groups.get_by_id",
            group_id=ids,
            fields=fields or cls.default_fields,
        )
        if isinstance(response, dict) and "groups" in response:
            response = response["groups"]
        return [cls(group) for group in response]


class User(Page, typing.Generic[FieldsTypevar]):
    _mention_prefix = "id"
    default_fields = ("sex",)

    def is_group(self) -> bool:
        return False

    def is_user(self) -> bool:
        return True

    @property
    def fullname(self) -> str:
        return f"""{self.fields["first_name"]} {self.fields["last_name"]}"""

    @property
    def id(self):
        return self.fields["id"]

    @property
    def fn(self):
        return self.fields["first_name"]

    @property
    def ln(self):
        return self.fields["last_name"]

    def if_gender(self, female: T, male: T = "", default: T | None = None) -> T | None:
        try:
            gender = self.fields["sex"]
        except KeyError as err:
            raise KeyError(
                f"User {self.id} must be fetched with field 'sex' to determine gender. "
                "Use fetch_one/fetch_many with fields=['sex'] or include 'sex' in default_fields."
            ) from err

        match (gender, default):
            case (1, _):
                return female
            case (2, _):
                return male
            case (0, None):
                return male
            case (0, default_value):
                return default_value
            case _:
                return default if default is not None else male

    def _extra_fields_to_format(self):
        extra_fields = super()._extra_fields_to_format()
        extra_fields.update(fn=self.fn, ln=self.ln)

        return extra_fields

    async def get_registration_date(
        self, session: aiohttp.ClientSession | None = None
    ) -> datetime.datetime:
        return await get_user_registration_date(self.id, session=session)

    @classmethod
    async def fetch_one(
        cls: type[User],
        api: API,
        id: IDType,
        /,
        *,
        fields: list[str] | None = None,
        name_case: str | None = None,
    ) -> User:
        user = await api.use_cache().method(
            "users.get",
            user_ids=id,
            fields=fields or cls.default_fields,
            name_case=name_case,
        )

        return cls(user[0])

    @classmethod
    async def fetch_many(
        cls: type[User],
        api: API,
        /,
        *ids: IDType,
        fields: list[str] | None = None,
        name_case: str | None = None,
    ) -> list[User]:
        users = await api.use_cache().method(
            "users.get",
            user_ids=ids,
            fields=fields or cls.default_fields,
            name_case=name_case,
        )

        return [cls(user) for user in users]
