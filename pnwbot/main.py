
import asyncio
import configparser
import contextlib
import logging
from datetime import datetime, timedelta
from logging import Logger
from pathlib import Path
from sqlite3 import Row
from threading import Thread, current_thread
from typing import Any, Union

import discord
import logger
import util.asqlite as asqlite
from database import *
from database.settings import Settings
from database.user import Image, User
from discord import CategoryChannel, Forbidden, Intents, Message, TextChannel
from discord.ext import commands, tasks
from loader import *
from util.commandtree import MrFriendlyCommandTree
from util.emoji_lib import Emojis

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

async def _get_guild_settings(guild_id: int) -> Settings:
    """
    Get's the Database Guild Settings.
    """
    _logger = logging.getLogger()
    async with asqlite.connect(database=Base.DB_FILE_PATH) as conn:
        res: Row | None = await conn.fetchone("""SELECT * FROM settings WHERE guild_id = ?""", (guild_id,))
        if res is None:
            _logger.error(msg=f"Failed to find the Discord Guild Settings. | Guild ID: {guild_id}")
        return Settings(**res) if res is not None else Settings(guild_id=guild_id)


async def _get_prefix(bot: "MrFriendly", message: Message) -> list[str]:
    """
    Get's the Database Guild Prefixes
    """
    prefixes = [bot._prefix]
    if message.guild is not None:
        _guild: int = message.guild.id

        async with asqlite.connect(database=Base.DB_FILE_PATH) as db:
            async with db.cursor() as cur:
                await cur.execute("""SELECT prefix FROM prefixes WHERE guild_id = ?""", _guild)
                res: list[Row] = await cur. fetchall()
                if res is not None and len(res) >= 1:
                    prefixes: list[str] = [entry["prefix"] for entry in res]

    wmo_func = commands.when_mentioned_or(*prefixes)
    return wmo_func(bot, message)


# TODO - Handle Suggestions-Feedback channel - Remove someones suggestion after it is sent.
# TODO - Add an About/Stats command.
    # - See Kuma_Kuma

