import logging
from dataclasses import fields
from typing import TYPE_CHECKING, cast

from database import Settings
from discord import (Color, Embed, Interaction, Message, Role, TextChannel,
                     app_commands)
from discord.ext import commands
from util.emoji_lib import Emojis

if TYPE_CHECKING:
    from main import MrFriendly



class SettingsEmbed(Embed):
    def __init__(self, data: Settings, title: str, description: str, color: Color) -> None:
        super().__init__(title=f"{Emojis.wrench} | {title} | {Emojis.wrench} ", description=description, color=color)
        for field in fields(class_or_instance=data):
            if "channel_id" in field.name:
                self.add_field(name=f"__{field.name}__", value=f"<#{getattr(data, field.name)}>")
            elif "role_id" in field.name:
                self.add_field(name=f"__{field.name}__", value=f"<@&{getattr(data, field.name)}>")
            else:
                self.add_field(name=f"__{field.name}__", value=f"{getattr(data, field.name)}")


class GuildSettings(commands.Cog):
    _logger: logging.Logger = logging.getLogger()
    def __init__(self, bot: "MrFriendly") -> None:
        self.bot: "MrFriendly" = bot
        self._logger.info(msg=f"{self.__class__.__name__} Cog has been loaded!")

    async def autocomplete_properties(self, interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [app_commands.Choice(name=field.name, value=field.name) for field in fields(class_or_instance=Settings) if current.lower() in field.name.lower()][:25]

    async def autocomplete_setting_choices(self, interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
        assert interaction.guild
        _property: str = interaction.namespace.property
        _properties: list[str] = [field.name for field in fields(class_or_instance=Settings)]
        if _property not in _properties:
            return [app_commands.Choice(name="Invalid Property", value=str(9999))][:25]

        if "channel_id" in _property:
            return [app_commands.Choice(name=entry.name, value=str(entry.id)) for entry in interaction.guild.text_channels if (current.lower() in entry.name.lower())][:25]

        if "role_id" in _property:
            return [app_commands.Choice(name=role.name, value=str(role.id)) for role in interaction.guild.roles if current.lower() in role.name.lower() or current.lower() in str(role.id).lower()][:25]
        if "message_id" in _property:
            return [app_commands.Choice(name=current, value=current)][:25]
        else:
            return [app_commands.Choice(name=str(count), value=str(count))for count in range(0, 100, 5) if current.lower() in str(count).lower()][:25]

    @app_commands.command(name="guild_setting", description="Set a Guild Setting property.")
    @commands.guild_only()
    @commands.has_any_role("Moderator")
    @app_commands.autocomplete(property=autocomplete_properties)
    @app_commands.autocomplete(value=autocomplete_setting_choices)
    async def set_property(self, interaction: Interaction, property: str, value: str) -> None:
        assert interaction.guild
        _value = int(value)
        _settings: Settings = await Settings.add_or_get_settings(guild_id=interaction.guild.id)
        if _value == 9999:
            _content: str = "Invalid Property selected"
        await _settings.update_property(property=property, value=_value)
        if "channel_id" in property:
            _content = f"Settings updated, set `{property}` to <#{_value}>"
        elif "role_id" in property:
            _content = f"Settings updated, set `{property}` to <@&{_value}>"

        elif "message_id" in property:
            _msg: Message | None = interaction.client._connection._get_message(msg_id=int(_value))
            _content = f"Settings updated, set `{property}` to {_msg.jump_url if _msg is not None else _value}"
        else:
            _content = f"Settings updated, set `{property}` to `{_value}`"
        self.bot._settings = _settings
        return await interaction.response.send_message(content=_content, ephemeral=True, delete_after=_settings.msg_timeout)

    @app_commands.command(name="show_settings", description="Show the current Guilds Settings.")
    @commands.guild_only()
    @commands.has_any_role("Moderator")
    async def show_settings(self, interaction: Interaction) -> None:
        assert interaction.guild
        _settings: Settings = self.bot._settings
        _embed = SettingsEmbed(data=_settings,
                               title=f"Guild Settings | {interaction.guild.name}",
                               description=f"Current guild settings",
                               color=Color.blurple())
        return await interaction.response.send_message(embed=_embed, ephemeral=True, delete_after=_settings.msg_timeout)


async def setup(bot: "MrFriendly") -> None:
    await bot.add_cog(GuildSettings(bot=bot))
