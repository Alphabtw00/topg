"""
Logging configuration
"""
import os
import logging
from datetime import datetime

def setup_logger():
    """
    Configure and return a logger with improved handling for repetitive errors
    """
    logger = logging.getLogger("topg_bot")
    
    # Set base level for the logger
    logger.setLevel(logging.INFO)
    
    # Create a more compact format for terminal output
    terminal_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message).200s", datefmt="%H:%M:%S")
    
    # Create console handler with a higher log level to reduce noise
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(terminal_formatter)
    
    # Add file handler with rotation for persistent logs
    try:
        os.makedirs('logs', exist_ok=True)
        
        # Use RotatingFileHandler instead of FileHandler
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            f'logs/bot_{datetime.now().strftime("%Y%m%d")}.log',
            maxBytes=10*1024*1024,  # 10 MB
            backupCount=5  # Keep 5 backup files
        )
        file_handler.setLevel(logging.DEBUG)  # Lower level for files to capture everything
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        
        logger.addHandler(file_handler)
    except Exception as e:
        logger.error(f"Failed to setup log file: {e}")
    
    # Add console handler
    logger.addHandler(console_handler)
    
    # Remove default handlers from root logger to avoid duplicate logs
    logging.getLogger().handlers = []
    
    return logger

# Add a rate limiter for repetitive error logs
class RateLimitedLoggerAdapter(logging.LoggerAdapter):
    """
    Adapter to rate limit repeated error messages
    """
    def __init__(self, logger, extra=None):
        super().__init__(logger, extra or {})
        self.message_counts = {}
        self.last_reported = {}
        self.report_threshold = 10  # Report every 10 occurrences
        self.time_window = 60  # Reset counts after 60 seconds
    
    def process(self, msg, kwargs):
        return msg, kwargs
    
    def error(self, msg, *args, **kwargs):
        # Generate a hash of the message to track duplicates
        msg_hash = hash(msg)
        current_time = datetime.now()
        
        # Reset counter if it's been more than time_window since last occurrence
        if msg_hash in self.last_reported and (current_time - self.last_reported[msg_hash]) > self.time_window:
            self.message_counts[msg_hash] = 0
        
        # Increment counter
        self.message_counts[msg_hash] = self.message_counts.get(msg_hash, 0) + 1
        self.last_reported[msg_hash] = current_time
        
        # Log only if we've hit the threshold or it's the first occurrence
        count = self.message_counts[msg_hash]
        if count == 1 or count % self.report_threshold == 0:
            if count > 1:
                # Add count for non-first occurrences
                msg = f"{msg} (occurred {count} times)"
            self.logger.error(msg, *args, **kwargs)

# Update get_logger to use the rate-limited adapter
def get_logger():
    """
    Get the application logger with rate limiting for errors
    """
    import time  # Make sure to import time
    logger = logging.getLogger("topg_bot")
    return RateLimitedLoggerAdapter(logger)