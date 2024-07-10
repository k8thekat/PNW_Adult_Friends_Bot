
import asyncio
import configparser
import logging
from datetime import datetime, timedelta
from logging import Logger
from pathlib import Path
from sqlite3 import Row
from typing import Any, Union

import discord
from discord import CategoryChannel, Intents, Message, TextChannel
from discord.ext import commands, tasks

import util.asqlite as asqlite
from database import *
from database.base import DB_FILE_PATH
from database.settings import Settings
from database.user import Image, User

TOKEN: str


def load_ini() -> Any:
    path: str = Path("./pnwbot/token.ini").as_posix()
    _parser = configparser.ConfigParser()
    _parser.read(filenames=path)
    if "DISCORD" in _parser.sections():
        _token: configparser.SectionProxy = _parser["DISCORD"]
        return _token.get(option="token")
    else:
        raise ValueError("Failed to find `DISCORD` section in token.ini file.")


async def _get_prefix(bot: "MrFriendly", message: Message):
    prefixes = [bot._prefix]
    if message.guild is not None:
        _guild: int = message.guild.id

        async with asqlite.connect(database=DB_FILE_PATH) as db:
            async with db.cursor() as cur:
                await cur.execute("""SELECT prefix FROM prefix WHERE guild_id = ?""", _guild)
                res: list[Row] = await cur. fetchall()
                if res is not None and len(res) >= 1:
                    prefixes: list[str] = [entry["prefix"] for entry in res]

    wmo_func = commands.when_mentioned_or(*prefixes)
    return wmo_func(bot, message)


# TODO - Member verified event to send message in #general channel.
# TODO - Role selection Embeds.
# TODO - Handle Suggestions-Feedback channel - Remove someones suggestion after it is sent.
# TODO - Infractions Handling.
# TODO - Verification Channels for New Users (Use Category + User ID for channel name)
    # - ?verify command

