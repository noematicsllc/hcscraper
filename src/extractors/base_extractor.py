"""Base extractor class with shared database connection logic."""

import os
import logging
from pathlib import Path
from typing import Optional, Any

try:
    import psycopg
except ImportError:
    psycopg = None

from ..storage.json_writer import JSONWriter
from ..api.client import HallmarkAPIClient

logger = logging.getLogger(__name__)


class BaseExtractor:
    """Base class for extractors with shared database connection logic.
    
    This class provides common functionality for all extractors:
    - Database connection management
    - Context manager protocol (__enter__/__exit__)
    - Resource cleanup (close method)
    
    All extractor classes should inherit from this base class to avoid
    code duplication and ensure consistent resource management.
    """

    def __init__(
        self,
        api_client: HallmarkAPIClient,
        output_directory: Path,
        save_json: bool = True,
        update_mode: bool = False
    ):
        """Initialize base extractor.

        Args:
            api_client: Configured API client
            output_directory: Directory for output files
            save_json: Whether to save JSON files (default: True)
            update_mode: If True, re-download existing files (default: False)
        """
        self.api_client = api_client
        self.output_directory = Path(output_directory)
        self.save_json = save_json
        self.update_mode = update_mode

        # Try to connect to database for store number lookup (optional)
        self._db_connection = self._connect_to_database()

        # Initialize storage handler
        if self.save_json:
            self.json_writer = JSONWriter(output_directory, db_connection=self._db_connection)

    def _connect_to_database(self) -> Optional[Any]:
        """Connect to database for store number lookup (optional).

        Returns:
            Database connection or None if connection fails or psycopg not available
        """
        if not psycopg:
            return None

        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            return None

        try:
            connection = psycopg.connect(database_url)
            logger.info("Connected to database for store number lookup")
            return connection
        except Exception as e:
            logger.debug(f"Could not connect to database for store lookup: {e}")
            return None

    def close(self) -> None:
        """Close database connection if it exists.

        Should be called when done with the extractor to prevent connection leaks.
        """
        if self._db_connection:
            try:
                self._db_connection.close()
                logger.debug("Database connection closed")
                self._db_connection = None
                # Clear reference in json_writer as well
                if hasattr(self, 'json_writer'):
                    self.json_writer.db_connection = None
            except Exception as e:
                logger.warning(f"Error closing database connection: {e}")

    def __enter__(self):
        """Context manager entry - returns self."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes database connection."""
        self.close()
        return False  # Don't suppress exceptions

