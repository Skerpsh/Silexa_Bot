import logging
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from bot import SilexaBot

logger = logging.getLogger("silexa_bot.tempvoice")


def build_room_dashboard_embed(
    channel: discord.VoiceChannel,
    owner_id: int,
    is_locked: bool,
    is_hidden: bool,
) -> discord.Embed:
    limit_str = f"{channel.user_limit} Members" if channel.user_limit else "Unlimited"
    lock_str = "🔒 Locked" if is_locked else "🔓 Open"
    vis_str = "👻 Hidden" if is_hidden else "👁️ Visible"

    embed = discord.Embed(
        title=f"🎛️ Voice Lounge Controls — {channel.name}",
        description=(
            "Welcome to your private **TempVoice Lounge**! Use the controls below "
            "to customize access, room capacity, and permissions."
        ),
        color=config.COLOR_BLURPLE,
    )
    embed.add_field(name="👑 Room Host", value=f"<@{owner_id}>", inline=True)
    embed.add_field(name="🛡️ Access", value=f"{lock_str} • {vis_str}", inline=True)
    embed.add_field(name="👥 Capacity", value=limit_str, inline=True)
    embed.set_footer(
        text="Room automatically deletes when everyone leaves • Earn XP & Coins while in Voice!"
    )
    return embed


class RenameLimitModal(discord.ui.Modal, title="Customize Voice Room"):
    room_name = discord.ui.TextInput(
        label="Voice Channel Name",
        placeholder="e.g., Late Night Ranked, Chill Vibes",
        min_length=2,
        max_length=45,
        required=True,
    )
    user_limit = discord.ui.TextInput(
        label="Member Limit (0 = Unlimited, 1-99)",
        placeholder="0",
        min_length=1,
        max_length=2,
        required=True,
    )

    def __init__(
        self,
        bot: SilexaBot,
        channel: discord.VoiceChannel,
        view_ref: "TempVoiceControlView",
    ) -> None:
        super().__init__()
        self.bot = bot
        self.channel = channel
        self.view_ref = view_ref
        self.room_name.default = channel.name
        self.user_limit.default = str(channel.user_limit or 0)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw_limit = self.user_limit.value.strip()
        if not raw_limit.isdigit() or not (0 <= int(raw_limit) <= 99):
            await interaction.response.send_message(
                "❌ Member limit must be a number between `0` (Unlimited) and `99`.",
                ephemeral=True,
            )
            return

        limit_val = int(raw_limit)
        new_name = self.room_name.value.strip()
        try:
            await self.channel.edit(name=new_name, user_limit=limit_val)
        except discord.HTTPException:
            await interaction.response.send_message(
                "⚠️ Discord rate-limits channel renames (max 2 renames per 10 minutes). Please try again shortly!",
                ephemeral=True,
            )
            return

        row = await self.bot.db.get_temp_voice(self.channel.id)
        if row:
            embed = build_room_dashboard_embed(
                self.channel,
                row["owner_id"],
                bool(row["is_locked"]),
                bool(row["is_hidden"]),
            )
            await interaction.response.edit_message(embed=embed, view=self.view_ref)
        else:
            await interaction.response.send_message("✅ Room updated!", ephemeral=True)


