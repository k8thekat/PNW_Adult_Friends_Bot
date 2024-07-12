import logging
import os
from functools import partial
from re import Match, Pattern, compile
from typing import Any, List, Optional, Union

import discord
from discord import ButtonStyle, Embed, Emoji, PartialEmoji, app_commands
from discord.ext import commands
from discord.ui import Button, View

from database import *
from database.settings import Role_Embed_Info

from ..main import MrFriendly

interaction = discord.Interaction

# TODO - Role selection Embeds.
# - Needs to support up to 8 buttons at once.


class RoleButton(Button):
    """This is for the Reaction Role View"""

    def __init__(self, *, style: ButtonStyle = ButtonStyle.green, label: Optional[str], custom_id: Optional[str], ):
        super().__init__(style=style, label=label, custom_id=custom_id)


class ReactionRoleView(View):
    def __init__(self, *, timeout: Union[float, None] = 180, buttons: list[RoleButton]) -> None:
        # def __init__(self, *, timeout: Union[float, None] = 180, custom_id: str, button_label: str, button_emoji: Union[str, Emoji, PartialEmoji, None]) -> None:
        super().__init__(timeout=timeout)
        for button in buttons:
            # self.add_item(RoleButton(custom_id=custom_id, label=button_label, emoji=button_emoji))
            self.add_item(button)


