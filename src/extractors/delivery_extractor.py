"""Delivery document data extraction coordinator."""

import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..api.client import HallmarkAPIClient
from ..storage.json_writer import JSONWriter
from ..storage.csv_writer import CSVWriter
from .order_extractor import ProgressTracker


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

        # Initialize progress tracker
        progress = ProgressTracker(total=len(delivery_ids), item_type="delivery")
        failed_delivery_ids = []

        for delivery_id in delivery_ids:
            request_start = time.time()

            success = self.extract_single_delivery(delivery_id)

            request_time = time.time() - request_start
            progress.update(success, request_time)

            if not success:
                failed_delivery_ids.append(delivery_id)

            # Log progress
            logger.info(progress.get_progress_message())

        # Get summary
        summary = progress.get_summary()

        # Format elapsed time for log
        elapsed = summary["elapsed_seconds"]
        if elapsed < 60:
            elapsed_str = f"{elapsed:.0f}s"
        elif elapsed < 3600:
            elapsed_str = f"{elapsed/60:.1f}m"
        else:
            elapsed_str = f"{elapsed/3600:.1f}h"

        logger.info(
            f"Batch extraction complete: {summary['successful']} successful, "
            f"{summary['failed']} failed out of {summary['total']} total "
            f"(elapsed: {elapsed_str}, avg: {summary['avg_request_time']:.1f}s/delivery)"
        )

        return {
            "total": summary["total"],
            "successful": summary["successful"],
            "failed": summary["failed"],
            "failed_delivery_ids": failed_delivery_ids,
            "elapsed_seconds": summary["elapsed_seconds"],
            "avg_request_time": summary["avg_request_time"]
        }
