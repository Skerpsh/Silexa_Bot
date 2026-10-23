import time
import discord
from discord import app_commands
from discord.ext import commands

import config
from bot import SilexaBot


class HelpCategorySelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(
                label="Overview & Quick Start",
                value="overview",
                emoji="✨",
                description="Overview of Silexa Bot modules & admin setup",
            ),
            discord.SelectOption(
                label="LFG / Squad Builder",
                value="lfg",
                emoji="🎮",
                description="Recruit teammates, manage rosters & auto-create squad voice",
            ),
            discord.SelectOption(
                label="Time Capsules",
                value="capsule",
                emoji="⏳",
                description="Seal messages and memories to unlock in the future",
            ),
            discord.SelectOption(
                label="Hall of Fame & Quote Board",
                value="quotes",
                emoji="⭐",
                description="Immortalize server moments with rendered Quote Cards",
            ),
            discord.SelectOption(
                label="Join-to-Create TempVoice",
                value="tempvoice",
                emoji="🔊",
                description="Private dynamic voice lounges with interactive controls",
            ),
            discord.SelectOption(
                label="Economy, Contracts & Profiles",
                value="economy",
                emoji="💰",
                description="Visual Profile Cards, XP, Coins, Badges & Daily Contracts",
            ),
        ]
        super().__init__(
            placeholder="Select a module to explore commands...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        choice = self.values[0]
        embed = build_help_embed(choice)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=180)
        self.add_item(HelpCategorySelect())


def build_help_embed(section: str = "overview") -> discord.Embed:
    if section == "lfg":
        embed = discord.Embed(
            title="🎮 LFG / Squad Builder",
            description=(
                "Assemble your squad for any game or activity with live roster tracking "
                "and automatic voice channel creation."
            ),
            color=config.COLOR_BLURPLE,
        )
        embed.add_field(
            name="Commands",
            value=(
                "• `/lfg create <game> [slots] [note] [auto_voice]` — Launch an interactive LFG lobby card\n"
                "• **Interactive Buttons:** Join Squad, Standby/Bench, Leave, Spawn Squad Voice, Close Lobby"
            ),
            inline=False,
        )
        embed.add_field(
            name="Economy Integration",
            value="Hosting or joining a squad grants **XP + Coins** and progresses your **Squad Up** daily contract!",
            inline=False,
        )
        return embed

    if section == "capsule":
        embed = discord.Embed(
            title="⏳ Time Capsules",
            description="Seal messages, predictions, or memories that stay locked until their reveal timestamp.",
            color=config.COLOR_GOLD,
        )
        embed.add_field(
            name="Commands",
            value=(
                "• `/capsule seal <title> <unlock_in> <message> [attachment] [public_teaser]`\n"
                "  *Supported durations:* `5m`, `1h`, `24h`, `7d`, `30d`, `365d` (e.g., `2d 12h`)\n"
                "• `/capsule list` — View all active & upcoming time capsules on this server\n"
                "• `/capsule inspect <id>` — View details of a specific capsule"
            ),
            inline=False,
        )
        return embed

    if section == "quotes":
        embed = discord.Embed(
            title="⭐ Hall of Fame & Quote Board",
            description=(
                "Turn iconic or hilarious chat messages into custom-rendered **Discord Modern Dark Quote Cards**."
            ),
            color=config.COLOR_GOLD,
        )
        embed.add_field(
            name="How to Add Quotes",
            value=(
                "1. **Right-Click Context Menu:** Right-click any message → **Apps** → **Save to Hall of Fame**\n"
                "2. **Star Reactions:** React with ⭐ (default threshold: 3 stars)\n"
                "3. **Slash Command:** `/halloffame quote <member> <text>`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Other Commands",
            value=(
                "• `/halloffame random` — Render a random quote from the server's Hall of Fame\n"
                "• `/halloffame top` — View the most-starred moments\n"
                "• `/halloffame setup <channel> [star_threshold]` — *(Admin)* Set the Hall of Fame channel"
            ),
            inline=False,
        )
        return embed

    if section == "tempvoice":
        embed = discord.Embed(
            title="🔊 Join-to-Create TempVoice",
            description="Dynamic private voice rooms with an in-chat interactive control dashboard.",
            color=config.COLOR_BLURPLE,
        )
        embed.add_field(
            name="Commands & Controls",
            value=(
                "• `/tempvoice setup [category]` — *(Admin)* Create the `➕ Join to Create` trigger channel\n"
                "• `/tempvoice panel` — Re-send the room control panel in your active voice channel\n"
                "• **Room Controls:** 🔒 Lock/Unlock, 👻 Hide/Reveal, ✏️ Rename & Limit (Modal), 👑 Claim Host, ➕ Permit/Kick Member"
            ),
            inline=False,
        )
        return embed

    if section == "economy":
        embed = discord.Embed(
            title="💰 Economy, Daily Contracts & Visual Profiles",
            description="Earn XP, Coins, and Badges across every server activity.",
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(
            name="Commands",
            value=(
                "• `/profile [member]` — Generate a custom HD **Visual Profile Card** + Bio & Contract buttons\n"
                "• `/contracts` — View your 3 daily contracts and claim bonus rewards\n"
                "• `/daily` — Claim your daily Coins & XP reward (with streak multiplier!)\n"
                "• `/pay <member> <amount>` — Send Coins to another member\n"
                "• `/leaderboard [category]` — View the top XP Ranks or Coin Balances\n"
                "• `/badges [member]` — View unlocked and locked achievement badges"
            ),
            inline=False,
        )
        return embed

    embed = discord.Embed(
        title="✨ Silexa Bot — Command Center",
        description=(
            "Welcome to **Silexa Bot**! Use the dropdown menu below to explore each feature module.\n\n"
            "**Core Modules:**\n"
            "🎮 **LFG Squad Builder** — `/lfg create`\n"
            "⏳ **Time Capsules** — `/capsule seal`, `/capsule list`\n"
            "⭐ **Hall of Fame** — `/halloffame`, ⭐ reactions & Right-Click `Save to Hall of Fame`\n"
            "🔊 **TempVoice Rooms** — `/tempvoice setup`, `/tempvoice panel`\n"
            "💰 **Visual Profiles & Contracts** — `/profile`, `/contracts`, `/daily`, `/leaderboard`"
        ),
        color=config.COLOR_BLURPLE,
    )
    embed.set_footer(text="Tip: Right-click any message -> Apps -> Save to Hall of Fame!")
    return embed


class General(commands.Cog):
    """General utility and help slash commands."""

    def __init__(self, bot: SilexaBot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check the bot's WebSocket and database latency.")
    async def ping(self, interaction: discord.Interaction) -> None:
        ws_ms = round(self.bot.latency * 1000)
        t0 = time.perf_counter()
        if interaction.guild_id:
            await self.bot.db.get_guild_settings(interaction.guild_id)
        db_ms = round((time.perf_counter() - t0) * 1000, 1)

        embed = discord.Embed(
            title="🏓 Pong!",
            description=(
                f"**Gateway Latency:** `{ws_ms} ms`\n"
                f"**Database Latency:** `{db_ms} ms`"
            ),
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="Open the interactive guide for all Silexa Bot features.")
    async def help_command(self, interaction: discord.Interaction) -> None:
        embed = build_help_embed("overview")
        await interaction.response.send_message(embed=embed, view=HelpView())


async def setup(bot: SilexaBot) -> None:
    await bot.add_cog(General(bot))
