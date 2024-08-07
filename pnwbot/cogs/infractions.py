import logging
from typing import TYPE_CHECKING, Union

import discord
from database import *
from discord import Embed, Interaction, Message, TextChannel, app_commands
from discord.ext import commands
from main import _get_guild_settings
from util.emoji_lib import Emojis

if TYPE_CHECKING:
    from main import MrFriendly


class InfractionEmbed(Embed):
    def __init__(self, moderator: Union[discord.User, discord.Member], infraction: Infraction, reason: str, user: Union[discord.User, discord.Member]) -> None:
        super().__init__(title=f"{Emojis.Ticket} __{user.display_name}__ | Infraction ID: **#{infraction.id}**", color=discord.Color.red())
        self.description = reason
        self.timestamp = infraction.created_at
        self.set_footer(text=f"Moderator: {moderator}")

# TODO - When removing an infraction, remove the message from the Infraction Channel.
# TODO - Needs Testing.


class InfractionsCog(commands.Cog):
    _logger: logging.Logger = logging.getLogger()

    def __init__(self, bot: "MrFriendly") -> None:
        self.bot = bot
        self._logger.info(msg=f"{self.__class__.__name__} Cog has been loaded!")

    async def autocomplete_infractions(self, interaction: Interaction, current: str) -> list[app_commands.Choice[int]]:
        assert interaction.guild
        if hasattr(interaction.namespace, "user") and hasattr(interaction.namespace.user, "id"):
            _user: User | None = await User.add_or_get_user(guild_id=interaction.guild.id, user_id=interaction.namespace.user.id)
        else:
            return [app_commands.Choice(name="No Entries Found...", value=9999)]

        if _user is None:
            return [app_commands.Choice(name="No Entries Found...", value=9999)]
        _infractions: set[Infraction] = await _user.get_infractions()
        return list(app_commands.Choice(name=f"Infraction {infraction.id}", value=infraction.id)
                    for infraction in _infractions if type(infraction) == Infraction and current.lower() in infraction.reason_msg_link.lower() or
                    current.lower() in str(infraction.id).lower())[:25]

    @app_commands.command(name="add_infraction")
    @commands.guild_only()
    @commands.has_role("Moderator")
    @app_commands.describe(reason="The reason for the Infraction.")
    async def add_infraction(self, interaction: Interaction, user: Union[discord.User, discord.Member], reason: str) -> None:
        # Since we have `guild_only()` we can assume that `context.guild` is not `None`
        # https://discord.com/channels/1259645744420360243/1259645744420360246/1260721454845267978
        # 1259645744420360243
        assert interaction.guild
        _settings: Settings = await _get_guild_settings(guild_id=interaction.guild.id)
        _log: int = _settings.infraction_log_channel_id

        _channel = interaction.guild.get_channel(_log)
        if _channel is None:
            self._logger.error(msg="Infraction Logging Channel ID is not a valid Channel ID.")
            return await interaction.response.send_message(content="Infraction Logging Channel ID is not a valid Channel ID.", ephemeral=True, delete_after=_settings.msg_timeout)

        if not isinstance(_channel, TextChannel):
            self._logger.error(msg="Infraction Logging Channel ID is not a Text Channel.")
            return await interaction.response.send_message(content="Infraction Logging Channel ID is not a Text Channel.", ephemeral=True, delete_after=_settings.msg_timeout)

        _user: User | None = await User.add_or_get_user(guild_id=interaction.guild.id, user_id=user.id)
        if _user is None:
            return await interaction.response.send_message(content=f"Unable to find or create {user.display_name} in the database.", ephemeral=True, delete_after=_settings.msg_timeout)

        _msg: Message = await _channel.send(content="Adding Infraction....")
        reason_msg_link: str = f"https://discord.com/channels/{interaction.guild.id}/{_channel.id}/{_channel.last_message_id}"
        _infraction: Infraction | None = await _user.add_infraction(reason_msg_link=reason_msg_link)
        if _infraction is None:
            await _msg.delete()
            return await interaction.response.send_message(content=f"Unable to add infraction for {user.display_name}.", ephemeral=True, delete_after=_settings.msg_timeout)
        # char limit of an Embed Description is 4096.
        if len(reason) > 4096:
            reason = reason[:4090] + "..."
        await _msg.edit(content=None, embed=InfractionEmbed(moderator=interaction.user, infraction=_infraction, reason=reason, user=user))
        return await interaction.response.send_message(content=f"Added Infraction #{_infraction.id} for {user.display_name} | Reason: {reason}.", ephemeral=True, delete_after=_settings.msg_timeout)

    @app_commands.command(name="remove_infraction")
    @commands.guild_only()
    @app_commands.autocomplete(infraction=autocomplete_infractions)
    @app_commands.describe(infraction="The Infraction by ID to remove.")
    @commands.has_role("Moderator")
    async def remove_infraction(self, interaction: Interaction, user: Union[discord.User, discord.Member], infraction: int) -> None:
        # Since we have `guild_only()` we can assume that `context.guild` is not `None`
        assert interaction.guild
        _settings: Settings = await _get_guild_settings(guild_id=interaction.guild.id)
        if infraction == 9999:
            self._logger.error(msg=f"Unable to find Infractions for Discord User. | ID: {user.id} | Name: {user.name}")
            return await interaction.response.send_message(content=f"Unable to find Infractions for {user}", ephemeral=True, delete_after=_settings.msg_timeout)

        _log: int | None = _settings.infraction_log_channel_id
        _channel = interaction.guild.get_channel(_log)
        if _channel is None:
            self._logger.error(msg="Infraction Logging Channel ID is not a valid Channel ID.")
            return await interaction.response.send_message(content="Infraction Logging Channel ID is not a valid Channel ID.", ephemeral=True, delete_after=_settings.msg_timeout)

        if not isinstance(_channel, TextChannel):
            self._logger.error(msg="Infraction Logging Channel ID is not a Text Channel.")
            return await interaction.response.send_message(content="Infraction Logging Channel ID is not a Text Channel.", ephemeral=True, delete_after=_settings.msg_timeout)

        _user: User | None = await User.add_or_get_user(guild_id=interaction.guild.id, user_id=user.id)
        if _user is None:
            return await interaction.response.send_message(content=f"Unable to find or create {user} in the database.", ephemeral=True)

        await _user.remove_infraction(id=infraction)
        return await interaction.response.send_message(content=f"{Emojis.Outbox_tray} | Removed **Infraction #{infraction}** for {user}.", ephemeral=True, delete_after=_settings.msg_timeout)

    @app_commands.command(name="list_infractions")
    @commands.guild_only()
    @commands.has_role("Moderator")
    async def list_infractions(self, interaction: Interaction, user: Union[discord.User, discord.Member]) -> None:
        # Since we have `guild_only()` we can assume that `context.guild` is not `None`
        assert interaction.guild
        _settings: Settings = await _get_guild_settings(guild_id=interaction.guild.id)
        _user: User | None = await User.add_or_get_user(guild_id=interaction.guild.id, user_id=user.id)
        if _user is None:
            return await interaction.response.send_message(content=f"Unable to find or create {user.name} in the database.", ephemeral=True, delete_after=_settings.msg_timeout)
        _infractions: set[Infraction] = await _user.get_infractions()
        if len(_infractions) == 0:
            return await interaction.response.send_message(content=f"{user.name} has no infractions.", ephemeral=True, delete_after=_settings.msg_timeout)
        _content: str = f"{Emojis.Ticket} | Infractions for **{user}**:\n"
        for infraction in _infractions:
            _content += f"> Infraction #{infraction.id} -> {infraction.reason_msg_link}"
        return await interaction.response.send_message(content=_content, ephemeral=True, delete_after=_settings.msg_timeout)


async def setup(bot: "MrFriendly") -> None:
    await bot.add_cog(InfractionsCog(bot=bot))
