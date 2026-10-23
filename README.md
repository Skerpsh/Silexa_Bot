<div align="center">

# ✨ Silexa Bot

**A modern, all-in-one Discord community, gaming & economy bot built with `discord.py` 2.x, `aiosqlite`, and `Pillow`.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.3%2B-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![SQLite](https://img.shields.io/badge/SQLite-aiosqlite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://github.com/omnilib/aiosqlite)
[![License: MIT](https://img.shields.io/badge/License-MIT-F0B232?style=for-the-badge)](LICENSE)

</div>

---

## 📖 Overview

**Silexa Bot** brings interactive, modern Discord UI features (**Slash Commands**, **Context Menus**, **Buttons**, **Select Menus**, and **Modals**) together with dynamic **Pillow-rendered visual cards** in a unified **Discord Modern Dark** aesthetic.

Every system is interconnected through an asynchronous SQLite engine: chatting, hanging out in voice rooms, assembling gaming squads, sealing time capsules, and getting inducted into the Hall of Fame all contribute to your server profile, badges, and daily contracts.

---

## 🌟 Key Features

### 1. 🎮 LFG / Squad Builder (`cogs/lfg.py`)
Assemble gaming squads or voice hangouts with real-time roster management:
- **Interactive Lobby Cards:** Players can join the active roster (`✅ Join Squad`), hop on the backup bench (`🕒 Standby`), or leave (`✖️ Leave`) with a single click.
- **Automatic Standby Promotion:** If an active squad member leaves, the first player on Standby is automatically promoted to the main roster.
- **Auto-Spawned Voice Channels:** When the squad fills up (or when the host clicks `🔊 Launch Voice`), Silexa Bot automatically creates a dedicated temporary voice room and pings the full team.

### 2. ⏳ Time Capsules (`cogs/capsule.py`)
Lock away messages, predictions, or screenshots to be revealed in the future:
- **Flexible Timers:** Supports durations from `1m` up to `365d+` (e.g., `10m`, `24h`, `7d`, `30d`, `2d 12h`).
- **Encrypted Vault & Live Countdown:** Optionally posts a public teaser card in the channel with a live Discord relative countdown (`<t:timestamp:R>`) while keeping the message contents hidden in the database.
- **Automatic Unsealing:** A background task monitors sealed capsules and broadcasts the reveal embed in the original channel as soon as the timer expires.

### 3. ⭐ Hall of Fame & Quote Board (`cogs/quotes.py`)
Immortalize iconic or hilarious server moments as custom-rendered **Discord Modern Dark Quote Cards**:
- **3 Ways to Induct Quotes:**
  1. **Message Context Menu:** Right-click any message → **Apps** → **Save to Hall of Fame**.
  2. **Star Reaction Threshold:** Automatically inducts messages that reach the server's ⭐ reaction threshold (default: `3`, configurable via `/halloffame setup`).
  3. **Manual Command:** Render a quote card directly via `/halloffame quote`.
- **Custom Graphic Rendering (`Pillow`):** Generates an `880px` dark-themed quote card featuring the author's circular avatar, stylized quotation marks, word-wrapped quote, channel tag, timestamp, and star badge.

### 4. 🔊 Join-to-Create TempVoice (`cogs/tempvoice.py`)
Self-managing private voice lounges with an in-chat control dashboard:
- **Instant Room Spawning:** Joining the `➕ Join to Create` trigger channel automatically creates `🎧 {User}'s Room`, moves the member inside, and posts an interactive control panel in the voice channel's built-in text chat.
- **Interactive Room Controls:**
  - `🔒 Lock / Unlock` — Toggle `@everyone` connect permissions.
  - `👻 Hide / Reveal` — Toggle `@everyone` visibility permissions.
  - `✏️ Rename & Limit` — Open a Discord Modal to change the room name and user cap (`0–99`).
  - `👑 Claim Host` — Claim ownership of the room if the original creator leaves.
  - `➕ Permit / 👢 Disconnect` — User select menu to whitelist a friend or remove a member from the room.
- **Auto-Cleanup:** Temporary voice channels (including LFG squad rooms) are automatically deleted as soon as the last human member leaves.

### 5. 💰 Server Economy, Daily Contracts & Visual Profiles (`cogs/economy.py`)
A deeply integrated progression system across all bot modules:
- **HD Visual Profile Cards (`/profile`):** Renders a `920×450` **Discord Modern Dark** profile card displaying server rank, level, XP progress bar, coin balance, messages sent, voice hours, LFG/HoF counters, custom bio, daily contract status, and unlocked badges.
- **Daily Contracts (`/contracts`):** Each member receives 3 personalized daily quests (spanning chat, voice time, LFG squads, Hall of Fame, and Time Capsules). Completing all 3 awards a **Daily Completion Bonus**.
- **Achievement Badges (`/badges`):** Unlock 8 server badges (`💬 Chatterbox`, `🎙️ Voice Regular`, `🎮 Squad Leader`, `⭐ Hall of Famer`, `⏳ Time Traveler`, `🔥 Dedicated`, `💎 High Roller`, `👑 Server Veteran`).

---

## 📋 Command Reference

| Category | Command / Action | Description |
| :--- | :--- | :--- |
| **General** | `/help` | Open the interactive categorized feature guide |
| | `/ping` | Check WebSocket gateway and SQLite database latency |
| **Economy & Profile** | `/profile [member]` | Render a visual Profile Card with interactive Bio & Contract buttons |
| | `/contracts` | View your 3 daily server contracts and completion progress |
| | `/daily` | Claim daily Coins & XP (with consecutive day streak bonuses) |
| | `/pay <member> <amount>` | Transfer Coins from your balance to another member |
| | `/leaderboard [category]` | View top 10 server members by **XP/Level** or **Coins** |
| | `/badges [member]` | Inspect unlocked and locked achievement badges |
| **LFG Squads** | `/lfg create <game> [slots] [note] [auto_voice]` | Create an interactive squad recruitment lobby card |
| **Time Capsules** | `/capsule seal <title> <unlock_in> <message> ...` | Seal a message or image until a future timestamp |
| | `/capsule list [include_opened]` | List active and upcoming Time Capsules on the server |
| | `/capsule inspect <capsule_id>` | View metadata (or unsealed contents) of a capsule |
| **Hall of Fame** | `Apps -> Save to Hall of Fame` | *(Right-click message)* Induct a message into the Hall of Fame |
| | `/halloffame quote <member> <text>` | Render a Quote Card and induct it into the Hall of Fame |
| | `/halloffame random` | Pull and render a random quote from the server's Hall of Fame |
| | `/halloffame top` | View the most-starred Hall of Fame quotes |
| | `/halloffame setup <channel> [star_threshold]` | *(Manage Server)* Configure the Hall of Fame channel & ⭐ threshold |
| **TempVoice** | `/tempvoice setup [category]` | *(Manage Channels)* Create the `➕ Join to Create` voice channel |
| | `/tempvoice panel` | Re-post the room control panel inside your active TempVoice room |

---

## 🗂️ Project Architecture

```text
Silexa_Bot/
├── cogs/
│   ├── __init__.py
│   ├── general.py        # /ping & interactive /help dropdown view
│   ├── economy.py        # Economy, XP listener, Daily Contracts, Badges & /profile
│   ├── lfg.py            # /lfg create & interactive LFGLobbyView with auto-voice
│   ├── capsule.py        # /capsule commands & background unsealer task loop
│   ├── quotes.py         # Context Menu, ⭐ reaction listener & /halloffame commands
│   └── tempvoice.py      # Join-to-Create listener, Room Control Panel & Voice XP loop
├── utils/
│   ├── __init__.py
│   ├── database.py       # Async SQLite layer (aiosqlite), schema & contract/badge logic
│   └── cards.py          # Pillow graphics engine for Profile Cards & Quote Cards
├── .env.example          # Environment configuration template
├── .gitignore            # Git exclusions (.env, data/, .venv/, __pycache__/)
├── LICENSE               # MIT License
├── README.md             # Project documentation
├── bot.py                # Application entry point & SilexaBot class
├── config.py             # Environment loader, color palette & economy tuning constants
└── requirements.txt      # Python package dependencies
```

---

## 🚀 Installation & Setup

### Prerequisites
- **Python 3.11+**
- A Discord Bot Application created in the [Discord Developer Portal](https://discord.com/developers/applications)

### 1. Clone the Repository
```bash
git clone https://github.com/Skerpsh/Silexa_Bot.git
cd Silexa_Bot
```

### 2. Create a Virtual Environment & Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy the template and add your bot token:
```bash
cp .env.example .env
```

Edit `.env`:
```env
DISCORD_TOKEN=your_discord_bot_token_here
# Optional: Add your Discord Server ID for instant (1-second) slash command syncing during development
DISCORD_GUILD_ID=
```

### 4. Configure Discord Developer Portal
1. Go to **Bot** → **Privileged Gateway Intents** and enable:
   - ✅ `SERVER MEMBERS INTENT`
   - ✅ `MESSAGE CONTENT INTENT`
   *(Note: Silexa Bot automatically detects your enabled application flags at startup and will still connect gracefully even if these intents are not toggled yet).*
2. Invite the bot to your server using the **OAuth2 URL Generator** with scopes `bot` and `applications.commands`, and permissions:
   - `Manage Channels`, `Move Members`, `View Channels`, `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`, `Add Reactions`, `Connect`.

### 5. Run the Bot
```bash
.venv/bin/python bot.py
```
Upon startup, the bot automatically initializes `data/silexa.db`, loads all Cogs, syncs Slash & Context Menu commands, and prints its ready-to-use OAuth2 Invite URL to the console.

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](file:///home/silex/Silexa_Bot/LICENSE) for more information.
