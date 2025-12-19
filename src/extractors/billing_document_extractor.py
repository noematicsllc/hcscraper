"""Billing document data extraction coordinator."""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..api.client import HallmarkAPIClient
from ..storage.json_writer import JSONWriter
from ..storage.csv_writer import CSVWriter


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

        stats = {
            "total": len(billing_document_ids),
            "successful": 0,
            "failed": 0,
            "failed_billing_document_ids": []
        }

        for idx, billing_document_id in enumerate(billing_document_ids, 1):
            logger.info(f"Processing billing document {idx}/{len(billing_document_ids)}: {billing_document_id}")

            success = self.extract_single_billing_document(billing_document_id)

            if success:
                stats["successful"] += 1
            else:
                stats["failed"] += 1
                stats["failed_billing_document_ids"].append(billing_document_id)

        logger.info(
            f"Batch extraction complete: {stats['successful']} successful, "
            f"{stats['failed']} failed out of {stats['total']} total"
        )

        return stats