class MrFriendly(commands.Bot):
    _logger: Logger = logging.getLogger(name=__name__)
    _database: Base = Base()
    _inactive_time = timedelta(days=180)  # How long a person has to have not been active in the server.

    def __init__(self) -> None:
        intents: Intents = Intents.default()
        intents.members = True
        intents.message_content = True
        self._prefix = "$"
        self.NSFW_category: int | None = None  # NSFW Pics Discord Category ID
        self._guild_id: int = 1259645744420360243
        self._to_clean_channels: set[TextChannel] = set()
        super().__init__(intents=intents, command_prefix=_get_prefix)

    async def on_ready(self) -> None:
        self._logger.info(msg=f'Logged on as {self.user}!')

    async def setup_hook(self) -> None:
        await self._database._create_tables()
        self.delete_pictures.start()
        self.kick_unverified_users.start()
        self.kick_inactive_users.start()
        self._guild_settings: Settings | None = await Settings.add_or_get_settings(guild_id=self._guild_id)

    @tasks.loop(minutes=5)
    async def delete_pictures(self) -> None:
        """
        Delete's pictures from channels that are over 14 days old.
        """
        await self.wait_until_ready()
        _guild: discord.Guild | None = self.get_guild(self._guild_id)
        if _guild is None:
            self._logger.error(msg=f"Failed to find the Discord Guild. | Guild ID: {self._guild_id}")
            return

        if self._NSFW_category is None:
            for category in _guild.categories:
                if category.name.lower() == "nsfw pics":
                    self._NSFW_category: CategoryChannel = category
                    break

        # check if we have any channels to clean
        # We are using a set, so no need to check for duplicates.
        if len(self._to_clean_channels) == 0:
            for channel in self._NSFW_category.channels:
                if isinstance(channel, TextChannel):
                    self._to_clean_channels.add(channel)

        _cur_channel: TextChannel = list(self._to_clean_channels)[0]
        self._to_clean_channels.remove(_cur_channel)
        # check messages older than 14 days and delete them with a maximum of 20 messages
        # to avoid overloading the api calls
        # similar logic to the check_msgs command to confirm the messages obtained
        older_date: datetime = discord.utils.utcnow() - timedelta(days=14)
        async for message in _cur_channel.history(limit=30, before=older_date, oldest_first=False):
            # if pinned then skip the message
            if message.pinned:
                continue

            try:
                await message.delete()
                await asyncio.sleep(delay=1)  # 1 second delay as a buffer for communicating with discord
            except Exception as ex:
                self._logger.error(msg=f"Failed to delete message. | Message ID: {message.id} | Exception: {ex}")  # print the exception to the local log while allowing us to continue delete attempts

    @tasks.loop(hours=6)
    async def kick_unverified_users(self) -> None:
        """
        Kicks users that haven't verified in 7 days.
        """
        # incase we aren't connected
        await self.wait_until_ready()

        # We need to get our verified_role_id from the settings.
        if self._guild_settings is None or self._guild_settings.verified_role_id is None:
            self._logger.error(msg=f"Failed to find the Discord Guild Verified Role. | Guild ID: {self._guild_id}")
            return

        _guild: discord.Guild | None = self.get_guild(self._guild_id)
        if _guild is None:
            self._logger.error(msg=f"Failed to find the Discord Guild. | Guild ID: {self._guild_id}")
            return

        if self.user is not None:
            _user: discord.Member | None = _guild.get_member(self.user.id)
            if _user is not None and _user.guild_permissions.kick_members is False:
                self._logger.error(msg=f"{self.user.name} does not have permission to kick members in the Discord Guild. | Guild ID: {self._guild_id}")

        # kick users that haven't verified in 7 days
        # requirements is only 1 role which is the default @everyone with a join time 7 days or later in the past
        for member in _guild.members:
            if member.joined_at is None:
                continue
            join_time_len: int = (discord.utils.utcnow() - member.joined_at).days
            res: discord.Role | None = member.get_role(self._guild_settings.verified_role_id)
            if (res is None) and join_time_len >= 7:
                await member.kick(reason="Failed to verify within 7 days")
                # delay between kicks
                await asyncio.sleep(delay=1)

    @tasks.loop(hours=24)
    async def kick_inactive_users(self) -> None:
        """
        Kicks users that haven't been active in the server for over our inactive time.
        """
        await self.wait_until_ready()

        _guild: discord.Guild | None = self.get_guild(self._guild_id)
        if _guild is None:
            self._logger.error(msg=f"Failed to find the Discord Guild. | Guild ID: {self._guild_id}")
            return

        if self.user is not None:
            _bot: discord.Member | None = _guild.get_member(self.user.id)
            if _bot is not None and _bot.guild_permissions.kick_members is False:
                self._logger.error(msg=f"{self.user.name} does not have permission to kick members in the Discord Guild. | Guild ID: {self._guild_id}")

        for member in _guild.members:
            _user: User | None = await User.add_or_get_user(guild_id=member.guild.id, user_id=member.id)
            _active_by: datetime = (datetime.now() - self._inactive_time)
            if _user is None:
                continue
            if _user.last_active_at < _active_by:
                await member.kick(reason="Inactive for over 6 months.")
                # delay between kicks
                await asyncio.sleep(delay=1)

    @tasks.loop(minutes=15)
    async def user_cleanup(self) -> None:
        await self.wait_until_ready()
        for guild in self.guilds:
            if self.user is not None:
                _user: discord.Member | None = guild.get_member(self.user.id)
                if _user is not None and _user.guild_permissions.manage_messages is False:
                    self._logger.error(msg=f"{self.user.name} does not have permission to manage messages in the Discord Guild. | Guild ID: {guild.id}")

            _users: list[User] = await User.get_banned_users(guild_id=guild.id)
            _users.extend(await User.get_unclean_users(guild_id=guild.id))

            for user in _users:
                if user.cleaned is True:
                    continue

                _images: list[Image] = list(await user.get_all_images())
                if len(_images) == 0:
                    await user.update_cleaned(cleaned=True)
                for image in _images[:30]:
                    _channel = guild.get_channel(image.channel_id)
                    if isinstance(_channel, TextChannel):
                        # !WARNING! - Could this fail if a user deletes the message themselves?
                        await _channel.get_partial_message(image.message_id).delete()
                        await user.remove_image(image=image)
                    else:
                        await user.remove_image(image=image)

    async def on_command(self, context: commands.Context) -> None:
        self._logger.info(msg=f'{context.author.name} used {context.command}...')

    async def on_command_error(self, context: commands.Context, error: commands.CommandError) -> None:
        if context.command is not None:
            if isinstance(error, commands.TooManyArguments):
                await context.send(content=f'You called the {context.command.name} command with too many arguments.')
            elif isinstance(error, commands.MissingRequiredArgument):
                await context.send(content=f'You called {context.command.name} command without the required arguments')

    async def on_reaction_add(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]) -> None:
        if user == self.user:
            return
        if reaction.message.guild is not None:
            _user: User | None = await User.add_or_get_user(guild_id=reaction.message.guild.id, user_id=user.id)
            if _user is None:
                self._logger.error(msg=f"Failed to find the Database User when updating their last active time. | Guild ID: {reaction.message.guild.id} | User ID: {user.id}")
                return
            await _user.update_last_active_at()

            if self._guild_settings is None:
                self._logger.error(msg=f"Failed to find the Discord Guild Settings in on_reaction_add. | Guild ID: {reaction.message.guild.id}")
                return

            if self.user is None:
                self._logger.error(msg=f"Failed to find the Discord Bot User in on_reaction_add. | Guild ID: {reaction.message.guild.id}")
                return

            _bot: discord.Member | None = reaction.message.guild.get_member(self.user.id)
            if _bot is not None and _bot.guild_permissions.manage_roles is False:
                self._logger.error(msg=f"{_bot.name} does not have permission to manage roles in the Discord Guild. | Guild ID: {reaction.message.guild.id}")
                return

            if reaction.message.id != self._guild_settings.rules_message_id:
                return

            if _user.verified is True:
                if self._guild_settings.verified_role_id is None:
                    return
                _role: discord.Role | None = reaction.message.guild.get_role(self._guild_settings.verified_role_id)
                if _role is not None and isinstance(user, discord.Member):
                    await user.add_roles(_role)

    async def on_message(self, message: discord.Message) -> None:
        # ignore ourselves and any message where the author isn't a Member
        if (message.author == self.user) or (isinstance(message.author, discord.Member) == False):
            return
        # update last active time
        if message.guild is not None:
            _user: User | None = await User.add_or_get_user(guild_id=message.guild.id, user_id=message.author.id)
            if _user is not None:
                await _user.update_last_active_at()

            if len(message.attachments) != 0 and _user is not None:
                await _user.add_image(channel_id=message.channel.id, message_id=message.id)

        # ignore moderator messages
        if self._guild_settings is not None and self._guild_settings.mod_role_id is not None:
            if isinstance(message.author, discord.Member) and message.author.get_role(self._guild_settings.mod_role_id) != None:
                return

        # check for posts without an attachment in specific channels
        # if found then delete it and alert the person
        if message.channel in self._NSFW_category.channels:
            if len(message.attachments) == 0:
                # no attachment, alert the user about where to post
                await message.delete(delay=3)
                if self._guild_settings is None:
                    return

                if self._guild_settings.flirting_channel_id is None:
                    await message.channel.send(content=f"{message.author.mention} | Text messages are not allowed in this channel.", delete_after=10)

                elif isinstance(message.channel, TextChannel) and message.guild is not None:
                    _channel = message.guild.get_channel(self._guild_settings.flirting_channel_id)
                    if _channel is None:
                        return
                    else:
                        await message.channel.send(content=f"{message.author.mention} Text messages are not allowed in this channel. Please post them in {_channel.mention}", delete_after=10)
                return
            else:
                # if there is an attachment then verify it is an image or video
                for entry in message.attachments:
                    if entry.content_type is not None and entry.content_type.split("/")[0] not in ["image", "video"]:
                        await message.delete(delay=3)
                        await message.channel.send(f"{message.author.mention}: Only Images and Videos are allowed in this channel", delete_after=10)
                        return

    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is not None:
            _user: User | None = await User.add_or_get_user(guild_id=message.guild.id, user_id=message.author.id)
            if _user is not None:
                _img: Image | None = await _user.get_image(channel_id=message.channel.id, message_id=message.id)
                if _img is None:
                    return
                await _user.remove_image(image=_img)

    async def on_member_leave(self, member: discord.Member) -> None:
        _user: User | None = await User.add_or_get_user(guild_id=member.guild.id, user_id=member.id)
        if _user is None:
            return
        await _user.add_leave()

    async def on_member_join(self, member: discord.Member) -> None:
        _user: User | None = await User.add_or_get_user(guild_id=member.guild.id, user_id=member.id)
        if _user is None:
            return
        await _user.update_cleaned(cleaned=False)

    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        _user: User | None = await User.add_or_get_user(guild_id=guild.id, user_id=user.id)
        if _user is None:
            return
        await _user.update_banned(banned=True)


