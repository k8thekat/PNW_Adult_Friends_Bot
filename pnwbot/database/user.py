from __future__ import annotations

import functools
from dataclasses import InitVar, dataclass, field, fields
from datetime import datetime
from sqlite3 import Cursor, Row
from typing import Any, Literal, Self, Union

import util.asqlite as asqlite

from .base import Base

__all__: tuple[str, ...] = ("User", "Leave", "Infraction", "Image",)


@dataclass
class Image:
    id: int
    guild_id: int
    channel_id: int
    message_id: int

    def __hash__(self) -> int:
        return hash((self.guild_id, self.channel_id, self.message_id))

    def __eq__(self, other) -> Any | Literal[False]:
        try:
            return (self.guild_id == other.guild_id) and (self.channel_id == other.channel_id) and (self.message_id == other.message_id)
        except AttributeError:
            return False


@dataclass
class Leave:
    user_id: int
    created_at: datetime

    def __post_init__(self) -> None:
        self.created_at = datetime.fromtimestamp(timestamp=self.created_at)  # type: ignore

    def __hash__(self) -> int:
        return hash((self.user_id, self.created_at))

    def __eq__(self, other) -> Any | Literal[False]:
        try:
            return self.user_id == other.user_id and self.created_at == other.created_at
        except AttributeError:
            return False


@dataclass
class Infraction(Base):
    id: int  # Primary Key
    guild_id: int
    user_id: int
    reason_msg_link: str
    created_at: datetime

    _pool: InitVar[asqlite.Pool | None] = None

    def __post_init__(self, _pool: asqlite.Pool | None = None) -> None:
        self.created_at = datetime.fromtimestamp(timestamp=self.created_at)  # type: ignore

    def __hash__(self) -> int:
        return hash((self.user_id, self.reason_msg_link))

    def __eq__(self, other) -> Any | Literal[False]:
        try:
            return self.user_id == other.user_id and self.reason_msg_link == other.reason_msg_link
        except AttributeError:
            return False


