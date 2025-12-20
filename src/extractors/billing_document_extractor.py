"""Billing document data extraction coordinator."""

import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..api.client import HallmarkAPIClient
from ..storage.json_writer import JSONWriter
from ..storage.csv_writer import CSVWriter
from .order_extractor import ProgressTracker


logger = logging.getLogger(__name__)


class BillingDocumentExtractor:
    """Coordinates billing document data extraction and storage."""

    def __init__(
        self,
        api_client: HallmarkAPIClient,
        output_directory: Path,
        save_json: bool = True,
        save_csv: bool = True
    ):
        """Initialize billing document extractor.

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

    def extract_single_billing_document(self, billing_document_id: str) -> bool:
        """Extract data for a single billing document.

        Args:
            billing_document_id: The billing document ID to extract

        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Extracting billing document {billing_document_id}")

        try:
            # Retrieve billing document data from API
            billing_data = self.api_client.get_billing_document_detail(billing_document_id)

            if billing_data is None:
                logger.error(f"Failed to retrieve billing document {billing_document_id}")
                return False

            # Save to files
            saved_files = []

            if self.save_json:
                try:
                    filepath = self.json_writer.save_billing_document(billing_document_id, billing_data)
                    saved_files.append(str(filepath))
                except Exception as e:
                    logger.error(f"Failed to save JSON for billing document {billing_document_id}: {e}")

            if self.save_csv:
                try:
                    filepath = self.csv_writer.save_billing_document(billing_document_id, billing_data)
                    saved_files.append(str(filepath))
                except Exception as e:
                    logger.error(f"Failed to save CSV for billing document {billing_document_id}: {e}")

            if saved_files:
                logger.info(f"Successfully extracted billing document {billing_document_id}, saved {len(saved_files)} files")
                return True
            else:
                logger.error(f"No files saved for billing document {billing_document_id}")
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

        # Initialize progress tracker
        progress = ProgressTracker(total=len(billing_document_ids), item_type="billing document")
        failed_billing_document_ids = []

        for billing_document_id in billing_document_ids:
            request_start = time.time()

            success = self.extract_single_billing_document(billing_document_id)

            request_time = time.time() - request_start
            progress.update(success, request_time)

            if not success:
                failed_billing_document_ids.append(billing_document_id)

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
            f"(elapsed: {elapsed_str}, avg: {summary['avg_request_time']:.1f}s/doc)"
        )

        return {
            "total": summary["total"],
            "successful": summary["successful"],
            "failed": summary["failed"],
            "failed_billing_document_ids": failed_billing_document_ids,
            "elapsed_seconds": summary["elapsed_seconds"],
            "avg_request_time": summary["avg_request_time"]
        }
