from __future__ import annotations

import importlib

from loguru import logger

from .base import AddonMeta, AddonConflictError, AddonDependencyError, BaseAddon

_INTERNAL_ADDONS = {
    "AutoDoc": ("vkflow.addons.autodoc", ["jinja2"], "autodoc"),
    "FastAPIAddon": ("vkflow.addons.fastapi", ["fastapi", "uvicorn"], "fastapi"),
}


def __getattr__(name: str):
    if name in _INTERNAL_ADDONS:
        module_path, deps, extra = _INTERNAL_ADDONS[name]
        for dep in deps:
            try:
                __import__(dep)
            except ImportError:
                raise ImportError(
                    f"Addon '{name}' requires extra dependencies. Install: pip install vkflow[{extra}]"
                ) from None
        mod = importlib.import_module(module_path)
        cls = getattr(mod, name)
        globals()[name] = cls
        return cls

    from importlib.metadata import entry_points

    eps = entry_points(group="vkflow.addons")
    for ep in eps:
        if ep.name == name:
            cls = ep.load()
            globals()[name] = cls
            return cls

    raise AttributeError(f"module 'vkflow.addons' has no attribute {name!r}")


def get_available_addons() -> dict[str, type[BaseAddon]]:
    """Return only addons whose dependencies are installed."""
    available: dict[str, type[BaseAddon]] = {}

    for cls_name, (module_path, deps, _extra) in _INTERNAL_ADDONS.items():
        all_deps_ok = True
        for dep in deps:
            try:
                __import__(dep)
            except ImportError:
                all_deps_ok = False
                break
        if all_deps_ok:
            mod = importlib.import_module(module_path)
            available[cls_name] = getattr(mod, cls_name)

    from importlib.metadata import entry_points

    eps = entry_points(group="vkflow.addons")
    for ep in eps:
        if ep.name not in available:
            try:
                cls = ep.load()
                available[ep.name] = cls
            except Exception as exc:
                logger.debug("Failed to load addon entry point {!r}: {}", ep.name, exc)

    return available


__all__ = [
    "AddonConflictError",
    "AddonDependencyError",
    "AddonMeta",
    "BaseAddon",
    "get_available_addons",
]
