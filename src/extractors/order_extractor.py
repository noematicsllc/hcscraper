"""Order data extraction coordinator."""

import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from ..api.client import HallmarkAPIClient
from ..storage.json_writer import JSONWriter
from ..storage.csv_writer import CSVWriter


logger = logging.getLogger(__name__)


class ProgressTracker:
    """Tracks extraction progress and provides time estimates."""

    def __init__(self, total: int, item_type: str = "order"):
        """Initialize progress tracker.

        Args:
            total: Total number of items to process
            item_type: Type of item being processed (for logging)
        """
        self.total = total
        self.item_type = item_type
        self.processed = 0
        self.successful = 0
        self.failed = 0
        self.start_time = time.time()
        self.request_times: List[float] = []

    def update(self, success: bool, request_time: float) -> None:
        """Update progress after processing an item.

        Args:
            success: Whether the item was processed successfully
            request_time: Time taken to process this item
        """
        self.processed += 1
        if success:
            self.successful += 1
        else:
            self.failed += 1
        self.request_times.append(request_time)

    def get_progress_message(self) -> str:
        """Get a formatted progress message.

        Returns:
            Human-readable progress string
        """
        percentage = (self.processed / self.total * 100) if self.total > 0 else 0
        eta = self._estimate_remaining_time()

        msg = f"Processing {self.item_type} {self.processed}/{self.total} ({percentage:.0f}%)"
        if eta:
            msg += f" - ETA: {eta}"

        return msg

    def _estimate_remaining_time(self) -> Optional[str]:
        """Estimate remaining time based on average request time.

        Returns:
            Human-readable time estimate, or None if not enough data
        """
        if len(self.request_times) < 2:
            return None

        # Use recent average (last 10 requests) for better estimate
        recent_times = self.request_times[-10:]
        avg_time = sum(recent_times) / len(recent_times)
        remaining = self.total - self.processed
        remaining_seconds = avg_time * remaining

        if remaining_seconds < 60:
            return f"{remaining_seconds:.0f}s"
        elif remaining_seconds < 3600:
            minutes = remaining_seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = remaining_seconds / 3600
            return f"{hours:.1f}h"

    def get_summary(self) -> Dict[str, Any]:
        """Get extraction summary statistics.

        Returns:
            Dict with summary statistics
        """
        elapsed = time.time() - self.start_time
        avg_time = sum(self.request_times) / len(self.request_times) if self.request_times else 0

        return {
            "total": self.total,
            "processed": self.processed,
            "successful": self.successful,
            "failed": self.failed,
            "elapsed_seconds": elapsed,
            "avg_request_time": avg_time
        }


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

        # Initialize progress tracker
        progress = ProgressTracker(total=len(order_ids), item_type="order")
        failed_order_ids = []

        for order_id in order_ids:
            request_start = time.time()

            success = self.extract_single_order(order_id)

            request_time = time.time() - request_start
            progress.update(success, request_time)

            if not success:
                failed_order_ids.append(order_id)

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
            f"(elapsed: {elapsed_str}, avg: {summary['avg_request_time']:.1f}s/order)"
        )

        return {
            "total": summary["total"],
            "successful": summary["successful"],
            "failed": summary["failed"],
            "failed_order_ids": failed_order_ids,
            "elapsed_seconds": summary["elapsed_seconds"],
            "avg_request_time": summary["avg_request_time"]
        }
