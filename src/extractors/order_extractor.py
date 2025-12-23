"""Order data extraction coordinator."""

import os
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Tuple

try:
    import psycopg
except ImportError:
    psycopg = None

from ..api.client import HallmarkAPIClient
from ..storage.json_writer import JSONWriter
from ..utils.config import DEFAULT_MAX_CONSECUTIVE_FAILURES


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
        self.skipped = 0  # Records skipped because they already exist
        self.start_time = time.time()
        self.request_times: List[float] = []

    def update(self, success: bool, request_time: float, skipped: bool = False) -> None:
        """Update progress after processing an item.

        Args:
            success: Whether the item was processed successfully
            request_time: Time taken to process this item
            skipped: Whether the item was skipped (already exists)
        """
        self.processed += 1
        if skipped:
            self.skipped += 1
        elif success:
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
            "skipped": self.skipped,
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
        update_mode: bool = False,
        max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES
    ):
        """Initialize order extractor.

        Args:
            api_client: Configured API client
            output_directory: Directory for output files
            save_json: Whether to save JSON files (default: True)
            update_mode: If True, re-download existing files. If False, skip existing files (default: False)
            max_consecutive_failures: Maximum consecutive failures before stopping (default: DEFAULT_MAX_CONSECUTIVE_FAILURES)
        """
        self.api_client = api_client
        self.output_directory = Path(output_directory)
        self.save_json = save_json
        self.update_mode = update_mode
        self.max_consecutive_failures = max_consecutive_failures

        # Try to connect to database for store number lookup (optional)
        self._db_connection = None
        if psycopg:
            database_url = os.getenv('DATABASE_URL')
            if database_url:
                try:
                    self._db_connection = psycopg.connect(database_url)
                    logger.info("Connected to database for store number lookup")
                except Exception as e:
                    logger.debug(f"Could not connect to database for store lookup: {e}")
                    self._db_connection = None

        # Initialize storage handler
        if self.save_json:
            self.json_writer = JSONWriter(output_directory, db_connection=self._db_connection)

    def extract_single_order(self, order_id: str) -> Tuple[bool, bool, bool]:
        """Extract data for a single order.

        Args:
            order_id: The order ID to extract

        Returns:
            Tuple of (success: bool, is_validation_failure: bool, was_skipped: bool)
            - success: True if successful, False otherwise
            - is_validation_failure: True if failure is due to validation (systemic issue), False for transient errors
            - was_skipped: True if record was skipped because it already exists
        """
        logger.info(f"Extracting order {order_id}")

        # SAFETY: Check if file already exists - skip by default to prevent wasting time/resources
        # and avoid potential data loss if re-extraction fails
        if not self.update_mode and self.save_json:
            if self.json_writer.order_file_exists(order_id):
                logger.info(
                    f"Order {order_id} already exists, skipping to save time and resources "
                    f"(use --update to re-download)"
                )
                return True, False, True  # Success=True, validation_failure=False, skipped=True

        try:
            # Retrieve order data from API
            order_data = self.api_client.get_order_detail(order_id)

            if order_data is None:
                logger.error(
                    f"CRITICAL: Failed to retrieve order {order_id}: API returned None. "
                    f"This usually indicates an authentication failure or API error. "
                    f"EXTRACTION WILL STOP TO PREVENT WASTING TIME ON BROKEN REQUESTS."
                )
                return False, True, False  # Validation failure - stop immediately

            # Validate that order_data is not empty
            if isinstance(order_data, dict) and len(order_data) == 0:
                logger.error(
                    f"CRITICAL: Failed to retrieve order {order_id}: API returned empty dict. "
                    f"This usually indicates an authentication failure or API error. "
                    f"EXTRACTION WILL STOP TO PREVENT WASTING TIME ON BROKEN REQUESTS."
                )
                return False, True, False  # Validation failure - stop immediately

            # Check if order_data has the expected structure
            if isinstance(order_data, dict) and 'orderHeader' not in order_data:
                logger.error(
                    f"CRITICAL: Invalid order data structure for order {order_id}: missing 'orderHeader'. "
                    f"Available keys: {list(order_data.keys())}. "
                    f"This usually indicates an API error or authentication failure. "
                    f"EXTRACTION WILL STOP TO PREVENT WASTING TIME ON BROKEN REQUESTS."
                )
                return False, True, False  # Validation failure - stop immediately

            # Save to file
            if self.save_json:
                try:
                    filepath = self.json_writer.save_order(order_id, order_data)
                    logger.info(f"Successfully extracted order {order_id}, saved to {filepath}")
                    return True, False, False  # Success, not validation failure, not skipped
                except ValueError as e:
                    # ValueError from validation - CRITICAL, stop immediately
                    logger.error(
                        f"CRITICAL: Validation failed for order {order_id}: {e}. "
                        f"Order data will not be saved to prevent incomplete files. "
                        f"EXTRACTION WILL STOP TO PREVENT WASTING TIME ON BROKEN REQUESTS."
                    )
                    return False, True, False  # Validation failure - stop immediately
                except Exception as e:
                    logger.error(f"Failed to save JSON for order {order_id}: {e}", exc_info=True)
                    return False, False, False  # Transient error - may retry
            else:
                logger.warning(f"save_json is False, no file saved for order {order_id}")
                return False, False, False

        except Exception as e:
            logger.error(f"Error extracting order {order_id}: {e}", exc_info=True)
            return False, False, False  # Assume transient error unless we can determine otherwise

    def extract_orders(self, order_ids: List[str]) -> Dict[str, Any]:
        """Extract data for multiple orders.

        Args:
            order_ids: List of order IDs to extract

        Returns:
            Dict with extraction statistics
        """
        logger.info(f"Starting batch extraction of {len(order_ids)} orders")
        if not self.update_mode:
            logger.info(
                "SAFETY: Update mode disabled - existing files will be skipped by default. "
                "This prevents wasting time/resources and avoids potential data loss. "
                "Use --update flag to re-download existing records."
            )

        # Initialize progress tracker
        progress = ProgressTracker(total=len(order_ids), item_type="order")
        failed_order_ids = []
        consecutive_failures = 0
        stopped_early = False
        stop_reason = None

        for order_id in order_ids:
            request_start = time.time()

            success, is_validation_failure, was_skipped = self.extract_single_order(order_id)

            request_time = time.time() - request_start
            progress.update(success, request_time, skipped=was_skipped)

            if not success:
                failed_order_ids.append(order_id)
                
                # CRITICAL: Stop immediately on validation failures (systemic issues)
                if is_validation_failure:
                    logger.error(
                        f"\n{'='*80}\n"
                        f"CRITICAL: VALIDATION FAILURE DETECTED\n"
                        f"{'='*80}\n"
                        f"Order {order_id} failed validation. This indicates a systemic problem:\n"
                        f"  - Authentication may have failed\n"
                        f"  - API structure may have changed\n"
                        f"  - API may be returning invalid responses\n"
                        f"\n"
                        f"EXTRACTION STOPPED IMMEDIATELY to prevent wasting hours processing\n"
                        f"thousands of records that will all fail.\n"
                        f"\n"
                        f"Please check:\n"
                        f"  1. Authentication is working (see authentication_critical.md)\n"
                        f"  2. API response structure hasn't changed\n"
                        f"  3. Network connectivity is stable\n"
                        f"{'='*80}\n"
                    )
                    stopped_early = True
                    stop_reason = "validation_failure"
                    break
                
                # For transient errors, track consecutive failures
                consecutive_failures += 1
                
                # Check if we've exceeded the failure threshold for transient errors
                if consecutive_failures >= self.max_consecutive_failures:
                    logger.error(
                        f"\n{'='*80}\n"
                        f"EXTRACTION STOPPED: Too many consecutive failures\n"
                        f"{'='*80}\n"
                        f"Stopping extraction after {consecutive_failures} consecutive failures "
                        f"(threshold: {self.max_consecutive_failures}).\n"
                        f"This may indicate network issues or API problems.\n"
                        f"{'='*80}\n"
                    )
                    stopped_early = True
                    stop_reason = "consecutive_failures"
                    break
            else:
                # Reset consecutive failures on success
                consecutive_failures = 0

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

        if stopped_early:
            if stop_reason == "validation_failure":
                logger.error(
                    f"Extraction stopped due to validation failure. "
                    f"Processed {summary['processed']}/{summary['total']} orders. "
                    f"DO NOT resume until the underlying issue is fixed."
                )
            else:
                logger.warning(
                    f"Extraction stopped early due to consecutive failures. "
                    f"Processed {summary['processed']}/{summary['total']} orders. "
                    f"Remaining orders can be resumed by running the same command again."
                )

        logger.info(
            f"Batch extraction complete: {summary['successful']} successful, "
            f"{summary['skipped']} skipped (already exist), "
            f"{summary['failed']} failed out of {summary['processed']} processed "
            f"(elapsed: {elapsed_str}, avg: {summary['avg_request_time']:.1f}s/order)"
        )

        return {
            "total": summary["total"],
            "processed": summary["processed"],
            "successful": summary["successful"],
            "skipped": summary["skipped"],
            "failed": summary["failed"],
            "failed_order_ids": failed_order_ids,
            "elapsed_seconds": summary["elapsed_seconds"],
            "avg_request_time": summary["avg_request_time"],
            "stopped_early": stopped_early,
            "stop_reason": stop_reason
        }

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
