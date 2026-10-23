from datetime import datetime, timezone
import time
import discord
from discord import app_commands
from discord.ext import commands

import config
from bot import SilexaBot
from utils.cards import render_quote_card


class Quotes(commands.Cog):
    """Hall of Fame & Visual Quote Board (Context Menu, Star Reactions, and Slash Commands)."""

    def __init__(self, bot: SilexaBot) -> None:
        self.bot = bot
        self.save_quote_ctx_menu = app_commands.ContextMenu(
            name="Save to Hall of Fame",
            callback=self.context_save_quote,
        )
        self.bot.tree.add_command(self.save_quote_ctx_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(
            self.save_quote_ctx_menu.name, type=self.save_quote_ctx_menu.type
        )

    hof_group = app_commands.Group(
        name="halloffame",
        description="Configure and browse the server's Hall of Fame Quote Board.",
    )

    async def _induct_message(
        self,
        guild: discord.Guild,
        message: discord.Message,
        nominated_by_id: int,
        stars_count: int = 1,
    ) -> tuple[discord.File, discord.Embed, discord.abc.Messageable]:
        """Render the quote card, store in DB, reward users, and return (file, embed, target_channel)."""
        author = message.author
        quote_text = message.clean_content.strip()
        if not quote_text and message.attachments:
            quote_text = f"[Media Attachment: {message.attachments[0].filename}]"
        if not quote_text:
            quote_text = "[Embedded Message]"

        try:
            avatar_bytes = await author.display_avatar.with_format("png").with_size(256).read()
        except Exception:
            avatar_bytes = None

        channel_name = getattr(message.channel, "name", "chat")
        card_buf = await render_quote_card(
            quote_text=quote_text,
            author_display_name=author.display_name,
            author_username=author.name,
            author_avatar_bytes=avatar_bytes,
            channel_name=channel_name,
            stars_count=stars_count,
            timestamp=message.created_at,
        )
        file = discord.File(card_buf, filename="hall_of_fame_quote.png")

        embed = discord.Embed(
            description=(
                f"⭐ **Inducted into the Hall of Fame!**\n"
                f"🎙️ **Author:** {author.mention}  •  📍 **Channel:** <#{message.channel.id}>  •  "
                f"🔗 [Jump to Original Message]({message.jump_url})"
            ),
            color=config.COLOR_GOLD,
        )
        embed.set_image(url="attachment://hall_of_fame_quote.png")

        settings = await self.bot.db.get_guild_settings(guild.id)
        target_channel: discord.abc.Messageable = message.channel
        if settings.get("hof_channel_id"):
            ch = guild.get_channel(settings["hof_channel_id"])
            if isinstance(ch, discord.abc.Messageable):
                target_channel = ch

        # Rewards & Contract Progress
        if not author.bot:
            await self.bot.db.add_rewards(
                guild.id, author.id, xp=50, coins=35, hof_inc=1
            )
            await self.bot.db.progress_contract(guild.id, author.id, "hall_of_fame", 1)

        if nominated_by_id != author.id:
            await self.bot.db.add_rewards(guild.id, nominated_by_id, xp=25, coins=15)
        await self.bot.db.progress_contract(guild.id, nominated_by_id, "hall_of_fame", 1)

        return file, embed, target_channel

    async def context_save_quote(
        self, interaction: discord.Interaction, message: discord.Message
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This action can only be used inside a server.", ephemeral=True
            )
            return

        if message.author.bot:
            await interaction.response.send_message(
                "❌ Bot messages cannot be inducted into the Hall of Fame!",
                ephemeral=True,
            )
            return

        existing = await self.bot.db.get_hof_entry(message.id)
        if existing:
            await interaction.response.send_message(
                "⭐ This message is already immortalized in the **Hall of Fame**!",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        stars_count = 1
        for r in message.reactions:
            if str(r.emoji) == "⭐":
                stars_count = max(1, r.count)

        file, embed, target_channel = await self._induct_message(
            guild=interaction.guild,
            message=message,
            nominated_by_id=interaction.user.id,
            stars_count=stars_count,
        )

        hof_msg_id: int | None = None
        if target_channel != interaction.channel:
            try:
                sent = await target_channel.send(embed=embed, file=file)
                hof_msg_id = sent.id
                await interaction.followup.send(
                    f"⭐ Saved {message.author.mention}'s quote to the Hall of Fame in {sent.jump_url}!"
                )
            except discord.HTTPException:
                sent = await interaction.followup.send(embed=embed, file=file, wait=True)
                hof_msg_id = sent.id
        else:
            sent = await interaction.followup.send(embed=embed, file=file, wait=True)
            hof_msg_id = sent.id

        await self.bot.db.add_hof_entry(
            message_id=message.id,
            guild_id=interaction.guild.id,
            channel_id=message.channel.id,
            author_id=message.author.id,
            nominated_by_id=interaction.user.id,
            quote_text=message.clean_content.strip() or "[Media Moment]",
            stars_count=stars_count,
            hof_message_id=hof_msg_id,
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if not payload.guild_id or payload.user_id == (self.bot.user.id if self.bot.user else 0):
            return

        settings = await self.bot.db.get_guild_settings(payload.guild_id)
        hof_emoji = settings.get("hof_emoji", "⭐")
        if str(payload.emoji) != hof_emoji:
            return

        existing = await self.bot.db.get_hof_entry(payload.message_id)
        if existing:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        channel = guild.get_channel(payload.channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            return

        if message.author.bot:
            return

        star_count = 0
        for r in message.reactions:
            if str(r.emoji) == hof_emoji:
                star_count = r.count
                break

        threshold = settings.get("hof_threshold", 3)
        if star_count < threshold:
            return

        file, embed, target_channel = await self._induct_message(
            guild=guild,
            message=message,
            nominated_by_id=payload.user_id,
            stars_count=star_count,
        )

        hof_msg_id: int | None = None
        try:
            sent = await target_channel.send(embed=embed, file=file)
            hof_msg_id = sent.id
        except discord.HTTPException:
            pass

        await self.bot.db.add_hof_entry(
            message_id=message.id,
            guild_id=guild.id,
            channel_id=message.channel.id,
            author_id=message.author.id,
            nominated_by_id=payload.user_id,
            quote_text=message.clean_content.strip() or "[Media Moment]",
            stars_count=star_count,
            hof_message_id=hof_msg_id,
        )

    @hof_group.command(
        name="setup",
        description="Configure the server's Hall of Fame channel and ⭐ reaction threshold.",
    )
    @app_commands.describe(
        channel="Channel where Hall of Fame quote cards will be posted",
        star_threshold="Number of ⭐ reactions required to auto-induct a message (default: 3)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def hof_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        star_threshold: app_commands.Range[int, 1, 25] = 3,
    ) -> None:
        if not interaction.guild_id:
            return

        await self.bot.db.update_guild_settings(
            interaction.guild_id,
            hof_channel_id=channel.id,
            hof_threshold=star_threshold,
        )

        embed = discord.Embed(
            title="⭐ Hall of Fame Configured!",
            description=(
                f"**Quote Board Channel:** {channel.mention}\n"
                f"**Auto-Induction Threshold:** `{star_threshold}` ⭐ reactions\n"
                f"**Manual Induction:** Right-click any message → **Apps** → **Save to Hall of Fame**"
            ),
            color=config.COLOR_GOLD,
        )
        await interaction.response.send_message(embed=embed)

    @hof_group.command(
        name="quote",
        description="Render a custom Quote Card for a member and add it to the Hall of Fame.",
    )
    @app_commands.describe(
        member="The member who said the iconic quote",
        text="The quote text to render onto the card",
    )
    async def hof_quote(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        text: app_commands.Range[str, 2, 360],
    ) -> None:
        if not interaction.guild_id or not interaction.guild or not interaction.channel_id:
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        if member.bot:
            await interaction.response.send_message(
                "❌ Cannot create a Hall of Fame quote for a bot!", ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            avatar_bytes = await member.display_avatar.with_format("png").with_size(256).read()
        except Exception:
            avatar_bytes = None

        channel_name = getattr(interaction.channel, "name", "chat")
        card_buf = await render_quote_card(
            quote_text=text.strip(),
            author_display_name=member.display_name,
            author_username=member.name,
            author_avatar_bytes=avatar_bytes,
            channel_name=channel_name,
            stars_count=1,
            timestamp=datetime.now(timezone.utc),
        )

        synthetic_id = int(time.time() * 1000) + interaction.user.id % 1000
        await self.bot.db.add_hof_entry(
            message_id=synthetic_id,
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            author_id=member.id,
            nominated_by_id=interaction.user.id,
            quote_text=text.strip(),
            stars_count=1,
        )

        await self.bot.db.add_rewards(
            interaction.guild_id, member.id, xp=50, coins=35, hof_inc=1
        )
        await self.bot.db.progress_contract(interaction.guild_id, member.id, "hall_of_fame", 1)
        await self.bot.db.progress_contract(interaction.guild_id, interaction.user.id, "hall_of_fame", 1)

        file = discord.File(card_buf, filename="hall_of_fame_quote.png")
        embed = discord.Embed(
            description=(
                f"⭐ **New Quote Immortalized!**\n"
                f"🎙️ **Quoted:** {member.mention}  •  ✨ **Saved by:** {interaction.user.mention}"
            ),
            color=config.COLOR_GOLD,
        )
        embed.set_image(url="attachment://hall_of_fame_quote.png")
        await interaction.followup.send(embed=embed, file=file)

    @hof_group.command(
        name="random",
        description="Pull a random legendary quote from the server's Hall of Fame.",
    )
    async def hof_random(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id or not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        row = await self.bot.db.get_random_hof_entry(interaction.guild_id)
        if not row:
            await interaction.response.send_message(
                "📭 The Hall of Fame is currently empty! Right-click a message → **Apps** → **Save to Hall of Fame** or use `/halloffame quote`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        member = interaction.guild.get_member(row["author_id"])
        display_name = member.display_name if member else f"User {row['author_id']}"
        username = member.name if member else str(row["author_id"])
        avatar_bytes = None
        if member:
            try:
                avatar_bytes = await member.display_avatar.with_format("png").with_size(256).read()
            except Exception:
                avatar_bytes = None

        ch = interaction.guild.get_channel(row["channel_id"])
        ch_name = getattr(ch, "name", "server-chat")

        card_buf = await render_quote_card(
            quote_text=row["quote_text"],
            author_display_name=display_name,
            author_username=username,
            author_avatar_bytes=avatar_bytes,
            channel_name=ch_name,
            stars_count=row["stars_count"],
            timestamp=datetime.fromtimestamp(row["created_at"], tz=timezone.utc),
        )

        file = discord.File(card_buf, filename="random_quote.png")
        embed = discord.Embed(
            title="🎲 Random Hall of Fame Moment",
            description=f"🎙️ **Author:** <@{row['author_id']}>  •  ⭐ **Stars:** `{row['stars_count']}`",
            color=config.COLOR_GOLD,
        )
        embed.set_image(url="attachment://random_quote.png")
        await interaction.followup.send(embed=embed, file=file)

    @hof_group.command(
        name="top",
        description="View the top quotes inducted into the server's Hall of Fame.",
    )
    async def hof_top(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        rows = await self.bot.db.get_top_hof_entries(interaction.guild_id, limit=10)
        if not rows:
            await interaction.response.send_message(
                "📭 No quotes in the Hall of Fame yet!", ephemeral=True
            )
            return

        lines: list[str] = []
        for idx, r in enumerate(rows, start=1):
            snippet = r["quote_text"]
            if len(snippet) > 90:
                snippet = snippet[:87] + "..."
            lines.append(
                f"**#{idx}** ⭐ `{r['stars_count']}` — *\"{snippet}\"*\n"
                f"└ — <@{r['author_id']}> (<t:{r['created_at']}:d>)"
            )

        embed = discord.Embed(
            title="⭐ Hall of Fame — Top Server Quotes",
            description="\n\n".join(lines),
            color=config.COLOR_GOLD,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: SilexaBot) -> None:
    await bot.add_cog(Quotes(bot))
