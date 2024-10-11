from __future__ import annotations

import asyncio
import inspect
import io
import logging
import os
import re
import time
import traceback
import unicodedata
from contextlib import redirect_stdout
from datetime import timedelta
from typing import TYPE_CHECKING, Union

import discord
import psutil
from discord import Interaction, app_commands
from discord.ext import commands
from main import _get_guild_settings
from util.utils import count_lines, count_others

# Local libs
if TYPE_CHECKING:
    from main import MrFriendly

from database import Settings
from loader import *

# TODO - Write get log function.
# Possibly pull the entire file, parts of the file (0-50) and or key words/errors from `logger.warn` or `logger.error`

class Util(commands.Cog):
    """
    Discord Development Util functions, commands and other misc functions for convenience.
    """
    PATTERN: re.Pattern[str] = re.compile(
        pattern=r'`{3}(?P<LANG>\w+)?\n?(?P<CODE>(?:(?!`{3}).)+)\n?`{3}', flags=re.DOTALL | re.MULTILINE)
    # _default_repo = "https://github.com/k8thekat/dpy_cogs"
    # _default_branch = "main"
    _logger: logging.Logger = logging.getLogger()
    _event_list: list[str] = ["on_member_remove", 
                   "on_member_join", 
                   "on_member_ban", 
                   "on_message", 
                   "on_message_delete",
                   "on_message_edit",
                   "on_member_update",
                   "on_presence_update",
                   "on_reaction_add",
                   "on_reaction_remove",
                   "on_reaction_clear", #on_raw_reaction_clear_emoji
                   "on_pull_vote_add",
                   "on_pull_vote_remove",
                   "on_voice_state_update",
                   "on_guild_channel_create",
                   "on_guild_channel_delete",
                   "on_guild_channel_update",
                   "on_guild_channel_pins_update",
                   "on_guild_role_create",
                   "on_guild_role_delete",
                   "on_guild_role_update",
                   "on_guild_join",
                   "on_guild_remove",
                   "on_guild_update",
                   "on_guild_emojis_update",
                   "on_scheduled_event_create",
                   "on_scheduled_event_delete",
                   "on_scheduled_event_update",
                   "on_thread_create",
                   "on_thread_join",
                   "on_thread_update",
                   "on_thread_remove",
                   "on_thread_delete",
                   "on_thread_member_join",
                   "on_thread_member_remove",
                   "on_webhooks_update",
                   "on_interaction",
                   "on_typing",
                   "on_connect"]
    
    def __init__(self, bot: "MrFriendly") -> None:
        self._bot: "MrFriendly" = bot
        self._name: str = os.path.basename(__file__).title()
        self._logger.info(msg=f"{self.__class__.__name__} Cog has been loaded!")

    async def cog_load(self) -> None:
        self._start_time: float = time.time()
        self._sessions: set[int] = set()

    @property
    def _uptime(self) -> timedelta:
        return timedelta(seconds=(round(number=time.time() - self._start_time)))
    
    @commands.Cog.listener('on_message')
    async def on_message_listener(self, message: discord.Message) -> None:
        # This is for our `REPL` sessions.
        if message.channel.id in self._sessions:
            return

    def _self_check(self, message: discord.Message) -> bool:
        return message.author == self._bot.user

    async def autocomplete_event_list(self, interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name= entry, value= entry) for entry in self._event_list if current.lower() in entry.lower()][:25]

    @commands.hybrid_command(name='reload', help="Reload all cogs.")
    @commands.is_owner()
    async def reload(self, context: commands.Context) -> None:
        """
        Reloads all cogs inside the cogs folder.
        """
        await context.typing(ephemeral=True)
        assert context.guild
        _settings: Settings = await _get_guild_settings(guild_id=context.guild.id)
        try:
            await self._bot._handler.cog_auto_loader(reload=True)
        except Exception as e:
            self._logger.error(msg=traceback.format_exc())
            await context.send(content=f"We encountered an **Error** - \n`{e}` {traceback.format_exc()}", ephemeral=True)

        await context.send(content=f'**SUCCESS** Reloading All Cogs ', ephemeral=True, delete_after=_settings.msg_timeout)

    @commands.command(help="Shows info about the bot", aliases=["botinfo", "info", "bi"])
    @commands.guild_only()
    async def about(self, context: commands.Context):
        """Tells you information about the bot itself."""
        import gc

        import objgraph
        from guppy import hpy
        await context.defer()
        assert self._bot.user
        assert context.guild
        app_mem = hpy().heap()
        _settings: Settings = await _get_guild_settings(guild_id=context.guild.id)
        information = await self._bot.application_info()
        embed = discord.Embed()
        
        embed.set_author(name=f"Made by {information.owner.name}", icon_url=information.owner.display_avatar.url)
        memory_usage = psutil.Process().memory_full_info().uss / 1024**2
        cpu_usage: float = psutil.cpu_percent()

        embed.add_field(name=f"{self._bot.user.name} info:", value=f"**Uptime:**\n{self._uptime}")
        embed.add_field(name="Process", value=f"{memory_usage:.2f} MiB\n{cpu_usage:.2f}% CPU")
        try:
            embed.add_field(name="Lines", value=f"Lines: {await count_lines('./', '.py'):,}"
                f"\nFunctions: {await count_others('./', '.py', 'def '):,}"
                f"\nClasses: {await count_others('./', '.py', 'class '):,}",
            )
        except (FileNotFoundError, UnicodeDecodeError):
            pass
        embed.add_field(name="Heap", value= f"{app_mem}")
        # embed.add_field(name="Object Count", value=f"{objgraph.show_most_common_types(objects=[self._bot])}")

        embed.set_footer(text=f"Made with discord.py v{discord.__version__}", icon_url="https://i.imgur.com/5BFecvA.png")
        embed.timestamp = discord.utils.utcnow()
        await context.send(embed=embed, ephemeral=True, delete_after=_settings.msg_timeout*2)

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
    async def charinfo(self, context: commands.Context, *, characters: str) -> discord.Message | None:
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
    async def ping(self, context: commands.Context) -> None:
        """Pong..."""
        assert context.guild
        _settings: Settings = await _get_guild_settings(guild_id=context.guild.id)
        await context.send(content=f'Pong `{round(number=self._bot.latency * 1000)}ms`', ephemeral=True, delete_after=_settings.msg_timeout)

    # @app_commands.command(name='event_spoof')
    # @app_commands.autocomplete(event=autocomplete_event_list)
    # async def event_spoofing(self, interaction: discord.Interaction, event: str, member: discord.Member | None = None, role: discord.Role | None = None, message: str | None = None) -> None:
    #     assert interaction.guild
    #     _settings: Settings = await _get_guild_settings(guild_id=interaction.guild.id)
    #     try:
    #         self._bot.dispatch(event[3:]) #Strip the `on_` from any event.
    #     except Exception as e:
    #         await interaction.response.send_message(content=f"We encountered an error... \n{e}", ephemeral= True, delete_after=_settings.msg_timeout)
    #     await interaction.response.send_message(content=f"Dispatched {event}...", ephemeral= True, delete_after=_settings.msg_timeout)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def repl(self, ctx: commands.Context):
        """Launches an interactive REPL session."""
        variables = {
            'ctx': ctx,
            'bot': self._bot,
            'message': ctx.message,
            'guild': ctx.guild,
            'channel': ctx.channel,
            'author': ctx.author,
            '_': None,
        }

        if ctx.channel.id in self._sessions:
            await ctx.send('Already running a REPL session in this channel. Exit it with `quit`.')
            return

        self._sessions.add(ctx.channel.id)
        await ctx.send('Enter code to execute or evaluate. `exit()` or `quit` to exit.')

        def check(message: discord.Message):
            return message.author.id == ctx.author.id and message.channel.id == ctx.channel.id and message.content.startswith('`')

        while True:
            try:
                response = await self._bot.wait_for('message', check=check, timeout=10.0 * 60.0)
            except asyncio.TimeoutError:
                await ctx.send('Exiting REPL session.')
                self._sessions.remove(ctx.channel.id)
                break

            cleaned = self.cleanup_code(response.content)

            if cleaned in ('quit', 'exit', 'exit()'):
                await ctx.send('Exiting.')
                self._sessions.remove(ctx.channel.id)
                return

            if cleaned in ('?'):
                await ctx.send(f"{variables.keys()}")

            executor = exec
            code = ''
            if cleaned.count('\n') == 0:
                # single statement, potentially 'eval'
                try:
                    code = compile(cleaned, '<repl session>', 'eval')
                except SyntaxError:
                    pass
                else:
                    executor = eval

            if executor is exec:
                try:
                    code = compile(cleaned, '<repl session>', 'exec')
                except SyntaxError as e:
                    await ctx.send(self.get_syntax_error(e))
                    continue

            variables['message'] = response

            fmt = None
            stdout = io.StringIO()

            try:
                with redirect_stdout(stdout):
                    result = executor(code, variables)
                    if inspect.isawaitable(result):
                        result = await result
            except Exception as e:
                value = stdout.getvalue()
                fmt = f'```py\n{value}{traceback.format_exc()}\n```'
            else:
                value = stdout.getvalue()
                if result is not None:
                    fmt = f'```py\n{value}{result}\n```'
                    variables['_'] = result
                elif value:
                    fmt = f'```py\n{value}\n```'

            try:
                if fmt is not None:
                    if len(fmt) > 2000:
                        await ctx.send('Content too big to be printed.')
                    else:
                        await ctx.send(fmt)
            except discord.Forbidden:
                pass
            except discord.HTTPException as e:
                await ctx.send(f'Unexpected error: `{e}`')

    def cleanup_code(self, content: str) -> str:
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])

        # remove `foo`
        return content.strip('` \n')

    def get_syntax_error(self, e: SyntaxError) -> str:
        if e.text is None:
            return f'```py\n{e.__class__.__name__}: {e}\n```'
        return f'```py\n{e.text}{"^":>{e.offset}}\n{e.__class__.__name__}: {e}```'


async def setup(bot: "MrFriendly") -> None:
    await bot.add_cog(Util(bot=bot))
