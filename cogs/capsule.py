import logging
import re
import time
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from bot import SilexaBot

logger = logging.getLogger("silexa_bot.capsule")

DURATION_PRESETS = [
    ("1 Minute (Quick Test)", "1m"),
    ("10 Minutes", "10m"),
    ("1 Hour", "1h"),
    ("24 Hours (1 Day)", "24h"),
    ("7 Days (1 Week)", "7d"),
    ("30 Days (1 Month)", "30d"),
    ("90 Days (3 Months)", "90d"),
    ("180 Days (6 Months)", "180d"),
    ("365 Days (1 Year)", "365d"),
]

DURATION_PATTERN = re.compile(r"(\d+)\s*([smhdwy])", re.IGNORECASE)
UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "y": 31536000,
}


def parse_duration(raw: str) -> int | None:
    """Parse a duration string like '7d', '2d 12h', '30m' into total seconds."""
    matches = DURATION_PATTERN.findall(raw.strip())
    if not matches:
        return None
    total = 0
    for amount_str, unit in matches:
        total += int(amount_str) * UNIT_SECONDS[unit.lower()]
    if total < 60 or total > 5 * 31536000:
        return None
    return total


class TimeCapsule(commands.Cog):
    """Seal messages and memories in Time Capsules that unlock automatically in the future."""

    def __init__(self, bot: SilexaBot) -> None:
        self.bot = bot
        self.check_capsules_loop.start()

    def cog_unload(self) -> None:
        self.check_capsules_loop.cancel()

    capsule_group = app_commands.Group(
        name="capsule",
        description="Create and inspect server Time Capsules.",
    )

    async def duration_autocomplete(
        self, _: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=label, value=val)
            for label, val in DURATION_PRESETS
            if current.lower() in label.lower() or current.lower() in val.lower()
        ]

    @capsule_group.command(
        name="seal",
        description="Seal a secret message or image inside a Time Capsule until a future date.",
    )
    @app_commands.describe(
        title="Title or label for your Time Capsule (e.g., '2027 Server Predictions')",
        unlock_in="How long until the capsule opens (e.g., 10m, 24h, 7d, 30d, 365d)",
        message="The secret message or prediction to lock inside",
        attachment="Optional image or screenshot to seal inside the capsule",
        public_teaser="Post a locked countdown card in this channel (contents stay hidden!)",
    )
    @app_commands.autocomplete(unlock_in=duration_autocomplete)
    async def capsule_seal(
        self,
        interaction: discord.Interaction,
        title: app_commands.Range[str, 2, 80],
        unlock_in: str,
        message: app_commands.Range[str, 1, 1500],
        attachment: discord.Attachment | None = None,
        public_teaser: bool = True,
    ) -> None:
        if not interaction.guild_id or not interaction.channel_id:
            await interaction.response.send_message(
                "This command can only be used inside a server channel.", ephemeral=True
            )
            return

        duration_sec = parse_duration(unlock_in)
        if duration_sec is None:
            await interaction.response.send_message(
                "❌ Invalid duration! Use formats like `5m`, `1h`, `24h`, `7d`, `30d`, or `365d` (minimum 1 minute).",
                ephemeral=True,
            )
            return

        now = int(time.time())
        open_at = now + duration_sec
        attachment_url = attachment.url if attachment else None

        capsule_id = await self.bot.db.create_capsule(
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            author_id=interaction.user.id,
            title=title.strip(),
            content=message.strip(),
            open_at=open_at,
            attachment_url=attachment_url,
        )

        # Reward & progress daily contract
        await self.bot.db.add_rewards(
            interaction.guild_id,
            interaction.user.id,
            xp=50,
            coins=35,
            capsules_inc=1,
        )
        await self.bot.db.progress_contract(
            interaction.guild_id, interaction.user.id, "time_capsule", 1
        )

        await interaction.response.send_message(
            f"🔒 **Time Capsule #{capsule_id} Sealed!**\n"
            f"Your message is encrypted in the vault and will automatically unseal <t:{open_at}:R> (<t:{open_at}:F>).",
            ephemeral=True,
        )

        if public_teaser and isinstance(interaction.channel, discord.abc.Messageable):
            teaser_embed = discord.Embed(
                title=f"⏳ Time Capsule #{capsule_id} — {title.strip()}",
                description=(
                    f"🔒 **Contents Locked & Encrypted**\n"
                    f"Sealed by {interaction.user.mention} on <t:{now}:d>.\n\n"
                    f"🔓 **Unlocks:** <t:{open_at}:R> (<t:{open_at}:F>)"
                ),
                color=config.COLOR_GOLD,
            )
            if attachment_url:
                teaser_embed.add_field(
                    name="📎 Sealed Media",
                    value="Contains 1 hidden attachment (revealed upon unlock)",
                    inline=False,
                )
            teaser_embed.set_footer(text=f"Capsule ID: #{capsule_id} • Use /capsule seal to create your own!")
            try:
                msg = await interaction.channel.send(embed=teaser_embed)
                await self.bot.db.set_capsule_teaser_message(capsule_id, msg.id)
            except discord.HTTPException:
                pass

    @capsule_group.command(
        name="list",
        description="List active and upcoming Time Capsules on this server.",
    )
    @app_commands.describe(include_opened="Also show already unsealed capsules")
    async def capsule_list(
        self,
        interaction: discord.Interaction,
        include_opened: bool = False,
    ) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        rows = await self.bot.db.get_guild_capsules(
            interaction.guild_id, include_opened=include_opened, limit=12
        )
        if not rows:
            await interaction.response.send_message(
                "📭 No Time Capsules found! Seal the first one with `/capsule seal`.",
                ephemeral=True,
            )
            return

        lines: list[str] = []
        for r in rows:
            status = "🔓 *Opened*" if r["is_opened"] else f"🔒 Unlocks <t:{r['open_at']}:R>"
            lines.append(
                f"**#{r['id']} — {r['title']}**\n"
                f"└ By <@{r['author_id']}> in <#{r['channel_id']}> • {status}"
            )

        embed = discord.Embed(
            title="⏳ Server Time Capsules",
            description="\n\n".join(lines),
            color=config.COLOR_GOLD,
        )
        embed.set_footer(text="Use /capsule inspect <id> to check a specific capsule")
        await interaction.response.send_message(embed=embed)

    @capsule_group.command(
        name="inspect",
        description="Inspect a Time Capsule by its ID (reveals contents only if unlocked).",
    )
    @app_commands.describe(capsule_id="The numeric ID of the Time Capsule")
    async def capsule_inspect(
        self,
        interaction: discord.Interaction,
        capsule_id: int,
    ) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        row = await self.bot.db.get_capsule_by_id(interaction.guild_id, capsule_id)
        if not row:
            await interaction.response.send_message(
                f"❌ Time Capsule `#{capsule_id}` was not found on this server.",
                ephemeral=True,
            )
            return

        if not row["is_opened"]:
            embed = discord.Embed(
                title=f"🔒 Time Capsule #{row['id']} — {row['title']}",
                description=(
                    f"**Status:** Sealed in the Vault\n"
                    f"**Author:** <@{row['author_id']}>\n"
                    f"**Sealed On:** <t:{row['created_at']}:F>\n"
                    f"**Unlocks:** <t:{row['open_at']}:F> (<t:{row['open_at']}:R>)\n\n"
                    "*The contents of this capsule cannot be read until the timer expires!*"
                ),
                color=config.COLOR_GOLD,
            )
            await interaction.response.send_message(embed=embed)
            return

        embed = self._build_unsealed_embed(row)
        await interaction.response.send_message(embed=embed)

    def _build_unsealed_embed(self, row: dict) -> discord.Embed:
        embed = discord.Embed(
            title=f"🔓 Time Capsule #{row['id']} Unsealed — {row['title']}",
            description=f">>> {row['content']}",
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(name="Sealed By", value=f"<@{row['author_id']}>", inline=True)
        embed.add_field(name="Originally Sealed", value=f"<t:{row['created_at']}:D>", inline=True)
        embed.add_field(name="Unsealed On", value=f"<t:{row['open_at']}:D>", inline=True)
        if row.get("attachment_url"):
            embed.set_image(url=row["attachment_url"])
        embed.set_footer(text=f"Time Capsule #{row['id']} • A message from the past")
        return embed

    @tasks.loop(seconds=20)
    async def check_capsules_loop(self) -> None:
        try:
            due = await self.bot.db.get_due_capsules()
        except Exception:
            return

        for row in due:
            await self.bot.db.mark_capsule_opened(row["id"])
            guild = self.bot.get_guild(row["guild_id"])
            if not guild:
                continue
            channel = guild.get_channel(row["channel_id"])
            if not isinstance(channel, discord.abc.Messageable):
                continue

            embed = self._build_unsealed_embed(row)
            try:
                await channel.send(
                    content=f"🎉 **A Time Capsule from the past has unlocked!** <@{row['author_id']}>",
                    embed=embed,
                )
            except discord.HTTPException as exc:
                logger.warning("Could not deliver unsealed capsule #%s: %s", row["id"], exc)

    @check_capsules_loop.before_loop
    async def before_check_capsules(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: SilexaBot) -> None:
    await bot.add_cog(TimeCapsule(bot))
