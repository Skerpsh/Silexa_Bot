from datetime import datetime, timedelta, timezone
import random
import time
from typing import Literal
import discord
from discord import app_commands
from discord.ext import commands

import config
from bot import SilexaBot
from utils.cards import render_profile_card
from utils.database import get_level_info, get_user_badges

ALL_BADGE_DEFINITIONS = [
    ("💬", "Chatterbox", "Send 50+ messages in text channels"),
    ("🎙️", "Voice Regular", "Spend 30+ minutes in Voice / TempVoice rooms"),
    ("🎮", "Squad Leader", "Host or join 3+ LFG Squad lobbies"),
    ("⭐", "Hall of Famer", "Get featured in the Hall of Fame"),
    ("⏳", "Time Traveler", "Seal at least 1 Time Capsule"),
    ("🔥", "Dedicated", "Reach a 7-day /daily streak"),
    ("💎", "High Roller", "Accumulate 2,500+ Coins in your balance"),
    ("👑", "Server Veteran", "Reach Level 10 or higher"),
]


def _progress_bar(current: int, target: int, length: int = 10) -> str:
    ratio = min(1.0, max(0.0, current / max(1, target)))
    filled = round(ratio * length)
    return "▰" * filled + "▱" * (length - filled)


def build_contracts_embed(member: discord.abc.User, contracts: list[dict]) -> discord.Embed:
    done_count = sum(1 for c in contracts if c["completed"] == 1)
    all_done = done_count == len(contracts) and len(contracts) > 0

    embed = discord.Embed(
        title=f"📋 Daily Contracts — {member.display_name}",
        description=(
            "Complete your daily contracts across chat, voice, squads, quotes, and time capsules "
            "to earn bonus **Coins** and **XP**!"
        ),
        color=config.COLOR_SUCCESS if all_done else config.COLOR_BLURPLE,
    )

    for idx, c in enumerate(contracts, start=1):
        status_icon = "✅" if c["completed"] else "⏳"
        bar = _progress_bar(c["progress"], c["target"])
        pct = int(min(1.0, c["progress"] / max(1, c["target"])) * 100)
        embed.add_field(
            name=f"{status_icon} Contract #{idx}: {c['title']}",
            value=(
                f"{c['description']}\n"
                f"`{bar}` **{c['progress']}/{c['target']}** ({pct}%)\n"
                f"🎁 **Reward:** `{c['reward_coins']} Coins` + `{c['reward_xp']} XP`"
            ),
            inline=False,
        )

    bonus_status = (
        "✅ **CLAIMED!** You completed all contracts today!"
        if all_done
        else f"🔒 Complete all 3 contracts ({done_count}/3) to unlock!"
    )
    embed.add_field(
        name="🏆 Daily Completion Bonus",
        value=(
            f"{bonus_status}\n"
            f"🎁 **Bonus Reward:** `+{config.ALL_CONTRACTS_BONUS_COINS} Coins` & `+{config.ALL_CONTRACTS_BONUS_XP} XP`"
        ),
        inline=False,
    )

    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    embed.set_footer(text=f"Contracts reset daily at 00:00 UTC (in {int((tomorrow - now).total_seconds() // 3600)}h)")
    return embed


class BioModal(discord.ui.Modal, title="Edit Profile Card Bio"):
    bio_input = discord.ui.TextInput(
        label="Your Profile Headline / Bio",
        placeholder="e.g., Ranked Grinder • Late Night Voice Regular",
        max_length=70,
        required=True,
    )

    def __init__(self, bot: SilexaBot, current_bio: str) -> None:
        super().__init__()
        self.bot = bot
        self.bio_input.default = current_bio[:70]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            return
        new_bio = self.bio_input.value.strip()
        await self.bot.db.set_user_bio(interaction.guild_id, interaction.user.id, new_bio)
        await interaction.response.send_message(
            f"✅ Your profile bio has been updated to: *\"{new_bio}\"*! Run `/profile` to see your refreshed card.",
            ephemeral=True,
        )


