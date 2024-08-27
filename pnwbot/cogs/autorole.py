import logging
import os
from re import Match, Pattern, compile
from typing import TYPE_CHECKING, Any, List, Optional, Union

import discord
import discord.http
from database import *
from database.settings import Role_Embed_Info
from discord import (ButtonStyle, Embed, Emoji, Message, PartialEmoji,
                     app_commands)
from discord.ext import commands, tasks
from discord.ui import Button, View
from main import _get_guild_settings

if TYPE_CHECKING:
    from main import MrFriendly

interaction = discord.Interaction

# TODO - Role selection Embeds.
# - Needs to support up to 8 buttons at once.
# - Possibly support role icons as emoji's as well.


class RoleButton(Button):
    """This is for the Reaction Role View"""

    def __init__(self, *, style: ButtonStyle = ButtonStyle.green, label: Optional[str], custom_id: Optional[str], emoji: Union[str, Emoji, PartialEmoji, None] = None) -> None:
        super().__init__(style=style, label=label, custom_id=custom_id, emoji=emoji)


class ReactionRoleView(View):
    def __init__(self, *, timeout: Union[float, None] = 180, buttons: list[RoleButton]) -> None:
        # def __init__(self, *, timeout: Union[float, None] = 180, custom_id: str, button_label: str, button_emoji: Union[str, Emoji, PartialEmoji, None]) -> None:
        super().__init__(timeout=timeout)
        for button in buttons:
            # self.add_item(RoleButton(custom_id=custom_id, label=button_label, emoji=button_emoji))
            self.add_item(button)