class AutoRole(commands.Cog):
    _logger: logging.Logger = logging.getLogger()

    def __init__(self, bot: MrFriendly) -> None:
        super().__init__()
        self._name: str = os.path.basename(__file__).title()
        self._logger.info(msg=f'**SUCCESS** Initializing {self._name}')
        self._bot = bot

    REACTION_ROLES_BUTTON_REGEX: Pattern[str] = compile(r'RR::BUTTON::(?P<ROLE_ID>\d+)')
    AGE_ROLE_GROUP: list[int] = [1259692047036715128, 1259660826915110942, 1259660900445454378, 1259661047602610176, 1259661129299267705]
    SEX_ORIENTATION_ROLE_GROUP: list[int] = [1259661460804599929, 1259661532095320074, 1259661605902483536, 1259661655319515236, 1259661691453571134, 1259661715004588134, 1259661742066110585, 1259661787758858304]
    GENDER_ROLE_GROUP: list[int] = [1259650732005789706, 1259650866835619912, 1259650920858386472, 1259650994707628052, 1259651332575596544, 1259683302760255558]
    PRONOUNS_ROLE_GROUP: list[int] = [1259660711835992136, 1259660769155354725, 1259660799555928194, 1259683965695164456]
    RELATIONSHIP_ROLE_GROUP: list[int] = [1259661152309215373, 1259661187155755139, 1259661227911680070, 1259661289433727026]
    DM_ROLE_GROUP: list[int] = [1259698813795565649, 1259698893558517822, 1259698953105051728]
    LOCATION_ROLE_GROUP: list[int] = [1260380394872635392, 1260380525860880515, 1260380565731934339, 1260380601953816669]

    async def autocomplete_role_embeds(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
        assert interaction.guild
        _role_embeds: list[Role_Embed_Info] = await Role_Embed_Info.get_all_role_embeds(guild_id=interaction.guild.id)
        return [app_commands.Choice(name=f"{role_embed.name} - {role_embed.id}", value=role_embed.id) for role_embed in _role_embeds if current.lower() in role_embed.name.lower()]

    async def autocomplete_embed_buttons(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int | str]]:
        assert interaction.guild
        _temp: Any = interaction.namespace.role_embed
        if _temp is None or isinstance(_temp, int):
            return [app_commands.Choice(name="Failed to find Role Embed...", value=9999)]

        _role_embed: Role_Embed_Info = await Role_Embed_Info.get_role_embed(id=_temp)
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

    @app_commands.command(name='role_embed')
    @commands.guild_only()
    @commands.has_role("Moderator")
    async def role_embed(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel], embed_title: str, field_body: str, role1: discord.Role,
                         role2: Optional[discord.Role] = None, role3: Optional[discord.Role] = None, role4: Optional[discord.Role] = None, role5: Optional[discord.Role] = None) -> None:
        """Displays an Embed in a channel that Users can interact with the button to `Add` or `Remove` a role."""
        assert interaction.guild
        assert interaction.channel
        embed = Embed(title=f'**{embed_title}**', color=discord.Color.blurple(), description="Please select a button below to add or remove the roles. You are limited to one role at a time, selecting another role removes the previously selected role.")
        embed.add_field(name='**What is this for?**', value=field_body)
        _roles: list[discord.Role | None] = [role1, role2, role3, role4, role5]
        _buttons: list[RoleButton] = []
        for entry in _roles:
            if entry is not None:
                _buttons.append(RoleButton(custom_id=f"RR::BUTTON::{entry.id}", label=entry.name))

        role_view = ReactionRoleView(timeout=None, buttons=_buttons)

        if channel == None:
            if isinstance(interaction.channel, discord.TextChannel):
                channel = interaction.channel
            else:
                return await interaction.response.send_message(content=f"This command can only be used in a Text Channel, please consider picking a channel next time.", ephemeral=True, delete_after=self._bot._guild_settings.msg_timeout)

        res: discord.Message = await channel.send(embed=embed, view=role_view)
        await Role_Embed_Info.add_role_embeds(name=embed_title, guild_id=interaction.guild.id, channel_id=channel.id, message_id=res.id)

    @app_commands.command(name="add_button")
    @commands.guild_only()
    @commands.has_role("Moderator")
    @app_commands.describe(role_embed="The ID of the embed you want to add roles to.", role="The role you want to add to the embed.")
    @app_commands.autocomplete(role_embed=autocomplete_role_embeds)
    async def add_button_to_role_embed(self, interaction: discord.Interaction, role_embed: int, role: discord.Role) -> None:
        assert interaction.guild
        _role_embed: Role_Embed_Info = await Role_Embed_Info.get_role_embed(id=role_embed)
        _channel = interaction.guild.get_channel(_role_embed.channel_id)
        if isinstance(_channel, discord.TextChannel):
            _msg: discord.Message = await _channel.fetch_message(_role_embed.message_id)
            _button = RoleButton(custom_id=f"RR::BUTTON::{role.id}", label=role.name)
            _view: View = discord.ui.View.from_message(_msg, timeout=None).add_item(item=_button)
            if len(_msg.embeds) > 1:
                return await interaction.response.send_message(content=f"This message has too many embeds to discern which one I need.", ephemeral=True, delete_after=self._bot._guild_settings.msg_timeout)
            await _msg.edit(view=_view)
            return await interaction.response.send_message(content=f"Added the role **{role.mention}** to our view for**{_role_embed.name}**", ephemeral=True, delete_after=self._bot._guild_settings.msg_timeout)

        return await interaction.response.send_message(content=f"This Channel we have does not seem to be a Text Channel. {_role_embed.message_id if _channel is None else _channel.mention}",
                                                       ephemeral=True, delete_after=self._bot._guild_settings.msg_timeout)

    @app_commands.command(name="remove_button")
    @commands.guild_only()
    @commands.has_role("Moderator")
    @app_commands.autocomplete(role_embed=autocomplete_role_embeds)
    @app_commands.autocomplete(button=autocomplete_embed_buttons)
    async def remove_button_to_role_embed(self, interaction: discord.Interaction, role_embed: int, button: str) -> None:
        assert interaction.guild
        _role_embed: Role_Embed_Info = await Role_Embed_Info.get_role_embed(id=role_embed)
        _channel = interaction.guild.get_channel(_role_embed.channel_id)
        if not isinstance(_channel, discord.TextChannel):
            return await interaction.response.send_message(content=f"Failed to find a Text Channel for : {_role_embed.channel_id}", ephemeral=True, delete_after=self._bot._guild_settings.msg_timeout)
        _msg: discord.Message = await _channel.fetch_message(_role_embed.message_id)
        _view: View = discord.ui.View.from_message(_msg, timeout=None)
        found = False
        for item in _view.children:
            if not isinstance(item, Button):
                continue
            if item.label == button or item.custom_id == button:
                _view.remove_item(item=item)
                await _msg.edit(view=_view)
                found = True
                break
        if not found:
            return await interaction.response.send_message(content=f"Failed to find and remove a button with the name: {button} from the Embed Message: {_msg.jump_url}", ephemeral=True, delete_after=self._bot._guild_settings.msg_timeout)
        return await interaction.response.send_message(content=f"Removed the button: {button} from the Embed Message: {_msg.jump_url}", ephemeral=True, delete_after=self._bot._guild_settings.msg_timeout)

    @commands.Cog.listener(name='on_interaction')
    async def on_reaction_role(self, interaction: discord.Interaction) -> None:
        if interaction.type != discord.InteractionType.component:
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
                return await interaction.response.send_message(content='Sorry, that role does not seem to exist anymore...', ephemeral=True)

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
                        return await interaction.response.send_message(content='Sorry, that role does not seem to exist anymore...', ephemeral=True)
                    _removed_role = True
                    await interaction.user.remove_roles(role, atomic=True)

            await interaction.user.add_roles(_reaction_role, atomic=True)
            return await interaction.response.send_message(content=f"Reassigned your role to {_reaction_role.mention} from {role.mention}."
                                                           if _removed_role is True else f"Gave you the role {_reaction_role.mention}.",
                                                           ephemeral=True, delete_after=self._bot._guild_settings.msg_timeout)


async def setup(bot: MrFriendly) -> None:
    await bot.add_cog(AutoRole(bot=bot))
