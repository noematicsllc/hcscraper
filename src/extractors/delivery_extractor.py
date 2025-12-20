"""Delivery document data extraction coordinator."""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..api.client import HallmarkAPIClient
from ..storage.json_writer import JSONWriter
from ..storage.csv_writer import CSVWriter


logger = logging.getLogger(__name__)


class DeliveryExtractor:
    """Coordinates delivery document data extraction and storage."""

    def __init__(
        self,
        api_client: HallmarkAPIClient,
        output_directory: Path,
        save_json: bool = True,
        save_csv: bool = True
    ):
        """Initialize delivery extractor.

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

    def extract_single_delivery(self, delivery_id: str) -> bool:
        """Extract data for a single delivery.

        Args:
            delivery_id: The delivery ID to extract

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Extracting delivery {delivery_id}")

        try:
            # Retrieve delivery data from API
            delivery_data = self.api_client.get_delivery_detail(delivery_id)

            if delivery_data is None:
                logger.error(f"Failed to retrieve delivery {delivery_id}")
                return False

            # Save to files
            saved_files = []

            if self.save_json:
                try:
                    filepath = self.json_writer.save_delivery(delivery_id, delivery_data)
                    saved_files.append(str(filepath))
                except Exception as e:
                    logger.error(f"Failed to save JSON for delivery {delivery_id}: {e}")

            if self.save_csv:
                try:
                    filepath = self.csv_writer.save_delivery(delivery_id, delivery_data)
                    saved_files.append(str(filepath))
                except Exception as e:
                    logger.error(f"Failed to save CSV for delivery {delivery_id}: {e}")

            if saved_files:
                logger.info(f"Successfully extracted delivery {delivery_id}, saved {len(saved_files)} files")
                return True
            else:
                logger.error(f"No files saved for delivery {delivery_id}")
                return False

        except Exception as e:
            logger.error(f"Error extracting delivery {delivery_id}: {e}", exc_info=True)
            return False

    def extract_deliveries(self, delivery_ids: List[str]) -> Dict[str, Any]:
        """Extract data for multiple deliveries.

        Args:
            delivery_ids: List of delivery IDs to extract

        Returns:
            Dict with extraction statistics
        """
        logger.info(f"Starting batch extraction of {len(delivery_ids)} deliveries")

        stats = {
            "total": len(delivery_ids),
            "successful": 0,
            "failed": 0,
            "failed_delivery_ids": []
        }

        for idx, delivery_id in enumerate(delivery_ids, 1):
            logger.info(f"Processing delivery {idx}/{len(delivery_ids)}: {delivery_id}")

            success = self.extract_single_delivery(delivery_id)

            if success:
                stats["successful"] += 1
            else:
                stats["failed"] += 1
                stats["failed_delivery_ids"].append(delivery_id)

        logger.info(
            f"Batch extraction complete: {stats['successful']} successful, "
            f"{stats['failed']} failed out of {stats['total']} total"
        )

        return stats
