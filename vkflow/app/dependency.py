import typing
import inspect
import dataclasses

from vkflow.app.storages import NewMessage


@dataclasses.dataclass
class Depends:
    callback: typing.Callable[[NewMessage], typing.Any] | None = None


class ArgumentDependency(typing.NamedTuple):
    name: str | None
    handler: Depends


class DependencyMixin:
    def __init__(self):
        self._dependencies: list[ArgumentDependency] = []

    def parse_dependency_arguments(self, func: typing.Callable) -> None:
        parameters = inspect.signature(func).parameters
        for name, argument in parameters.items():
            if isinstance(argument.default, Depends):
                if argument.default.callback is None:
                    argument.default.callback = argument.annotation
                self._dependencies.append(ArgumentDependency(name=name, handler=argument.default))

    async def make_dependency_arguments(self, ctx: NewMessage) -> dict[str, typing.Any]:
        prepared_mapping = {}
        for dependency in self._dependencies:
            argument_value = dependency.handler.callback(ctx)

            if inspect.isawaitable(argument_value):
                argument_value = await argument_value

            if dependency.name is not None:
                prepared_mapping[dependency.name] = argument_value

        return prepared_mapping
