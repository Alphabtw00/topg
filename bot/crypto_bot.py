"""
Main Discord bot class implementation
"""
import asyncio
import logging
from datetime import datetime
from discord.ext import commands
from utils.logger import get_logger
from api.http_client import setup_http_session
from bot.memory_monitor import monitor_memory_usage
from commands.health import Health
from commands.github_checker import GithubChecker

logger = get_logger()

class CryptoBot(commands.Bot):
    """
    Main Discord bot class with extended functionality for crypto tracking
    """
    __slots__ = ("http_session", "startup_time", "metrics", "bg_task", "memory_task")
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http_session = None
        self.startup_time = datetime.now()
        self.metrics = {
            'processed_count': 0,
            'processing_times': [],
            'last_cleanup': datetime.now().timestamp()
        }
        
    async def cleanup_metrics(self):
        """Efficient metrics cleanup using batch operations"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run hourly
                current_time = datetime.now().timestamp()
                # Batch cleanup in one operation
                self.metrics['processing_times'] = [
                    t for t in self.metrics['processing_times'][-1000:]  # Keep last 1000 entries max
                    if current_time - t[1] < 3600  # Only from last hour
                ]
                # Clear error counts
                from utils.cache import clear_error_counts
                clear_error_counts()
                self.metrics['last_cleanup'] = current_time
                logger.info("Metrics cleanup completed")
            except Exception as e:
                logger.error(f"Metrics cleanup error: {e}")
    
    async def setup_hook(self):
        """Setup hook that runs before the bot is ready"""
        # This runs before on_ready
        self.http_session = await setup_http_session()
        self.bg_task = self.loop.create_task(self.cleanup_metrics())
        self.memory_task = self.loop.create_task(monitor_memory_usage())
        
        # Register commands
        await self.add_cog(Health(self))
        await self.add_cog(GithubChecker(self))

        from bot.events import setup_events  # Adjust import based on your project structure
        await setup_events(self)
        
        try:
            synced = await self.tree.sync()
            logger.info(f"Successfully synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
        logger.info("HTTP session initialized")

    async def on_ready(self):
        """Event handler for when the bot is ready"""
        from config import TARGET_CHANNEL_IDS, ALLOWED_USER_IDS
        
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")

        # Fetch channel info concurrently
        if TARGET_CHANNEL_IDS:
            async def get_channel_info(ch_id):
                channel = self.get_channel(ch_id)
                if channel is None:
                    try:
                        channel = await self.fetch_channel(ch_id)
                    except Exception as e:
                        logger.error(f"Could not fetch channel with ID {ch_id}: {e}")
                        return None
                guild_name = channel.guild.name if channel.guild else "DMs"
                return f"{channel.name} (Server: {guild_name})"

            channel_infos = await asyncio.gather(
                *[get_channel_info(ch_id) for ch_id in TARGET_CHANNEL_IDS]
            )
            channel_infos = [info for info in channel_infos if info]
            logger.info(f"Bot will respond in channels: {', '.join(channel_infos)}")
        else:
            logger.info("Bot will respond in all channels.")

        # Fetch admin user info concurrently
        if ALLOWED_USER_IDS:
            async def get_user_info(user_id):
                try:
                    user = self.get_user(int(user_id))
                    if user is None:
                        user = await self.fetch_user(int(user_id))
                    return f"{user.name}#{user.discriminator} (ID: {user.id})"
                except Exception as e:
                    logger.error(f"Could not fetch user with ID {user_id}: {e}")
                    return None

            user_infos = await asyncio.gather(
                *[get_user_info(user_id) for user_id in ALLOWED_USER_IDS]
            )
            user_infos = [info for info in user_infos if info]
            logger.info(f"Allowed admin users: {', '.join(user_infos)}")

    async def close(self):
        """Properly close resources when the bot is shutting down"""
        logger.info("Bot is shutting down...")
        if self.http_session:
            await self.http_session.close()
        await super().close()

    def record_metric(self, processing_time):
        """
        Record a processing metric
        
        Args:
            processing_time: Time in seconds the processing took
        """
        current_time = datetime.now().timestamp()
        self.metrics['processed_count'] += 1
        self.metrics['processing_times'].append((processing_time, current_time))