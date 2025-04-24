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
from commands.health import Health
from commands.github_checker import GithubChecker
from commands.settings import SettingsCommands
from commands.truth_commands import TruthCommands
from commands.website_info import WebsiteChecker
from commands.ban import BanCommand
from handlers.mysql_handler import setup_db_pool, close_db_pool
from utils.formatters import relative_time
from handlers.truth_tracker import start_tracking
from api.provider import ApiServiceProvider

logger = get_logger()

class CryptoBot(commands.Bot):
    """
    Main Discord bot class with extended functionality for crypto tracking
    """
    __slots__ = (
        "startup_time", "metrics", "bg_tasks", 
        "max_reconnect_attempts", "reconnect_delay", "heartbeat_missed_threshold",
        "is_first_connect", "last_metrics_report", "shutdown_in_progress"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.services = None
        self.startup_time = datetime.now()
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5
        self.heartbeat_missed_threshold = 3
        self.is_first_connect = True
        self.last_metrics_report = datetime.now()
        self.shutdown_in_progress = False
        
        # Tracked background tasks
        self.bg_tasks = []
        
        # Performance metrics
        self.metrics = {
            'processed_count': 0,
            'processing_times': [],
            'last_cleanup': datetime.now().timestamp(),
            'command_usage': {},
            'errors' : {},
            'api_latency': {}
        }

    async def setup_hook(self):
        """Setup hook that runs before the bot is ready"""
        # This runs before on_ready
        # Set up database connection
        try:

            self.services = await ApiServiceProvider(self).setup()
            logger.info("Services provider initialized")

            db_connected = await setup_db_pool()
            if not db_connected:
                logger.critical("Failed to establish database connection")
                self.shutdown_in_progress = True
                return
            logger.info("Database connection successful")
            
            # Set up settings tables
            from service.auto_message_settings import setup_settings_tables
            settings_setup = await setup_settings_tables()
            if settings_setup:
                logger.debug("Settings tables initialized successfully")
            else:
                logger.warning("Settings tables initialization had issues, but will continue")
            
            # Set up truthsocial tables
            from repository.truth_repo import setup_truth_tables
            truth_setup = await setup_truth_tables()
            if truth_setup:
                logger.debug("Truth tables initialized successfully")
            else:
                logger.warning("Truth tables initialization had issues, but will continue")

        except Exception as e:
            logger.critical(f"Database connection error: {e}")
            self.shutdown_in_progress = True
            return

        # Start background tasks with tracking
        self.start_background_task(self.cleanup_metrics(), "metrics_cleanup")
        self.start_background_task(self.monitor_memory_usage(), "memory_monitor")
        self.start_background_task(self.heartbeat_monitor(), "heartbeat_monitor")
        self.start_background_task(self.periodic_metrics_report(), "metrics_report")
        self.start_background_task(start_tracking(self), "truth_tracker")

        # Register commands
        await self.add_cog(Health(self))
        await self.add_cog(GithubChecker(self))
        await self.add_cog(SettingsCommands(self))
        await self.add_cog(WebsiteChecker(self))
        await self.add_cog(BanCommand(self))
        await self.add_cog(TruthCommands(self))

        from bot.events import setup_events  # Adjust import based on your project structure
        await setup_events(self)
        
        try:
            synced = await self.tree.sync()
            logger.info(f"Successfully synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

    async def on_ready(self):
        """Event handler for when the bot is ready"""
        from config import (
            BOT_INPUT_CHANNEL_IDS, BOT_OUTPUT_CHANNEL_IDS, FORWARD_BOT_IDS,
            USER_INPUT_CHANNEL_IDS, USER_OUTPUT_CHANNEL_IDS, FORWARD_USER_IDS
        )
        
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Bot connected to {len(self.guilds)} server(s)")
                
        # Log bot forwarding configuration if enabled
        if BOT_OUTPUT_CHANNEL_IDS and FORWARD_BOT_IDS:
            input_info = "all channels" if not BOT_INPUT_CHANNEL_IDS else f"{len(BOT_INPUT_CHANNEL_IDS)} channels"
            logger.info(f"Echo bot message forwarding: {len(FORWARD_BOT_IDS)} bots from {input_info} to {len(BOT_OUTPUT_CHANNEL_IDS)} channels")
        
        # Log user forwarding configuration if enabled
        if USER_OUTPUT_CHANNEL_IDS and FORWARD_USER_IDS:
            input_info = "all channels" if not USER_INPUT_CHANNEL_IDS else f"{len(USER_INPUT_CHANNEL_IDS)} channels"
            logger.info(f"Dani message forwarding: {len(FORWARD_USER_IDS)} users from {input_info} to {len(USER_OUTPUT_CHANNEL_IDS)} channels")
        
        # Set the first connect flag to false
        if self.is_first_connect:
            self.is_first_connect = False
        else:
            logger.info("Bot has reconnected")

    async def close(self):
        """Properly close resources when the bot is shutting down"""
        # Prevent duplicate shutdown logs
        if self.shutdown_in_progress:
            return
            
        self.shutdown_in_progress = True
        logger.info("Bot is shutting down...")
        
        # Close services
        if hasattr(self, 'services'):
            await self.services.close()
            logger.info("Services closed successfully")
        
        # Cancel all background tasks
        for task in self.bg_tasks:
            task_name = task.get_name() if hasattr(task, 'get_name') else str(task)
            try:
                if not task.done() and not task.cancelled():
                    task.cancel()
                    logger.info(f"Background task '{task_name}' canceled")
            except Exception as e:
                logger.error(f"Error canceling background task '{task_name}': {e}")
    
        try:
            await close_db_pool()
            logger.info("Database connection pool closed successfully")
        except Exception as e:
            logger.error(f"Error closing database pool: {e}")
        
        await super().close()

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
                await asyncio.sleep(12000)  # Run every 10 hours
                logger.info("Starting periodic metrics cleanup task...")

                start_time = datetime.now()
                current_time = start_time.timestamp()
                cutoff_time = current_time - 3600

                if len(self.metrics['processing_times']) > 1000:
                    self.metrics['processing_times'] = [
                        t for t in self.metrics['processing_times'][-1000:]
                        if t[1] > cutoff_time
                    ]
                    logger.info("Cleaned processing times")
            

                # Reset processed count periodically to prevent integer overflow
                if self.metrics['processed_count'] > 1_000_000:
                    self.metrics['processed_count'] = 0
                    logger.info(f"Cleared processed counts after hitting processed limit.")

                # Clear error counts
                if sum(self.metrics['errors'].values()) > 1000:
                    self.clear_error_counts()
                    logger.info("Cleared error counts after exceeding error limit")

                # Suggest garbage collection
                gc.collect()
                logger.info("Garbage collection completed successfully.")
                
                self.metrics['last_cleanup'] = start_time.timestamp()
                logger.info(f"Metrics cleanup completed in {(datetime.now() - start_time).total_seconds():.2f} seconds. Next cleanup at {(start_time + timedelta(hours=10)).strftime('%Y-%m-%d %H:%M:%S')}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metrics cleanup error: {e}")

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
                
                total_errors = self.get_error_count()
                error_types = len(self.metrics['errors'])
                top_errors = sorted(
                self.metrics['errors'].items(), 
                    key=lambda x: x[1], 
                    reverse=True
                )[:3]
                
                # Format top errors for logging
                top_errors_formatted = ", ".join(
                    f"{key}={count}" for key, count in top_errors
                ) if top_errors else "none"
                
                last_cleanup_ms = self.metrics['last_cleanup'] * 1000  # Convert to milliseconds for relative_time
                cleanup_time_str = datetime.fromtimestamp(self.metrics['last_cleanup']).strftime('%Y-%m-%d %H:%M:%S')
                cleanup_relative = relative_time(last_cleanup_ms, include_ago=True)

                # Collect and log metrics
                logger.info(
                    f"Metrics Report | Uptime: {int(hours)}h {int(minutes)}m | "
                    f"Memory: {memory:.1f}MB | "
                    f"Processed: {self.metrics['processed_count']} | "
                    f"Avg Processing: {avg_time:.4f}s | "
                    f"Errors: {total_errors} ({error_types} types, Top: {top_errors_formatted}) | "
                    f"Last Cleanup: {cleanup_time_str} ({cleanup_relative})"
                )
                
                self.last_metrics_report = datetime.now()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics report: {e}")

    async def monitor_memory_usage(self, threshold_mb=300, check_interval=3600):
        """
        Monitor and manage memory usage
        
        Args:
            threshold_mb: Memory threshold in MB to trigger cleanup
            check_interval: Check interval in seconds
        """
        logger.info(f"Memory monitor started (threshold: {threshold_mb}MB, interval: {check_interval}s)")
        
        while True:
            try:
                memory = psutil.Process().memory_info().rss / 1024 ** 2  # Get memory usage in MB
                
                if memory > threshold_mb:
                    logger.warning(f"Memory cleanup triggered at {memory:.1f}MB")
                    
                    # Clear caches
                    pre_cleanup = memory
                    from utils.validators import ADDRESS_CACHE
                    ADDRESS_CACHE.clear()
                    
                    # Suggest garbage collection
                    gc.collect()
                    
                    # Check memory after cleanup
                    post_cleanup = psutil.Process().memory_info().rss / 1024 ** 2
                    logger.info(f"Memory cleanup: {pre_cleanup:.1f}MB → {post_cleanup:.1f}MB (saved: {pre_cleanup-post_cleanup:.1f}MB)")
                
                await asyncio.sleep(check_interval)  # Check periodically
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in memory monitor: {e}")
                await asyncio.sleep(60)  # Shorter interval if error occurs
    
    async def process_commands(self, message):
        """
        Override the process_commands method to completely disable command processing
        """
        # Do nothing, effectively disabling command processing
        return
    
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

    def increment_error_count(self, error_key):
        """
        Record an error for a specific key
        
        Args:
            error_key: Key to track the error
            
        Returns:
            int: Updated error count
        """
        # Initialize the error key if not present
        if error_key not in self.metrics['errors']:
            self.metrics['errors'][error_key] = 0
        
        # Increment the error count
        self.metrics['errors'][error_key] = self.metrics['errors'][error_key] + 1
        count = self.metrics['errors'][error_key]
        
        return count

    def get_error_count(self, error_key=None):
        """
        Get the count of a specific error or all errors
        
        Args:
            error_key: Optional key to get specific error count
            
        Returns:
            int: Error count for the specified key or total
        """
        if error_key is None:
            # Sum all error counts
            return sum(self.metrics['errors'].values())
        
        # Return count for specific key or 0 if not found
        return self.metrics['errors'].get(error_key, 0)

    def clear_error_counts(self):
        """Clear all error counts"""
        self.metrics['errors'] = {}
        logger.debug("Error counts cleared")

    #manual reconnect (not needed in most cases) only if discord fails auto connect
    async def _monitor_reconnection(self):
        """Monitor whether the auto-reconnection succeeds, use manual reconnect as fallback"""
        # Wait for a reasonable time for auto-reconnect
        await asyncio.sleep(60)
        
        # If we're still disconnected, try manual reconnection
        if not self.is_ready():
            logger.warning("Auto-reconnection appears to have failed, attempting manual reconnect")
            success = await self.attempt_reconnect()
            if not success:
                logger.critical("All reconnection attempts failed. Bot will need to be restarted manually.")
        
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
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                await asyncio.sleep(5)