@dataclass
class User(Base):
    guild_id: int
    user_id: int
    created_at: datetime
    verified: bool # DEFAULT - FALSE
    last_active_at: datetime
    banned: bool # DEFAULT - FALSE
    cleaned: bool # Default - FALSE
    user_leaves: set[Leave] = field(default_factory=set)
    user_infractions: set[Infraction] = field(default_factory=set)
    user_images: set[Image] = field(default_factory=set)

    _pool: InitVar[asqlite.Pool | None] = None

    def __post_init__(self, _pool: asqlite.Pool | None = None) -> None:
        self.created_at = datetime.fromtimestamp(timestamp=self.created_at)  # type: ignore
        self.last_active_at = datetime.fromtimestamp(timestamp=self.last_active_at)  # type: ignore
        self.verified = bool(self.verified)
        self.banned = bool(self.banned)
        self.cleaned = bool(self.cleaned)

    @staticmethod
    def exists(func):
        @functools.wraps(wrapped=func)
        async def wrapper_exists(self: Self, *args, **kwargs) -> Any:
            res: Row | None = await self._fetchone(SQL=f"""SELECT * FROM users WHERE user_id = ?""", parameters=(self.user_id,))
            if res is None:
                raise ValueError(f"The `user_id` of this class doesn't exist in the database table. ID: {self.user_id}")
            return await func(self, *args, **kwargs)
        return wrapper_exists

    @classmethod
    async def add_or_get_user(cls, guild_id: int, user_id: int) -> Self | None:
        async with asqlite.connect(database=cls.DB_FILE_PATH) as conn:
            _exists: Row | None = await conn.fetchone(f"""SELECT * FROM users WHERE guild_id = ? AND user_id = ?""", (guild_id, user_id))
            if _exists is None:
                _time: float = datetime.now().timestamp()
                res: Row | None = await conn.fetchone(
                    """INSERT INTO users(guild_id, user_id, created_at, last_active_at) VALUES(?, ?, ?, ?) RETURNING *""",
                    (guild_id, user_id, _time, _time))
                return cls(**res) if res is not None else None
            else:
                return cls(**_exists)

    @classmethod
    async def get_banned_users(cls, guild_id: int) -> list[Self]:
        async with asqlite.connect(database=cls.DB_FILE_PATH) as conn:
            res: list[Row] = await conn.fetchall(f"""SELECT * FROM users WHERE guild_id = ? AND banned = 1""", (guild_id,))
            return [cls(**row) for row in res]

    @classmethod
    async def get_unclean_users(cls, guild_id: int) -> list[Self]:
        """
        Get's a list of Database User classes that have not been cleaned. \n
        **AKA** - Images left in the Discord Server.
        """
        async with asqlite.connect(database=cls.DB_FILE_PATH) as conn:
            res: list[Row] = await conn.fetchall(f"""SELECT * FROM users WHERE guild_id = ? AND cleaned = 0""", (guild_id,))
            return [cls(**row) for row in res]

    @exists
    async def update_banned(self, banned: bool) -> bool:
        await self._fetchone(SQL=f"""UPDATE users SET banned = ? WHERE user_id = ?""", parameters=(banned, self.user_id))
        self.banned = banned
        return self.banned

    @exists
    async def update_verified(self, verified: bool) -> bool:
        await self._fetchone(SQL=f"""UPDATE users SET verified = ? WHERE user_id = ?""", parameters=(verified, self.user_id))
        self.verified = verified
        return self.verified

    @exists
    async def update_last_active_at(self) -> datetime:
        await self._fetchone(SQL=f"""UPDATE users SET last_active_at = ? WHERE user_id = ?""", parameters=(datetime.now().timestamp(), self.user_id))
        self.last_active_at = datetime.now()
        return self.last_active_at

    @exists
    async def add_leave(self) -> Leave | None:
        res: Row | None = await self._fetchone(SQL=f"""INSERT INTO user_leaves(user_id, created_at) VALUES(?, ?) RETURNING *""", parameters=(self.user_id, datetime.now().timestamp()))
        if res is None:
            return res
        self.user_leaves.add(Leave(**res))
        return Leave(**res)

    @exists
    async def get_leaves(self, before: datetime = datetime.now()) -> set[Leave]:
        res: list[Row] = await self._fetchall(SQL=f"""SELECT * FROM user_leaves WHERE user_id = ? AND created_at <= ?""",
                                              parameters=(self.user_id, before.timestamp()))
        if len(res) == 0:
            return set()
        self.user_leaves = set([Leave(**row) for row in res])
        return set([Leave(**row) for row in res])

    @exists
    async def add_infraction(self, reason_msg_link: str) -> Infraction | None:
        res: Row | None = await self._fetchone(SQL="""INSERT INTO infractions(guild_id, user_id, reason_msg_link, created_at) VALUES(?, ?, ?, ?) 
                ON CONFLICT(user_id, reason_msg_link) DO NOTHING RETURNING *""",
                                               parameters=(self.guild_id, self.user_id, reason_msg_link, datetime.now().timestamp()),)
        if res is None:
            return res
        self.user_infractions.add(Infraction(**res))
        return Infraction(**res)

    @exists
    async def get_infractions(self, before: datetime = datetime.now()) -> set[Infraction]:
        res: list[Row] = await self._fetchall(
            SQL="""SELECT * FROM infractions WHERE guild_id = ? AND user_id = ? AND created_at <= ?""",
            parameters=(self.guild_id, self.user_id, before.timestamp()),
        )
        if len(res) == 0:
            return set()
        self.user_infractions = set([Infraction(**row) for row in res])
        return set([Infraction(**row) for row in res])

    @exists
    async def remove_infraction(self, infraction: Infraction | None = None, id: int | None = None) -> set[Infraction]:
        if infraction is None and id is None:
            raise ValueError("Either infraction or id must be provided")

        if infraction is not None:
            id = infraction.id

        await self._execute(SQL=f"""DELETE FROM infractions WHERE id=?""",
                            parameters=(id,))

        for infraction in self.user_infractions:
            if infraction.id == id:
                self.user_infractions.remove(infraction)

        return self.user_infractions

    @exists
    async def add_image(self, channel_id: int, message_id: int) -> set[Image]:
        res: Row | None = await self._fetchone(SQL=f"""INSERT INTO user_images(user_id, guild_id, channel_id, message_id) VALUES(?, ?, ?, ?)""",
                                               parameters=(self.user_id, self.guild_id, channel_id, message_id))
        if res is None:
            return self.user_images
        self.user_images.add(Image(**res))
        return self.user_images

    @exists
    async def get_image(self, channel_id: int, message_id: int) -> Image | None:
        res: Row | None = await self._fetchone(SQL=f"""SELECT * FROM user_images WHERE user_id = ? AND guild_id = ? AND channel_id = ? AND message_id = ?""",
                                               parameters=(self.user_id, self.guild_id, channel_id, message_id))
        return Image(**res) if res is not None else None

    @exists
    async def get_all_images(self) -> set[Image]:
        res: list[Row] = await self._fetchall(SQL=f"""SELECT * FROM user_images WHERE user_id = ? AND guild_id = ?""",
                                              parameters=(self.user_id, self.guild_id))
        if len(res) == 0:
            return set()
        self.user_images = set([Image(**row) for row in res])
        return set([Image(**row) for row in res])

    @exists
    async def remove_image(self, image: Image) -> set[Image]:
        await self._execute(SQL=f"""DELETE FROM user_images WHERE id=?""", parameters=(image.id,))
        self.user_images.remove(image)
        return self.user_images

    @exists
    async def update_cleaned(self, cleaned: bool) -> bool:
        """
        Update the Database Users cleaned status.
        """
        await self._fetchone(SQL=f"""UPDATE users SET cleaned = ? WHERE user_id = ?""", parameters=(cleaned, self.user_id))
        self.cleaned = cleaned
        return self.cleaned
