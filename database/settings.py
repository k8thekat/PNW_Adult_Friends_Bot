from __future__ import annotations

import functools
from dataclasses import InitVar, dataclass, fields
from sqlite3 import Row
from typing import Any, Literal, Self

import util.asqlite as asqlite

from .base import DB_FILE_PATH, Base

__all__: tuple[Literal['Settings']] = ("Settings",)


@dataclass
class Settings(Base):
    guild_id: int
    mod_role_id: int | None
    verified_role_id: int | None
    welcome_channel_id: int | None
    rules_message_id: int | None
    notification_channel_id: int | None
    flirting_channel_id: int | None
    msg_timeout: int

    _pool: InitVar[asqlite.Pool | None] = None

    def __post_init__(self, _pool: asqlite.Pool | None = None) -> None:
        self._fields: list[str] = [field.name for field in fields(class_or_instance=self)]

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
    async def add_or_get_settings(cls, guild_id: int) -> Self | None:
        async with asqlite.connect(database=DB_FILE_PATH) as conn:
            _exists: Row | None = await conn.fetchone(f"""SELECT * FROM guilds WHERE guild_id = ?""", (guild_id,))
            if _exists is None:
                await conn.execute(f"""INSERT INTO guilds(guild_id) VALUES(?)""", (guild_id,))
            res: Row | None = await conn.fetchone(f"""INSERT INTO settings(guild_id) VALUES(?) RETURNING *""", (guild_id,))
            return cls(**res) if res is not None else None

    @exists
    async def update_mod_role_id(self, role_id: int) -> Self:
        if len(str(object=role_id)) < 15:
            raise ValueError("Your `user_id` value is to short. (<15)")
        await self._execute(SQL=f"""UPDATE settings SET mod_role_id = ? WHERE guild_id = ?""", parameters=(role_id, self.guild_id))
        self.mod_role_id = role_id
        return self

    @exists
    async def update_msg_timeout(self, msg_timeout: int) -> Self:
        await self._execute(SQL=f"""UPDATE settings SET msg_timeout = ? WHERE guild_id = ?""", parameters=(msg_timeout, self.guild_id))
        self.msg_timeout = msg_timeout
        return self

    @exists
    async def update_verified_role_id(self, role_id: int) -> Self:
        if len(str(object=role_id)) < 15:
            raise ValueError("Your `role_id` value is to short. (<15)")
        await self._execute(SQL=f"""UPDATE settings SET verified_role_id = ? WHERE guild_id = ?""", parameters=(role_id, self.guild_id))
        self.verified_role_id = role_id
        return self

    @exists
    async def update_welcome_channel_id(self, channel_id: int) -> Self:
        if len(str(object=channel_id)) < 15:
            raise ValueError("Your `channel_id` value is to short. (<15)")
        await self._execute(SQL=f"""UPDATE settings SET welcome_channel_id = ? WHERE guild_id = ?""", parameters=(channel_id, self.guild_id))
        self.welcome_channel_id = channel_id
        return self

    @exists
    async def update_rules_message_id(self, message_id: int) -> Self:
        if len(str(object=message_id)) < 15:
            raise ValueError("Your `message_id` value is to short. (<15)")
        await self._execute(SQL=f"""UPDATE settings SET rules_message_id = ? WHERE guild_id = ?""", parameters=(message_id, self.guild_id))
        self.rules_message_id = message_id
        return self

    @exists
    async def update_notification_channel_id(self, channel_id: int) -> Self:
        if len(str(object=channel_id)) < 15:
            raise ValueError("Your `channel_id` value is to short. (<15)")
        await self._execute(SQL=f"""UPDATE settings SET notification_channel_id = ? WHERE guild_id = ?""", parameters=(channel_id, self.guild_id))
        self.notification_channel_id = channel_id
        return self

    @exists
    async def update_flirting_channel_id(self, channel_id: int) -> Self:
        if len(str(object=channel_id)) < 15:
            raise ValueError("Your `channel_id` value is to short. (<15)")
        await self._execute(SQL=f"""UPDATE settings SET flirting_channel_id = ? WHERE guild_id = ?""", parameters=(channel_id, self.guild_id))
        self.flirting_channel_id = channel_id
        return self
