import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import click
import toml
from pydantic import ValidationError

from delfino import commands
from delfino.constants import ENTRY_POINT, PYPROJECT_TOML_FILENAME
from delfino.contexts import AppContext
from delfino.models.pyproject_toml import PyprojectToml
from delfino.utils import find_commands, get_package_manager


class Commands(click.MultiCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        sys.path.append(os.getcwd())

        self._project_root = Path(os.getcwd())
        pyproject_toml_path = (self._project_root / PYPROJECT_TOML_FILENAME).relative_to(self._project_root)

        # When evaluating available commands, the program should not fail. We save the exception
        # to show it only when a command is executed.
        self._pyproject_toml: Union[PyprojectToml, Exception]
        self._hidden_plugins: Set[str] = set()

        try:
            self._pyproject_toml = PyprojectToml(file_path=pyproject_toml_path, **toml.load(pyproject_toml_path))
            self._hidden_plugins = self._pyproject_toml.tool.delfino.disable_commands
        except (FileNotFoundError, ValidationError) as exc:
            self._pyproject_toml = exc

        self._plugins: Dict[str, click.Command] = find_commands(commands.__package__, required=True)
        self._plugins.update(find_commands("commands", required=False))
        self._plugins.update(find_commands("tasks", required=False, new_name="commands"))

    def list_commands(self, ctx: click.Context) -> List[str]:
        """Override to hide commands marked as hidden in the ``pyproject.toml`` file."""
        del ctx
        return sorted(set(self._plugins.keys()).difference(self._hidden_plugins))

    def get_command(self, ctx: click.Context, cmd_name: str) -> Optional[click.Command]:
        """Override to give all commands a common ``AppContext`` or fail if ``pyproject.toml`` is broken/missing."""
        if isinstance(self._pyproject_toml, Exception):
            click.secho(f"Delfino appears to be misconfigured: {self._pyproject_toml}", fg="red", err=True)
            raise click.Abort() from self._pyproject_toml

        ctx.obj = AppContext(
            project_root=self._project_root,
            py_project_toml=self._pyproject_toml,
            package_manager=get_package_manager(self._project_root, self._pyproject_toml),
        )

        return self._plugins[cmd_name]

    def invoke(self, ctx: click.Context) -> Any:
        """Override to turn ``AssertionError`` exception into ``click.exceptions.Exit``."""
        try:
            return super().invoke(ctx)
        except AssertionError as exc:
            click.secho(f"Command '{ctx.invoked_subcommand}' is misconfigured. {exc}", fg="red", err=True)
            raise click.exceptions.Exit(1)

    def get_help(self, *args, **kwargs) -> str:
        help_str = super().get_help(*args, **kwargs)

        if self._hidden_plugins:
            help_str += (
                f"\n\nDisabled command{'s' if len(self._hidden_plugins) > 1 else ''}: "
                + ", ".join(sorted(self._hidden_plugins))
                + f" (see 'tool.{ENTRY_POINT}.disable_commands' in '{PYPROJECT_TOML_FILENAME}')"
            )

        return help_str


# @click.group(cls=Commands)
# def main():
#     context = click.get_current_context()

main = Commands()

if __name__ == "__main__":
    main()
