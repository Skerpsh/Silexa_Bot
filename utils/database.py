import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import aiosqlite

import config

CONTRACT_TEMPLATES: list[dict[str, Any]] = [
    {
        "type": "messages",
        "title": "Active Chatter",
        "description": "Send {target} messages in any text channel",
        "target": 15,
        "reward_coins": 120,
        "reward_xp": 80,
    },
    {
        "type": "voice_minutes",
        "title": "Voice Hangout",
        "description": "Spend {target} minutes in a Voice / TempVoice room",
        "target": 10,
        "reward_coins": 150,
        "reward_xp": 100,
    },
    {
        "type": "lfg_participate",
        "title": "Squad Up",
        "description": "Host or join {target} LFG Squad lobby (/lfg)",
        "target": 1,
        "reward_coins": 160,
        "reward_xp": 110,
    },
    {
        "type": "hall_of_fame",
        "title": "Quote Collector",
        "description": "Save a message to the Hall of Fame or get featured",
        "target": 1,
        "reward_coins": 150,
        "reward_xp": 100,
    },
    {
        "type": "time_capsule",
        "title": "Time Traveler",
        "description": "Seal {target} Time Capsule for the future (/capsule seal)",
        "target": 1,
        "reward_coins": 140,
        "reward_xp": 95,
    },
]


def get_level_info(total_xp: int) -> tuple[int, int, int]:
    """
    Given total_xp, returns (level, xp_into_current_level, xp_required_for_next_level).
    Level 1 starts at 0 XP and requires 150 XP for Level 2.
    Each subsequent level requires `150 + (level - 1) * 75` XP.
    """
    level = 1
    remaining = max(0, total_xp)
    while True:
        needed = 150 + (level - 1) * 75
        if remaining < needed:
            return level, remaining, needed
        remaining -= needed
        level += 1


def get_user_badges(user_data: dict[str, Any]) -> list[dict[str, str]]:
    """Compute unlocked badges based on user stats."""
    badges: list[dict[str, str]] = []
    level, _, _ = get_level_info(user_data.get("xp", 0))

    if user_data.get("messages_sent", 0) >= 50:
        badges.append({"icon": "💬", "code": "CHATTER", "name": "Chatterbox", "desc": "Sent 50+ chat messages"})
    if user_data.get("voice_minutes", 0) >= 30:
        badges.append({"icon": "🎙️", "code": "VOICE", "name": "Voice Regular", "desc": "30+ mins in Voice channels"})
    if user_data.get("lfg_count", 0) >= 3:
        badges.append({"icon": "🎮", "code": "SQUAD", "name": "Squad Leader", "desc": "Joined or hosted 3+ LFG lobbies"})
    if user_data.get("hof_count", 0) >= 1:
        badges.append({"icon": "⭐", "code": "FAMER", "name": "Hall of Famer", "desc": "Featured in the Hall of Fame"})
    if user_data.get("capsules_count", 0) >= 1:
        badges.append({"icon": "⏳", "code": "CHRONO", "name": "Time Traveler", "desc": "Sealed a Time Capsule"})
    if user_data.get("daily_streak", 0) >= 7:
        badges.append({"icon": "🔥", "code": "STREAK", "name": "Dedicated", "desc": "Reached a 7-day daily streak"})
    if user_data.get("coins", 0) >= 2500:
        badges.append({"icon": "💎", "code": "TYCOON", "name": "High Roller", "desc": "Accumulated 2,500+ Coins"})
    if level >= 10:
        badges.append({"icon": "👑", "code": "VETERAN", "name": "Server Veteran", "desc": "Reached Level 10+"})

    return badges