client = MrFriendly()


@ client.hybrid_group(name='pnwkink')
async def main_bot(context: commands.Context):
    if context.author.guild_permissions.administrator == False:
        return

    if context.invoked_subcommand is None:
        await context.send('Invalid command passed...', ephemeral=True, delete_after=client.Message_Timeout)


@ main_bot.command(name='test')
async def test(context: commands.Context, author_ref: str):
    if context.author.guild_permissions.administrator == False:
        return

    return


@ main_bot.command(name="sync")
async def sync(context: commands.Context, local: bool = True, reset: bool = False):
    if context.author.guild_permissions.administrator == False:
        print("User not administrator")
        return

    """Syncs Bot Commands to the current guild this command was used in."""
    await context.defer()
    if ((type(reset)) == bool and (reset == True)):
        if ((type(local) == bool) and (local == True)):
            # Local command tree reset
            client.tree.clear_commands(guild=context.guild)
            return await context.send('**WARNING** Resetting PNWKink Commands Locally...', ephemeral=True, delete_after=client.Message_Timeout)

        elif context.author.id == 479429344213860372:
            # Global command tree reset, limited by LightningTH discord ID
            client.tree.clear_commands(guild=None)
            return await context.send('**WARNING** Resetting PNWKink Commands Globally...', ephemeral=True, delete_after=client.Message_Timeout)
        else:
            return await context.send('**ERROR** You do not have permission to reset the commands.', ephemeral=True, delete_after=client.Message_Timeout)

    if ((type(local) == bool) and (local == True)):
        # Local command tree sync
        client.tree.copy_global_to(guild=context.guild)
        await client.tree.sync(guild=context.guild)
        return await context.send(f'Successfully Sync\'d PNWKink Commands to {context.guild.name}...', ephemeral=True, delete_after=client.Message_Timeout)

    elif context.author.id == self.owner:
        # Global command tree sync, limited by LightningTH discord ID
        await client.tree.sync(guild=None)
        await context.send('Successfully Sync\'d PNWKink Commands Globally...', ephemeral=True, delete_after=client.Message_Timeout)


TOKEN = load_ini()
client.run(token=TOKEN)