class MrFriendly(commands.Bot):
    """
    MrFriendly _summary_ \n

    <@&> role \n
    <#> channel \n
    <@!> user
    """
    _logger: Logger = logging.getLogger(name=__name__)
    _database: Base = Base()
    _inactive_time = timedelta(days=180)  # How long a person has to have not been active in the server.
    _bot_name: str = __qualname__
    _emojis = Emojis

    def __init__(self) -> None:
        intents: Intents = Intents.default()
        intents.members = True
        intents.message_content = True
        intents.presences = True
        self._prefix = "$"
        self.owner_id = None
        # Perms Int - 19096431750358
        self.nsfw_category: CategoryChannel | None = None  # NSFW Pics Discord Category ID
        self._guild_id: int = 1259645744420360243  # PNW Adult Friends
        self._to_clean_channels: set[TextChannel] = set()

        super().__init__(intents=intents,
                         command_prefix=_get_prefix,
                         tree_cls=MrFriendlyCommandTree,
                         strip_after_prefix=True)

    async def on_ready(self) -> None:
        self._logger.info(msg=f'Logged on as {self._bot_name}!')

    async def setup_hook(self) -> None:
        await self._database._create_tables()
        self.delete_pictures.start()
        self.kick_unverified_users.start()
        # self.kick_inactive_users.start() #! Disabling Until the server is popular. 8/25/2024
        self._handler = Handler(bot=self)
        self._client_task: asyncio.Task = asyncio.create_task(coro=self.setup_attributes())
        await self._handler.cog_auto_loader()

    @tasks.loop(minutes=5, reconnect=True)
    async def delete_pictures(self) -> None:
        """
        Delete's pictures from channels that are over 14 days old.
        """
        if self.nsfw_category is None:
            await self.setup_attributes()

        # check if we have any channels to clean
        # We are using a set, so no need to check for duplicates.
        if len(self._to_clean_channels) == 0 and isinstance(self.nsfw_category, CategoryChannel):
            for channel in self.nsfw_category.channels:
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

    @tasks.loop(hours=6, reconnect=True)
    async def kick_unverified_users(self) -> None:
        """
        Kicks users that haven't verified in 7 days.
        """
        self._logger.info(msg="Performing kick_unverified_users loop.")
        # We need to get our verified_role_id from the settings.
        _settings: Settings = await _get_guild_settings(guild_id=self._guild_id)
        _guild: discord.Guild | None = self.get_guild(self._guild_id)
        if _guild is None:
            self._logger.error(msg=f"Failed to find the Discord Guild in kick_unverified_user. | Guild ID: {self._guild_id}")
            return

        if self.user is not None:
            _user: discord.Member | None = _guild.get_member(self.user.id)
            if _user is not None and _user.guild_permissions.kick_members is False:
                self._logger.error(msg=f"{self.user.name} does not have permission to kick members in the Discord Guild. | Guild ID: {self._guild_id}")

        # kick users that haven't verified in 7 days
        # requirements is only 1 role which is the default @everyone with a join time 7 days or later in the past
        for member in _guild.members:
            #Skip bot accounts
            # self._logger.info(msg=f"**DEBUG** - is bot? {member.bot}")
            if member.bot is True:
                continue
            if member.joined_at is None:
                self._logger.warning(msg=f"User does not have a `joined_at` property. | Discord ID: {member.id} Guild ID: {_guild.id}")
                continue
            join_time_len: int = (discord.utils.utcnow() - member.joined_at).days
            res: discord.Role | None = member.get_role(_settings.verified_role_id)
            if (res is None) and join_time_len >= 7:
                try:
                    await member.kick(reason="Failed to verify within 7 days")
                    self._logger.info(msg=f"Kicked {member} for not verifying in 7 days. | Guild ID: {self._guild_id}")
                except Forbidden:
                    self._logger.error(msg=f"Unable to kick {member} due to Missing Permissions")
                except Exception as e:
                    self._logger.error(msg=f"Unable to kick {member} due to {e}")
                # delay between kicks
                await asyncio.sleep(delay=1)

    @tasks.loop(hours=24, reconnect=True)
    async def kick_inactive_users(self) -> None:
        """
        Kicks users that haven't been active in the server for over our inactive time.
        """
        _guild: discord.Guild | None = self.get_guild(self._guild_id)
        if _guild is None:
            self._logger.error(msg=f"Failed to find the Discord Guild in kick_inactive_users. | Guild ID: {self._guild_id}")
            return

        if self.user is not None:
            _bot: discord.Member | None = _guild.get_member(self.user.id)
            if _bot is not None and _bot.guild_permissions.kick_members is False:
                self._logger.error(msg=f"{self.user.name} does not have permission to kick members in the Discord Guild. | Guild ID: {self._guild_id}")

        for member in _guild.members:
            if member.bot is True:
                continue
            _user: User | None = await User.add_or_get_user(guild_id=member.guild.id, user_id=member.id)
            _active_by: datetime = (datetime.now() - self._inactive_time)
            if _user is None:
                continue
            if _user.last_active_at < _active_by:
                try:
                    await member.kick(reason="Inactive for over 6 months.")
                    self._logger.info(msg=f"Kicked {member} for being inactive for 6 months. | Guild ID: {self._guild_id}")
                except Forbidden:
                    self._logger.error(msg=f"Unable to kick {member} due to Missing Permissions")
                except Exception as e:
                    self._logger.error(msg=f"Unable to kick {member} due to {e}")
                # delay between kicks
                await asyncio.sleep(delay=1)

    @tasks.loop(minutes=15)
    async def user_cleanup(self) -> None:
        """
        Removes a Discord Member messages that contain images.
        """
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
                    continue
                for image in _images[:30]:
                    _channel = guild.get_channel(image.channel_id)
                    if isinstance(_channel, TextChannel):
                        try:
                            await _channel.get_partial_message(image.message_id).delete()
                        except Forbidden:
                            self._logger.error(msg=f"Unable to delete the message {image.message_id} in {_channel} - Permission Forbidden | Guild ID: {guild.id}")
                        except Exception as e:
                            self._logger.error(msg=f"Unable to delete the message {image.message_id} in {_channel} | Guild ID: {guild.id} | Error : {e}")
                        await user.remove_image(image=image)
                    else:
                        await user.remove_image(image=image)

    async def on_command(self, context: commands.Context) -> None:
        """
        An event that is called when a command is found and is about to be invoked.

        This event is called regardless of whether the command itself succeeds via error or completes.
        """
        if context.guild is not None:
            return self._logger.info(msg=f'{context.author.name} used {context.command}...| {context.guild.id}')
        
        self._logger.info(msg=f'{context.author.name} used {context.command}...')

    async def on_command_error(self, context: commands.Context, error: commands.CommandError) -> None:
        """
        An error handler that is called when an error is raised inside a command either through user input error, check failure, or an error in your own code.

        This handles Prefix and Hybrid commands.
        """
        if context.command is not None:
            if isinstance(error, commands.TooManyArguments):
                await context.send(content=f'You called the {context.command.name} command with too many arguments.')
            elif isinstance(error, commands.MissingRequiredArgument):
                await context.send(content=f'You called {context.command.name} command without the required arguments')
        else:
            self._logger.error(msg=f"Command Error - {error}")
            self._logger.error(msg=f"{traceback.format_exc()}")

    async def on_error(self, event: str, *args, **kwargs) -> None:
        """
        Usually when an event raises an uncaught exception, a traceback is logged to stderr and the exception is ignored. If you want to change this behavior and handle the exception for whatever reason yourself, this event can be overridden. \n 
        
        Which, when done, will suppress the default action of printing the traceback. The information of the exception raised and the exception itself can be retrieved with a standard call to `sys.exc_info()`.
        """
        self._logger.error(msg=f"Error event - {event} | {args} | {kwargs}")
        self._logger.error(msg=traceback.print_exc())

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        """
        Called when a Member changes their VoiceState.

        The following, but not limited to, examples illustrate when this event is called:
            - A member joins a voice or stage channel.
            - A member leaves a voice or stage channel.
            - A member is muted or deafened by their own accord.
            - A member is muted or deafened by a guild administrator.

        """
        if member == self.user:
            return
        _user: User | None = await User.add_or_get_user(guild_id=member.guild.id, user_id=member.id)
        if _user is None:
            self._logger.error(msg=f"Failed to find the Database User when updating their last active time. | Guild ID: {member.guild.id} | User ID: {member.id}")
            return
        await _user.update_last_active_at()

    async def on_reaction_add(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]) -> None:
        """
        Called when a message has a reaction added to it. Similar to `on_message_edit()`, if the message is not found in the internal message cache, then this event will not be called. \n 
        Consider using `on_raw_reaction_add()` instead.
        """
        if user == self.user:
            return
        if reaction.message.guild is not None:
            _user: User | None = await User.add_or_get_user(guild_id=reaction.message.guild.id, user_id=user.id)
            if _user is None:
                self._logger.error(msg=f"Failed to find the Database User when updating their last active time. | Guild ID: {reaction.message.guild.id} | User ID: {user.id}")
                return
            await _user.update_last_active_at()

            if self.user is None:
                self._logger.error(msg=f"Failed to find the Discord Bot User in on_reaction_add. | Guild ID: {reaction.message.guild.id}")
                return

            _bot: discord.Member | None = reaction.message.guild.get_member(self.user.id)
            if _bot is not None and _bot.guild_permissions.manage_roles is False:
                self._logger.error(msg=f"{_bot.name} does not have permission to manage roles in the Discord Guild. | Guild ID: {reaction.message.guild.id}")
                return
            _settings: Settings = await _get_guild_settings(guild_id=reaction.message.guild.id)
            if reaction.message.id is not _settings.rules_message_id:
                return

            if _user.verified is True:
                _role: discord.Role | None = reaction.message.guild.get_role(_settings.verified_role_id)
                if _role is not None and isinstance(user, discord.Member):
                    await user.add_roles(_role)

    async def on_message(self, message: discord.Message) -> None | discord.Message:
        """
        Called when a Message receives an update event. If the message is not found in the internal message cache, then these events will not be called. Messages might not be in cache if the message is too old or the client is participating in high traffic guilds.

        If this occurs increase the max_messages parameter or use the `on_raw_message_edit()` event instead.

        The following non-exhaustive cases trigger this event:

            - A message has been pinned or unpinned.

            - The message content has been changed.

            - The message has received an embed.

                - For performance reasons, the embed server does not do this in a “consistent” manner.

            - The message’s embeds were suppressed or unsuppressed.

            - A call message has received an update to its participants or ending time.

        """
        # ignore ourselves and any message where the author isn't a Member
        if (message.author == self.user) or (isinstance(message.author, discord.Member) == False):
            return
        # update last active time
        if message.guild is not None:
            _settings: Settings = await _get_guild_settings(guild_id=message.guild.id)
            _user: User | None = await User.add_or_get_user(guild_id=message.guild.id, user_id=message.author.id)
            if _user is not None:
                await _user.update_last_active_at()
            
            if len(message.attachments) != 0 and _user is not None:
                # We update the DB with the Discord Message Attachment/Image information for when the user leaves to keep privacy.
                await _user.add_image(channel_id=message.channel.id, message_id=message.id)

            # ignore moderator messages, but handle commands.
            if isinstance(message.author, discord.Member) and message.content.startswith("!test") is False:
                if message.author.guild_permissions.administrator is True or await self.is_owner(message.author):
                    return await super().on_message(message)
                if _settings is not None and _settings.mod_role_id is not None and message.author.get_role(_settings.mod_role_id) is not None:
                    return await super().on_message(message)

            if self.nsfw_category is None:
                await self.setup_attributes()

            # check for posts without an attachment in specific channels
            # if found then delete it and alert the person
            if isinstance(self.nsfw_category, CategoryChannel) and message.channel in self.nsfw_category.channels:
                if len(message.attachments) == 0:
                    # no attachment, alert the user about where to post
                    await message.delete(delay=3)
                    _response: str = f"{message.author.mention} | Text messages are not allowed in this channel."
                    if _settings.flirting_channel_id is not None and message.guild is not None:
                        _channel = message.guild.get_channel(_settings.flirting_channel_id)
                    if isinstance(message.channel, TextChannel) and _channel is not None:
                        await message.channel.send(content=f"{message.author.mention} Text messages are not allowed in this channel. Please post them in {_channel.mention}", delete_after=10)
                    else:
                        await message.channel.send(content=_response, delete_after=10)

                else:
                    # if there is an attachment then verify it is an image or video
                    for entry in message.attachments:
                        if entry.content_type is not None and entry.content_type.split("/")[0] not in ["image", "video"]:
                            await message.delete(delay=1)
                            await message.channel.send(f"{message.author.mention}: Only Images and Videos are allowed in this channel", delete_after=10)
                            return

    async def on_message_delete(self, message: discord.Message) -> None:
        """
        Called when a message is deleted. If the message is not found in the internal message cache, then this event will not be called. Messages might not be in cache if the message is too old or the client is participating in high traffic guilds.

        If this occurs increase the max_messages parameter or use the `on_raw_message_delete()` event instead.

        This requires `Intents.messages` to be enabled.
        """
        if message.guild is None:
            return
        _user: User | None = await User.add_or_get_user(guild_id=message.guild.id, user_id=message.author.id)
        if _user is None:
            return

        _img: Image | None = await _user.get_image(channel_id=message.channel.id, message_id=message.id)
        if _img is None:
            return
        await _user.remove_image(image=_img)

    async def on_member_remove(self, member: discord.Member) -> None:
        """
        Called when a Member leaves a Guild.

        If the guild or member could not be found in the internal cache this event will not be called, you may use `on_raw_member_remove()` instead.

        This requires `Intents.members` to be enabled.
        """
        if isinstance(member.guild, discord.Guild) is True:
            _settings: Settings = await _get_guild_settings(guild_id=member.guild.id)
            _channel = member.guild.get_channel(_settings.notification_channel_id)
            if isinstance(_channel, TextChannel):
                await _channel.send(content=f"<t:{int(datetime.now().timestamp())}:R> | {self._emojis.arrow_left} {member.mention}|{member.display_name} has left the server.")
        _user: User | None = await User.add_or_get_user(guild_id=member.guild.id, user_id=member.id)
        if _user is None:
            return
        await _user.update_cleaned(cleaned=False)
        res: Leave | None = await _user.add_leave()
        # self._logger.info(msg=f"**DEBUG** - {_user.user_leaves} {res}")
        self._logger.info(msg=f"{member} has left the server. | Member Leave Count: {len(_user.user_leaves)} Guild ID: {member.guild.id}")

    async def on_member_join(self, member: discord.Member) -> None:
        """
        Called when a Member joins a Guild.

        This requires `Intents.members` to be enabled.
        """
        if isinstance(member.guild, discord.Guild) is True:
            self._logger.info(msg=f"{member.name} has joined {member.guild.name}.")
            _settings: Settings = await _get_guild_settings(guild_id=member.guild.id)
            _channel = member.guild.get_channel(_settings.notification_channel_id)
            if isinstance(_channel, TextChannel):
                await _channel.send(content=f"<t:{int(datetime.now().timestamp())}:R> | {self._emojis.arrow_right} {member.mention} has joined the server.")

        _user: User | None = await User.add_or_get_user(guild_id=member.guild.id, user_id=member.id)
        if _user is None:
            return
        await _user.update_cleaned(cleaned=False)

    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        """
        Called when a user gets banned from a Guild.

        This requires Intents.moderation to be enabled.\n
        **Args**:
            - guild (Guild) : The guild the user got banned from.
            - user (Union[User, Member]) : The user that got banned. Can be either User or Member depending if the user was in the guild or not at the time of removal.
 
        """

        _settings: Settings = await _get_guild_settings(guild_id=guild.id)
        _channel = guild.get_channel(_settings.notification_channel_id)
        if isinstance(_channel, TextChannel):
            await _channel.send(content=f"<t:{int(datetime.now().timestamp())}:R> | {self._emojis.no_entry} {user.mention} has been banned from the server.")

        _user: User | None = await User.add_or_get_user(guild_id=guild.id, user_id=user.id)
        if _user is None:
            return

        await _user.update_banned(banned=True)
   
    async def setup_attributes(self) -> None:
        """
        Retrieves the Guild Settings from the Database and set's the `self.nsfw_category` property for us to use.
        """
        await self.wait_until_ready()

        guild: discord.Guild | None = self.get_guild(self._guild_id)
        if guild is None:
            self._logger.warning(msg=f"We failed to find the guild. | Guild ID: {self._guild_id}")
            return
        
        for category in guild.categories:
            if category.name.lower() == "nsfw pics-videos":
                self.nsfw_category = category
                break



