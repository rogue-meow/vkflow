from vkflow.json_parsers import json_parser_policy
from vkflow.base.api_serializable import APISerializableMixin


class UIBuilder(APISerializableMixin):
    scheme: dict
    _dumped_scheme: str | None = None

    def represent_as_api_param(self) -> str | bytes:
        if self._dumped_scheme is None:
            self._dumped_scheme = json_parser_policy.dumps(self.scheme)
        return self._dumped_scheme
