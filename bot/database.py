import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "sanctions.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sanctions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                moderator_name TEXT NOT NULL,
                type TEXT NOT NULL,
                reason TEXT,
                duration INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                active INTEGER NOT NULL DEFAULT 1
            )
        """)
        await db.commit()


async def add_sanction(
    user_id: int,
    user_name: str,
    guild_id: int,
    moderator_id: int,
    moderator_name: str,
    sanction_type: str,
    reason: str = None,
    duration: int = None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO sanctions
                (user_id, user_name, guild_id, moderator_id, moderator_name, type, reason, duration, created_at, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), 1)
            """,
            (user_id, user_name, guild_id, moderator_id, moderator_name, sanction_type, reason, duration),
        )
        await db.commit()
        return cursor.lastrowid


async def get_sanctions(guild_id: int, user_id: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id:
            cursor = await db.execute(
                "SELECT * FROM sanctions WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
                (guild_id, user_id),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM sanctions WHERE guild_id = ? ORDER BY created_at DESC LIMIT 100",
                (guild_id,),
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_sanction_by_id(sanction_id: int, guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM sanctions WHERE id = ? AND guild_id = ?",
            (sanction_id, guild_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def deactivate_sanction(sanction_id: int, guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sanctions SET active = 0 WHERE id = ? AND guild_id = ?",
            (sanction_id, guild_id),
        )
        await db.commit()
