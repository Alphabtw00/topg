# bot/crypto_bot.py
"""
Main Discord bot class implementation
"""
import asyncio
import logging
import gc
import psutil
from datetime import datetime, timedelta
from discord.ext import commands, tasks
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
    __slots__ = (
        "http_session", "startup_time", "metrics", "bg_tasks", 
        "max_reconnect_attempts", "reconnect_delay", "heartbeat_missed_threshold",
        "is_first_connect", "last_metrics_report"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http_session = None
        self.startup_time = datetime.now()
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5 
        self.heartbeat_missed_threshold = 3
        self.is_first_connect = True
        self.last_metrics_report = datetime.now()
        
        # Tracked background tasks
        self.bg_tasks = []
        
        # Performance metrics
        self.metrics = {
            'processed_count': 0,
            'processing_times': [],
            'last_cleanup': datetime.now().timestamp(),
            'command_usage': {},
            'errors': {
                'count': 0,
                'last_errors': []
            },
            'api_latency': {}
        }
        
    def start_background_task(self, coro, name=None):
        """
        Start and track a background task
        
        Args:
            coro: Coroutine to run as background task
            name: Optional name for the task
        """
        task = self.loop.create_task(coro)
        if name:
            task.set_name(name)
        self.bg_tasks.append(task)
        return task
        
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

                # Suggest garbage collection
                gc.collect()
                
                # Report memory usage
                memory = psutil.Process().memory_info().rss / 1024 ** 2  # MB
                logger.info(f"Memory usage: {memory:.1f}MB")

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
                        
                        if missed_heartbeats >= self.heartbeat_missed_threshold:
                            logger.error("Multiple missed heartbeats - connection may be unstable")
                            # Force reconnection if we've missed too many heartbeats
                            if hasattr(self.ws, 'close'):
                                await self.ws.close(code=1000)
                                logger.info("Closed websocket to force reconnection")
                                missed_heartbeats = 0
                    else:
                        if missed_heartbeats > 0:
                            logger.info(f"Heartbeat resumed after {missed_heartbeats} missed beats")
                        missed_heartbeats = 0
                        
                    last_ack = current_ack
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                await asyncio.sleep(5)
                
    async def periodic_metrics_report(self):
        """Report periodic metrics for monitoring"""
        while True:
            try:
                await asyncio.sleep(3600)  # Report every hour
                
                # Calculate uptime
                uptime = datetime.now() - self.startup_time
                hours, remainder = divmod(uptime.total_seconds(), 3600)
                minutes, seconds = divmod(remainder, 60)
                
                # Get memory usage
                memory = psutil.Process().memory_info().rss / 1024 ** 2  # MB
                
                # Calculate average processing time if any metrics exist
                avg_time = 0
                if self.metrics['processing_times']:
                    recent_times = [t[0] for t in self.metrics['processing_times'][-100:]]
                    if recent_times:
                        avg_time = sum(recent_times) / len(recent_times)
                
                # Collect and log metrics
                logger.info(
                    f"Metrics Report | Uptime: {int(hours)}h {int(minutes)}m | "
                    f"Memory: {memory:.1f}MB | "
                    f"Processed: {self.metrics['processed_count']} | "
                    f"Avg Processing: {avg_time:.4f}s"
                )
                
                self.last_metrics_report = datetime.now()
            except Exception as e:
                logger.error(f"Error in metrics report: {e}")

    async def setup_hook(self):
        """Setup hook that runs before the bot is ready"""
        # This runs before on_ready
        self.http_session = await setup_http_session()

        db_connected = await setup_db_pool()
        if db_connected:
            logger.info("Database connection successful")
        else:
            logger.critical("Failed to establish database connection")
        
        # Start background tasks with tracking
        self.start_background_task(self.cleanup_metrics(), "metrics_cleanup")
        self.start_background_task(monitor_memory_usage(), "memory_monitor")
        self.start_background_task(self.heartbeat_monitor(), "heartbeat_monitor")
        self.start_background_task(self.periodic_metrics_report(), "metrics_report")

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
        from config import (
            TARGET_CHANNEL_IDS, ALLOWED_USER_IDS, 
            BOT_INPUT_CHANNEL_IDS, BOT_OUTPUT_CHANNEL_IDS, FORWARD_BOT_IDS,
            USER_INPUT_CHANNEL_IDS, USER_OUTPUT_CHANNEL_IDS, FORWARD_USER_IDS
        )
        
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
                
        # Log bot forwarding configuration if enabled
        if BOT_OUTPUT_CHANNEL_IDS and FORWARD_BOT_IDS:
            input_info = "all channels" if not BOT_INPUT_CHANNEL_IDS else f"{len(BOT_INPUT_CHANNEL_IDS)} channels"
            logger.info(f"Echo bot message forwarding: {len(FORWARD_BOT_IDS)} bots from {input_info} to {len(BOT_OUTPUT_CHANNEL_IDS)} channels")
        
        # Log user forwarding configuration if enabled
        if USER_OUTPUT_CHANNEL_IDS and FORWARD_USER_IDS:
            input_info = "all channels" if not USER_INPUT_CHANNEL_IDS else f"{len(USER_INPUT_CHANNEL_IDS)} channels"
            logger.info(f"Dani message forwarding: {len(FORWARD_USER_IDS)} users from {input_info} to {len(USER_OUTPUT_CHANNEL_IDS)} channels")
        
        # Fetch and log admin user info
        if ALLOWED_USER_IDS:
            user_infos = [info for info in await asyncio.gather(
                *[get_user_info(user_id) for user_id in ALLOWED_USER_IDS]
            ) if info]
            if user_infos:
                logger.info(f"Allowed admin users: {', '.join(user_infos)}")
                
        # Set the first connect flag to false
        if self.is_first_connect:
            self.is_first_connect = False
        else:
            logger.info("Bot has reconnected")

    async def close(self):
        """Properly close resources when the bot is shutting down"""
        logger.info("Bot is shutting down...")
        
        # Cancel all background tasks
        for task in self.bg_tasks:
            task_name = task.get_name() if hasattr(task, 'get_name') else str(task)
            try:
                task.cancel()
                logger.info(f"Background task '{task_name}' canceled")
            except Exception as e:
                logger.error(f"Error canceling background task '{task_name}': {e}")
                
        # Close the HTTP session
        if self.http_session:
            try:
                await self.http_session.close()
                logger.info("HTTP session closed successfully")
            except Exception as e:
                logger.error(f"Error closing HTTP session: {e}")
            
        # Close the database pool
        try:
            from handlers.mysql_handler import close_db_pool
            await close_db_pool()
            logger.info("Database connection pool closed successfully")
        except Exception as e:
            logger.error(f"Error closing database pool: {e}")
        
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
        
    def record_command_usage(self, command_name):
        """
        Record command usage for metrics
        
        Args:
            command_name: Name of the command used
        """
        if command_name not in self.metrics['command_usage']:
            self.metrics['command_usage'][command_name] = 0
        self.metrics['command_usage'][command_name] += 1
        
    def record_api_latency(self, endpoint, latency):
        """
        Record API latency for monitoring
        
        Args:
            endpoint: API endpoint name
            latency: Request latency in seconds
        """
        if endpoint not in self.metrics['api_latency']:
            self.metrics['api_latency'][endpoint] = []
            
        # Keep only recent latency data
        self.metrics['api_latency'][endpoint] = (
            self.metrics['api_latency'][endpoint][-99:] + [latency]
        )