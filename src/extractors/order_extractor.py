"""Order data extraction coordinator."""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..api.client import HallmarkAPIClient
from ..storage.json_writer import JSONWriter
from ..storage.csv_writer import CSVWriter


logger = logging.getLogger(__name__)


class OrderExtractor:
    """Coordinates order data extraction and storage."""

    def __init__(
        self,
        api_client: HallmarkAPIClient,
        output_directory: Path,
        save_json: bool = True,
        save_csv: bool = True
    ):
        """Initialize order extractor.

        Args:
            api_client: Configured API client
            output_directory: Directory for output files
            save_json: Whether to save JSON files (default: True)
            save_csv: Whether to save CSV files (default: True)
        """
        self.api_client = api_client
        self.output_directory = Path(output_directory)
        self.save_json = save_json
        self.save_csv = save_csv

        # Initialize storage handlers
        if self.save_json:
            self.json_writer = JSONWriter(output_directory)
        if self.save_csv:
            self.csv_writer = CSVWriter(output_directory)

    def extract_single_order(self, order_id: str) -> bool:
        """Extract data for a single order.

        Args:
            order_id: The order ID to extract

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Extracting order {order_id}")

        try:
            # Retrieve order data from API
            order_data = self.api_client.get_order_detail(order_id)

            if order_data is None:
                logger.error(f"Failed to retrieve order {order_id}")
                return False

            # Save to files
            saved_files = []

            if self.save_json:
                try:
                    filepath = self.json_writer.save_order(order_id, order_data)
                    saved_files.append(str(filepath))
                except Exception as e:
                    logger.error(f"Failed to save JSON for order {order_id}: {e}")

            if self.save_csv:
                try:
                    filepath = self.csv_writer.save_order(order_id, order_data)
                    saved_files.append(str(filepath))
                except Exception as e:
                    logger.error(f"Failed to save CSV for order {order_id}: {e}")

            if saved_files:
                logger.info(f"Successfully extracted order {order_id}, saved {len(saved_files)} files")
                return True
            else:
                logger.error(f"No files saved for order {order_id}")
                return False

        except Exception as e:
            logger.error(f"Error extracting order {order_id}: {e}", exc_info=True)
            return False

    def extract_orders(self, order_ids: List[str]) -> Dict[str, Any]:
        """Extract data for multiple orders.

        Args:
            order_ids: List of order IDs to extract

        Returns:
            Dict with extraction statistics
        """
        logger.info(f"Starting batch extraction of {len(order_ids)} orders")

        stats = {
            "total": len(order_ids),
            "successful": 0,
            "failed": 0,
            "failed_order_ids": []
        }

        for idx, order_id in enumerate(order_ids, 1):
            logger.info(f"Processing order {idx}/{len(order_ids)}: {order_id}")

            success = self.extract_single_order(order_id)

            if success:
                stats["successful"] += 1
            else:
                stats["failed"] += 1
                stats["failed_order_ids"].append(order_id)

        logger.info(
            f"Batch extraction complete: {stats['successful']} successful, "
            f"{stats['failed']} failed out of {stats['total']} total"
        )

        return stats
