import time
import discord
from discord import app_commands
from discord.ext import commands

import config
from bot import SilexaBot
from utils.database import SHOP_ITEMS


def build_shop_embed(user_data: dict, owned_items: list[str]) -> discord.Embed:
    now = int(time.time())
    boost_until = user_data.get("xp_boost_until", 0)
    boost_str = (
        f"🚀 Active (ends <t:{boost_until}:R>)"
        if boost_until > now
        else "Inactive"
    )
    active_theme = user_data.get("equipped_theme", "default").capitalize()
    active_title = user_data.get("equipped_title") or "None"

    embed = discord.Embed(
        title="🛒 Silexa Customization & Booster Shop",
        description=(
            f"💰 **Your Balance:** `{user_data['coins']:,} Coins`\n"
            f"🎨 **Equipped Theme:** `{active_theme}`  •  🏷️ **Title:** `{active_title}`\n"
            f"⚡ **2x XP Boost:** {boost_str}\n\n"
            "Select any item from the dropdown menu below to purchase and equip it instantly!"
        ),
        color=config.COLOR_GOLD,
    )

    theme_lines: list[str] = []
    title_lines: list[str] = []
    boost_lines: list[str] = []

    for item_id, item in SHOP_ITEMS.items():
        status = "✅ *Owned*" if item_id in owned_items else f"`{item['price']:,} Coins`"
        line = f"{item['emoji']} **{item['name']}** — {status}\n└ *{item['description']}*"
        if item["category"] == "theme":
            theme_lines.append(line)
        elif item["category"] == "title":
            title_lines.append(line)
        else:
            boost_lines.append(line)

    embed.add_field(
        name="🎨 Visual Profile Card Themes",
        value="\n".join(theme_lines),
        inline=False,
    )
    embed.add_field(
        name="🏷️ Exclusive Profile Titles",
        value="\n".join(title_lines),
        inline=False,
    )
    embed.add_field(
        name="🚀 Boosters & Consumables",
        value="\n".join(boost_lines),
        inline=False,
    )
    embed.set_footer(text="Purchased themes & titles are automatically equipped • Use /profile to preview!")
    return embed


