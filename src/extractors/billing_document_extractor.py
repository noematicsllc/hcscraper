"""Billing document data extraction coordinator."""

import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..api.client import HallmarkAPIClient
from ..utils.config import DEFAULT_MAX_CONSECUTIVE_FAILURES
from .order_extractor import ProgressTracker
from .base_extractor import BaseExtractor


logger = logging.getLogger(__name__)


class BillingDocumentExtractor(BaseExtractor):
    """Coordinates billing document data extraction and storage."""

    def __init__(
        self,
        api_client: HallmarkAPIClient,
        output_directory: Path,
        save_json: bool = True,
        update_mode: bool = False,
        max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES
    ):
        """Initialize billing document extractor.

        Args:
            api_client: Configured API client
            output_directory: Directory for output files
            save_json: Whether to save JSON files (default: True)
            update_mode: If True, re-download existing files. If False, skip existing files (default: False)
            max_consecutive_failures: Maximum consecutive failures before stopping (default: DEFAULT_MAX_CONSECUTIVE_FAILURES)
        """
        # Initialize base class (handles database connection and JSON writer)
        super().__init__(api_client, output_directory, save_json, update_mode)
        
        # BillingDocumentExtractor-specific initialization
        self.max_consecutive_failures = max_consecutive_failures

    def extract_single_billing_document(self, billing_document_id: str) -> bool:
        """Extract data for a single billing document.

        Args:
            billing_document_id: The billing document ID to extract

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Extracting billing document {billing_document_id}")

        # Check if file already exists
        if not self.update_mode and self.save_json:
            if self.json_writer.billing_document_file_exists(billing_document_id):
                logger.info(f"Billing document {billing_document_id} already exists, skipping (use --update to re-download)")
                return True

        try:
            # Retrieve billing document data from API
            billing_data = self.api_client.get_billing_document_detail(billing_document_id)

            if billing_data is None:
                logger.error(f"Failed to retrieve billing document {billing_document_id}")
                return False

            # Save to file
            if self.save_json:
                try:
                    filepath = self.json_writer.save_billing_document(billing_document_id, billing_data)
                    logger.info(f"Successfully extracted billing document {billing_document_id}, saved to {filepath}")
                    return True
                except Exception as e:
                    logger.error(f"Failed to save JSON for billing document {billing_document_id}: {e}")
                    return False
            else:
                logger.warning(f"save_json is False, no file saved for billing document {billing_document_id}")
                return False

        except Exception as e:
            logger.error(f"Error extracting billing document {billing_document_id}: {e}", exc_info=True)
            return False

    def extract_billing_documents(self, billing_document_ids: List[str]) -> Dict[str, Any]:
        """Extract data for multiple billing documents.

        Args:
            billing_document_ids: List of billing document IDs to extract

        Returns:
            Dict with extraction statistics
        """
        logger.info(f"Starting batch extraction of {len(billing_document_ids)} billing documents")
        if not self.update_mode:
            logger.info("Update mode disabled - existing files will be skipped")

        # Initialize progress tracker
        progress = ProgressTracker(total=len(billing_document_ids), item_type="billing document")
        failed_billing_document_ids = []
        consecutive_failures = 0
        stopped_early = False

        for billing_document_id in billing_document_ids:
            request_start = time.time()

            success = self.extract_single_billing_document(billing_document_id)

            request_time = time.time() - request_start
            progress.update(success, request_time)

            if not success:
                failed_billing_document_ids.append(billing_document_id)
                consecutive_failures += 1
                
                # Check if we've exceeded the failure threshold
                if consecutive_failures >= self.max_consecutive_failures:
                    logger.error(
                        f"Stopping extraction after {consecutive_failures} consecutive failures "
                        f"(threshold: {self.max_consecutive_failures})"
                    )
                    stopped_early = True
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
            logger.warning(
                f"Extraction stopped early due to consecutive failures. "
                f"Processed {summary['processed']}/{summary['total']} billing documents. "
                f"Remaining documents can be resumed by running the same command again."
            )

        logger.info(
            f"Batch extraction complete: {summary['successful']} successful, "
            f"{summary['failed']} failed out of {summary['processed']} processed "
            f"(elapsed: {elapsed_str}, avg: {summary['avg_request_time']:.1f}s/doc)"
        )

        return {
            "total": summary["total"],
            "processed": summary["processed"],
            "successful": summary["successful"],
            "failed": summary["failed"],
            "failed_billing_document_ids": failed_billing_document_ids,
            "elapsed_seconds": summary["elapsed_seconds"],
            "avg_request_time": summary["avg_request_time"],
            "stopped_early": stopped_early
        }

