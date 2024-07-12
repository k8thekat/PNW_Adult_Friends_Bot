import logging
from typing import Literal, Union

import discord
from discord import Embed, Interaction, Message, TextChannel, app_commands
from discord.ext import commands
from main import MrFriendly

from database.user import Infraction, User


class InfractionEmbed(Embed):
    def __init__(self, moderator: Union[discord.User, discord.Member], infraction: Infraction, reason: str, user: Union[discord.User, discord.Member]) -> None:
        super().__init__(title=f"__{user.display_name}__ | Infraction ID: **#{infraction.id}**", color=discord.Color.red())
        self.description = reason
        self.timestamp = infraction.created_at
        self.set_footer(text=f"Moderator: {moderator.mention}")


# TODO - Needs Testing.
class InfractionsCog(commands.Cog):
    _logger: logging.Logger = logging.getLogger()

    def __init__(self, bot: MrFriendly) -> None:
        super().__init__()
        self.bot: MrFriendly = bot

    async def autocomplete_infractions(self, interaction: Interaction, current: str) -> list[app_commands.Choice[int]]:
        assert interaction.guild
        if hasattr(interaction.namespace, "user") and isinstance(interaction.namespace.user, (discord.Member, discord.User)):
            _user: User | None = await User.add_or_get_user(guild_id=interaction.guild.id, user_id=interaction.namespace.user.id)
        else:
            return [app_commands.Choice(name="No Entries Found...", value=9999)]

        if _user is None:
            return [app_commands.Choice(name="No Entries Found...", value=9999)]
        _infractions: set[Infraction] = await _user.get_infractions()
        return list(app_commands.Choice(name=f"Infraction {infraction.id}", value=infraction.id)
                    for infraction in _infractions if type(infraction) == Infraction and current.lower() in infraction.reason_msg_link.lower() or
                    current.lower() in str(infraction.id).lower())[:25]

    @ commands.command()
    @ commands.guild_only()
    @ commands.has_role("Moderator")
    @ app_commands.describe(reason="The reason for the Infraction.")
    async def add_infraction(self, context: commands.Context, user: Union[discord.User, discord.Member], reason: str) -> Message:
        # Since we have `guild_only()` we can assume that `context.guild` is not `None`
        # https://discord.com/channels/1259645744420360243/1259645744420360246/1260721454845267978
        # 1259645744420360243
        assert context.guild
        _log: int | None = self.bot._guild_settings.infraction_log_channel_id
        if _log is None:
            self._logger.error(msg="Infraction Logging Channel ID has not been set.")
            return await context.send(content="Infraction Logging Channel ID has not been set.", ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)

        _channel = context.guild.get_channel(_log)
        if _channel is None:
            self._logger.error(msg="Infraction Logging Channel ID is not a valid Channel ID.")
            return await context.send(content="Infraction Logging Channel ID is not a valid Channel ID.", ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)

        if not isinstance(_channel, TextChannel):
            self._logger.error(msg="Infraction Logging Channel ID is not a Text Channel.")
            return await context.send(content="Infraction Logging Channel ID is not a Text Channel.", ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)

        _user: User | None = await User.add_or_get_user(guild_id=context.guild.id, user_id=user.id)
        if _user is None:
            return await context.send(content=f"Unable to find or create {user.display_name} in the database.", ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)

        reason_msg_link: str = f"https://discord.com/channels/{context.guild.id}/{_channel.id}/{_channel.last_message_id}"

        _infraction: Infraction | None = await _user.add_infraction(reason_msg_link=reason_msg_link)
        if _infraction is None:
            return await context.send(content=f"Unable to add infraction for {user.display_name}.", ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)
        # char limit of an Embed Description is 4096.
        if len(reason) > 4096:
            reason = reason[:4090] + "..."
        await _channel.send(embed=InfractionEmbed(moderator=context.author, infraction=_infraction, reason=reason, user=user))
        return await context.send(content=f"Added Infraction #{_infraction.id} for {user.display_name} | Reason: {reason}.", ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)

    @ commands.command()
    @ commands.guild_only()
    @ app_commands.autocomplete(Infraction=autocomplete_infractions)
    @app_commands.describe(infraction="The Infraction by ID to remove.")
    @ commands.has_role("Moderator")
    async def remove_infraction(self, context: commands.Context, user: Union[discord.User, discord.Member], infraction: int) -> Message:
        # Since we have `guild_only()` we can assume that `context.guild` is not `None`
        assert context.guild
        if infraction == 9999:
            self._logger.error(msg=f"Unable to find Infractions for Discord User. | ID: {user.id} | Name: {user.name}")
            return await context.send(content=f"Unable to find Infractions for {user.name}", ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)

        _log: int | None = self.bot._guild_settings.infraction_log_channel_id
        if _log is None:
            self._logger.error(msg="Infraction Logging Channel ID has not been set.")
            return await context.send(content="Infraction Logging Channel ID has not been set.", ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)

        _channel = context.guild.get_channel(_log)
        if _channel is None:
            self._logger.error(msg="Infraction Logging Channel ID is not a valid Channel ID.")
            return await context.send(content="Infraction Logging Channel ID is not a valid Channel ID.", ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)

        if not isinstance(_channel, TextChannel):
            self._logger.error(msg="Infraction Logging Channel ID is not a Text Channel.")
            return await context.send(content="Infraction Logging Channel ID is not a Text Channel.", ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)

        _user: User | None = await User.add_or_get_user(guild_id=context.guild.id, user_id=user.id)
        if _user is None:
            return await context.send(content=f"Unable to find or create {user.name} in the database.", ephemeral=True)

        await _user.remove_infraction(id=infraction)
        return await context.send(content=f"Removed Infraction #{infraction} for {user.name}.", ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)

    @ commands.command()
    @ commands.guild_only()
    @ commands.has_role("Moderator")
    async def list_infractions(self, context: commands.Context, user: Union[discord.User, discord.Member]) -> Message:
        # Since we have `guild_only()` we can assume that `context.guild` is not `None`
        assert context.guild
        _user: User | None = await User.add_or_get_user(guild_id=context.guild.id, user_id=user.id)
        if _user is None:
            return await context.send(content=f"Unable to find or create {user.name} in the database.", ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)
        _infractions: set[Infraction] = await _user.get_infractions()
        if len(_infractions) == 0:
            return await context.send(content=f"{user.name} has no infractions.", ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)
        _content: str = f"Infractions for **{user.name}**:\n"
        for infraction in _infractions:
            _content += f"> Infraction #{infraction.id} -> {infraction.reason_msg_link}"
        return await context.send(content=_content, ephemeral=True, delete_after=self.bot._guild_settings.msg_timeout)
