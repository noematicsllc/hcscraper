"""Logging configuration for Hallmark Connect scraper."""

import logging
import sys
from pathlib import Path
from typing import Optional, Dict


# Component to log file mapping
COMPONENT_LOG_FILES = {
    'auth': 'auth.log',
    'extractors': 'extractors.log',
    'api': 'api.log',
    'storage': 'storage.log',
    'main': 'main.log',
}


def _get_component_from_logger_name(name: str) -> str:
    """Determine component from logger name.
    
    Args:
        name: Logger name (e.g., 'src.auth.authenticator')
        
    Returns:
        Component name or 'main' if no match
    """
    if 'auth' in name:
        return 'auth'
    elif 'extractor' in name:
        return 'extractors'
    elif 'api' in name or 'client' in name or 'request' in name:
        return 'api'
    elif 'storage' in name or 'json_writer' in name:
        return 'storage'
    else:
        return 'main'


class ComponentFilter(logging.Filter):
    """Filter that only allows records from a specific component."""
    
    def __init__(self, component: str):
        """Initialize component filter.
        
        Args:
            component: Component name (auth, extractors, api, storage, main)
        """
        super().__init__()
        self.component = component
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Check if record belongs to this component."""
        return _get_component_from_logger_name(record.name) == self.component


def setup_logging(
    log_level: str = "INFO",
    log_to_console: bool = True,
    log_dir: Optional[Path] = None
) -> None:
    """Configure logging for the application with component-based file logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_console: Whether to log to console (default: True)
        log_dir: Directory for component log files (default: ./logs)
    """
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create formatters
    detailed_formatter = logging.Formatter(
        fmt='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console formatter - minimal for routine operations
    console_formatter = logging.Formatter(
        fmt='[%(levelname)s] %(message)s'
    )

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Determine log directory
    if log_dir:
        log_directory = Path(log_dir)
    else:
        log_directory = Path('./logs')
    
    log_directory.mkdir(parents=True, exist_ok=True)

    # Console handler - only show WARNING and above for routine operations
    # INFO and DEBUG go to files only (unless DEBUG level is set)
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        # Console shows WARNING+ by default, but can be overridden with DEBUG level
        console_level = logging.DEBUG if numeric_level == logging.DEBUG else logging.WARNING
        console_handler.setLevel(console_level)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # Component-based file handlers - each component gets its own file
    for component in COMPONENT_LOG_FILES.keys():
        log_path = log_directory / COMPONENT_LOG_FILES[component]
        handler = logging.FileHandler(log_path, mode='a', encoding='utf-8')
        handler.setLevel(numeric_level)
        handler.setFormatter(detailed_formatter)
        handler.addFilter(ComponentFilter(component))
        root_logger.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        logging.Logger: Logger instance
    """
    return logging.getLogger(name)
