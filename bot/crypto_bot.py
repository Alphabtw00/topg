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
from handlers.mysql_handler import setup_db_pool

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
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5 
        self.heartbeat_missed_threshold = 3
        self.metrics = {
            'processed_count': 0,
            'processing_times': [],
            'last_cleanup': datetime.now().timestamp()
        }
        
    async def cleanup_metrics(self):
        """Efficient metrics cleanup using batch operations"""
        while True:
            try:
                await asyncio.sleep(36000)  # Run every 10 hours
                current_time = datetime.now().timestamp()
                # Batch cleanup in one operation
                self.metrics['processing_times'] = [
                    t for t in self.metrics['processing_times'][-1000:]  # Keep last 1000 entries max
                    if current_time - t[1] < 3600  # Only from last hour
                ]

                # Reset processed count periodically to prevent integer overflow
                if self.metrics['processed_count'] > 1_000_000:
                    self.metrics['processed_count'] = 0
                    logger.info(f"Cleared processed counts after hitting processed limit.")

                # Clear error counts
                from utils.cache import get_error_count, clear_error_counts  
                error_count = get_error_count()  # Fetch current error count
                
                if error_count > 1000:
                    clear_error_counts()  # Clear errors
                    logger.info(f"Cleared error counts after exceeding error limit")

                self.metrics['last_cleanup'] = current_time
                logger.info("Metrics cleanup completed")
            except Exception as e:
                logger.error(f"Metrics cleanup error: {e}")

    async def attempt_reconnect(self):
        """Handle reconnection with exponential backoff"""
        attempts = 0
        while attempts < self.max_reconnect_attempts:
            try:
                logger.info(f"Reconnection attempt {attempts+1}/{self.max_reconnect_attempts}")
                await self.connect(reconnect=True)
                return True
            except Exception as e:
                attempts += 1
                wait_time = self.reconnect_delay * (2 ** attempts)
                logger.error(f"Reconnection failed: {e}. Waiting {wait_time}s before retry.")
                await asyncio.sleep(wait_time)
        return False
    

    async def heartbeat_monitor(self):
        """Monitor Discord heartbeats to detect connection issues early"""
        last_ack = None
        missed_heartbeats = 0
        
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                if hasattr(self.ws, 'last_heartbeat_ack'):
                    current_ack = self.ws.last_heartbeat_ack
                    
                    if current_ack == last_ack:
                        missed_heartbeats += 1
                        logger.warning(f"Missed heartbeat detected: {missed_heartbeats} in a row")
                        
                        if missed_heartbeats >= 3:
                            logger.error("Multiple missed heartbeats - connection may be unstable")
                            # Force reconnection if we've missed too many heartbeats
                            if hasattr(self.ws, 'close'):
                                await self.ws.close(code=1000)
                                logger.info("Closed websocket to force reconnection")
                                missed_heartbeats = 0
                    else:
                        missed_heartbeats = 0
                        
                    last_ack = current_ack
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                await asyncio.sleep(5)

    async def setup_hook(self):
        """Setup hook that runs before the bot is ready"""
        # This runs before on_ready
        self.http_session = await setup_http_session()

        db_connected = await setup_db_pool()
        if db_connected:
            logger.info("Database connection successful")
        else:
            logger.critical("Failed to establish database connection")
        
        
        self.bg_task = self.loop.create_task(self.cleanup_metrics())
        self.memory_task = self.loop.create_task(monitor_memory_usage())
        self.heartbeat_task = self.loop.create_task(self.heartbeat_monitor())

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
        from config import TARGET_CHANNEL_IDS, ALLOWED_USER_IDS, INPUT_CHANNEL_IDS, OUTPUT_CHANNEL_IDS
        
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")

        # Helper function to fetch channel info
        async def get_channel_info(ch_id):
            channel = self.get_channel(ch_id)
            if channel is None:
                try:
                    channel = await self.fetch_channel(ch_id)
                except Exception as e:
                    logger.error(f"Could not fetch channel with ID {ch_id}: {e}")
                    return None
            guild_name = channel.guild.name if hasattr(channel, 'guild') and channel.guild else "DMs"
            return f"{channel.name} (Server: {guild_name})"

        # Helper function to fetch user info
        async def get_user_info(user_id):
            try:
                user = self.get_user(user_id)
                if user is None:
                    user = await self.fetch_user(user_id)
                return f"{user.name}#{user.discriminator if hasattr(user, 'discriminator') else '0'} (ID: {user.id})"
            except Exception as e:
                logger.error(f"Could not fetch user with ID {user_id}: {e}")
                return None

        # Log target channels
        if TARGET_CHANNEL_IDS:
            target_infos = [info for info in await asyncio.gather(
                *[get_channel_info(ch_id) for ch_id in TARGET_CHANNEL_IDS]
            ) if info]
            if target_infos:
                logger.info(f"Bot will respond in channels: {', '.join(target_infos)}")
        else:
            logger.info("Bot will respond in all channels.")
                
        # Log input channels if configured
        if INPUT_CHANNEL_IDS:
            input_infos = [info for info in await asyncio.gather(
                *[get_channel_info(ch_id) for ch_id in INPUT_CHANNEL_IDS]
            ) if info]
            if input_infos:
                logger.info(f"Bot will copy messages from: {', '.join(input_infos)}")
            
            # Only log output channels if input channels are configured
            if OUTPUT_CHANNEL_IDS:
                output_infos = [info for info in await asyncio.gather(
                    *[get_channel_info(ch_id) for ch_id in OUTPUT_CHANNEL_IDS]
                ) if info]
                if output_infos:
                    logger.info(f"Bot will forward messages to: {', '.join(output_infos)}")
        
        # Fetch and log admin user info
        if ALLOWED_USER_IDS:
            user_infos = [info for info in await asyncio.gather(
                *[get_user_info(user_id) for user_id in ALLOWED_USER_IDS]
            ) if info]
            if user_infos:
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