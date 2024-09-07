from typing import TYPE_CHECKING

import discord
from discord.app_commands import (AppCommandError, CommandInvokeError,
                                  CommandTree)

if TYPE_CHECKING:
    from ..main import MrFriendly

#TODO - Traceback Embed or send errors to Owner.

class MrFriendlyCommandTree(CommandTree):
    client: "MrFriendly"

    async def on_error(self, interaction: discord.Interaction, error: AppCommandError):
        if interaction.command is None:
            self.client._logger.error(msg=f"Command Error - {error} - {interaction.data}")
            return await super().on_error(interaction, error)
        if interaction.channel is None:
            self.client._logger.error(msg=f"Command Error - {error} - {interaction.data}")
            return await super().on_error(interaction, error)
        if isinstance(error, discord.errors.HTTPException):
            if isinstance(interaction.channel, discord.TextChannel):
                self.client._logger.error(msg=f"Command Error - HTTPException - {error} - {interaction.data}")
                await interaction.channel.send(content=f" {interaction.user.mention} - Unable to process __/{interaction.command.name}__ - Please try your command again~")
                return await super().on_error(interaction, error)

        if isinstance(error, CommandInvokeError):
            if isinstance(interaction.channel, discord.TextChannel):
                self.client._logger.error(msg=f"Command Error - CommandInvokeError - {error} - {interaction.data}")
                await interaction.channel.send(content=f" {interaction.user.mention} - Unable to process __/{interaction.command.name}__ - Please try your command again~")
                return await super().on_error(interaction, error)