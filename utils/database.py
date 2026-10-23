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

SHOP_ITEMS: dict[str, dict[str, Any]] = {
    "theme_cyberpunk": {
        "id": "theme_cyberpunk",
        "category": "theme",
        "theme_key": "cyberpunk",
        "name": "Cyberpunk Neon Theme",
        "price": 600,
        "emoji": "🌆",
        "description": "Hot Magenta & Electric Cyan neon palette for your /profile card.",
    },
    "theme_crimson": {
        "id": "theme_crimson",
        "category": "theme",
        "theme_key": "crimson",
        "name": "Crimson Blood Theme",
        "price": 600,
        "emoji": "🩸",
        "description": "Dark Obsidian card with Blood Crimson & Ember Gold accents.",
    },
    "theme_emerald": {
        "id": "theme_emerald",
        "category": "theme",
        "theme_key": "emerald",
        "name": "Emerald Matrix Theme",
        "price": 650,
        "emoji": "🧪",
        "description": "Deep forest slate with glowing Neon Emerald & Mint highlights.",
    },
    "theme_royal": {
        "id": "theme_royal",
        "category": "theme",
        "theme_key": "royal",
        "name": "Royal Gold Theme",
        "price": 1000,
        "emoji": "👑",
        "description": "Luxury velvet dark card with Imperial Gold & Amber trim.",
    },
    "title_legend": {
        "id": "title_legend",
        "category": "title",
        "title_text": "SERVER LEGEND",
        "name": "Title: Server Legend",
        "price": 500,
        "emoji": "⚡",
        "description": "Displays the [SERVER LEGEND] title tag on your /profile card.",
    },
    "title_warlord": {
        "id": "title_warlord",
        "category": "title",
        "title_text": "SQUAD WARLORD",
        "name": "Title: Squad Warlord",
        "price": 500,
        "emoji": "⚔️",
        "description": "Displays the [SQUAD WARLORD] title tag on your /profile card.",
    },
    "title_oracle": {
        "id": "title_oracle",
        "category": "title",
        "title_text": "CHRONO ORACLE",
        "name": "Title: Chrono Oracle",
        "price": 550,
        "emoji": "⏳",
        "description": "Displays the [CHRONO ORACLE] title tag on your /profile card.",
    },
    "title_vip": {
        "id": "title_vip",
        "category": "title",
        "title_text": "HIGH ROLLER VIP",
        "name": "Title: High Roller VIP",
        "price": 1200,
        "emoji": "💎",
        "description": "Displays the prestigious [HIGH ROLLER VIP] tag on your /profile card.",
    },
    "boost_xp_24h": {
        "id": "boost_xp_24h",
        "category": "consumable",
        "name": "2x XP Overclock (24 Hours)",
        "price": 400,
        "emoji": "🚀",
        "description": "Doubles all XP earned from chat, voice, LFG, and contracts for 24 hours!",
    },
}


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

    async def _safe_add_column(self, table: str, column_def: str) -> None:
        try:
            await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        except aiosqlite.OperationalError:
            pass

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
                lfg_category_id INTEGER,
                wrapped_channel_id INTEGER,
                last_wrapped_week TEXT
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
                equipped_theme TEXT NOT NULL DEFAULT 'default',
                equipped_title TEXT NOT NULL DEFAULT '',
                xp_boost_until INTEGER NOT NULL DEFAULT 0,
                weekly_xp INTEGER NOT NULL DEFAULT 0,
                weekly_messages INTEGER NOT NULL DEFAULT 0,
                weekly_voice_minutes INTEGER NOT NULL DEFAULT 0,
                weekly_lfg_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS user_inventory (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                purchased_at INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id, item_id)
            );

            CREATE TABLE IF NOT EXISTS lfg_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                host_id INTEGER NOT NULL,
                game TEXT NOT NULL,
                created_at INTEGER NOT NULL
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
        # Ensure existing databases get new columns seamlessly
        await self._safe_add_column("guild_settings", "wrapped_channel_id INTEGER")
        await self._safe_add_column("guild_settings", "last_wrapped_week TEXT")
        await self._safe_add_column("users", "equipped_theme TEXT NOT NULL DEFAULT 'default'")
        await self._safe_add_column("users", "equipped_title TEXT NOT NULL DEFAULT ''")
        await self._safe_add_column("users", "xp_boost_until INTEGER NOT NULL DEFAULT 0")
        await self._safe_add_column("users", "weekly_xp INTEGER NOT NULL DEFAULT 0")
        await self._safe_add_column("users", "weekly_messages INTEGER NOT NULL DEFAULT 0")
        await self._safe_add_column("users", "weekly_voice_minutes INTEGER NOT NULL DEFAULT 0")
        await self._safe_add_column("users", "weekly_lfg_count INTEGER NOT NULL DEFAULT 0")
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
        Adds XP (doubled if 2x XP booster is active), coins, and stat increments to a user.
        Also updates weekly counters for Weekly Wrapped.
        Returns (old_level, new_level, leveled_up).
        """
        user = await self.ensure_user(guild_id, user_id)
        now = int(time.time())
        effective_xp = xp * 2 if (xp > 0 and user.get("xp_boost_until", 0) > now) else xp

        old_level, _, _ = get_level_info(user["xp"])
        new_xp = max(0, user["xp"] + effective_xp)
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
                capsules_count = capsules_count + ?,
                weekly_xp = weekly_xp + ?,
                weekly_messages = weekly_messages + ?,
                weekly_voice_minutes = weekly_voice_minutes + ?,
                weekly_lfg_count = weekly_lfg_count + ?
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
                max(0, effective_xp),
                messages_inc,
                voice_minutes_inc,
                lfg_inc,
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
    # Shop & Customization Inventory
    # ------------------------------------------------------------------
    async def get_user_inventory(self, guild_id: int, user_id: int) -> list[str]:
        async with self.conn.execute(
            "SELECT item_id FROM user_inventory WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cur:
            rows = await cur.fetchall()
            return [str(r["item_id"]) for r in rows]

    async def purchase_shop_item(
        self, guild_id: int, user_id: int, item_id: str
    ) -> tuple[bool, str]:
        item = SHOP_ITEMS.get(item_id)
        if not item:
            return False, "Item not found in shop."

        user = await self.ensure_user(guild_id, user_id)
        owned = await self.get_user_inventory(guild_id, user_id)

        if item["category"] in ("theme", "title") and item_id in owned:
            return False, "You already own this item! Use `/shop equip` or the Equip menu to activate it."

        if user["coins"] < item["price"]:
            return (
                False,
                f"Insufficient Coins! You need **{item['price']:,} Coins**, but you have **{user['coins']:,} Coins**.",
            )

        now = int(time.time())
        await self.conn.execute(
            "UPDATE users SET coins = coins - ? WHERE guild_id = ? AND user_id = ?",
            (item["price"], guild_id, user_id),
        )

        if item["category"] == "consumable" and item_id == "boost_xp_24h":
            current_boost = max(now, user.get("xp_boost_until", 0))
            new_boost = current_boost + 86400
            await self.conn.execute(
                "UPDATE users SET xp_boost_until = ? WHERE guild_id = ? AND user_id = ?",
                (new_boost, guild_id, user_id),
            )
            await self.conn.commit()
            return (
                True,
                f"🚀 **2x XP Overclock Activated!** Your XP gains are doubled until <t:{new_boost}:F> (<t:{new_boost}:R>).",
            )

        await self.conn.execute(
            "INSERT OR IGNORE INTO user_inventory (guild_id, user_id, item_id, purchased_at) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, item_id, now),
        )

        if item["category"] == "theme":
            await self.conn.execute(
                "UPDATE users SET equipped_theme = ? WHERE guild_id = ? AND user_id = ?",
                (item["theme_key"], guild_id, user_id),
            )
            await self.conn.commit()
            return (
                True,
                f"🎨 Purchased and equipped **{item['name']}**! Check out your new look with `/profile`.",
            )

        if item["category"] == "title":
            await self.conn.execute(
                "UPDATE users SET equipped_title = ? WHERE guild_id = ? AND user_id = ?",
                (item["title_text"], guild_id, user_id),
            )
            await self.conn.commit()
            return (
                True,
                f"🏷️ Purchased and equipped title **[{item['title_text']}]**! View it with `/profile`.",
            )

        await self.conn.commit()
        return True, f"Purchased **{item['name']}**!"

    async def equip_user_item(
        self, guild_id: int, user_id: int, item_id: str
    ) -> tuple[bool, str]:
        await self.ensure_user(guild_id, user_id)
        if item_id == "theme_default":
            await self.conn.execute(
                "UPDATE users SET equipped_theme = 'default' WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            await self.conn.commit()
            return True, "🎨 Equipped the default **Discord Modern Dark** theme!"

        if item_id == "title_none":
            await self.conn.execute(
                "UPDATE users SET equipped_title = '' WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            await self.conn.commit()
            return True, "🏷️ Cleared your custom profile title."

        owned = await self.get_user_inventory(guild_id, user_id)
        if item_id not in owned:
            return False, "You do not own this item yet! Purchase it in `/shop` first."

        item = SHOP_ITEMS.get(item_id)
        if not item:
            return False, "Unknown item."

        if item["category"] == "theme":
            await self.conn.execute(
                "UPDATE users SET equipped_theme = ? WHERE guild_id = ? AND user_id = ?",
                (item["theme_key"], guild_id, user_id),
            )
            await self.conn.commit()
            return True, f"🎨 Equipped **{item['name']}**!"

        if item["category"] == "title":
            await self.conn.execute(
                "UPDATE users SET equipped_title = ? WHERE guild_id = ? AND user_id = ?",
                (item["title_text"], guild_id, user_id),
            )
            await self.conn.commit()
            return True, f"🏷️ Equipped title **[{item['title_text']}]**!"

        return False, "This item cannot be equipped."

    # ------------------------------------------------------------------
    # Weekly Wrapped & Server Analytics
    # ------------------------------------------------------------------
    async def log_lfg_game(self, guild_id: int, host_id: int, game: str) -> None:
        now = int(time.time())
        await self.conn.execute(
            "INSERT INTO lfg_logs (guild_id, host_id, game, created_at) VALUES (?, ?, ?, ?)",
            (guild_id, host_id, game, now),
        )
        await self.conn.commit()

    async def get_weekly_wrapped_data(self, guild_id: int) -> dict[str, Any]:
        week_ago = int(time.time()) - 7 * 86400

        # Top chatter of the week
        async with self.conn.execute(
            """
            SELECT user_id, weekly_messages, weekly_xp
            FROM users
            WHERE guild_id = ? AND weekly_messages > 0
            ORDER BY weekly_messages DESC, weekly_xp DESC
            LIMIT 1
            """,
            (guild_id,),
        ) as cur:
            top_chatter = dict(row) if (row := await cur.fetchone()) else None

        # Top voice champion of the week
        async with self.conn.execute(
            """
            SELECT user_id, weekly_voice_minutes
            FROM users
            WHERE guild_id = ? AND weekly_voice_minutes > 0
            ORDER BY weekly_voice_minutes DESC
            LIMIT 1
            """,
            (guild_id,),
        ) as cur:
            top_voice = dict(row) if (row := await cur.fetchone()) else None

        # Top LFG squad leader of the week
        async with self.conn.execute(
            """
            SELECT user_id, weekly_lfg_count
            FROM users
            WHERE guild_id = ? AND weekly_lfg_count > 0
            ORDER BY weekly_lfg_count DESC
            LIMIT 1
            """,
            (guild_id,),
        ) as cur:
            top_lfg = dict(row) if (row := await cur.fetchone()) else None

        # Most played LFG game in the last 7 days
        async with self.conn.execute(
            """
            SELECT game, COUNT(*) AS cnt
            FROM lfg_logs
            WHERE guild_id = ? AND created_at >= ?
            GROUP BY LOWER(game)
            ORDER BY cnt DESC
            LIMIT 1
            """,
            (guild_id, week_ago),
        ) as cur:
            top_game = dict(row) if (row := await cur.fetchone()) else None

        # Best quote of the week
        async with self.conn.execute(
            """
            SELECT author_id, quote_text, stars_count
            FROM hall_of_fame
            WHERE guild_id = ? AND created_at >= ?
            ORDER BY stars_count DESC, created_at DESC
            LIMIT 1
            """,
            (guild_id, week_ago),
        ) as cur:
            top_quote = dict(row) if (row := await cur.fetchone()) else None

        # Server weekly totals
        async with self.conn.execute(
            """
            SELECT
                COALESCE(SUM(weekly_messages), 0) AS total_messages,
                COALESCE(SUM(weekly_voice_minutes), 0) AS total_voice,
                COALESCE(SUM(weekly_lfg_count), 0) AS total_lfg,
                COALESCE(SUM(weekly_xp), 0) AS total_xp,
                COUNT(CASE WHEN weekly_xp > 0 OR weekly_messages > 0 OR weekly_voice_minutes > 0 THEN 1 END) AS active_members
            FROM users
            WHERE guild_id = ?
            """,
            (guild_id,),
        ) as cur:
            totals_row = await cur.fetchone()
            totals = dict(totals_row) if totals_row else {}

        return {
            "top_chatter": top_chatter,
            "top_voice": top_voice,
            "top_lfg": top_lfg,
            "top_game": top_game,
            "top_quote": top_quote,
            "totals": totals,
        }

    async def reset_weekly_stats(self, guild_id: int) -> None:
        await self.conn.execute(
            """
            UPDATE users
            SET weekly_xp = 0,
                weekly_messages = 0,
                weekly_voice_minutes = 0,
                weekly_lfg_count = 0
            WHERE guild_id = ?
            """,
            (guild_id,),
        )
        await self.conn.commit()

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
