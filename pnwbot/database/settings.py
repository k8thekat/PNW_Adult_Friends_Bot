from __future__ import annotations

import functools
from dataclasses import InitVar, dataclass, fields
from sqlite3 import Row
from typing import Any, Optional, Self, Union

import util.asqlite as asqlite
from discord import CategoryChannel, TextChannel

from .base import *

__all__: tuple[str, ...] = ("Settings", "Role_Embed_Info",)


@dataclass
class Role_Embed_Info(Base):
    id: int
    name: str
    guild_id: int
    channel_id: int
    message_id: int

    _pool: InitVar[asqlite.Pool | None] = None

    def __post_init__(self, _pool: asqlite.Pool | None = None) -> None:
        self._fields: list[str] = [field.name for field in fields(class_or_instance=self)]

    @classmethod
    async def add_role_embeds(cls, name: str, guild_id: int, channel_id: int, message_id: int) -> Role_Embed_Info:
        if len(str(channel_id)) < 15:
            raise ValueError("Your `channel_id` value is to short (<15)")
        if len(str(guild_id)) < 15:
            raise ValueError("Your `guild_id` value is to short (<15)")
        if len(str(message_id)) < 15:
            raise ValueError("Your `message_id` value is to short (<15)")
        async with DB_Pool().connect() as conn:
            res: Row | None = await conn.fetchone("""INSERT INTO role_embeds(name, guild_id, channel_id, message_id) VALUES(?, ?, ?, ?)
                                                ON CONFLICT(guild_id, channel_id, message_id) DO NOTHING RETURNING *""",
                                                  (name, guild_id, channel_id, message_id))
        if res is None:
            raise ValueError(f"Unable to add an entry into the `role_embeds` table. | Guild ID: {guild_id} Channel ID: {channel_id} Message ID: {message_id} ")
        return Role_Embed_Info(**res)

    @classmethod
    async def remove_role_embed(cls, embed_info: Union[Role_Embed_Info, None] = None, id: Union[int, None] = None) -> bool:
        if embed_info is None and id is None:
            raise ValueError("Either `embed_info` or `id` must be provided.")
        if embed_info is not None:
            id = embed_info.id
        async with DB_Pool().connect() as conn:
            res: Row | None = await conn.fetchone("""DELETE FROM role_embeds WHERE id = ?""", (id,))
        return True if res is not None else False

    @classmethod
    async def get_all_role_embeds(cls, guild_id: int) -> list[Role_Embed_Info]:
        if len(str(guild_id)) < 15:
            raise ValueError("Your `guild_id` value is to short (<15)")
        async with DB_Pool().connect() as conn:
            res: list[Row] = await conn.fetchall("""SELECT * FROM role_embeds WHERE guild_id = ?""", (guild_id,))
        if len(res) == 0:
            raise ValueError(f"There is no entries in the `role_embeds` table for the Guild ID provided. | Guild ID: {guild_id}")
        return [Role_Embed_Info(**info) for info in res]

    @classmethod
    async def get_role_embed(cls, guild_id: int, id: int) -> Role_Embed_Info:
        async with DB_Pool().connect() as conn:
            res: Row | None = await conn.fetchone("""SELECT * FROM role_embeds WHERE guild_id = ? AND id = ?""", (guild_id, id))
        if res is None:
            raise ValueError(f"There is no entry in the `role_embeds` table for the Guild ID and ID provided. Guild ID: {guild_id} |ID: {id}")
        return Role_Embed_Info(**res)


