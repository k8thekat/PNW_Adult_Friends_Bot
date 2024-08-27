
import logging
from sqlite3 import Row

import util.asqlite as asqlite
from database import *
from database.settings import Settings
from discord import (CategoryChannel, Guild, Member, PermissionOverwrite, Role,
                     TextChannel)
from discord.ext import commands
from util import utils


async def _get_guild_settings(guild_id: int) -> Settings:
    _logger = logging.getLogger()
    async with asqlite.connect(database=Base.DB_FILE_PATH) as conn:
        res: Row | None = await conn.fetchone("""SELECT * FROM settings WHERE guild_id = ?""", (guild_id,))
        if res is None:
            _logger.error(msg=f"Failed to find the Discord Guild Settings. | Guild ID: {guild_id}")
        return Settings(**res) if res is not None else Settings(guild_id=guild_id)



class Verify(commands.Cog):
    _logging: logging.Logger = logging.getLogger()

    async def on_member_update(self, before_member: Member, after_member: Member) -> None:
        _settings: Settings = await Settings.add_or_get_settings(guild_id=after_member.guild.id)
        # check the before member if they have the verified role id.
        if _settings.verified_role_id in [role.id for role in before_member.roles]:
            return
        # check if the after member has the verified role id.
        elif _settings.verified_role_id not in [role.id for role in after_member.roles]:
            return
        else:
            _channel = after_member.guild.get_channel(_settings.welcome_channel_id)
            if not isinstance(_channel, TextChannel):
                return

            _intros_channel = None
            _roles_channel = None
            if _settings.personal_intros_channel_id is not None:
                _intros_channel = after_member.guild.get_channel(_settings.personal_intros_channel_id)
            if _settings.roles_channel_id is not None:
                _roles_channel = after_member.guild.get_channel(_settings.roles_channel_id)
            # TODO - See about converting this to use the `welcome.md`
            await _channel.send(content=f"""Hello everyone, please welcome {after_member.mention} to our community.
                                    Please head on over to our Roles channel {"<not set>" if _roles_channel is None else _roles_channel.mention} and select a role.
                                    You can also head on over to our Intros channel {'<not set>' if _intros_channel is None else _intros_channel.mention} and introduce yourself!""")
            return

    async def user_verify_process(self, guild: Guild, member: Member) -> None:
        _verify_category = guild.get_channel(1276028226166198394)
        _settings: Settings = await _get_guild_settings(guild_id=guild.id)
        _mod_role: Role | None = guild.get_role(_settings.mod_role_id)
        if isinstance(_verify_category, CategoryChannel):
            _overwrites: dict[Role | Member, PermissionOverwrite] = {
                guild.default_role: PermissionOverwrite(read_messages=False),
                guild.me: PermissionOverwrite(read_messages=True)
            }
            member.mention
            usr_chan: TextChannel = await _verify_category.create_text_channel(name=f"{member.display_name} || Verification", position=0, topic=str(member.id), reason=f"Verifying {member.display_name}", overwrites=_overwrites)
            await usr_chan.send(content=f"{_mod_role.mention if _mod_role is not None else ''} {await utils.parse_markdown(path='./verify_intro.md')}")

    @commands.hybrid_command(name="verify")
    @commands.guild_only()
    @commands.has_any_role("Moderator")
    async def verify_user(self, context: commands.Context) -> None:
        # TODO - Finish fleshing out the `?verify` command.
        if isinstance(context.channel, TextChannel) and context.channel.topic is not None and context.guild is not None:
            _get_user: Member | None = context.guild.get_member(int(context.channel.topic))
        pass
