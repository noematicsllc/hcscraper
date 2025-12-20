"""Bulk billing document extraction - search and download billing documents by date range."""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from ..api.client import HallmarkAPIClient
from ..utils.config import BANNER_HALLMARK_CUSTOMER_IDS
from .billing_document_extractor import BillingDocumentExtractor


logger = logging.getLogger(__name__)


class BulkBillingExtractor:
    """Search for billing documents by date range and download all results."""

    def __init__(
        self,
        api_client: HallmarkAPIClient,
        output_directory: Path,
        customer_ids: Optional[Union[List[str], str]] = None,
        billing_status: str = "All",
        save_json: bool = True,
        save_csv: bool = True
    ):
        """Initialize bulk billing extractor.

        Args:
            api_client: Configured API client
            output_directory: Directory for output files
            customer_ids: Customer IDs to search for (default: Banner's Hallmark stores)
            billing_status: Billing status filter ("All", "Paid", "Unpaid")
            save_json: Whether to save JSON files (default: True)
            save_csv: Whether to save CSV files (default: True)
        """
        self.api_client = api_client
        self.output_directory = Path(output_directory)
        self.billing_status = billing_status
        self.save_json = save_json
        self.save_csv = save_csv

        # Use Banner's Hallmark customer IDs as default
        if customer_ids is None:
            self.customer_ids = BANNER_HALLMARK_CUSTOMER_IDS
        elif isinstance(customer_ids, str):
            self.customer_ids = customer_ids.split(",")
        else:
            self.customer_ids = customer_ids

        # Initialize the single billing document extractor for downloading
        self.billing_extractor = BillingDocumentExtractor(
            api_client=api_client,
            output_directory=output_directory,
            save_json=save_json,
            save_csv=save_csv
        )

    def search_billing_documents(
        self,
        start_date: str,
        end_date: str,
        page_size: int = 50
    ) -> List[Dict[str, Any]]:
        """Search for all billing documents in the date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            page_size: Number of results per page (default: 50)

        Returns:
            List of billing document records from search results
        """
        logger.info(f"Searching for billing documents from {start_date} to {end_date}")

        all_documents = []
        page_number = 1
        total_pages = None

        while True:
            logger.info(f"Fetching page {page_number}" + (f" of {total_pages}" if total_pages else ""))

            result = self.api_client.search_billing_documents(
                customer_ids=self.customer_ids,
                start_date=start_date,
                end_date=end_date,
                billing_status=self.billing_status,
                page_size=page_size,
                page_number=page_number
            )

            if result is None:
                logger.error(f"Failed to fetch page {page_number}")
                break

            # Extract billing document records from result
            documents = result.get("billingDocumentRecords", [])
            if not documents:
                documents = result.get("records", [])

            if not documents:
                logger.debug(f"No billing documents found on page {page_number}")
                # Check if this is the first page with no results
                if page_number == 1:
                    logger.info("No billing documents found for the given date range")
                break

            all_documents.extend(documents)
            logger.info(f"Found {len(documents)} billing documents on page {page_number}")

            # Check pagination info
            total_records = result.get("totalRecords", 0)
            if total_records == 0:
                total_records = result.get("totalCount", len(all_documents))

            if total_records > 0:
                total_pages = (total_records + page_size - 1) // page_size
                logger.debug(f"Total records: {total_records}, total pages: {total_pages}")

            # Check if we've fetched all pages
            if len(all_documents) >= total_records or len(documents) < page_size:
                break

            page_number += 1

        logger.info(f"Search complete. Found {len(all_documents)} total billing documents")
        return all_documents

    def extract_billing_document_ids(self, documents: List[Dict[str, Any]]) -> List[str]:
        """Extract billing document IDs from search results.

        Args:
            documents: List of billing document records from search

        Returns:
            List of billing document IDs
        """
        document_ids = []
        for doc in documents:
            # Try different possible field names for billing document ID
            doc_id = (
                doc.get("billingDocumentNumber") or
                doc.get("billingDocumentId") or
                doc.get("invoiceNumber") or
                doc.get("Id")
            )
            if doc_id:
                document_ids.append(str(doc_id))
            else:
                logger.warning(f"Could not extract billing document ID from record: {doc}")

        logger.info(f"Extracted {len(document_ids)} billing document IDs")
        return document_ids

    def search_and_download(
        self,
        start_date: str,
        end_date: str,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """Search for billing documents and download all results.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            page_size: Number of results per page (default: 50)

        Returns:
            Dict with extraction statistics
        """
        logger.info(f"Starting bulk billing document extraction from {start_date} to {end_date}")

        # Step 1: Search for all billing documents
        documents = self.search_billing_documents(start_date, end_date, page_size)

        if not documents:
            logger.info("No billing documents to download")
            return {
                "total_found": 0,
                "total_downloaded": 0,
                "successful": 0,
                "failed": 0,
                "failed_billing_document_ids": []
            }

        # Step 2: Extract billing document IDs
        document_ids = self.extract_billing_document_ids(documents)

        if not document_ids:
            logger.error("No billing document IDs could be extracted from search results")
            return {
                "total_found": len(documents),
                "total_downloaded": 0,
                "successful": 0,
                "failed": 0,
                "failed_billing_document_ids": []
            }

        logger.info(f"Found {len(document_ids)} billing documents to download")

        # Step 3: Download each billing document using the single document extractor
        stats = self.billing_extractor.extract_billing_documents(document_ids)

        # Add search stats
        stats["total_found"] = len(documents)
        stats["total_downloaded"] = stats["total"]

        return stats

    def get_search_summary(
        self,
        start_date: str,
        end_date: str
    ) -> Optional[Dict[str, Any]]:
        """Get a summary of billing documents matching the search criteria without downloading.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            Dict with search summary, or None if search fails
        """
        logger.info(f"Getting search summary for billing documents from {start_date} to {end_date}")

        # Just fetch the first page to get total count
        result = self.api_client.search_billing_documents(
            customer_ids=self.customer_ids,
            start_date=start_date,
            end_date=end_date,
            billing_status=self.billing_status,
            page_size=1,
            page_number=1
        )

        if result is None:
            logger.error("Failed to get billing documents search summary")
            return None

        total_records = result.get("totalRecords", 0)
        if total_records == 0:
            total_records = result.get("totalCount", 0)

        return {
            "start_date": start_date,
            "end_date": end_date,
            "billing_status": self.billing_status,
            "total_billing_documents": total_records,
            "customer_ids_count": len(self.customer_ids)
        }