class Database:
    def __init__(self, db_path: Path = config.DB_PATH) -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self.init_schema()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database connection is not initialized. Call await db.connect() first.")
        return self._conn

    async def init_schema(self) -> None:
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                hof_channel_id INTEGER,
                hof_threshold INTEGER NOT NULL DEFAULT 3,
                hof_emoji TEXT NOT NULL DEFAULT '⭐',
                jtc_channel_id INTEGER,
                jtc_category_id INTEGER,
                lfg_category_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS users (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                xp INTEGER NOT NULL DEFAULT 0,
                coins INTEGER NOT NULL DEFAULT 100,
                messages_sent INTEGER NOT NULL DEFAULT 0,
                voice_minutes INTEGER NOT NULL DEFAULT 0,
                lfg_count INTEGER NOT NULL DEFAULT 0,
                hof_count INTEGER NOT NULL DEFAULT 0,
                capsules_count INTEGER NOT NULL DEFAULT 0,
                daily_streak INTEGER NOT NULL DEFAULT 0,
                last_daily_date TEXT,
                bio TEXT NOT NULL DEFAULT 'Server Member & Adventurer',
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS daily_contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                contract_date TEXT NOT NULL,
                contract_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                target INTEGER NOT NULL DEFAULT 1,
                reward_coins INTEGER NOT NULL DEFAULT 100,
                reward_xp INTEGER NOT NULL DEFAULT 50,
                completed INTEGER NOT NULL DEFAULT 0,
                UNIQUE(guild_id, user_id, contract_date, contract_type)
            );

            CREATE TABLE IF NOT EXISTS time_capsules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                attachment_url TEXT,
                created_at INTEGER NOT NULL,
                open_at INTEGER NOT NULL,
                teaser_message_id INTEGER,
                is_opened INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS hall_of_fame (
                message_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                nominated_by_id INTEGER NOT NULL,
                hof_message_id INTEGER,
                quote_text TEXT NOT NULL,
                stars_count INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS temp_voice_channels (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                is_locked INTEGER NOT NULL DEFAULT 0,
                is_hidden INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );
            """
        )
        await self.conn.commit()

    # ------------------------------------------------------------------
    # Guild Settings
    # ------------------------------------------------------------------
    async def get_guild_settings(self, guild_id: int) -> dict[str, Any]:
        await self.conn.execute(
            "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)",
            (guild_id,),
        )
        await self.conn.commit()
        async with self.conn.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else {}

    async def update_guild_settings(self, guild_id: int, **kwargs: Any) -> None:
        await self.get_guild_settings(guild_id)
        if not kwargs:
            return
        columns = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [guild_id]
        await self.conn.execute(
            f"UPDATE guild_settings SET {columns} WHERE guild_id = ?",
            values,
        )
        await self.conn.commit()

    # ------------------------------------------------------------------
    # Users & Economy
    # ------------------------------------------------------------------
    async def ensure_user(self, guild_id: int, user_id: int) -> dict[str, Any]:
        await self.conn.execute(
            "INSERT OR IGNORE INTO users (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id),
        )
        await self.conn.commit()
        async with self.conn.execute(
            "SELECT * FROM users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else {}

    async def get_user_rank(self, guild_id: int, user_id: int) -> int:
        await self.ensure_user(guild_id, user_id)
        async with self.conn.execute(
            """
            SELECT COUNT(*) + 1 AS rank
            FROM users
            WHERE guild_id = ? AND xp > (
                SELECT xp FROM users WHERE guild_id = ? AND user_id = ?
            )
            """,
            (guild_id, guild_id, user_id),
        ) as cur:
            row = await cur.fetchone()
            return int(row["rank"]) if row else 1

    async def add_rewards(
        self,
        guild_id: int,
        user_id: int,
        xp: int = 0,
        coins: int = 0,
        messages_inc: int = 0,
        voice_minutes_inc: int = 0,
        lfg_inc: int = 0,
        hof_inc: int = 0,
        capsules_inc: int = 0,
    ) -> tuple[int, int, bool]:
        """
        Adds XP, coins, and stat increments to a user.
        Returns (old_level, new_level, leveled_up).
        """
        user = await self.ensure_user(guild_id, user_id)
        old_level, _, _ = get_level_info(user["xp"])
        new_xp = max(0, user["xp"] + xp)
        new_coins = max(0, user["coins"] + coins)
        new_level, _, _ = get_level_info(new_xp)

        await self.conn.execute(
            """
            UPDATE users
            SET xp = ?,
                coins = ?,
                messages_sent = messages_sent + ?,
                voice_minutes = voice_minutes + ?,
                lfg_count = lfg_count + ?,
                hof_count = hof_count + ?,
                capsules_count = capsules_count + ?
            WHERE guild_id = ? AND user_id = ?
            """,
            (
                new_xp,
                new_coins,
                messages_inc,
                voice_minutes_inc,
                lfg_inc,
                hof_inc,
                capsules_inc,
                guild_id,
                user_id,
            ),
        )
        await self.conn.commit()
        return old_level, new_level, new_level > old_level

    async def set_user_bio(self, guild_id: int, user_id: int, bio: str) -> None:
        await self.ensure_user(guild_id, user_id)
        await self.conn.execute(
            "UPDATE users SET bio = ? WHERE guild_id = ? AND user_id = ?",
            (bio[:90], guild_id, user_id),
        )
        await self.conn.commit()

    async def transfer_coins(
        self, guild_id: int, sender_id: int, receiver_id: int, amount: int
    ) -> bool:
        if amount <= 0:
            return False
        sender = await self.ensure_user(guild_id, sender_id)
        if sender["coins"] < amount:
            return False
        await self.ensure_user(guild_id, receiver_id)
        await self.conn.execute(
            "UPDATE users SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, sender_id),
        )
        await self.conn.execute(
            "UPDATE users SET coins = coins + ? WHERE guild_id = ? AND user_id = ?",
            (amount, guild_id, receiver_id),
        )
        await self.conn.commit()
        return True

    async def get_leaderboard(
        self, guild_id: int, sort_by: str = "xp", limit: int = 10
    ) -> list[dict[str, Any]]:
        column = "coins" if sort_by == "coins" else "xp"
        async with self.conn.execute(
            f"SELECT * FROM users WHERE guild_id = ? ORDER BY {column} DESC LIMIT ?",
            (guild_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Daily Contracts
    # ------------------------------------------------------------------
    @staticmethod
    def today_str() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async def get_or_create_daily_contracts(
        self, guild_id: int, user_id: int
    ) -> list[dict[str, Any]]:
        await self.ensure_user(guild_id, user_id)
        today = self.today_str()
        async with self.conn.execute(
            """
            SELECT * FROM daily_contracts
            WHERE guild_id = ? AND user_id = ? AND contract_date = ?
            ORDER BY id ASC
            """,
            (guild_id, user_id, today),
        ) as cur:
            existing = [dict(r) for r in await cur.fetchall()]
            if existing:
                return existing

        # Pick 3 distinct contracts for the user today (deterministic seed per user+day)
        rng = random.Random(f"{guild_id}:{user_id}:{today}")
        chosen = rng.sample(CONTRACT_TEMPLATES, k=3)
        for tpl in chosen:
            desc = tpl["description"].format(target=tpl["target"])
            await self.conn.execute(
                """
                INSERT OR IGNORE INTO daily_contracts
                (guild_id, user_id, contract_date, contract_type, title, description, target, reward_coins, reward_xp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    user_id,
                    today,
                    tpl["type"],
                    tpl["title"],
                    desc,
                    tpl["target"],
                    tpl["reward_coins"],
                    tpl["reward_xp"],
                ),
            )
        await self.conn.commit()

        async with self.conn.execute(
            """
            SELECT * FROM daily_contracts
            WHERE guild_id = ? AND user_id = ? AND contract_date = ?
            ORDER BY id ASC
            """,
            (guild_id, user_id, today),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def progress_contract(
        self, guild_id: int, user_id: int, contract_type: str, amount: int = 1
    ) -> list[dict[str, Any]]:
        """
        Increments progress for a matching active contract today.
        Returns a list of newly completed contract dicts (including an optional bonus entry).
        """
        contracts = await self.get_or_create_daily_contracts(guild_id, user_id)
        newly_completed: list[dict[str, Any]] = []
        already_all_done = all(c["completed"] == 1 for c in contracts)

        for c in contracts:
            if c["contract_type"] == contract_type and c["completed"] == 0:
                new_prog = min(c["target"], c["progress"] + amount)
                now_done = 1 if new_prog >= c["target"] else 0
                await self.conn.execute(
                    """
                    UPDATE daily_contracts
                    SET progress = ?, completed = ?
                    WHERE id = ?
                    """,
                    (new_prog, now_done, c["id"]),
                )
                c["progress"] = new_prog
                c["completed"] = now_done
                if now_done == 1:
                    await self.add_rewards(
                        guild_id,
                        user_id,
                        xp=c["reward_xp"],
                        coins=c["reward_coins"],
                    )
                    newly_completed.append(c)

        await self.conn.commit()

        if newly_completed and not already_all_done:
            updated = await self.get_or_create_daily_contracts(guild_id, user_id)
            if all(c["completed"] == 1 for c in updated):
                await self.add_rewards(
                    guild_id,
                    user_id,
                    xp=config.ALL_CONTRACTS_BONUS_XP,
                    coins=config.ALL_CONTRACTS_BONUS_COINS,
                )
                newly_completed.append(
                    {
                        "title": "All Daily Contracts Completed!",
                        "reward_coins": config.ALL_CONTRACTS_BONUS_COINS,
                        "reward_xp": config.ALL_CONTRACTS_BONUS_XP,
                        "is_bonus": True,
                    }
                )

        return newly_completed

    # ------------------------------------------------------------------
    # Time Capsules
    # ------------------------------------------------------------------
    async def create_capsule(
        self,
        guild_id: int,
        channel_id: int,
        author_id: int,
        title: str,
        content: str,
        open_at: int,
        attachment_url: str | None = None,
        teaser_message_id: int | None = None,
    ) -> int:
        now = int(time.time())
        async with self.conn.execute(
            """
            INSERT INTO time_capsules
            (guild_id, channel_id, author_id, title, content, attachment_url, created_at, open_at, teaser_message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                channel_id,
                author_id,
                title,
                content,
                attachment_url,
                now,
                open_at,
                teaser_message_id,
            ),
        ) as cur:
            capsule_id = cur.lastrowid or 0
        await self.conn.commit()
        return int(capsule_id)

    async def set_capsule_teaser_message(
        self, capsule_id: int, message_id: int
    ) -> None:
        await self.conn.execute(
            "UPDATE time_capsules SET teaser_message_id = ? WHERE id = ?",
            (message_id, capsule_id),
        )
        await self.conn.commit()

    async def get_due_capsules(self) -> list[dict[str, Any]]:
        now = int(time.time())
        async with self.conn.execute(
            "SELECT * FROM time_capsules WHERE is_opened = 0 AND open_at <= ?",
            (now,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def mark_capsule_opened(self, capsule_id: int) -> None:
        await self.conn.execute(
            "UPDATE time_capsules SET is_opened = 1 WHERE id = ?",
            (capsule_id,),
        )
        await self.conn.commit()

    async def get_guild_capsules(
        self, guild_id: int, include_opened: bool = False, limit: int = 15
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM time_capsules WHERE guild_id = ? ORDER BY open_at ASC LIMIT ?"
            if include_opened
            else "SELECT * FROM time_capsules WHERE guild_id = ? AND is_opened = 0 ORDER BY open_at ASC LIMIT ?"
        )
        async with self.conn.execute(query, (guild_id, limit)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_capsule_by_id(
        self, guild_id: int, capsule_id: int
    ) -> dict[str, Any] | None:
        async with self.conn.execute(
            "SELECT * FROM time_capsules WHERE guild_id = ? AND id = ?",
            (guild_id, capsule_id),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------
    # Hall of Fame (Quote Board)
    # ------------------------------------------------------------------
    async def get_hof_entry(self, message_id: int) -> dict[str, Any] | None:
        async with self.conn.execute(
            "SELECT * FROM hall_of_fame WHERE message_id = ?",
            (message_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def add_hof_entry(
        self,
        message_id: int,
        guild_id: int,
        channel_id: int,
        author_id: int,
        nominated_by_id: int,
        quote_text: str,
        stars_count: int = 1,
        hof_message_id: int | None = None,
    ) -> None:
        now = int(time.time())
        await self.conn.execute(
            """
            INSERT OR REPLACE INTO hall_of_fame
            (message_id, guild_id, channel_id, author_id, nominated_by_id, hof_message_id, quote_text, stars_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                guild_id,
                channel_id,
                author_id,
                nominated_by_id,
                hof_message_id,
                quote_text,
                stars_count,
                now,
            ),
        )
        await self.conn.commit()

    async def get_random_hof_entry(self, guild_id: int) -> dict[str, Any] | None:
        async with self.conn.execute(
            "SELECT * FROM hall_of_fame WHERE guild_id = ? ORDER BY RANDOM() LIMIT 1",
            (guild_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_top_hof_entries(
        self, guild_id: int, limit: int = 10
    ) -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT * FROM hall_of_fame WHERE guild_id = ? ORDER BY stars_count DESC, created_at DESC LIMIT ?",
            (guild_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # TempVoice (Join-to-Create)
    # ------------------------------------------------------------------
    async def register_temp_voice(
        self, channel_id: int, guild_id: int, owner_id: int
    ) -> None:
        now = int(time.time())
        await self.conn.execute(
            """
            INSERT OR REPLACE INTO temp_voice_channels
            (channel_id, guild_id, owner_id, is_locked, is_hidden, created_at)
            VALUES (?, ?, ?, 0, 0, ?)
            """,
            (channel_id, guild_id, owner_id, now),
        )
        await self.conn.commit()

    async def get_temp_voice(self, channel_id: int) -> dict[str, Any] | None:
        async with self.conn.execute(
            "SELECT * FROM temp_voice_channels WHERE channel_id = ?",
            (channel_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def update_temp_voice(self, channel_id: int, **kwargs: Any) -> None:
        if not kwargs:
            return
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [channel_id]
        await self.conn.execute(
            f"UPDATE temp_voice_channels SET {cols} WHERE channel_id = ?",
            vals,
        )
        await self.conn.commit()

    async def delete_temp_voice(self, channel_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM temp_voice_channels WHERE channel_id = ?",
            (channel_id,),
        )
        await self.conn.commit()