class MemberAccessSelect(discord.ui.UserSelect):
    def __init__(self, bot: SilexaBot, channel_id: int) -> None:
        super().__init__(
            placeholder="➕ Permit a friend OR 👢 Disconnect a member...",
            min_values=1,
            max_values=1,
        )
        self.bot = bot
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return
        row = await self.bot.db.get_temp_voice(self.channel_id)
        if not row or interaction.user.id != row["owner_id"]:
            await interaction.response.send_message(
                "❌ Only the room host can manage member access!", ephemeral=True
            )
            return

        channel = interaction.guild.get_channel(self.channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Voice channel no longer exists.", ephemeral=True)
            return

        selected = self.values[0]
        if not isinstance(selected, discord.Member):
            selected = interaction.guild.get_member(selected.id)  # type: ignore[assignment]
        if not isinstance(selected, discord.Member):
            await interaction.response.send_message("Could not find that server member.", ephemeral=True)
            return

        if selected.id == interaction.user.id:
            await interaction.response.send_message("You already own this room!", ephemeral=True)
            return

        # If target is currently inside the room -> disconnect and block
        if selected in channel.members:
            try:
                await selected.move_to(None, reason="Disconnected by TempVoice room host")
                await channel.set_permissions(selected, connect=False)
                await interaction.response.send_message(
                    f"👢 Disconnected {selected.mention} and blocked them from rejoining.",
                    ephemeral=True,
                )
            except discord.HTTPException:
                await interaction.response.send_message(
                    "❌ Failed to disconnect member (check bot permissions).",
                    ephemeral=True,
                )
        else:
            try:
                await channel.set_permissions(selected, connect=True, view_channel=True)
                await interaction.response.send_message(
                    f"✅ Permitted {selected.mention} to view and join your room!",
                    ephemeral=True,
                )
            except discord.HTTPException:
                await interaction.response.send_message(
                    "❌ Failed to update channel permissions.",
                    ephemeral=True,
                )


class TempVoiceControlView(discord.ui.View):
    def __init__(self, bot: SilexaBot, channel_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.channel_id = channel_id
        self.add_item(MemberAccessSelect(bot, channel_id))

    async def _get_context(
        self, interaction: discord.Interaction
    ) -> tuple[discord.VoiceChannel | None, dict | None]:
        if not interaction.guild:
            return None, None
        ch = interaction.guild.get_channel(self.channel_id)
        row = await self.bot.db.get_temp_voice(self.channel_id)
        if not isinstance(ch, discord.VoiceChannel) or not row:
            return None, None
        return ch, row

    @discord.ui.button(label="Lock / Unlock", emoji="🔒", style=discord.ButtonStyle.secondary)
    async def toggle_lock(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel, row = await self._get_context(interaction)
        if not channel or not row or not interaction.guild:
            await interaction.response.send_message("This temporary room is no longer active.", ephemeral=True)
            return

        if interaction.user.id != row["owner_id"]:
            await interaction.response.send_message("❌ Only the room host can lock or unlock this room!", ephemeral=True)
            return

        new_locked = 0 if row["is_locked"] else 1
        everyone = interaction.guild.default_role
        overwrite = channel.overwrites_for(everyone)
        overwrite.connect = False if new_locked else None

        try:
            await channel.set_permissions(everyone, overwrite=overwrite)
            await self.bot.db.update_temp_voice(channel.id, is_locked=new_locked)
        except discord.HTTPException:
            await interaction.response.send_message("❌ Failed to update permissions.", ephemeral=True)
            return

        embed = build_room_dashboard_embed(
            channel, row["owner_id"], bool(new_locked), bool(row["is_hidden"])
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Hide / Reveal", emoji="👻", style=discord.ButtonStyle.secondary)
    async def toggle_hide(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel, row = await self._get_context(interaction)
        if not channel or not row or not interaction.guild:
            await interaction.response.send_message("This temporary room is no longer active.", ephemeral=True)
            return

        if interaction.user.id != row["owner_id"]:
            await interaction.response.send_message("❌ Only the room host can hide or reveal this room!", ephemeral=True)
            return

        new_hidden = 0 if row["is_hidden"] else 1
        everyone = interaction.guild.default_role
        overwrite = channel.overwrites_for(everyone)
        overwrite.view_channel = False if new_hidden else None

        try:
            await channel.set_permissions(everyone, overwrite=overwrite)
            await self.bot.db.update_temp_voice(channel.id, is_hidden=new_hidden)
        except discord.HTTPException:
            await interaction.response.send_message("❌ Failed to update permissions.", ephemeral=True)
            return

        embed = build_room_dashboard_embed(
            channel, row["owner_id"], bool(row["is_locked"]), bool(new_hidden)
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Rename & Limit", emoji="✏️", style=discord.ButtonStyle.primary)
    async def rename_limit(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel, row = await self._get_context(interaction)
        if not channel or not row:
            await interaction.response.send_message("This temporary room is no longer active.", ephemeral=True)
            return

        if interaction.user.id != row["owner_id"]:
            await interaction.response.send_message("❌ Only the room host can rename or resize this room!", ephemeral=True)
            return

        await interaction.response.send_modal(RenameLimitModal(self.bot, channel, self))

    @discord.ui.button(label="Claim Host", emoji="👑", style=discord.ButtonStyle.success)
    async def claim_host(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        channel, row = await self._get_context(interaction)
        if not channel or not row or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This temporary room is no longer active.", ephemeral=True)
            return

        if interaction.user.id == row["owner_id"]:
            await interaction.response.send_message("👑 You are already the host of this room!", ephemeral=True)
            return

        if interaction.user not in channel.members:
            await interaction.response.send_message(
                "❌ You must be connected to this voice channel to claim host!",
                ephemeral=True,
            )
            return

        current_owner_in_vc = any(m.id == row["owner_id"] for m in channel.members)
        if current_owner_in_vc:
            await interaction.response.send_message(
                f"❌ The current host (<@{row['owner_id']}>) is still in the voice channel!",
                ephemeral=True,
            )
            return

        await self.bot.db.update_temp_voice(channel.id, owner_id=interaction.user.id)
        try:
            await channel.set_permissions(
                interaction.user, connect=True, view_channel=True, manage_channels=True, move_members=True
            )
        except discord.HTTPException:
            pass

        embed = build_room_dashboard_embed(
            channel, interaction.user.id, bool(row["is_locked"]), bool(row["is_hidden"])
        )
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(
            f"👑 {interaction.user.mention} has claimed ownership of **{channel.name}**!"
        )


class TempVoice(commands.Cog):
    """Join-to-Create Dynamic Private Voice Rooms & Voice Economy Tracker."""

    def __init__(self, bot: SilexaBot) -> None:
        self.bot = bot
        self.voice_xp_loop.start()

    def cog_unload(self) -> None:
        self.voice_xp_loop.cancel()

    tempvoice_group = app_commands.Group(
        name="tempvoice",
        description="Set up and control dynamic Join-to-Create voice rooms.",
    )

    @tempvoice_group.command(
        name="setup",
        description="Create the '➕ Join to Create' voice channel and category for dynamic rooms.",
    )
    @app_commands.describe(
        category="Optional existing category where temporary voice rooms should be created"
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def tempvoice_setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel | None = None,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            target_category = category or await interaction.guild.create_category(
                name="🔊 Voice Lounges",
                reason="Silexa Bot Join-to-Create TempVoice setup",
            )
            jtc_channel = await interaction.guild.create_voice_channel(
                name="➕ Join to Create",
                category=target_category,
                reason="Silexa Bot Join-to-Create trigger channel",
            )
        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Failed to create channels — please ensure I have the `Manage Channels` permission!"
            )
            return

        await self.bot.db.update_guild_settings(
            interaction.guild.id,
            jtc_channel_id=jtc_channel.id,
            jtc_category_id=target_category.id,
        )

        embed = discord.Embed(
            title="🔊 Join-to-Create TempVoice Ready!",
            description=(
                f"**Trigger Channel:** {jtc_channel.mention}\n"
                f"**Category:** `{target_category.name}`\n\n"
                "Whenever a member joins **➕ Join to Create**, Silexa Bot will automatically "
                "spawn a private room for them with an interactive control panel!"
            ),
            color=config.COLOR_SUCCESS,
        )
        await interaction.followup.send(embed=embed)

    @tempvoice_group.command(
        name="panel",
        description="Re-send the interactive Room Control Panel in your current TempVoice channel.",
    )
    async def tempvoice_panel(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        if not interaction.user.voice or not isinstance(
            interaction.user.voice.channel, discord.VoiceChannel
        ):
            await interaction.response.send_message(
                "❌ You must be inside a TempVoice channel to open its control panel!",
                ephemeral=True,
            )
            return

        vc = interaction.user.voice.channel
        row = await self.bot.db.get_temp_voice(vc.id)
        if not row:
            await interaction.response.send_message(
                "❌ Your current voice channel is not a dynamic TempVoice room.",
                ephemeral=True,
            )
            return

        embed = build_room_dashboard_embed(
            vc, row["owner_id"], bool(row["is_locked"]), bool(row["is_hidden"])
        )
        view = TempVoiceControlView(self.bot, vc.id)
        await interaction.response.send_message(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return

        guild = member.guild
        settings = await self.bot.db.get_guild_settings(guild.id)
        jtc_channel_id = settings.get("jtc_channel_id")

        # 1. Member joined the "➕ Join to Create" trigger channel
        if after.channel and jtc_channel_id and after.channel.id == jtc_channel_id:
            category = after.channel.category
            if not category and settings.get("jtc_category_id"):
                cat_ch = guild.get_channel(settings["jtc_category_id"])
                if isinstance(cat_ch, discord.CategoryChannel):
                    category = cat_ch

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                member: discord.PermissionOverwrite(
                    connect=True,
                    view_channel=True,
                    manage_channels=True,
                    move_members=True,
                ),
            }

            try:
                new_vc = await guild.create_voice_channel(
                    name=f"🎧 {member.display_name[:22]}'s Room",
                    category=category,
                    overwrites=overwrites,
                    reason=f"Join-to-Create room for {member.display_name}",
                )
                await self.bot.db.register_temp_voice(new_vc.id, guild.id, member.id)
                await member.move_to(new_vc, reason="Moved to personal TempVoice room")

                embed = build_room_dashboard_embed(
                    new_vc, member.id, is_locked=False, is_hidden=False
                )
                view = TempVoiceControlView(self.bot, new_vc.id)
                await new_vc.send(content=f"👋 Welcome {member.mention}!", embed=embed, view=view)
            except discord.HTTPException as exc:
                logger.warning("Failed to spawn TempVoice room in %s: %s", guild.name, exc)

        # 2. Cleanup empty temporary voice channel when the last human leaves
        if before.channel and before.channel != after.channel:
            temp_row = await self.bot.db.get_temp_voice(before.channel.id)
            if temp_row:
                human_members = [m for m in before.channel.members if not m.bot]
                if len(human_members) == 0:
                    await self.bot.db.delete_temp_voice(before.channel.id)
                    try:
                        await before.channel.delete(reason="TempVoice room empty")
                    except discord.HTTPException:
                        pass

    @tasks.loop(minutes=1)
    async def voice_xp_loop(self) -> None:
        """Reward active voice participants with XP, Coins, and progress Voice Daily Contracts."""
        for guild in self.bot.guilds:
            afk_id = guild.afk_channel.id if guild.afk_channel else None
            for vc in guild.voice_channels:
                if vc.id == afk_id:
                    continue
                active_humans = [
                    m
                    for m in vc.members
                    if not m.bot and not m.voice.self_deaf and not m.voice.deaf
                ]
                if not active_humans:
                    continue

                for member in active_humans:
                    try:
                        await self.bot.db.add_rewards(
                            guild_id=guild.id,
                            user_id=member.id,
                            xp=config.VOICE_XP_PER_MIN,
                            coins=config.VOICE_COINS_PER_MIN,
                            voice_minutes_inc=1,
                        )
                        await self.bot.db.progress_contract(
                            guild.id, member.id, "voice_minutes", 1
                        )
                    except Exception:
                        logger.exception("Error awarding voice XP for user %s", member.id)

    @voice_xp_loop.before_loop
    async def before_voice_xp_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: SilexaBot) -> None:
    await bot.add_cog(TempVoice(bot))