class AutoRole(commands.Cog):
    _logger: logging.Logger = logging.getLogger()

    def __init__(self, bot: "MrFriendly") -> None:
        self._bot: "MrFriendly" = bot
        self._logger.info(msg=f"{self.__class__.__name__} Cog has been loaded!")

    REACTION_ROLES_BUTTON_REGEX: Pattern[str] = compile(pattern=r'RR::BUTTON::(?P<ROLE_ID>\d+)')
    AGE_ROLE_GROUP: list[int] = [1259692047036715128, 1259660826915110942, 1259660900445454378, 1259661047602610176, 1259661129299267705]
    SEX_ORIENTATION_ROLE_GROUP: list[int] = [1259661460804599929, 1259661532095320074, 1259661605902483536, 1259661655319515236, 1259661691453571134, 1259661715004588134, 1259661742066110585, 1259661787758858304]
    GENDER_ROLE_GROUP: list[int] = [1259650732005789706, 1259650866835619912, 1259650920858386472, 1259650994707628052, 1259651332575596544, 1259683302760255558]
    PRONOUNS_ROLE_GROUP: list[int] = [1259660711835992136, 1259660769155354725, 1259660799555928194, 1259683965695164456]
    RELATIONSHIP_ROLE_GROUP: list[int] = [1259661152309215373, 1259661187155755139, 1259661227911680070, 1259661289433727026]
    DM_ROLE_GROUP: list[int] = [1259698813795565649, 1259698893558517822, 1259698953105051728]
    LOCATION_ROLE_GROUP: list[int] = [1260380394872635392, 1260380525860880515, 1260380565731934339, 1260380601953816669]

    async def cog_load(self) -> None:
        self.validate_role_embeds.start()

    @tasks.loop(minutes=1, reconnect=True)
    async def validate_role_embeds(self) -> None:
        """
        Validates the Role Embeds we generated and stored in our database.
        """

        for guild in self._bot.guilds:
            try:
                _guild_embeds: list[Role_Embed_Info] = await Role_Embed_Info.get_all_role_embeds(guild_id=guild.id)
            except ValueError:
                self._logger.warn(msg=f"No Role Embeds in this Guild | Guild ID: {guild.id}")
                continue

            for embed in _guild_embeds:
                _guild: discord.Guild | None = self._bot.get_guild(embed.guild_id)
                if _guild is None:
                    continue
                _channel = _guild.get_channel(embed.channel_id)
                if _channel is None or not isinstance(_channel, discord.TextChannel):
                    continue
                try:
                    await _channel.fetch_message(embed.message_id)
                except discord.NotFound:
                    await Role_Embed_Info.remove_role_embed(embed_info=embed)
                    self._logger.warn(msg=f"Removed a Role Embed Info Message from the Database. | Embed ID: {embed.id} | Guild ID: {guild.id}")
                except discord.HTTPException:
                    self._logger.error(msg=f"Failed to find a Role Embed Info Message `HTTPException`, {embed.guild_id} {embed.channel_id} {embed.message_id} | Guild ID: {guild.id}")
                    continue
                except Exception as e:
                    await Role_Embed_Info.remove_role_embed(embed_info=embed)
                    self._logger.error(msg=f"Failed to find a Role Embed Info Message removing from the Database. | Embed ID: {embed.guild_id} Embed Channel ID: {embed.channel_id} Embed Message ID: {embed.message_id} | Guild ID: {guild.id}")

    async def autocomplete_role_embeds(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
        assert interaction.guild
        _role_embeds: list[Role_Embed_Info] = await Role_Embed_Info.get_all_role_embeds(guild_id=interaction.guild.id)
        return [app_commands.Choice(name=f"{role_embed.name} - {role_embed.id}", value=role_embed.id) for role_embed in _role_embeds if current.lower() in role_embed.name.lower()]

    async def autocomplete_embed_buttons(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int | str]]:
        assert interaction.guild
        if hasattr(interaction.namespace, "role_embed") is False:
            return [app_commands.Choice(name="Failed to find Role Embed...", value=9999)]

        _role_embed: Role_Embed_Info = await Role_Embed_Info.get_role_embed(guild_id=interaction.guild.id, id=interaction.namespace.role_embed)
        _channel = interaction.guild.get_channel(_role_embed.channel_id)
        if not isinstance(_channel, discord.TextChannel):
            return [app_commands.Choice(name="Failed to Parse Channel...", value=9999)]

        _msg: discord.Message = await _channel.fetch_message(_role_embed.message_id)
        _view: View = discord.ui.View.from_message(_msg, timeout=None)
        _choices: list[app_commands.Choice] = []
        for item in _view.children:
            if not isinstance(item, Button):
                continue
            if item.label is not None and item.custom_id is not None:
                _name: str = item.label
                _value: str = item.custom_id

            elif item.label is None and item.custom_id is not None:
                _name = item.custom_id
                _value = item.custom_id

            elif item.label is not None and item.custom_id is None:
                _name = item.label
                _value = item.label
            if (current.lower() in _name.lower()) or (current.lower() in _value.lower()):
                _choices.append(app_commands.Choice(name=_name, value=_value))
        return _choices

    @commands.Cog.listener(name="on_message")
    async def on_message(self, message: discord.Message):
        if message.guild is None:
            return
        if len(message.embeds) != 0:
            # Keep our Embed message cache.
            self._bot._cache[message.id] = message

    @commands.Cog.listener(name="on_raw_message_delete")
    async def on_raw_message_delete_embed_tracker(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.message_id not in self._bot._cache:
            return
        _cache_message: Message = self._bot._cache[payload.message_id]
        if payload.guild_id is not None:
            # Remove our Role Embeds first.
            _role_embeds: list[Role_Embed_Info] = await Role_Embed_Info.get_all_role_embeds(guild_id=payload.guild_id)
            if len(_role_embeds) != 0:
                _embed_info: Role_Embed_Info | None = next((embed for embed in _role_embeds if embed.message_id == _cache_message.id and embed.channel_id == _cache_message.channel.id), None)
                if _embed_info is not None:
                    await Role_Embed_Info.remove_role_embed(embed_info=_embed_info)

    @commands.Cog.listener(name='on_interaction')
    async def on_reaction_role(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component:
            return

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if interaction.app_permissions.manage_roles is False:
            return

        custom_id: Any | str = (interaction.data or {}).get('custom_id', '')
        match: Match[str] | None = self.REACTION_ROLES_BUTTON_REGEX.fullmatch(custom_id)
        _groups: List[List[int]] = [self.AGE_ROLE_GROUP, self.SEX_ORIENTATION_ROLE_GROUP, self.GENDER_ROLE_GROUP,
                                    self.PRONOUNS_ROLE_GROUP, self.RELATIONSHIP_ROLE_GROUP, self.DM_ROLE_GROUP,
                                    self.LOCATION_ROLE_GROUP]
        if match:
            role_id = int(match.group('ROLE_ID'))
            _reaction_role: discord.Role | None = interaction.guild.get_role(role_id)
            if not _reaction_role:
                return await interaction.response.send_message(content='Sorry, that role does not seem to exist anymore...', ephemeral=True, delete_after=10)

            group: List[int] | None = next((group for group in _groups if _reaction_role.id in group), None)
            if group is None:
                return
            _removed_role = False
            for role_id in group:
                # If the user doesn't have any of the existing roles in the group we add the.
                if interaction.user.get_role(role_id) is None:
                    continue
                else:
                    role: discord.Role | None = interaction.guild.get_role(role_id)
                    if not isinstance(role, discord.Role):
                        return await interaction.response.send_message(content='Sorry, that role does not seem to exist anymore...', ephemeral=True, delete_after=10)
                    _removed_role = True
                    await interaction.user.remove_roles(role, atomic=True)

            _settings: Settings = await _get_guild_settings(guild_id=interaction.guild.id)
            await interaction.user.add_roles(_reaction_role, atomic=True)
            return await interaction.response.send_message(content=f"Reassigned your role to {_reaction_role.mention} from {role.mention}."
                                                           if _removed_role is True else f"Gave you the role {_reaction_role.mention}.",
                                                           ephemeral=True, delete_after=15)

    @app_commands.command(name='role_embed')
    @commands.guild_only()
    @commands.has_role("Moderator")
    async def role_embed(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel], embed_title: str, field_body: str, role1: discord.Role,
                         role2: Optional[discord.Role] = None, role3: Optional[discord.Role] = None, role4: Optional[discord.Role] = None, role5: Optional[discord.Role] = None) -> None:
        """Displays an Embed in a channel that Users can interact with the button to `Add` or `Remove` a role."""
        assert interaction.guild
        assert interaction.channel
        _settings: Settings = await _get_guild_settings(guild_id=interaction.guild.id)
        _embed = Embed(title=f'**{embed_title}**', color=discord.Color.blurple(), description="Please select a button below to add or remove the roles. You are limited to one role at a time, selecting another role removes the previously selected role.")
        _embed.add_field(name='**What is this for?**', value=field_body)
        _roles: list[discord.Role | None] = [role1, role2, role3, role4, role5]
        _buttons: list[RoleButton] = []
        for entry in _roles:
            if entry is not None:
                _buttons.append(RoleButton(custom_id=f"RR::BUTTON::{entry.id}", label=entry.name))

        _role_view = ReactionRoleView(timeout=None, buttons=_buttons)

        if channel is None:
            if isinstance(interaction.channel, discord.TextChannel):
                channel = interaction.channel
            else:
                return await interaction.response.send_message(content=f"This command can only be used in a Text Channel, please consider picking a channel next time.", ephemeral=True, delete_after=_settings.msg_timeout)

        await interaction.response.send_message(content="Please wait while I create the embed...", ephemeral=True, delete_after=2)
        _msg: discord.Message = await channel.send(embed=_embed, view=_role_view)
        await Role_Embed_Info.add_role_embeds(name=embed_title, guild_id=interaction.guild.id, channel_id=channel.id, message_id=_msg.id)

    @app_commands.command(name="add_button")
    @commands.guild_only()
    @commands.has_role("Moderator")
    @app_commands.describe(role_embed="The ID of the embed you want to add roles to.", role="The role you want to add to the embed.")
    @app_commands.autocomplete(role_embed=autocomplete_role_embeds)
    async def add_button_to_role_embed(self, interaction: discord.Interaction, role_embed: int, role: discord.Role) -> None:
        assert interaction.guild
        _role_embed: Role_Embed_Info = await Role_Embed_Info.get_role_embed(guild_id=interaction.guild.id, id=role_embed)
        _channel = interaction.guild.get_channel(_role_embed.channel_id)
        _settings: Settings = await _get_guild_settings(guild_id=interaction.guild.id)
        if isinstance(_channel, discord.TextChannel):
            _msg: discord.Message = await _channel.fetch_message(_role_embed.message_id)
            _button = RoleButton(custom_id=f"RR::BUTTON::{role.id}", label=role.name, emoji=role.unicode_emoji)
            _view: View = discord.ui.View.from_message(_msg, timeout=None).add_item(item=_button)
            if len(_msg.embeds) > 1:
                return await interaction.response.send_message(content=f"This message has too many embeds to discern which one I need.", ephemeral=True, delete_after=_settings.msg_timeout)
            await _msg.edit(view=_view)
            return await interaction.response.send_message(content=f"Added the role **{role.mention}** to our view for**{_role_embed.name}**", ephemeral=True, delete_after=_settings.msg_timeout)

        return await interaction.response.send_message(content=f"This Channel we have does not seem to be a Text Channel. {_role_embed.message_id if _channel is None else _channel.mention}",
                                                       ephemeral=True, delete_after=_settings.msg_timeout)

    @app_commands.command(name="remove_button")
    @commands.guild_only()
    @commands.has_role("Moderator")
    @app_commands.autocomplete(role_embed=autocomplete_role_embeds)
    @app_commands.autocomplete(button=autocomplete_embed_buttons)
    async def remove_button_to_role_embed(self, interaction: discord.Interaction, role_embed: int, button: str) -> None:
        assert interaction.guild
        _role_embed: Role_Embed_Info = await Role_Embed_Info.get_role_embed(guild_id=interaction.guild.id, id=role_embed)
        _channel = interaction.guild.get_channel(_role_embed.channel_id)
        _settings: Settings = await _get_guild_settings(guild_id=interaction.guild.id)
        if not isinstance(_channel, discord.TextChannel):
            return await interaction.response.send_message(content=f"Failed to find a Text Channel for : {_role_embed.channel_id}", ephemeral=True, delete_after=_settings.msg_timeout)
        _msg: discord.Message = await _channel.fetch_message(_role_embed.message_id)
        _view: View = discord.ui.View.from_message(_msg, timeout=None)
        found = False
        for item in _view.children:
            if not isinstance(item, Button):
                continue
            if item.label == button or item.custom_id == button:
                _temp: Button[View] = item
                _view.remove_item(item=item)
                await _msg.edit(view=_view)
                found = True
                break
        if not found:
            return await interaction.response.send_message(content=f"Failed to find and remove a button from the Embed Message: {_msg.jump_url}", ephemeral=True, delete_after=_settings.msg_timeout)
        return await interaction.response.send_message(content=f"Removed the button: {_temp.label} from the Embed Message: {_msg.jump_url}", ephemeral=True, delete_after=_settings.msg_timeout)


async def setup(bot: "MrFriendly") -> None:
    await bot.add_cog(AutoRole(bot=bot))
