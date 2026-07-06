import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "sanctions.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # ── Sanctions ──────────────────────────────────────────────────────────
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

        # ── Tickets ────────────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                closed_at TEXT
            )
        """)

        # ── Salons vocaux privés ───────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS private_voice (
                channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                mode TEXT NOT NULL DEFAULT 'public',
                panel_message_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS voice_whitelist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                UNIQUE(channel_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS voice_blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                UNIQUE(channel_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS voice_saved_whitelist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                UNIQUE(owner_id, guild_id, user_id)
            )
        """)

        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# Sanctions
# ═══════════════════════════════════════════════════════════════════════════════

async def add_sanction(
    user_id: int, user_name: str, guild_id: int,
    moderator_id: int, moderator_name: str,
    sanction_type: str, reason: str = None, duration: int = None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO sanctions
                (user_id, user_name, guild_id, moderator_id, moderator_name,
                 type, reason, duration, created_at, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), 1)
            """,
            (user_id, user_name, guild_id, moderator_id, moderator_name,
             sanction_type, reason, duration),
        )
        await db.commit()
        return cursor.lastrowid


async def get_sanctions(guild_id: int, user_id: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if user_id:
            cursor = await db.execute(
                "SELECT * FROM sanctions WHERE guild_id=? AND user_id=? ORDER BY created_at DESC",
                (guild_id, user_id),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM sanctions WHERE guild_id=? ORDER BY created_at DESC LIMIT 100",
                (guild_id,),
            )
        return [dict(r) for r in await cursor.fetchall()]


async def get_sanction_by_id(sanction_id: int, guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM sanctions WHERE id=? AND guild_id=?", (sanction_id, guild_id)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def deactivate_sanction(sanction_id: int, guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sanctions SET active=0 WHERE id=? AND guild_id=?", (sanction_id, guild_id)
        )
        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# Tickets
# ═══════════════════════════════════════════════════════════════════════════════

async def save_ticket(channel_id, user_id, user_name, guild_id, ticket_type):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO tickets (channel_id, user_id, user_name, guild_id, type, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'open', datetime('now'))""",
            (channel_id, user_id, user_name, guild_id, ticket_type),
        )
        await db.commit()


async def get_ticket_info(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tickets WHERE channel_id=?", (channel_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def close_ticket(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tickets SET status='closed', closed_at=datetime('now') WHERE channel_id=?",
            (channel_id,),
        )
        await db.commit()


async def reopen_ticket(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tickets SET status='open', closed_at=NULL WHERE channel_id=?",
            (channel_id,),
        )
        await db.commit()


async def delete_ticket(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tickets WHERE channel_id=?", (channel_id,))
        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# Salons vocaux privés
# ═══════════════════════════════════════════════════════════════════════════════

async def create_private_voice(channel_id: int, owner_id: int, guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO private_voice
               (channel_id, owner_id, guild_id, mode, created_at)
               VALUES (?, ?, ?, 'public', datetime('now'))""",
            (channel_id, owner_id, guild_id),
        )
        await db.commit()


async def get_private_voice(channel_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM private_voice WHERE channel_id=?", (channel_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_private_voice(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM private_voice WHERE channel_id=?", (channel_id,))
        await db.execute("DELETE FROM voice_whitelist WHERE channel_id=?", (channel_id,))
        await db.execute("DELETE FROM voice_blacklist WHERE channel_id=?", (channel_id,))
        await db.commit()


async def set_voice_mode(channel_id: int, mode: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE private_voice SET mode=? WHERE channel_id=?", (mode, channel_id)
        )
        await db.commit()


async def set_voice_owner(channel_id: int, owner_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE private_voice SET owner_id=? WHERE channel_id=?", (owner_id, channel_id)
        )
        await db.commit()


async def set_voice_panel_message(channel_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE private_voice SET panel_message_id=? WHERE channel_id=?",
            (message_id, channel_id),
        )
        await db.commit()


# ── Whitelist ──────────────────────────────────────────────────────────────────

async def add_voice_whitelist(channel_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO voice_whitelist (channel_id, user_id) VALUES (?, ?)",
            (channel_id, user_id),
        )
        await db.commit()


async def rm_voice_whitelist(channel_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM voice_whitelist WHERE channel_id=? AND user_id=?",
            (channel_id, user_id),
        )
        await db.commit()


async def clear_voice_whitelist(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM voice_whitelist WHERE channel_id=?", (channel_id,))
        await db.commit()


async def get_voice_whitelist(channel_id: int) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM voice_whitelist WHERE channel_id=?", (channel_id,)
        )
        return [r[0] for r in await cursor.fetchall()]


async def is_in_voice_whitelist(channel_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM voice_whitelist WHERE channel_id=? AND user_id=?",
            (channel_id, user_id),
        )
        return await cursor.fetchone() is not None


# ── Blacklist ──────────────────────────────────────────────────────────────────

async def add_voice_blacklist(channel_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO voice_blacklist (channel_id, user_id) VALUES (?, ?)",
            (channel_id, user_id),
        )
        await db.commit()


async def rm_voice_blacklist(channel_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM voice_blacklist WHERE channel_id=? AND user_id=?",
            (channel_id, user_id),
        )
        await db.commit()


async def get_voice_blacklist(channel_id: int) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM voice_blacklist WHERE channel_id=?", (channel_id,)
        )
        return [r[0] for r in await cursor.fetchall()]


async def is_in_voice_blacklist(channel_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM voice_blacklist WHERE channel_id=? AND user_id=?",
            (channel_id, user_id),
        )
        return await cursor.fetchone() is not None


# ── Whitelist sauvegardée ──────────────────────────────────────────────────────

async def save_voice_whitelist(owner_id: int, guild_id: int, user_ids: list[int]):
    """Remplace la whitelist sauvegardée de l'owner par la liste fournie."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM voice_saved_whitelist WHERE owner_id=? AND guild_id=?",
            (owner_id, guild_id),
        )
        for uid in user_ids:
            await db.execute(
                "INSERT OR IGNORE INTO voice_saved_whitelist (owner_id, guild_id, user_id) VALUES (?, ?, ?)",
                (owner_id, guild_id, uid),
            )
        await db.commit()


async def load_voice_whitelist(owner_id: int, guild_id: int) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM voice_saved_whitelist WHERE owner_id=? AND guild_id=?",
            (owner_id, guild_id),
        )
        return [r[0] for r in await cursor.fetchall()]