class ProfileCardView(discord.ui.View):
    def __init__(self, bot: SilexaBot, guild_id: int, target: discord.Member | discord.User, current_bio: str) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.guild_id = guild_id
        self.target = target
        self.current_bio = current_bio

    @discord.ui.button(label="Daily Contracts", emoji="📋", style=discord.ButtonStyle.primary)
    async def view_contracts(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        contracts = await self.bot.db.get_or_create_daily_contracts(self.guild_id, self.target.id)
        embed = build_contracts_embed(self.target, contracts)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Badges", emoji="🏅", style=discord.ButtonStyle.secondary)
    async def view_badges(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        user_data = await self.bot.db.ensure_user(self.guild_id, self.target.id)
        unlocked_names = {b["name"] for b in get_user_badges(user_data)}
        lines = []
        for icon, name, desc in ALL_BADGE_DEFINITIONS:
            state = "✅ **Unlocked**" if name in unlocked_names else "🔒 *Locked*"
            lines.append(f"{icon} **{name}** — {state}\n└ *{desc}*")
        embed = discord.Embed(
            title=f"🏅 Server Badges — {self.target.display_name}",
            description="\n\n".join(lines),
            color=config.COLOR_GOLD,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Edit Bio", emoji="✏️", style=discord.ButtonStyle.secondary)
    async def edit_bio(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "❌ You can only edit your own profile bio! Run `/profile` for yourself.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(BioModal(self.bot, self.current_bio))


class Economy(commands.Cog):
    """Server Economy, Visual Profiles, Badges, and Daily Contracts."""

    def __init__(self, bot: SilexaBot) -> None:
        self.bot = bot
        self._chat_cooldowns: dict[tuple[int, int], float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        guild_id = message.guild.id
        user_id = message.author.id
        now = time.monotonic()
        key = (guild_id, user_id)

        # Ignore empty system events where there is no content and message_content intent is active
        if self.bot.intents.message_content and len(message.content.strip()) < 2 and not message.attachments:
            return

        last_award = self._chat_cooldowns.get(key, 0.0)
        if now - last_award >= config.CHAT_COOLDOWN_SECONDS:
            self._chat_cooldowns[key] = now
            xp_gain = random.randint(config.CHAT_XP_MIN, config.CHAT_XP_MAX)
            coin_gain = random.randint(config.CHAT_COINS_MIN, config.CHAT_COINS_MAX)
        else:
            xp_gain = 0
            coin_gain = 0

        _, new_level, leveled_up = await self.bot.db.add_rewards(
            guild_id=guild_id,
            user_id=user_id,
            xp=xp_gain,
            coins=coin_gain,
            messages_inc=1,
        )
        completed = await self.bot.db.progress_contract(guild_id, user_id, "messages", 1)

        if leveled_up:
            embed = discord.Embed(
                description=(
                    f"🎉 **Level Up!** {message.author.mention} just reached **Level {new_level}**! "
                    f"Check out your updated card with `/profile`."
                ),
                color=config.COLOR_GOLD,
            )
            try:
                await message.channel.send(embed=embed, delete_after=15)
            except discord.HTTPException:
                pass

        for c in completed:
            try:
                await message.channel.send(
                    embed=discord.Embed(
                        description=(
                            f"✅ **Contract Complete!** {message.author.mention} finished **{c['title']}** "
                            f"and earned **+{c['reward_coins']} Coins** & **+{c['reward_xp']} XP**!"
                        ),
                        color=config.COLOR_SUCCESS,
                    ),
                    delete_after=15,
                )
            except discord.HTTPException:
                pass

    @app_commands.command(
        name="profile",
        description="Render a visual Discord Modern Dark Profile Card with stats, XP, and badges.",
    )
    @app_commands.describe(member="The server member whose profile card you want to view")
    async def profile(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return

        await interaction.response.defer()
        target = member or interaction.user

        user_data = await self.bot.db.ensure_user(interaction.guild_id, target.id)
        rank = await self.bot.db.get_user_rank(interaction.guild_id, target.id)
        contracts = await self.bot.db.get_or_create_daily_contracts(interaction.guild_id, target.id)
        contracts_done = sum(1 for c in contracts if c["completed"] == 1)

        level, xp_curr, xp_need = get_level_info(user_data["xp"])
        badges = get_user_badges(user_data)

        try:
            avatar_bytes = await target.display_avatar.with_format("png").with_size(256).read()
        except Exception:
            avatar_bytes = None

        card_buf = await render_profile_card(
            display_name=target.display_name,
            username=target.name,
            avatar_bytes=avatar_bytes,
            level=level,
            xp_current=xp_curr,
            xp_needed=xp_need,
            rank=rank,
            coins=user_data["coins"],
            messages_sent=user_data["messages_sent"],
            voice_minutes=user_data["voice_minutes"],
            lfg_count=user_data["lfg_count"],
            hof_count=user_data["hof_count"],
            daily_streak=user_data["daily_streak"],
            bio=user_data["bio"],
            badges=badges,
            contracts_done=contracts_done,
            contracts_total=len(contracts),
        )

        file = discord.File(card_buf, filename="profile.png")
        view = ProfileCardView(self.bot, interaction.guild_id, target, user_data["bio"])
        await interaction.followup.send(file=file, view=view)

    @app_commands.command(
        name="contracts",
        description="View your 3 daily server contracts and track your progress.",
    )
    async def contracts(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return

        contracts_list = await self.bot.db.get_or_create_daily_contracts(
            interaction.guild_id, interaction.user.id
        )
        embed = build_contracts_embed(interaction.user, contracts_list)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="daily",
        description="Claim your daily Coins and XP reward (with streak bonuses!).",
    )
    async def daily(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return

        user_data = await self.bot.db.ensure_user(interaction.guild_id, interaction.user.id)
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        if user_data["last_daily_date"] == today_str:
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            unix_ts = int(tomorrow.timestamp())
            await interaction.response.send_message(
                f"⏳ You have already claimed your daily reward today! Come back <t:{unix_ts}:R>.",
                ephemeral=True,
            )
            return

        if user_data["last_daily_date"] == yesterday_str:
            new_streak = user_data["daily_streak"] + 1
        else:
            new_streak = 1

        streak_bonus = min(new_streak - 1, 10) * config.DAILY_STREAK_BONUS
        total_coins = config.DAILY_BASE_COINS + streak_bonus
        total_xp = config.DAILY_BASE_XP

        await self.bot.db.conn.execute(
            """
            UPDATE users
            SET daily_streak = ?, last_daily_date = ?
            WHERE guild_id = ? AND user_id = ?
            """,
            (new_streak, today_str, interaction.guild_id, interaction.user.id),
        )
        await self.bot.db.conn.commit()
        _, new_level, leveled_up = await self.bot.db.add_rewards(
            interaction.guild_id,
            interaction.user.id,
            xp=total_xp,
            coins=total_coins,
        )

        updated = await self.bot.db.ensure_user(interaction.guild_id, interaction.user.id)
        embed = discord.Embed(
            title="🎁 Daily Reward Claimed!",
            description=(
                f"You received **+{total_coins:,} Coins** and **+{total_xp} XP**!\n\n"
                f"🔥 **Current Streak:** `{new_streak} day(s)` (+{streak_bonus} Streak Bonus Coins)\n"
                f"💰 **New Balance:** `{updated['coins']:,} Coins`"
            ),
            color=config.COLOR_GOLD,
        )
        if leveled_up:
            embed.add_field(
                name="🎉 Level Up!",
                value=f"You advanced to **Level {new_level}**!",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="pay",
        description="Transfer Coins from your balance to another server member.",
    )
    @app_commands.describe(
        member="The member who will receive the Coins",
        amount="Amount of Coins to transfer",
    )
    async def pay(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return

        if member.id == interaction.user.id:
            await interaction.response.send_message("❌ You cannot send Coins to yourself!", ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message("❌ Bots don't need Coins!", ephemeral=True)
            return

        ok = await self.bot.db.transfer_coins(
            interaction.guild_id, interaction.user.id, member.id, amount
        )
        if not ok:
            sender = await self.bot.db.ensure_user(interaction.guild_id, interaction.user.id)
            await interaction.response.send_message(
                f"❌ Insufficient funds! You currently have **{sender['coins']:,} Coins**.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="💸 Coin Transfer Complete",
            description=(
                f"{interaction.user.mention} sent **{amount:,} Coins** to {member.mention}!"
            ),
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="leaderboard",
        description="Display the server leaderboard for XP Levels or Coin Wealth.",
    )
    @app_commands.describe(category="Rank members by XP/Levels or Coins")
    async def leaderboard(
        self,
        interaction: discord.Interaction,
        category: Literal["xp", "coins"] = "xp",
    ) -> None:
        if not interaction.guild_id or not interaction.guild:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return

        rows = await self.bot.db.get_leaderboard(interaction.guild_id, sort_by=category, limit=10)
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines: list[str] = []

        for idx, row in enumerate(rows, start=1):
            rank_icon = medals.get(idx, f"`#{idx:02d}`")
            lvl, _, _ = get_level_info(row["xp"])
            if category == "coins":
                lines.append(
                    f"{rank_icon} <@{row['user_id']}> — **{row['coins']:,} Coins** *(Level {lvl})*"
                )
            else:
                lines.append(
                    f"{rank_icon} <@{row['user_id']}> — **Level {lvl}** (`{row['xp']:,} XP` • `{row['coins']:,} Coins`)"
                )

        title = (
            f"🏆 {interaction.guild.name} — XP & Level Leaderboard"
            if category == "xp"
            else f"💎 {interaction.guild.name} — Richest Members"
        )
        embed = discord.Embed(
            title=title,
            description="\n".join(lines) if lines else "No leaderboard entries yet!",
            color=config.COLOR_GOLD if category == "coins" else config.COLOR_BLURPLE,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="badges",
        description="View all unlocked and locked achievement badges for a member.",
    )
    @app_commands.describe(member="Member whose badges you want to inspect")
    async def badges(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return

        target = member or interaction.user
        user_data = await self.bot.db.ensure_user(interaction.guild_id, target.id)
        unlocked_names = {b["name"] for b in get_user_badges(user_data)}

        lines = []
        for icon, name, desc in ALL_BADGE_DEFINITIONS:
            status = "✅ **Unlocked**" if name in unlocked_names else "🔒 *Locked*"
            lines.append(f"{icon} **{name}** — {status}\n└ *{desc}*")

        embed = discord.Embed(
            title=f"🏅 Server Achievements & Badges — {target.display_name}",
            description="\n\n".join(lines),
            color=config.COLOR_GOLD,
        )
        embed.set_footer(text=f"Unlocked {len(unlocked_names)}/{len(ALL_BADGE_DEFINITIONS)} badges")
        await interaction.response.send_message(embed=embed)


async def setup(bot: SilexaBot) -> None:
    await bot.add_cog(Economy(bot))
