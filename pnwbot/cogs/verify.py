
import logging
from sqlite3 import Row
from typing import TYPE_CHECKING

import util.asqlite as asqlite
from database import *
from database.settings import Settings
from discord import (CategoryChannel, Forbidden, Member, Message,
                     PermissionOverwrite, Reaction, Role, TextChannel)
from discord.ext import commands
from util.utils import MarkDownPlaceHolders, parse_markdown

if TYPE_CHECKING:
    from main import MrFriendly


async def _get_guild_settings(guild_id: int) -> Settings:
    _logger = logging.getLogger()
    async with asqlite.connect(database=Base.DB_FILE_PATH) as conn:
        res: Row | None = await conn.fetchone("""SELECT * FROM settings WHERE guild_id = ?""", (guild_id,))
        if res is None:
            _logger.error(msg=f"Failed to find the Discord Guild Settings. | Guild ID: {guild_id}")
        return Settings(**res) if res is not None else Settings(guild_id=guild_id)


class Verify(commands.Cog):
    _logger: logging.Logger = logging.getLogger()
    to_be_verified: list[Member] = []
    
    def __init__(self, bot: "MrFriendly") -> None:
        self._bot: "MrFriendly" = bot
        self._logger.info(msg=f"{self.__class__.__name__} Cog has been loaded!")
        
    @commands.Cog.listener()
    async def on_member_remove(self, member: Member) -> None:
        _verify_category = member.guild.get_channel(1276028226166198394)
        if not isinstance(_verify_category, CategoryChannel):
            return
        for channel in _verify_category.channels:
            if not isinstance(channel, TextChannel):
                return
            if channel.topic is not None and channel.topic == str(object=member.id):
                try:
                    await channel.delete(reason=f"{member.display_name} left the server prior to the verification process finishing.")
                except Exception as e:
                    self._logger.error(msg=f"Failed to remove Verification channel - {member.display_name} -> {channel.name}")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: Reaction, member: Member) -> None:
        if reaction.message.guild is None:
            return
        _settings: Settings = await _get_guild_settings(guild_id=reaction.message.guild.id)
        # We only care about the rules message id reactions. Doesn't matter what reaction honestly.
        if reaction.message.id == _settings.rules_message_id:
            _dbuser: User | None = await User.add_or_get_user(guild_id=reaction.message.guild.id, user_id=member.id)
            if member in self.to_be_verified and _dbuser is not None:
                await _dbuser.update_verified(verified= True)
            if _dbuser is None:
                chan = reaction.message.guild.get_channel(_settings.notification_channel_id)
                self._logger.error(msg=f"Failed to Add and or Get the Discord Member {member.id} from our Database, unable to verify the user.")
                if chan is not None and isinstance(chan, TextChannel):
                    await chan.send(content=f"Failed to Add and or Get the Discord Member {member.id} from our Database, unable to verify the user.")
                

    async def rules_reaction_check(self, member: Member) -> bool:
        """
        Check's the rules message for a :thumbsup: emoji reaction from the discord.Member
        """
        _settings: Settings = await _get_guild_settings(guild_id=member.guild.id)
        _rules_chan = member.guild.get_channel(_settings.rules_channel_id)
        if not isinstance(_rules_chan, TextChannel):
            return False
        
        _rules_msg: Message = await _rules_chan.fetch_message(_settings.rules_message_id)
        self._logger.warn(msg=f"**DEBUG** -- Checking {member.name} has reacted to rules message. {_rules_msg}")
        for reaction in _rules_msg.reactions:
            # We only care that the user has reacted; regardless of what reaction it is.
            async for user in reaction.users():
                self._logger.warn(msg=f"**DEBUG** -- Validating member match to reactions ->{user.id}  || {member.id}")
                if user == member:
                    return True
            
        return False
    
    @commands.Cog.listener(name="on_member_join")
    async def user_verify_process(self, member: Member) -> None:
        """
        Create's a Text Channel for the Discord Member joining the server under the User Verification category.

        Args:
            guild (Guild): The Discord Guild to create the channel in.
            member (Member): The Discord Member to create the channel for.
        """
        _verify_category = member.guild.get_channel(1276028226166198394) #User Verification category.
        _settings: Settings = await _get_guild_settings(guild_id=member.guild.id)
        
        if isinstance(_verify_category, CategoryChannel):
            _overwrites: dict[Role | Member, PermissionOverwrite] = {
                member.guild.default_role: PermissionOverwrite(read_messages=False),
                member.guild.me: PermissionOverwrite(read_messages=True),
                member: PermissionOverwrite(read_message_history=True, read_messages=True, view_channel=True, send_messages=True, attach_files=True)
            }
            _mod_role: Role | None = member.guild.get_role(_settings.mod_role_id)
            if _mod_role is not None:
                _overwrites[_mod_role] = PermissionOverwrite(read_message_history=True, read_messages=True, view_channel=True, send_messages=True, attach_files=True, manage_messages= True)

            usr_chan: TextChannel = await _verify_category.create_text_channel(name=f"__{member.display_name}__", position=0, topic=str(object=member.id), reason=f"Verifying {member.display_name}", overwrites=_overwrites)
            await usr_chan.edit(overwrites= _overwrites)
            await usr_chan.send(content=f"{_mod_role.mention if _mod_role is not None else ''}")
            await usr_chan.send(content=f"{parse_markdown(path='../verify_intro.md', placeholder_struct=MarkDownPlaceHolders(member=member, settings=_settings))}")

    @commands.hybrid_command(name="verify")
    @commands.guild_only()
    @commands.has_any_role("Moderator")
    async def verify_user(self, context: commands.Context) -> Message | None:
        assert context.guild
        _settings: Settings = await _get_guild_settings(guild_id=context.guild.id)

        if isinstance(context.channel, TextChannel) and context.channel.topic is not None and context.guild is not None:
            _content: str = f"Failed to Verify <@!{context.channel.topic}>"
            _member: Member | None = context.guild.get_member(int(context.channel.topic))
            _verify_role: Role | None = context.guild.get_role(_settings.verified_role_id)
            _welcome_channel = context.guild.get_channel(_settings.welcome_channel_id)
            if _member is None:
                return await context.send(content=_content + ", please manually verify the user.")
            
            # Database handling of our User's verified status.
            _dbuser: User | None = await User.add_or_get_user(guild_id=context.guild.id, user_id=_member.id)
            if _dbuser is not None:
                await _dbuser.update_verified(verified=True)
                self._logger.info(msg=f"Updated {_dbuser.user_id} verified status in the DB. {_dbuser.verified}")

            if _verify_role is None:
                return await context.send(content=_content + " due to no Verified Discord Role set in our settings., please manually verify the user.")
                # await context.send(content="Unable to send the welcome message, please set your Welcome Channel ID.")

            if _welcome_channel is None:
                self._logger.warn(msg=f"Unable to send the welcome message, please set your Welcome Channel ID. | Guild ID: {context.guild.id}")
                return await context.send(content="Unable to send the welcome message, please set your Welcome Channel ID.")

            if self.rules_reaction_check(member=_member) is False:
                self.to_be_verified.append(_member)
                return await context.send(content=f"The {_member.display_name} has yet to :thumbsup: to the rules message! -> <#{_settings.rules_channel_id}>, please do so!, aborting verification process.")

            try:
                await _member.add_roles(_verify_role)
                await context.channel.delete(reason=f"Verified {_member.display_name} by {context.author.name}, removing channel.")
            except Forbidden:
                self._logger.warn(msg=f"Unable to add role {_settings.verified_role_id}. | Guild ID: {context.guild.id}")
                return await context.send(content=_content + " due to improper permissions set.")
            except Exception as e:
                self._logger.error(msg=f"Unable to add role {_settings.verified_role_id} | Guild ID: {context.guild.id} | Error: {e}")

            if isinstance(_welcome_channel, TextChannel):
                return await _welcome_channel.send(content=parse_markdown(path="../welcome.md", placeholder_struct=MarkDownPlaceHolders(member= _member, settings=_settings)))

        return await context.send(content="Unable to process this verification, please manually verify the user and delete the channel when done.")


async def setup(bot: "MrFriendly") -> None:
    await bot.add_cog(Verify(bot=bot))