Friendly = MrFriendly()


@Friendly.hybrid_group(name='prefix')
async def prefix(context: commands.Context) -> None:
    pass


@prefix.command(name="add", help=f"Add a prefix to {Friendly._bot_name}", aliases=["prea", "pa"])
@commands.is_owner()
@commands.guild_only()
async def add_prefix(context: commands.Context, prefix: str) -> Message:
    """
    Add a prefix to the guild.
    """
    assert context.guild
    _settings: Settings = await _get_guild_settings(guild_id=context.guild.id)
    await Friendly._database._execute(SQL="""INSERT INTO prefixes(guild_id, prefix) VALUES(?, ?)""", parameters=(context.guild.id, prefix.lstrip()))
    return await context.send(content=f"Added the prefix `{prefix}` for {context.guild.name}", delete_after=_settings.msg_timeout)


@prefix.command(name="delete", help=f"Delete a prefix from {Friendly._bot_name} for a guild.", aliases=["pred", "pd"])
@commands.is_owner()
@commands.guild_only()
async def delete_prefix(context: commands.Context, prefix: str) -> Message:
    """
    Delete a prefix from the guild.
    """
    assert context.guild
    _settings: Settings = await _get_guild_settings(guild_id=context.guild.id)
    await Friendly._database._execute(SQL="""DELETE FROM prefixes WHERE guild_id = ? and prefix = ?""", parameters=(context.guild.id, prefix.lstrip()))
    return await context.send(content=f"Removed the prefix - `{prefix}`", delete_after=_settings.msg_timeout)


