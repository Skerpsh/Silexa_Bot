import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
COGS_DIR = BASE_DIR / "cogs"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "silexa.db"

load_dotenv(BASE_DIR / ".env")

_raw_token = os.getenv("DISCORD_TOKEN", "").strip().strip("'\"")
if _raw_token.lower().startswith("bot "):
    _raw_token = _raw_token[4:].strip()
DISCORD_TOKEN: str | None = _raw_token or None
DISCORD_GUILD_ID: int | None = (
    int(os.environ["DISCORD_GUILD_ID"])
    if os.getenv("DISCORD_GUILD_ID", "").strip().isdigit()
    else None
)

# Discord Modern Dark Color Palette (Hex & RGB)
COLOR_BLURPLE = 0x5865F2
COLOR_GOLD = 0xF0B232
COLOR_SUCCESS = 0x23A55A
COLOR_DANGER = 0xF23F43
COLOR_DARK_EMBED = 0x2B2D31

# Economy & Leveling Constants
CHAT_XP_MIN = 15
CHAT_XP_MAX = 25
CHAT_COINS_MIN = 3
CHAT_COINS_MAX = 8
CHAT_COOLDOWN_SECONDS = 45

VOICE_XP_PER_MIN = 10
VOICE_COINS_PER_MIN = 4

DAILY_BASE_COINS = 250
DAILY_BASE_XP = 100
DAILY_STREAK_BONUS = 35
ALL_CONTRACTS_BONUS_COINS = 300
ALL_CONTRACTS_BONUS_XP = 200
