"""
Logging utilities for WhatPyLib.
"""

import logging
import sys
from typing import Optional


# Default log format
DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Package logger name
LOGGER_NAME = "whatpylib"


def setup_logging(
    level: str = "INFO",
    format_string: Optional[str] = None,
    date_format: Optional[str] = None,
    stream: Optional[object] = None,
) -> logging.Logger:
    """
    Set up logging for the library.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom log format string
        date_format: Custom date format string
        stream: Output stream (defaults to stderr)
        
    Returns:
        Configured logger
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Create handler
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setLevel(logger.level)
    
    # Create formatter
    formatter = logging.Formatter(
        fmt=format_string or DEFAULT_FORMAT,
        datefmt=date_format or DEFAULT_DATE_FORMAT,
    )
    handler.setFormatter(formatter)
    
    # Add handler
    logger.addHandler(handler)
    
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger for the library.
    
    Args:
        name: Optional sub-logger name (e.g., "connection", "crypto")
        
    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(f"{LOGGER_NAME}.{name}")
    return logging.getLogger(LOGGER_NAME)


class LogMixin:
    """
    Mixin class that provides a logger property.
    
    Usage:
        class MyClass(LogMixin):
            def my_method(self):
                self.logger.info("Something happened")
    """
    
    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class."""
        return get_logger(self.__class__.__name__)