class ShopBuySelect(discord.ui.Select):
    def __init__(self, bot: SilexaBot, guild_id: int, owner_id: int) -> None:
        self.bot = bot
        self.guild_id = guild_id
        self.owner_id = owner_id

        options = [
            discord.SelectOption(
                label=f"{item['name']} ({item['price']} Coins)",
                value=item_id,
                emoji=item["emoji"],
                description=item["description"][:95],
            )
            for item_id, item in SHOP_ITEMS.items()
        ]
        super().__init__(
            placeholder="🛒 Select an item to purchase...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        item_id = self.values[0]
        ok, msg = await self.bot.db.purchase_shop_item(
            self.guild_id, interaction.user.id, item_id
        )
        if not ok:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
            return

        if interaction.user.id == self.owner_id:
            user_data = await self.bot.db.ensure_user(self.guild_id, interaction.user.id)
            owned = await self.bot.db.get_user_inventory(self.guild_id, interaction.user.id)
            await interaction.response.edit_message(
                embed=build_shop_embed(user_data, owned), view=self.view
            )
            await interaction.followup.send(f"✅ {msg}", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ {msg}", ephemeral=True)


class EquipItemSelect(discord.ui.Select):
    def __init__(self, bot: SilexaBot, guild_id: int, owned_items: list[str]) -> None:
        self.bot = bot
        self.guild_id = guild_id

        options = [
            discord.SelectOption(
                label="Default Theme (Discord Modern Dark)",
                value="theme_default",
                emoji="🌑",
                description="Equip the classic Discord Modern Dark profile card theme",
            ),
            discord.SelectOption(
                label="Clear Profile Title (None)",
                value="title_none",
                emoji="✖️",
                description="Remove your equipped profile title tag",
            ),
        ]
        for item_id in owned_items:
            item = SHOP_ITEMS.get(item_id)
            if item and item["category"] in ("theme", "title"):
                options.append(
                    discord.SelectOption(
                        label=f"Equip: {item['name']}",
                        value=item_id,
                        emoji=item["emoji"],
                        description=item["description"][:95],
                    )
                )

        super().__init__(
            placeholder="🎒 Select an owned Theme or Title to equip...",
            min_values=1,
            max_values=1,
            options=options[:25],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        choice = self.values[0]
        ok, msg = await self.bot.db.equip_user_item(
            self.guild_id, interaction.user.id, choice
        )
        prefix = "✅" if ok else "❌"
        await interaction.response.send_message(f"{prefix} {msg}", ephemeral=True)


class InventoryView(discord.ui.View):
    def __init__(self, bot: SilexaBot, guild_id: int, owned_items: list[str]) -> None:
        super().__init__(timeout=180)
        self.add_item(EquipItemSelect(bot, guild_id, owned_items))


class ShopView(discord.ui.View):
    def __init__(self, bot: SilexaBot, guild_id: int, owner_id: int) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.add_item(ShopBuySelect(bot, guild_id, owner_id))

    @discord.ui.button(label="My Inventory & Equip", emoji="🎒", style=discord.ButtonStyle.secondary)
    async def open_inventory(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        owned = await self.bot.db.get_user_inventory(self.guild_id, interaction.user.id)
        user_data = await self.bot.db.ensure_user(self.guild_id, interaction.user.id)
        owned_names = [
            f"{SHOP_ITEMS[i]['emoji']} **{SHOP_ITEMS[i]['name']}**"
            for i in owned
            if i in SHOP_ITEMS
        ]
        desc = (
            "\n".join(owned_names)
            if owned_names
            else "*You haven't purchased any custom themes or titles yet!*"
        )
        embed = discord.Embed(
            title=f"🎒 {interaction.user.display_name}'s Locker & Inventory",
            description=(
                f"🎨 **Equipped Theme:** `{user_data.get('equipped_theme', 'default').capitalize()}`\n"
                f"🏷️ **Equipped Title:** `{user_data.get('equipped_title') or 'None'}`\n\n"
                f"**Unlocked Cosmetics ({len(owned_names)}):**\n{desc}"
            ),
            color=config.COLOR_BLURPLE,
        )
        await interaction.response.send_message(
            embed=embed,
            view=InventoryView(self.bot, self.guild_id, owned),
            ephemeral=True,
        )


class Shop(commands.Cog):
    """Server Customization Shop, Profile Themes, Titles, and 2x XP Boosters."""

    def __init__(self, bot: SilexaBot) -> None:
        self.bot = bot

    shop_group = app_commands.Group(
        name="shop",
        description="Browse and equip custom Profile Card themes, titles, and XP boosters.",
    )

    @shop_group.command(
        name="browse",
        description="Open the interactive Server Shop to buy Profile Themes, Titles, and 2x XP Boosters.",
    )
    async def shop_browse(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        user_data = await self.bot.db.ensure_user(interaction.guild_id, interaction.user.id)
        owned = await self.bot.db.get_user_inventory(interaction.guild_id, interaction.user.id)
        embed = build_shop_embed(user_data, owned)
        view = ShopView(self.bot, interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @shop_group.command(
        name="inventory",
        description="View your purchased themes and titles and equip them.",
    )
    async def shop_inventory(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message(
                "This command can only be used inside a server.", ephemeral=True
            )
            return

        owned = await self.bot.db.get_user_inventory(interaction.guild_id, interaction.user.id)
        user_data = await self.bot.db.ensure_user(interaction.guild_id, interaction.user.id)
        owned_names = [
            f"{SHOP_ITEMS[i]['emoji']} **{SHOP_ITEMS[i]['name']}**"
            for i in owned
            if i in SHOP_ITEMS
        ]
        desc = (
            "\n".join(owned_names)
            if owned_names
            else "*No custom items owned yet — browse `/shop browse` to unlock themes and titles!*"
        )
        embed = discord.Embed(
            title=f"🎒 {interaction.user.display_name}'s Locker & Inventory",
            description=(
                f"🎨 **Equipped Theme:** `{user_data.get('equipped_theme', 'default').capitalize()}`\n"
                f"🏷️ **Equipped Title:** `{user_data.get('equipped_title') or 'None'}`\n\n"
                f"**Unlocked Cosmetics ({len(owned_names)}):**\n{desc}"
            ),
            color=config.COLOR_BLURPLE,
        )
        await interaction.response.send_message(
            embed=embed,
            view=InventoryView(self.bot, interaction.guild_id, owned),
        )


async def setup(bot: SilexaBot) -> None:
    await bot.add_cog(Shop(bot))
