"""Logging utilities for SQL retriever bot."""

import logging
import sys
from pathlib import Path
from typing import Optional, Union

from config import LOGGING_CONFIG


def get_logger(name: str) -> logging.Logger:
    """Get configured logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOGGING_CONFIG['level']))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Add console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, LOGGING_CONFIG['level']))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Add file handler
    log_file = Path(LOGGING_CONFIG['log_file'])
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(getattr(logging, LOGGING_CONFIG['level']))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


def setup_logging(level: Optional[str] = None, log_file: Optional[str] = None):
    """Setup logging configuration.
    
    Args:
        level: Log level override
        log_file: Log file path override
    """
    config = LOGGING_CONFIG.copy()
    
    if level:
        config['level'] = level
    if log_file:
        config['log_file'] = log_file
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, config['level']),
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured - Level: {config['level']}, File: {config['log_file']}")


# Default logger instance
default_logger = get_logger(__name__) 