import logging
import re
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Cursor, Row
from typing import Any, Literal, Self

import util.asqlite as asqlite

__all__: tuple[str, ...] = ("Base", "DB_Pool")



@dataclass
class VersionInfo():
    major: int = 0
    minor: int = 0
    revision: int = 0
    level: str = "release"
    
    @staticmethod
    def _parse_version() -> "VersionInfo":
        """
        Get's the version information from the database `__init__.py`.

        Returns:
            VersionInfo: _description_
        """
        # Grab Version from __init__.py
        version: str = ''
        tmp = VersionInfo()
        with open(file='pnwbot/database/__init__.py') as file:
            version = re.search(pattern=r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]', string=file.read(), flags=re.MULTILINE).group(1).split(".")  # type:ignore
        tmp.major = int(version[0])
        tmp.minor = int(version[1])
        tmp.revision = int(version[2])
        return tmp
        
    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.revision, self.level))

    def __eq__(self, other: "VersionInfo") -> Any | Literal[False]:
        try:
            return (self.major == other.major) and (self.minor == other.minor) and (self.revision == other.revision) and (self.level == other.level)
        except AttributeError:
            return False
        
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.revision}-{self.level}"


class DB_Pool:
    _instance = None
    _logger: logging.Logger = logging.getLogger()
    _path: str
    _pool: asqlite.Pool | None = None
    dir: Path = Path(__file__).parent
    DB_FILENAME: str = "mrfriendly.db"
    DB_FILE_PATH: str = Path(dir).joinpath(DB_FILENAME).as_posix()

    async def setup_pool(self) -> None:
        if self._pool is None:
            self._pool = await asqlite.create_pool(database= self.DB_FILE_PATH)

    @classmethod
    def get_pool(cls) -> asqlite.Pool:
        """
        Retrieves an existing Bridge class object.\n
        **`DO NOT CALL THIS METHOD OUTSIDE OF AN API CLASS (ADSModule, Core, etc..)`**

        Raises:
        ---
            ValueError: If the Bridge class does not exist.

        Returns:
        ---
            Bridge: A singleton class of Bridge
        """
        
        if cls._instance == None:
            raise ValueError("Failed to setup connection. You need to initiate `<class Bridge>` first.")
        if cls._instance._pool is None:
            raise ValueError("Setup pool first...")
        return cls._instance._pool

    def __new__(cls, *args, **kwargs) -> Self:
        if not cls._instance:
            cls._instance = super(DB_Pool, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, *args, **kwargs) -> None:
        self._logger.debug(msg=f"DEBUG Pool __init__ as {id(self)}")

    @asynccontextmanager
    async def connect(cls):
        """async with DB_Pool().connect() as db:"""
        self = cls
        await self.setup_pool()
        pool = self.get_pool()
        async with pool.acquire() as connection:
            yield connection
    

class Base():
    """
    MrFriendly's DATABASE

    **Most tables are running STRICT**\n
    Will raise `sqlite3.IntegrityError` if value does not match column type.
    """
    dir: Path = Path(__file__).parent
    DB_FILENAME: str = "mrfriendly.db"
    DB_FILE_PATH: str = Path(dir).joinpath(DB_FILENAME).as_posix()
    SCHEMA_FILE_PATH: str = Path(dir).joinpath("schema.sql").as_posix()
    _logger: logging.Logger = logging.getLogger()
    pool: asqlite.Pool | None = None

    async def _fetchone(self, SQL: str, parameters: tuple[Any, ...] | dict[str, Any] | None = None) -> Row | None:
        """
        Query for a single Row.

        Args:
            SQL (str): The SQL query statement.

        Returns:
            Row | None: A Row.
        """
        if self.pool is None:
            self.pool = DB_Pool.get_pool()

        async with self.pool.acquire() as conn:
            if parameters is None:
                return await conn.fetchone(SQL)
            else:
                return await conn.fetchone(SQL, parameters)

    async def _fetchall(self, SQL: str, parameters: tuple[Any, ...] | dict[str, Any] | None = None) -> list[Row]:
        """
        Query for a list of Rows.

        Args:
            SQL (str): The SQL query statement.

        Returns:
            list[Row]: A list of Rows.
        """

        if self.pool is None:
            self.pool = DB_Pool.get_pool()

        async with self.pool.acquire() as conn:
            if parameters is None:
                return await conn.fetchall(SQL)
            else:
                return await conn.fetchall(SQL, parameters)

    async def _execute(self, SQL: str, parameters: tuple[Any, ...] | dict[str, Any] | None = None) -> Row | None:
        """
        Execute a SQL statement.

        Args:
            SQL (str): The SQL statement.
        """
        if self.pool is None:
            self.pool = DB_Pool.get_pool()

        async with self.pool.acquire() as conn:
            if parameters is None:
                res: asqlite.Cursor = await conn.execute(SQL)
            else:
                res = await conn.execute(SQL, parameters)
            return await res.fetchone()

    async def _execute_with_cursor(self, SQL: str, parameters: tuple[Any, ...] | dict[str, Any] | None = None) -> Cursor:
        """
        Execute a SQL statement.

        Args:
            SQL (str): The SQL statement.
        """
        if self.pool is None:
            self.pool = DB_Pool.get_pool()

        async with self.pool.acquire() as conn:
            if parameters is None:
                res: asqlite.Cursor = await conn.execute(SQL)
            else:
                res = await conn.execute(SQL, parameters)
            return res.get_cursor()

    async def _create_tables(self) -> None:
        """
        Creates the DATABASE tables from `SCHEMA_FILE_PATH`. \n

        """
        self._logger.info(msg=f"Initializing our Database...")
        
        with open(file=self.SCHEMA_FILE_PATH, mode="r") as f:
            async with DB_Pool().connect() as conn:
                async with conn.cursor() as cur:
                    await cur.executescript(sql_script=f.read())

        await self._check_update()


    async def _check_update(self) -> Any | None:
        """
        Handles our Database alterations and updates.
        """
        self._logger.info(msg=f"Checking Database for updates...")
        #check if the version table exists.
        res: Row | None = await self._fetchone(SQL=f"""SELECT * FROM version""")
        version: VersionInfo = VersionInfo()._parse_version()
        if res is None:
            # First update to add version support.
            await self._execute(SQL=f"""INSERT INTO version(major, minor, revision, level) VALUES(?,?,?,?) RETURNING *""", 
                        parameters=(version.major, version.minor, version.revision, version.level))
            return await self._check_update()
        e_version = VersionInfo(**res)
        self._logger.info(msg=f"Found Database version {e_version}...")
        
        if e_version != version:
            if version == VersionInfo(major=0, minor= 0, revision=2, level="release"):
                self._logger.info(msg=f"Updating our Database from {e_version} to {version}...")
                try:
                    await self._execute(SQL="""ALTER TABLE settings ADD COLUMN rules_channel_id INTEGER DEFAULT 0""")
                except sqlite3.OperationalError as e:
                    pass
                await self._execute(SQL=f"""UPDATE version SET major = ?, minor = ?, revision = ?""", parameters=(version.major, version.minor, version.revision))
                await self._check_update()
        
      
        else:
            self._logger.info(msg=f"No Updates found, our Database is currently on version {e_version}...")
        

                
       
                
