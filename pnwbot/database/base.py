import logging
from pathlib import Path
from sqlite3 import Cursor, Row
from typing import Any

import util.asqlite as asqlite

__all__: tuple[str, ...] = ("Base",)


class Base:
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
    _pool: asqlite.Pool | None

    def __init__(self, pool: asqlite.Pool | None = None) -> None:
        self._pool = pool

    @property
    def pool(self) -> asqlite.Pool:
        if self._pool is None:
            self._logger.error(msg="Database Pool has not been initialized")
            raise ValueError("Database Pool has not been initialized")
        return self._pool

    async def _fetchone(self, SQL: str, parameters: tuple[Any, ...] | dict[str, Any] | None = None) -> Row | None:
        """
        Query for a single Row.

        Args:
            SQL (str): The SQL query statement.

        Returns:
            Row | None: A Row.
        """
        if self._pool is None:
            self._pool = await asqlite.create_pool(database=self.DB_FILE_PATH)

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

        if self._pool is None:
            self._pool = await asqlite.create_pool(database=self.DB_FILE_PATH)

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
        if self._pool is None:
            self._pool = await asqlite.create_pool(database=self.DB_FILE_PATH)

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
        if self._pool is None:
            self._pool = await asqlite.create_pool(database=self.DB_FILE_PATH)

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
        self._logger.info(f"CREATE TABLE {self.SCHEMA_FILE_PATH}")
        self._logger.info(f"{self.dir}")
        with open(file=self.SCHEMA_FILE_PATH, mode="r") as f:
            async with asqlite.connect(database=self.DB_FILE_PATH) as db:
                async with db.cursor() as cur:
                    await cur.executescript(sql_script=f.read())
