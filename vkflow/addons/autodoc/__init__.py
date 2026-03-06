from __future__ import annotations

import inspect
import pathlib
import shutil
from typing import TYPE_CHECKING, Any

from vkflow.addons.base import AddonMeta, BaseAddon

if TYPE_CHECKING:
    from vkflow.app.bot import App, Bot

_PACKAGE_DIR = pathlib.Path(__file__).parent


class _TemplateAppProxy:
    """Proxy object that provides the interface templates expect from App."""

    def __init__(self, name: str, description: str, site_title: str, prefixes: Any):
        self.name = name
        self.description = description
        self.site_title = site_title
        self.prefixes = prefixes


class AutoDoc(BaseAddon):
    meta = AddonMeta(
        name="autodoc",
        description="HTML documentation generator for bot commands",
        version="1.0.0",
        required_packages=["jinja2"],
        pip_extras="autodoc",
    )

    def __init__(
        self,
        *,
        site_title: str = "Документация к чат-боту",
        directory: str = "autodocs",
        filename: str = "index.html",
        build_on_startup: bool = False,
        templates_dir: pathlib.Path | None = None,
        assets_dir: pathlib.Path | None = None,
    ):
        super().__init__()
        self.site_title = site_title
        self.directory = directory
        self.filename = filename
        self.build_on_startup = build_on_startup

        self.templates_dir = templates_dir or _PACKAGE_DIR / "templates"
        self.assets_dir = assets_dir or _PACKAGE_DIR / "assets"

    def setup(self, app: App) -> None:
        self.check_dependencies()
        super().setup(app)

    async def on_startup(self, app: App, bots: list[Bot]) -> None:
        if self.build_on_startup:
            self.render()

    def render(
        self,
        directory: str | None = None,
        filename: str | None = None,
    ) -> pathlib.Path:
        import jinja2
        from loguru import logger

        directory = directory or self.directory
        filename = filename or self.filename

        env = jinja2.Environment(loader=jinja2.FileSystemLoader(self.templates_dir))

        main_template = env.get_template("index.html")
        saved_path_dir = pathlib.Path(directory)

        if saved_path_dir.exists():
            shutil.rmtree(saved_path_dir)

        saved_path_dir.mkdir()

        shutil.copytree(self.assets_dir, saved_path_dir / "assets")
        organized_data = self._organize_commands()

        proxy = _TemplateAppProxy(
            name=self.app.name,
            description=self.app.description,
            site_title=self.site_title,
            prefixes=self.app.prefixes,
        )

        saving_path = saved_path_dir / filename

        with open(saving_path, "wb+") as autodoc_file:
            main_template.stream(app=proxy, organized_data=organized_data).dump(
                autodoc_file, encoding="utf-8"
            )

        logger.opt(colors=True).success(
            "Documentation was built in directory <c>{directory}</c>",
            directory=directory,
        )

        return saving_path

    def _organize_commands(self) -> list[dict]:
        try:
            from vkflow.commands.core import Command as ExtCommand
        except ImportError:
            ExtCommand = None  # noqa: N806

        app = self.app
        sections = []
        processed_commands: set[int] = set()

        COMMAND_CLASS_DOCSTRING = None  # noqa: N806

        if ExtCommand:
            COMMAND_CLASS_DOCSTRING = inspect.getdoc(ExtCommand)  # noqa: N806

        def is_class_docstring(text: str) -> bool:
            if not text:
                return False

            if COMMAND_CLASS_DOCSTRING:
                text_normalized = text.strip()

                if text_normalized == COMMAND_CLASS_DOCSTRING:
                    return True

                if text_normalized.lower() == COMMAND_CLASS_DOCSTRING.lower():
                    return True

            return bool(text.lower().strip().startswith("a class that represents a command"))

        def process_command_description(cmd: Any) -> None:
            if ExtCommand and isinstance(cmd, ExtCommand):
                if hasattr(cmd, "_autodoc_description_resolved"):
                    return

                cmd._autodoc_brief = cmd.brief if cmd.brief else ""
                description_text = ""

                if hasattr(cmd, "__doc__") and cmd.__doc__ and not is_class_docstring(cmd.__doc__):
                    description_text = cmd.__doc__

                cmd._autodoc_description = description_text

                help_text = cmd.help if cmd.help else ""

                if help_text and is_class_docstring(help_text):
                    help_text = ""

                cmd._autodoc_full_description = help_text
                cmd._autodoc_description_resolved = True

            else:
                if not hasattr(cmd, "_autodoc_description_resolved"):
                    cmd._autodoc_brief = ""
                    cmd._autodoc_description = getattr(cmd, "trusted_description", "")
                    cmd._autodoc_full_description = ""
                    cmd._autodoc_description_resolved = True

        for cog in app._cogs.values():
            cog_commands = []

            if hasattr(cog, "_cog_commands"):
                for cmd in cog._cog_commands:
                    if not getattr(cmd, "exclude_from_autodoc", False):
                        process_command_description(cmd)
                        cog_commands.append(cmd)
                        processed_commands.add(id(cmd))

            if cog_commands:
                sections.append(
                    {
                        "type": "cog",
                        "name": cog.qualified_name,
                        "description": cog.description,
                        "commands": cog_commands,
                    }
                )

        for package in app.packages:
            if package is app:
                continue

            pkg_commands = []

            for cmd in package.commands:
                if id(cmd) not in processed_commands and not getattr(cmd, "exclude_from_autodoc", False):
                    process_command_description(cmd)
                    pkg_commands.append(cmd)
                    processed_commands.add(id(cmd))

            if pkg_commands:
                package_name = getattr(package, "name", package.__class__.__name__)
                package_desc = getattr(package, "description", "")

                sections.append(
                    {
                        "type": "package",
                        "name": package_name,
                        "description": package_desc,
                        "commands": pkg_commands,
                    }
                )

        app_commands = []

        for cmd in app.commands:
            if id(cmd) not in processed_commands and not getattr(cmd, "exclude_from_autodoc", False):
                process_command_description(cmd)
                app_commands.append(cmd)
                processed_commands.add(id(cmd))

        if app_commands:
            sections.append(
                {
                    "type": "package",
                    "name": "Основные команды",
                    "description": "Команды приложения",
                    "commands": app_commands,
                }
            )

        return sections
