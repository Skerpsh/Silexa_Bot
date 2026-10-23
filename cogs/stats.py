from datetime import datetime, timezone
import logging
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from bot import SilexaBot
from utils.cards import render_weekly_wrapped_card, _format_voice_time

logger = logging.getLogger("silexa_bot.stats")


class ServerStats(commands.Cog):
    """Server Analytics and Automatic 'Weekly Wrapped' Infographic Digest."""

    def __init__(self, bot: SilexaBot) -> None:
        self.bot = bot
        self.weekly_digest_loop.start()

    def cog_unload(self) -> None:
        self.weekly_digest_loop.cancel()

    wrapped_group = app_commands.Group(
        name="wrapped",
        description="Generate the Server Weekly Wrapped infographic card and configure Sunday digests.",
    )

    async def _resolve_member_name(self, guild: discord.Guild, user_id: int) -> str:
        member = guild.get_member(user_id)
        if member:
            return member.display_name
        try:
            user = await self.bot.fetch_user(user_id)
            return user.display_name
        except discord.HTTPException:
            return f"User {user_id}"

    async def _generate_wrapped_bundle(
        self, guild: discord.Guild
    ) -> tuple[discord.File, discord.Embed, dict]:
        data = await self.bot.db.get_weekly_wrapped_data(guild.id)

        if data["top_chatter"]:
            tc = data["top_chatter"]
            chatter_name = await self._resolve_member_name(guild, tc["user_id"])
            chatter_stats = f"{tc['weekly_messages']:,} Messages ({tc['weekly_xp']:,} XP)"
        else:
            chatter_name = "No Chatter Yet"
            chatter_stats = "0 Messages"

        if data["top_voice"]:
            tv = data["top_voice"]
            voice_name = await self._resolve_member_name(guild, tv["user_id"])
            voice_stats = f"{_format_voice_time(tv['weekly_voice_minutes'])} in Voice"
        else:
            voice_name = "No Voice Activity"
            voice_stats = "0m in Voice"

        if data["top_lfg"]:
            tl = data["top_lfg"]
            lfg_name = await self._resolve_member_name(guild, tl["user_id"])
            lfg_stats = f"{tl['weekly_lfg_count']} LFG Squad(s) Joined"
        else:
            lfg_name = "No Squads Yet"
            lfg_stats = "Run /lfg create!"

        if data["top_game"]:
            tg = data["top_game"]
            top_game_name = tg["game"]
            top_game_stats = f"{tg['cnt']} LFG Lobby(s) Hosted"
        else:
            top_game_name = "No LFG Games Yet"
            top_game_stats = "0 LFG Lobbies"

        if data["top_quote"]:
            tq = data["top_quote"]
            quote_snippet = tq["quote_text"]
            quote_author = await self._resolve_member_name(guild, tq["author_id"])
        else:
            quote_snippet = "Right-click any iconic message -> Apps -> Save to Hall of Fame!"
            quote_author = ""

        totals = data.get("totals", {})
        buf = await render_weekly_wrapped_card(
            guild_name=guild.name,
            chatter_name=chatter_name,
            chatter_stats=chatter_stats,
            voice_name=voice_name,
            voice_stats=voice_stats,
            lfg_name=lfg_name,
            lfg_stats=lfg_stats,
            top_game_name=top_game_name,
            top_game_stats=top_game_stats,
            quote_snippet=quote_snippet,
            quote_author=quote_author,
            total_messages=totals.get("total_messages", 0),
            total_voice_minutes=totals.get("total_voice", 0),
            total_lfg=totals.get("total_lfg", 0),
            active_members=totals.get("active_members", 0),
        )
        file = discord.File(buf, filename="weekly_wrapped.png")

        mvp_mentions: list[str] = []
        if data["top_chatter"]:
            mvp_mentions.append(f"💬 **Top Chatter:** <@{data['top_chatter']['user_id']}>")
        if data["top_voice"]:
            mvp_mentions.append(f"🎙️ **Voice Champion:** <@{data['top_voice']['user_id']}>")
        if data["top_lfg"]:
            mvp_mentions.append(f"🎮 **Squad Leader:** <@{data['top_lfg']['user_id']}>")

        embed = discord.Embed(
            title=f"📊 {guild.name} — Weekly Wrapped",
            description=(
                "Here is the live breakdown of this week's community MVPs, voice hours, "
                "most-played squad games, and Hall of Fame highlights!\n\n"
                + ("\n".join(mvp_mentions) if mvp_mentions else "*Start chatting or join voice to claim a spot!*")
            ),
            color=config.COLOR_BLURPLE,
        )
        embed.set_image(url="attachment://weekly_wrapped.png")
        return file, embed, data

    @wrapped_group.command(
        name="view",
        description="Render the Server Weekly Wrapped infographic card with top chatters, voice & games.",
    )
    async def wrapped_view(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        await interaction.response.defer()
        file, embed, _ = await self._generate_wrapped_bundle(interaction.guild)
        await interaction.followup.send(embed=embed, file=file)

    @wrapped_group.command(
        name="setup",
        description="Configure the channel for automatic Sunday Weekly Wrapped summaries.",
    )
    @app_commands.describe(channel="Text channel where the Sunday Weekly Wrapped digest will be posted")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def wrapped_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        if not interaction.guild_id:
            return

        await self.bot.db.update_guild_settings(
            interaction.guild_id,
            wrapped_channel_id=channel.id,
        )

        embed = discord.Embed(
            title="📊 Weekly Wrapped Auto-Digest Configured!",
            description=(
                f"**Broadcast Channel:** {channel.mention}\n"
                f"**Schedule:** Every Sunday (UTC)\n\n"
                "Each Sunday, Silexa Bot will post the **Server Weekly Wrapped** infographic, "
                "reward the weekly MVPs with **+150 Coins & +100 XP**, and start a fresh weekly race!"
            ),
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)

    @tasks.loop(minutes=30)
    async def weekly_digest_loop(self) -> None:
        now = datetime.now(timezone.utc)
        # Trigger on Sundays (weekday == 6) at or after 18:00 UTC
        if now.weekday() != 6 or now.hour < 18:
            return

        iso_year, iso_week, _ = now.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"

        for guild in self.bot.guilds:
            try:
                settings = await self.bot.db.get_guild_settings(guild.id)
                ch_id = settings.get("wrapped_channel_id")
                if not ch_id or settings.get("last_wrapped_week") == week_key:
                    continue

                channel = guild.get_channel(ch_id)
                if not isinstance(channel, discord.abc.Messageable):
                    continue

                file, embed, data = await self._generate_wrapped_bundle(guild)

                # Reward weekly MVPs before resetting
                mvp_ids = set()
                for key in ("top_chatter", "top_voice", "top_lfg"):
                    if data.get(key):
                        mvp_ids.add(data[key]["user_id"])

                for uid in mvp_ids:
                    await self.bot.db.add_rewards(guild.id, uid, xp=100, coins=150)

                await channel.send(
                    content="🎉 **Happy Sunday! Here is this week's Server Weekly Wrapped!**",
                    embed=embed,
                    file=file,
                )
                await self.bot.db.reset_weekly_stats(guild.id)
                await self.bot.db.update_guild_settings(guild.id, last_wrapped_week=week_key)
            except Exception:
                logger.exception("Error posting Weekly Wrapped for guild %s", guild.id)

    @weekly_digest_loop.before_loop
    async def before_weekly_digest_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: SilexaBot) -> None:
    await bot.add_cog(ServerStats(bot))
