from __future__ import annotations

import dataclasses
import importlib
from abc import ABC
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vkflow.app.bot import App, Bot


@dataclasses.dataclass(frozen=True)
class AddonMeta:
    """Metadata for an addon."""

    name: str
    description: str = ""
    version: str = "0.0.0"
    author: str = ""
    required_packages: list[str] = dataclasses.field(default_factory=list)
    pip_extras: str | None = None


class AddonDependencyError(ImportError):
    """Addon dependencies are not installed."""

    def __init__(self, addon_name: str, pip_extras: str | None = None):
        if pip_extras:
            msg = (
                f"Addon '{addon_name}' requires extra dependencies. "
                f"Install: pip install vkflow[{pip_extras}]"
            )
        else:
            msg = f"Addon '{addon_name}' has missing dependencies."
        super().__init__(msg)
        self.addon_name = addon_name
        self.pip_extras = pip_extras


class AddonConflictError(RuntimeError):
    """Two addons with the same meta.name."""

    def __init__(self, name: str, existing: Any, new: Any):
        super().__init__(
            f"Addon conflict: '{name}' is already registered "
            f"({type(existing).__name__}), cannot register {type(new).__name__}"
        )
        self.addon_name = name
        self.existing = existing
        self.new = new


class BaseAddon(ABC):
    """Base class for all VKQuick addons."""

    meta: AddonMeta

    def __init__(self):
        self._app: App | None = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "meta") or cls.meta is BaseAddon.__dict__.get("meta"):
            return

    @property
    def app(self) -> App:
        if self._app is None:
            raise RuntimeError(f"Addon '{self.meta.name}' is not attached to an App. Call setup() first.")
        return self._app

    def setup(self, app: App) -> None:
        self._app = app

    async def on_startup(self, app: App, bots: list[Bot]) -> None:  # noqa: B027
        pass

    async def on_shutdown(self, app: App, bots: list[Bot]) -> None:  # noqa: B027
        pass

    def check_dependencies(self) -> None:
        for package_name in self.meta.required_packages:
            try:
                importlib.import_module(package_name)
            except ImportError:
                raise AddonDependencyError(self.meta.name, self.meta.pip_extras) from None
