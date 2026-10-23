import time
import discord
from discord import app_commands
from discord.ext import commands

import config
from bot import SilexaBot

POPULAR_GAMES = [
    "Valorant",
    "Apex Legends",
    "Counter-Strike 2",
    "Call of Duty: Warzone",
    "Overwatch 2",
    "Marvel Rivals",
    "League of Legends",
    "Fortnite",
    "Helldivers 2",
    "Minecraft",
    "GTA Online",
    "Chill & Voice Hangout",
]


class LFGLobbyView(discord.ui.View):
    def __init__(
        self,
        bot: SilexaBot,
        guild_id: int,
        host: discord.Member,
        game: str,
        max_slots: int,
        note: str,
        auto_voice: bool,
    ) -> None:
        super().__init__(timeout=14400)  # 4 hours active lobby timeout
        self.bot = bot
        self.guild_id = guild_id
        self.host = host
        self.game = game
        self.max_slots = max_slots
        self.note = note
        self.auto_voice = auto_voice

        self.roster: list[int] = [host.id]
        self.standby: list[int] = []
        self.rewarded_users: set[int] = {host.id}
        self.voice_channel_id: int | None = None
        self.is_closed: bool = False
        self.created_at: int = int(time.time())

    def build_embed(self) -> discord.Embed:
        count = len(self.roster)
        is_full = count >= self.max_slots

        if self.is_closed:
            status_badge = "🔴 **Lobby Closed**"
            color = config.COLOR_DARK_EMBED
        elif is_full:
            status_badge = f"🔥 **SQUAD FULL ({count}/{self.max_slots})**"
            color = config.COLOR_SUCCESS
        else:
            spots_left = self.max_slots - count
            status_badge = f"🟢 **Recruiting — Need +{spots_left} ({count}/{self.max_slots})**"
            color = config.COLOR_BLURPLE

        embed = discord.Embed(
            title=f"🎮 LFG Squad — {self.game}",
            description=(
                f"{status_badge}\n"
                f"📝 **Lobby Note:** {self.note}\n"
                f"⏱️ **Created:** <t:{self.created_at}:R>"
            ),
            color=color,
        )

        # Roster Slots Visualization
        slot_lines: list[str] = []
        for idx in range(self.max_slots):
            if idx < len(self.roster):
                uid = self.roster[idx]
                crown = "👑 " if uid == self.host.id else "🔹 "
                slot_lines.append(f"`Slot {idx + 1}:` {crown}<@{uid}>")
            else:
                slot_lines.append(f"`Slot {idx + 1}:` *Open Slot*")

        embed.add_field(
            name=f"👥 Active Squad Roster ({count}/{self.max_slots})",
            value="\n".join(slot_lines),
            inline=False,
        )

        if self.standby:
            standby_mentions = ", ".join(f"<@{uid}>" for uid in self.standby)
            embed.add_field(
                name=f"🕒 Standby / Bench ({len(self.standby)})",
                value=standby_mentions,
                inline=False,
            )

        if self.voice_channel_id:
            embed.add_field(
                name="🔊 Squad Voice Channel",
                value=f"Join Ready Room: <#{self.voice_channel_id}>",
                inline=False,
            )

        embed.set_footer(text=f"Hosted by {self.host.display_name} • Click a button below to join!")
        return embed

    async def _reward_participation(self, user_id: int) -> None:
        if user_id in self.rewarded_users:
            return
        self.rewarded_users.add(user_id)
        await self.bot.db.add_rewards(
            self.guild_id,
            user_id,
            xp=35,
            coins=25,
            lfg_inc=1,
        )
        await self.bot.db.progress_contract(self.guild_id, user_id, "lfg_participate", 1)

    async def _ensure_squad_voice(self, guild: discord.Guild) -> discord.VoiceChannel | None:
        if self.voice_channel_id:
            existing = guild.get_channel(self.voice_channel_id)
            if isinstance(existing, discord.VoiceChannel):
                return existing

        settings = await self.bot.db.get_guild_settings(guild.id)
        category: discord.CategoryChannel | None = None
        cat_id = settings.get("lfg_category_id") or settings.get("jtc_category_id")
        if cat_id:
            ch = guild.get_channel(cat_id)
            if isinstance(ch, discord.CategoryChannel):
                category = ch

        try:
            vc = await guild.create_voice_channel(
                name=f"🎮 {self.game[:20]} Squad",
                category=category,
                user_limit=self.max_slots,
                reason=f"LFG Squad voice room hosted by {self.host.display_name}",
            )
            self.voice_channel_id = vc.id
            await self.bot.db.register_temp_voice(vc.id, guild.id, self.host.id)
            return vc
        except discord.HTTPException:
            return None

    @discord.ui.button(label="Join Squad", emoji="✅", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.is_closed:
            await interaction.response.send_message("This LFG lobby is closed.", ephemeral=True)
            return

        uid = interaction.user.id
        if uid in self.roster:
            await interaction.response.send_message("You are already in the active squad roster!", ephemeral=True)
            return

        if len(self.roster) >= self.max_slots:
            if uid not in self.standby:
                self.standby.append(uid)
                await interaction.response.edit_message(embed=self.build_embed(), view=self)
                await interaction.followup.send(
                    "Squad is currently full — added you to the **Standby / Bench** list! You'll be auto-promoted if a spot opens.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message("The squad is full and you are already on standby.", ephemeral=True)
            return

        if uid in self.standby:
            self.standby.remove(uid)
        self.roster.append(uid)
        await self._reward_participation(uid)

        just_filled = len(self.roster) >= self.max_slots
        vc_mention = ""
        if just_filled and self.auto_voice and interaction.guild:
            vc = await self._ensure_squad_voice(interaction.guild)
            if vc:
                vc_mention = f"\n🔊 **Voice Channel Ready:** {vc.mention}"

        await interaction.response.edit_message(embed=self.build_embed(), view=self)

        if just_filled and interaction.channel:
            pings = " ".join(f"<@{m_id}>" for m_id in self.roster)
            await interaction.followup.send(
                f"🚨 **SQUAD FULL!** Ready up for **{self.game}**: {pings}{vc_mention}"
            )

    @discord.ui.button(label="Standby", emoji="🕒", style=discord.ButtonStyle.secondary)
    async def standby_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.is_closed:
            await interaction.response.send_message("This LFG lobby is closed.", ephemeral=True)
            return

        uid = interaction.user.id
        if uid == self.host.id:
            await interaction.response.send_message(
                "As the lobby host, you cannot move yourself to standby. Use **Close Lobby** if you want to disband.",
                ephemeral=True,
            )
            return

        if uid in self.standby:
            await interaction.response.send_message("You are already on the standby list.", ephemeral=True)
            return

        if uid in self.roster:
            self.roster.remove(uid)
        self.standby.append(uid)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Leave", emoji="✖️", style=discord.ButtonStyle.danger)
    async def leave_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if self.is_closed:
            await interaction.response.send_message("This LFG lobby is closed.", ephemeral=True)
            return

        uid = interaction.user.id
        if uid == self.host.id:
            await interaction.response.send_message(
                "You are the lobby host! Click **Close Lobby** if you want to end recruitment.",
                ephemeral=True,
            )
            return

        promoted_id: int | None = None
        if uid in self.roster:
            self.roster.remove(uid)
            if self.standby and len(self.roster) < self.max_slots:
                promoted_id = self.standby.pop(0)
                self.roster.append(promoted_id)
                await self._reward_participation(promoted_id)
        elif uid in self.standby:
            self.standby.remove(uid)
        else:
            await interaction.response.send_message("You aren't in this lobby.", ephemeral=True)
            return

        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        if promoted_id:
            await interaction.followup.send(
                f"⚡ <@{promoted_id}> has been promoted from Standby to the active **{self.game}** squad!"
            )

    @discord.ui.button(label="Launch Voice", emoji="🔊", style=discord.ButtonStyle.primary)
    async def launch_voice_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.host.id:
            await interaction.response.send_message(
                "Only the lobby host can manually spawn the squad voice channel.",
                ephemeral=True,
            )
            return
        if not interaction.guild:
            return

        vc = await self._ensure_squad_voice(interaction.guild)
        if not vc:
            await interaction.response.send_message(
                "❌ Could not create a voice channel — check my `Manage Channels` permission!",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await interaction.followup.send(f"🔊 Squad voice room created: {vc.mention}!", ephemeral=True)

    @discord.ui.button(label="Close Lobby", emoji="🔒", style=discord.ButtonStyle.secondary)
    async def close_btn(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        is_mod = (
            isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.manage_messages
        )
        if interaction.user.id != self.host.id and not is_mod:
            await interaction.response.send_message(
                "Only the lobby host or a server moderator can close this lobby.",
                ephemeral=True,
            )
            return

        self.is_closed = True
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        self.stop()


class LFG(commands.Cog):
    """Looking For Group (LFG) Squad Builder."""

    def __init__(self, bot: SilexaBot) -> None:
        self.bot = bot

    lfg_group = app_commands.Group(
        name="lfg",
        description="Assemble a gaming squad or voice hangout lobby.",
    )

    async def game_autocomplete(
        self, _: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        matches = [
            g for g in POPULAR_GAMES if current.lower() in g.lower()
        ]
        return [app_commands.Choice(name=g, value=g) for g in matches[:25]]

    @lfg_group.command(
        name="create",
        description="Create an interactive LFG squad card with live slots and auto-voice.",
    )
    @app_commands.describe(
        game="Game or activity name (e.g. Valorant, Apex Legends, Helldivers 2)",
        slots="Total squad size including yourself (2 to 12, default: 5)",
        note="Details: rank, mode, region (NA-East/West), mic requirements",
        auto_voice="Automatically create a temporary voice channel when the squad fills up",
    )
    @app_commands.autocomplete(game=game_autocomplete)
    async def lfg_create(
        self,
        interaction: discord.Interaction,
        game: str,
        slots: app_commands.Range[int, 2, 12] = 5,
        note: str = "Mic preferred • Good vibes only!",
        auto_voice: bool = True,
    ) -> None:
        if not interaction.guild_id or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        # Reward host for launching a squad & progress daily contract
        await self.bot.db.add_rewards(
            interaction.guild_id,
            interaction.user.id,
            xp=40,
            coins=30,
            lfg_inc=1,
        )
        await self.bot.db.progress_contract(
            interaction.guild_id, interaction.user.id, "lfg_participate", 1
        )

        view = LFGLobbyView(
            bot=self.bot,
            guild_id=interaction.guild_id,
            host=interaction.user,
            game=game.strip()[:60],
            max_slots=slots,
            note=note.strip()[:200],
            auto_voice=auto_voice,
        )
        await interaction.response.send_message(embed=view.build_embed(), view=view)


async def setup(bot: SilexaBot) -> None:
    await bot.add_cog(LFG(bot))
