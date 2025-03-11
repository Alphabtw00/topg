"""
Logging configuration
"""
import os
import logging
from datetime import datetime

def setup_logger():
    """
    Configure and return a logger for the application
    """
    logger = logging.getLogger("topg_bot")
    
    # Configure base logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Add file handler for persistent logs
    try:
        os.makedirs('logs', exist_ok=True)
        file_handler = logging.FileHandler(f'logs/bot_{datetime.now().strftime("%Y%m%d")}.log')
        file_handler.setLevel(logging.WARNING)
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(file_handler)
    except Exception as e:
        logger.error(f"Failed to setup log file: {e}")
    
    return logger

def get_logger():
    """
    Get the application logger
    """
    return logging.getLogger("topg_bot")