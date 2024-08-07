from __future__ import annotations

import inspect
import json
import logging
import os
import re
import time
import unicodedata
from datetime import timedelta
from typing import TYPE_CHECKING, Union

import aiofiles
import discord
import psutil
from discord import app_commands
from discord.ext import commands
from main import _get_guild_settings

# Local libs
if TYPE_CHECKING:
    from main import MrFriendly

from database import Settings

# TODO - Write get log function.
# Possibly pull the entire file, parts of the file (0-50) and or key words/errors from `logger.warn` or `logger.error`


class Util(commands.Cog):
    PATTERN: re.Pattern[str] = re.compile(
        r'`{3}(?P<LANG>\w+)?\n?(?P<CODE>(?:(?!`{3}).)+)\n?`{3}', flags=re.DOTALL | re.MULTILINE)
    # _default_repo = "https://github.com/k8thekat/dpy_cogs"
    # _default_branch = "main"
    _logger = logging.getLogger()

    def __init__(self, bot: "MrFriendly") -> None:
        self._bot: "MrFriendly" = bot
        self._name: str = os.path.basename(__file__).title()
        self._logger.info(msg=f"{self.__class__.__name__} Cog has been loaded!")

    async def cog_load(self) -> None:
        self._start_time: float = time.time()

    @property
    def _uptime(self) -> timedelta:
        return timedelta(seconds=(round(number=time.time() - self._start_time)))

    def _self_check(self, message: discord.Message) -> bool:
        return message.author == self._bot.user

    async def count_lines(self, path: str, filetype: str = ".py", skip_venv: bool = True):
        lines = 0
        for i in os.scandir(path):
            if i.is_file():
                if i.path.endswith(filetype):
                    if skip_venv and re.search(r"(\\|/)?venv(\\|/)", i.path):
                        continue
                    lines += len((await (await aiofiles.open(i.path, "r")).read()).split("\n"))
            elif i.is_dir():
                lines += await self.count_lines(i.path, filetype)
        return lines

    async def count_others(self, path: str, filetype: str = ".py", file_contains: str = "def", skip_venv: bool = True):
        """Counts the files in directory or functions."""
        line_count = 0
        for i in os.scandir(path):
            if i.is_file():
                if i.path.endswith(filetype):
                    if skip_venv and re.search(r"(\\|/)?venv(\\|/)", i.path):
                        continue
                    line_count += len(
                        [line for line in (await (await aiofiles.open(i.path, "r")).read()).split("\n") if file_contains in line]
                    )
            elif i.is_dir():
                line_count += await self.count_others(i.path, filetype, file_contains)
        return line_count

    @commands.command(help="Shows info about the bot", aliases=["botinfo", "info", "bi"])
    @commands.guild_only()
    async def about(self, context: commands.Context):
        """Tells you information about the bot itself."""
        await context.defer()
        assert self._bot.user
        assert context.guild
        _settings: Settings = await _get_guild_settings(guild_id=context.guild.id)
        information = await self._bot.application_info()
        embed = discord.Embed()
        # embed.add_field(name="Latest updates:", value=get_latest_commits(limit=5), inline=False)

        embed.set_author(
            name=f"Made by {information.owner.mention}", icon_url=information.owner.display_avatar.url,)
        memory_usage = psutil.Process().memory_full_info().uss / 1024**2
        cpu_usage: float = psutil.cpu_percent()

        embed.add_field(
            name="Process", value=f"{memory_usage:.2f} MiB\n{cpu_usage:.2f}% CPU")
        embed.add_field(
            name=f"{self._bot.user.name} info:",
            value=f"**Uptime:**\n{self._uptime}")
        try:
            embed.add_field(
                name="Lines",
                value=f"Lines: {await self.count_lines('./', '.py'):,}"
                f"\nFunctions: {await self.count_others('./', '.py', 'def '):,}"
                f"\nClasses: {await self.count_others('./', '.py', 'class '):,}",
            )
        except (FileNotFoundError, UnicodeDecodeError):
            pass

        embed.set_footer(
            text=f"Made with discord.py v{discord.__version__}",
            icon_url="https://i.imgur.com/5BFecvA.png",
        )
        embed.timestamp = discord.utils.utcnow()
        await context.send(embed=embed, ephemeral=True, delete_after=_settings.msg_timeout)

    @commands.hybrid_command(name='clear')
    @app_commands.default_permissions(manage_messages=True)
    @commands.guild_only()
    @app_commands.describe(all='Default\'s to False, removes ALL messages from selected Channel regardless of who sent them when True.')
    async def clear(self, interaction: discord.Interaction | commands.Context, channel: Union[discord.VoiceChannel, discord.TextChannel, discord.Thread, None], amount: app_commands.Range[int, 0, 100] = 15, all: bool = False):
        """Cleans up Messages sent by anyone. Limit 100"""
        assert interaction.guild
        _settings: Settings = await _get_guild_settings(guild_id=interaction.guild.id)
        if isinstance(interaction, discord.Interaction):
            await interaction.response.send_message(content="Removing messages...", delete_after=_settings.msg_timeout)

        assert isinstance(interaction.channel, (discord.VoiceChannel, discord.TextChannel, discord.Thread))
        channel = channel or interaction.channel

        if all:
            messages: list[discord.Message] = await channel.purge(limit=amount, bulk=False)
        else:
            messages = await channel.purge(limit=amount, check=self._self_check, bulk=False)

        return await channel.send(f'Cleaned up **{len(messages)} {"messages" if len(messages) > 1 else "message"}**. Wow, look at all this space!', delete_after=_settings.msg_timeout)

    @commands.command(name='charinfo', aliases=['ci'])
    @commands.guild_only()
    async def charinfo(self, context: commands.Context, *, characters: str):
        """Shows you information about a number of characters.
        Only up to 25 characters at a time.
        """
        assert context.guild
        _settings: Settings = await _get_guild_settings(guild_id=context.guild.id)

        def to_string(c):
            digit: str = f'{ord(c):x}'
            name: str = unicodedata.name(c, 'Name not found.')
            return f'`\\U{digit:>08}`: {name} - `{c}` \N{EM DASH} {c} \N{EM DASH} <http://www.fileformat.info/info/unicode/char/{digit}>'

        msg = '\n'.join(map(to_string, characters))
        if len(msg) > 2000:
            return await context.send(content='Output too long to display.')
        await context.send(content=msg, ephemeral=True, delete_after=_settings.msg_timeout)

    @commands.command(name='ping')
    async def ping(self, context: commands.Context):
        """Pong..."""
        assert context.guild
        _settings: Settings = await _get_guild_settings(guild_id=context.guild.id)
        await context.send(content=f'Pong `{round(number=self._bot.latency * 1000)}ms`', ephemeral=True, delete_after=_settings.msg_timeout)


async def setup(bot: "MrFriendly"):
    await bot.add_cog(Util(bot))