@dataclass
class Settings(Base):
    guild_id: int
    mod_role_id: int = 0
    verified_role_id: int = 0
    welcome_channel_id: int = 0
    rules_message_id: int = 0
    rules_channel_id: int = 0
    notification_channel_id: int = 0
    flirting_channel_id: int = 0
    personal_intros_channel_id: int = 0
    roles_channel_id: int = 0
    infraction_log_channel_id: int = 0
    msg_timeout: int = 60

    _pool: InitVar[DB_Pool| None] = None

    def __post_init__(self, _pool: DB_Pool| None = None) -> None:
        self._fields: list[str] = [field.name for field in fields(class_or_instance=self)]

    def __eq__(self, other: "Settings") -> bool:
        try:
            return self.guild_id == other.guild_id
        except AttributeError:
            return False
    
    def __hash__(self) -> int:
        return hash(self.guild_id)


    @staticmethod
    def exists(func):
        @functools.wraps(wrapped=func)
        async def wrapper_exists(self: Self, *args, **kwargs) -> Any:
            res: Row | None = await self._fetchone(SQL=f"""SELECT guild_id FROM guilds WHERE guild_id = ?""", parameters=(self.guild_id,))
            if res is None:
                raise ValueError(f"The `guild_id` of this class doesn't exist in the database table. ID: {self.guild_id}")
            return await func(self, *args, **kwargs)
        return wrapper_exists

    @classmethod
    async def add_or_get_settings(cls, guild_id: int) -> Self:
        if len(str(object=guild_id)) < 15:
            raise ValueError("Your `guild_id` value is to short. (<15)")
        async with DB_Pool().connect() as conn:
            # Check if the guild id is in the database.
            _exists: Row | None = await conn.fetchone(f"""SELECT * FROM guilds WHERE guild_id = ?""", (guild_id,))
          
            if _exists is None:
                # It doesn't exist so we need to add it to two tables. guilds and settings.
                await conn.execute(f"""INSERT INTO guilds(guild_id) VALUES(?)""", (guild_id,))
                res: Row | None = await conn.fetchone(f"""INSERT INTO settings(guild_id) VALUES(?) RETURNING *""", (guild_id,))
                if res is None:
                    cls._logger.error(msg=f"Failed to Add Settings from the Database. | Guild ID: {guild_id}")
                    return cls(guild_id=guild_id)
            else:
                # It does exist so let's get all the guilds settings.
                res: Row | None = await conn.fetchone(f"""SELECT * FROM settings WHERE guild_id = ?""", (guild_id))
                if res is None:
                    cls._logger.error(msg=f"Failed to Get Settings form the Database. | Guild ID: {guild_id}")
                    return cls(guild_id=guild_id)
            return cls(**res)

    @exists
    async def update_property(self, property: str, value: Any) -> Self:
        if property not in self._fields:
            raise ValueError(f"{property} is not a valid property. | Valid Properties: {self._fields}")
        if not property == "msg_timeout":
            if len(str(object=value)) < 15:
                raise ValueError("Your `value` value is to short. (<15)")

        await self._execute(SQL=f"""UPDATE settings SET {property} = ? WHERE guild_id = ?""", parameters=(value, self.guild_id))
        setattr(self, property, value)
        return self

    # @exists
    # async def update_mod_role_id(self, role_id: Optional[int]) -> Self:
    #     if len(str(object=role_id)) < 15:
    #         raise ValueError("Your `role_id` value is to short. (<15)")
    #     await self._execute(SQL=f"""UPDATE settings SET mod_role_id = ? WHERE guild_id = ?""", parameters=(role_id, self.guild_id))
    #     self.mod_role_id = role_id
    #     return self

    # @exists
    # async def update_msg_timeout(self, msg_timeout: int) -> Self:
    #     await self._execute(SQL=f"""UPDATE settings SET msg_timeout = ? WHERE guild_id = ?""", parameters=(msg_timeout, self.guild_id))
    #     self.msg_timeout = msg_timeout
    #     return self

    # @exists
    # async def update_verified_role_id(self, role_id: Optional[int]) -> Self:
    #     if len(str(object=role_id)) < 15:
    #         raise ValueError("Your `role_id` value is to short. (<15)")
    #     await self._execute(SQL=f"""UPDATE settings SET verified_role_id = ? WHERE guild_id = ?""", parameters=(role_id, self.guild_id))
    #     self.verified_role_id = role_id
    #     return self

    # @exists
    # async def update_welcome_channel_id(self, channel_id: Optional[int]) -> Self:
    #     if len(str(object=channel_id)) < 15:
    #         raise ValueError("Your `channel_id` value is to short. (<15)")
    #     await self._execute(SQL=f"""UPDATE settings SET welcome_channel_id = ? WHERE guild_id = ?""", parameters=(channel_id, self.guild_id))
    #     self.welcome_channel_id = channel_id
    #     return self

    # @exists
    # async def update_rules_message_id(self, message_id: Optional[int]) -> Self:
    #     if len(str(object=message_id)) < 15:
    #         raise ValueError("Your `message_id` value is to short. (<15)")
    #     await self._execute(SQL=f"""UPDATE settings SET rules_message_id = ? WHERE guild_id = ?""", parameters=(message_id, self.guild_id))
    #     self.rules_message_id = message_id
    #     return self

    # @exists
    # async def update_notification_channel_id(self, channel_id: Optional[int]) -> Self:
    #     if len(str(object=channel_id)) < 15:
    #         raise ValueError("Your `channel_id` value is to short. (<15)")
    #     await self._execute(SQL=f"""UPDATE settings SET notification_channel_id = ? WHERE guild_id = ?""", parameters=(channel_id, self.guild_id))
    #     self.notification_channel_id = channel_id
    #     return self

    # @exists
    # async def update_flirting_channel_id(self, channel_id: Optional[int]) -> Self:
    #     if len(str(object=channel_id)) < 15:
    #         raise ValueError("Your `channel_id` value is to short. (<15)")
    #     await self._execute(SQL=f"""UPDATE settings SET flirting_channel_id = ? WHERE guild_id = ?""", parameters=(channel_id, self.guild_id))
    #     self.flirting_channel_id = channel_id
    #     return self

    # @exists
    # async def update_personal_intros_channel_id(self, channel_id: Optional[int]) -> Self:
    #     if len(str(object=channel_id)) < 15:
    #         raise ValueError("Your `channel_id` value is to short. (<15)")
    #     await self._execute(SQL=f"""UPDATE settings SET personal_intros_channel_id = ? WHERE guild_id = ?""", parameters=(channel_id, self.guild_id))
    #     self.personal_intros_channel_id = channel_id
    #     return self

    # @exists
    # async def update_roles_channel_id(self, channel_id: Optional[int]) -> Self:
    #     if len(str(object=channel_id)) < 15:
    #         raise ValueError("Your `channel_id` value is to short. (<15)")
    #     await self._execute(SQL=f"""UPDATE settings SET roles_channel_id = ? WHERE guild_id = ?""", parameters=(channel_id, self.guild_id))
    #     self.roles_channel_id = channel_id
    #     return self

    # @exists
    # async def update_infraction_log_channel_id(self, channel_id: Optional[int]) -> Self:
    #     if len(str(object=channel_id)) < 15:
    #         raise ValueError("Your `channel_id` value is to short. (<15)")
    #     await self._execute(SQL=f"""UPDATE settings SET infraction_log_channel_id = ? WHERE guild_id = ?""", parameters=(channel_id, self.guild_id))
    #     self.infraction_log_channel_id = channel_id
    #     return self