@prefix.command(name="clear", help=f"Clear all prefixes for {Friendly._bot_name} in a guild.", aliases=["prec", "pc"])
@commands.is_owner()
@commands.guild_only()
async def clear_prefix(context: commands.Context) -> Message:
    """
    Removes all prefixes for the guild.
    """
    assert context.guild
    _settings: Settings = await _get_guild_settings(guild_id=context.guild.id)
    await Friendly._database._execute(SQL="""DELETE FROM prefixes WHERE guild_id = ?""", parameters=(context.guild.id,))
    return await context.send(content=f"Removed all prefix's for {context.guild.name}", delete_after=_settings.msg_timeout)

@Friendly.hybrid_command(name="sync")
@commands.is_owner()
@commands.guild_only()
async def sync(context: commands.Context, local: bool = True, reset: bool = False):
    """
    Syncs Bot Commands to the current guild this command was used in.
    """
    await context.typing(ephemeral=True)
    assert Friendly.user
    assert context.guild
    _settings: Settings = await _get_guild_settings(guild_id=context.guild.id)
    if ((type(reset)) == bool and (reset == True)):
        if ((type(local) == bool) and (local == True)):
            # Local command tree reset
            Friendly.tree.clear_commands(guild=context.guild)
            return await context.send(content=f"**WARNING** Resetting {Friendly.user.name} Commands Locally...", ephemeral=True, delete_after=_settings.msg_timeout)

        elif context.author.id == Friendly.owner_ids:
            # Global command tree reset, limited by Owner IDs
            Friendly.tree.clear_commands(guild=None)
            return await context.send(content=f"**WARNING** Resetting {Friendly.user.name} Commands Globally...", ephemeral=True, delete_after=_settings.msg_timeout)
        else:
            return await context.send(content="**ERROR** You do not have permission to reset the commands.", ephemeral=True, delete_after=_settings.msg_timeout)

    if ((type(local) == bool) and (local == True)):
        # Local command tree sync
        Friendly.tree.copy_global_to(guild=context.guild)
        await Friendly.tree.sync(guild=context.guild)
        return await context.send(content=f"Successfully Sync\'d {Friendly.user.name} Commands to {context.guild.name}...", ephemeral=True, delete_after=_settings.msg_timeout)

    elif context.author.id == Friendly.owner_ids:
        # Global command tree sync, limited by Owner IDs.
        await Friendly.tree.sync(guild=None)
        await context.send(content=f"Successfully Sync\'d {Friendly.user.name} Commands Globally...", ephemeral=True, delete_after=_settings.msg_timeout)


async def main() -> None:
    cur_thread: Thread = current_thread()
    cur_thread.name = "PNW Adult Friends"
    TOKEN = load_ini()

    async with Friendly:
        await Friendly.start(token=TOKEN)


if __name__ == "__main__":
    logger.init()

    with contextlib.suppress(KeyboardInterrupt, RuntimeError, asyncio.CancelledError):
        asyncio.run(main())
