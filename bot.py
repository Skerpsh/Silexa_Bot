import logging
import sys
import discord
from discord.ext import commands

import config
from utils.database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
)
logger = logging.getLogger("silexa_bot")


class SilexaBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        intents.reactions = True

        # Slash commands & Context Menus only (no text prefix commands needed)
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )
        self.db = Database(config.DB_PATH)

    async def setup_hook(self) -> None:
        """Initialize database, verify gateway intents, load Cogs, and sync Application Commands."""
        flags = self.application_flags
        if not (flags.gateway_guild_members or flags.gateway_guild_members_limited):
            logger.warning(
                "SERVER MEMBERS INTENT is not enabled in Discord Developer Portal -> Bot. "
                "Auto-disabling 'members' intent so the bot can connect immediately."
            )
            self._connection._intents.members = False

        if not (flags.gateway_message_content or flags.gateway_message_content_limited):
            logger.warning(
                "MESSAGE CONTENT INTENT is not enabled in Discord Developer Portal -> Bot. "
                "Auto-disabling 'message_content' intent so the bot can connect immediately."
            )
            self._connection._intents.message_content = False

        await self.db.connect()
        logger.info("Connected to SQLite database at %s", config.DB_PATH)

        if config.COGS_DIR.exists():
            for cog_file in sorted(config.COGS_DIR.glob("*.py")):
                if cog_file.name.startswith("_"):
                    continue
                extension = f"cogs.{cog_file.stem}"
                try:
                    await self.load_extension(extension)
                    logger.info("Loaded extension: %s", extension)
                except Exception:
                    logger.exception("Failed to load extension: %s", extension)

        try:
            if config.DISCORD_GUILD_ID:
                guild_obj = discord.Object(id=config.DISCORD_GUILD_ID)
                self.tree.copy_global_to(guild=guild_obj)
                synced = await self.tree.sync(guild=guild_obj)
                logger.info(
                    "Synced %d slash/context command(s) to guild %s",
                    len(synced),
                    config.DISCORD_GUILD_ID,
                )
            else:
                synced = await self.tree.sync()
                logger.info("Globally synced %d slash/context command(s)", len(synced))
        except Exception:
            logger.exception("Failed to sync application commands")

    async def on_ready(self) -> None:
        if self.user:
            logger.info("✅ Logged in as %s (ID: %s)", self.user, self.user.id)
            perms = discord.Permissions(
                manage_channels=True,
                move_members=True,
                view_channel=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                add_reactions=True,
                connect=True,
            )
            invite_url = discord.utils.oauth_url(
                self.user.id,
                permissions=perms,
                scopes=("bot", "applications.commands"),
            )
            logger.info("🔗 Invite URL: %s", invite_url)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="/help • Squads, Profiles & Voice",
            )
        )

    async def close(self) -> None:
        await self.db.close()
        await super().close()


def main() -> None:
    token = config.DISCORD_TOKEN
    if not token or token == "your_discord_bot_token_here":
        logger.error(
            "DISCORD_TOKEN is not set in .env! "
            "Get your Bot Token from: Discord Developer Portal -> Your App -> Bot -> Reset Token."
        )
        sys.exit(1)

    if "." not in token and len(token) == 64:
        logger.error(
            "It looks like you pasted your application's PUBLIC KEY (64-char hex) instead of the BOT TOKEN! "
            "In the Discord Developer Portal, open the 'Bot' tab on the left menu and click 'Reset Token' to copy your Bot Token."
        )
        sys.exit(1)

    bot = SilexaBot()
    try:
        bot.run(token, log_handler=None)
    except discord.LoginFailure:
        logger.error(
            "Invalid DISCORD_TOKEN (401 Unauthorized). "
            "Make sure you copied the token from the 'Bot' tab (Reset Token), NOT the Public Key or OAuth2 Client Secret."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
