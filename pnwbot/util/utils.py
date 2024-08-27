import importlib
import inspect
import os
import re
import types
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Mapping, TypedDict

import aiofiles
from database.settings import Settings


def reload_module_dependencies(module_path: str, /) -> set[str]:
    """Reloads all dependencies of a module with importlib

    Parameters
    ----------
    module_path : str
        The module to reload, dot qualified.

    Returns
    -------
    set[str]
        The reloaded modules

    Raises
    ------
    ModuleNotFoundError
        You passed an invalid module path.
    """
    out = []
    mod_to_reload = importlib.import_module(module_path)

    def get_pred(value):
        return isinstance(value, types.ModuleType) or (inspect.isclass(value) or inspect.isfunction(value) and value.__module__ is not mod_to_reload)

    items = inspect.getmembers(mod_to_reload, predicate=get_pred)

    for _, value in items:
        if isinstance(value, types.ModuleType):
            importlib.reload(value)
            out.append(value.__name__)
        elif inspect.isclass(value) or (inspect.isfunction(value) and value.__module__ is not mod_to_reload):
            module = importlib.import_module(value.__module__)
            importlib.reload(module)
            out.append(module.__name__)

    return set(out)


async def count_lines(path: str, filetype: str = ".py", skip_venv: bool = True) -> int:
    lines: int = 0
    for i in os.scandir(path):
        if i.is_file():
            if i.path.endswith(filetype):
                if skip_venv and re.search(r"(\\|/)?venv(\\|/)", i.path):
                    continue
                lines += len((await (await aiofiles.open(i.path, "r")).read()).split("\n"))
        elif i.is_dir():
            lines += await count_lines(i.path, filetype)
    return lines


async def count_others(path: str, filetype: str = ".py", file_contains: str = "def", skip_venv: bool = True) -> int:
    line_count: int = 0
    for i in os.scandir(path):
        if i.is_file():
            if i.path.endswith(filetype):
                if skip_venv and re.search(r"(\\|/)?venv(\\|/)", i.path):
                    continue
                line_count += len(
                    [line for line in (await (await aiofiles.open(i.path, "r")).read()).split("\n") if file_contains in line]
                )
        elif i.is_dir():
            line_count += await count_others(i.path, filetype, file_contains)
    return line_count


@dataclass()
class MarkDownPlaceHolders():
    """When accessing Database Settings always use `_settings` as the variable name.\n
    - **member**: `discord.Guild.Member`
    -
    """
    member: str = "member.mention"
    moderator_role: str = "guild.get_role(_settings.mod_role_id)"
    rules_channel: str = "guild.get_channel(_settings.rules_message_id)"
    roles_channel: str = "guild.get_channel(_settings.roles_channel_id)"
    intro_channel: str = "guild.get_channel(_settings.personal_intros_channel_id)"

    def to_dict(self) -> dict[str, str]:
        return {key: str(object=value) for key, value in asdict(obj=self).items()}


async def parse_markdown(path: str, placeholder_struct: MarkDownPlaceHolders = MarkDownPlaceHolders(), replace_placeholders: bool = True) -> str:
    """
    Parse a markdown file to replace keywords from the .md file with attributes of `MarkDownPlaceHolders`.

    Returns the contents as an `f-string`.

    Args:
        path (str): Will resolve path relative to `__file__.parent()`.
        placeholder_struct (MarkDownPlaceHolders): The Dataclass structure to use for Placeholder swaps.
        replace_placeholders (bool, optional): Controls the replacement of the placeholders. Defaults to True.

    Returns:
        str: f-string of the file contents with or without the placeholders replaced.
    """
    _file: Path = Path(__file__).parent.joinpath(path).resolve()

    _contents = ""
    if _file.is_file():
        if replace_placeholders is True:
            _contents: str = _file.read_text(encoding="utf-8").format(**placeholder_struct.to_dict())
        else:
            _contents: str = _file.read_text(encoding="utf-8")
    return f"{_contents}"
