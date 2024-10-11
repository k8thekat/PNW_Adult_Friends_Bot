import logging
import os
import pathlib
import sys
import traceback
from typing import TYPE_CHECKING

from discord.ext import commands
from util.utils import reload_module_dependencies

if TYPE_CHECKING:
    from main import MrFriendly


class Handler():
    """
    This is the Basic Module (aka Cogs) Loader for AMP to Discord Integration/Interactions
    """
    def __init__(self, bot: "MrFriendly") -> None:
        self._bot: "MrFriendly" = bot
        self._cog_path: pathlib.Path = pathlib.Path(__file__).parent
        self._name: str = os.path.basename(p=__file__).title()
        self._logger: logging.Logger = logging.getLogger()
        sys.path.append(self._cog_path.as_posix())
        self._loaded_cogs: list[str] = []

    async def cog_auto_loader(self, reload: bool = False) -> None:
        """This will load all Cogs inside of the cogs folder."""
        # path = f'cogs'  # This gets us to the folder for the module specific scripts to load via the cog.
        path = "cogs"
        # Grab all the cogs inside my `cogs` folder and duplicate the list.
        cog_file_list = pathlib.Path.joinpath(self._cog_path, "cogs").iterdir()
        cur_cog_file_list = list(cog_file_list)

        # This while loop will force it to load EVERY cog it finds until the list is empty.
        while len(cur_cog_file_list) > 0:
            for script in cur_cog_file_list:
                # Ignore Py-cache or similar files.
                # Lets Ignore our Custom Permissions Cog. We will load it on-demand.
                if script.name.startswith('__') or script.name.startswith('_') or not script.name.endswith('.py'):
                    cur_cog_file_list.remove(script)
                    continue

                cog: str = f'{path}.{script.name[:-3]}'
                try:
                    if reload and cog in self._loaded_cogs:
                        self._logger.info(msg="Attempting to reload all cogs.")
                        await self._bot.reload_extension(name=cog)
                        cur_cog_file_list.remove(script)

                    else:
                        await self._bot.load_extension(name=cog)
                        # Append to our loaded cogs for dependency check
                        self._loaded_cogs.append(cog)
                        # Remove the entry from our cog list; so we don't attempt to load it again.
                        cur_cog_file_list.remove(script)

                    self._logger.info(msg=f'**FINISHED LOADING** {self._name} -> **{cog}**')

                except commands.errors.ExtensionAlreadyLoaded:
                    cur_cog_file_list.remove(script)
                    self._logger.error(msg=f'**ERROR** Loading Cog ** - {cog} ExtensionAlreadyLoaded {traceback.format_exc()}')
                    continue

                except FileNotFoundError as e:
                    self._logger.error(msg=f'**ERROR** Loading Cog ** - {cog} File Not Found {traceback.format_exc()}')

        self._logger.info(msg=f'**All Cog Modules Loaded**')
