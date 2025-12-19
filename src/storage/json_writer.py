"""JSON storage for order data."""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


logger = logging.getLogger(__name__)


class JSONWriter:
    """Handles writing order data to JSON files."""

    def __init__(self, output_directory: Path):
        """Initialize JSON writer.

        Args:
            output_directory: Directory to write JSON files
        """
        self.output_directory = Path(output_directory)
        self.output_directory.mkdir(parents=True, exist_ok=True)

    def save_order(self, order_id: str, order_data: Dict[str, Any]) -> Path:
        """Save order data to JSON file.

        Args:
            order_id: The order ID
            order_data: The order data to save

        Returns:
            Path to the saved file

        Raises:
            IOError: If file write fails
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"order_{order_id}_{timestamp}.json"
        filepath = self.output_directory / filename

        # Wrap data with metadata
        output = {
            "order_id": order_id,
            "extracted_at": datetime.now().isoformat(),
            "data": order_data
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved order {order_id} to {filepath}")
            return filepath

        except IOError as e:
            logger.error(f"Failed to write JSON file {filepath}: {e}")
            raise
