"""Bulk billing document extraction - search and download billing documents by date range."""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from ..api.client import HallmarkAPIClient
from ..utils.config import BANNER_HALLMARK_CUSTOMER_IDS, DEFAULT_MAX_CONSECUTIVE_FAILURES
from .billing_document_extractor import BillingDocumentExtractor


logger = logging.getLogger(__name__)


class BulkBillingDocumentExtractor:
    """Extract billing documents by searching and downloading from date range."""

    def __init__(
        self,
        api_client: HallmarkAPIClient,
        output_directory: Path,
        customer_ids: Optional[Union[List[str], str]] = None,
        save_json: bool = True,
        update_mode: bool = False,
        max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES,
        billing_status: str = "All"
    ):
        """Initialize bulk billing document extractor.

        Args:
            api_client: Configured API client
            output_directory: Directory for output files
            customer_ids: Customer IDs to search for (default: Banner's Hallmark stores)
            save_json: Whether to save JSON files (default: True)
            update_mode: If True, re-download existing files. If False, skip existing files (default: False)
            max_consecutive_failures: Maximum consecutive failures before stopping (default: DEFAULT_MAX_CONSECUTIVE_FAILURES)
            billing_status: Billing status filter (default: "All")
        """
        self.api_client = api_client
        self.output_directory = Path(output_directory)
        self.save_json = save_json
        self.update_mode = update_mode
        self.max_consecutive_failures = max_consecutive_failures
        self.billing_status = billing_status

        # Use Banner's Hallmark customer IDs as default
        if customer_ids is None:
            self.customer_ids = BANNER_HALLMARK_CUSTOMER_IDS
            logger.info(f"Using default Banner's Hallmark customer IDs ({len(self.customer_ids)} stores)")
        elif isinstance(customer_ids, str):
            self.customer_ids = customer_ids.split(",")
            logger.info(f"Using provided customer IDs from string ({len(self.customer_ids)} stores)")
        else:
            self.customer_ids = customer_ids
            logger.info(f"Using provided customer IDs from list ({len(self.customer_ids)} stores)")

        # Initialize the single billing document extractor for downloading
        self.billing_document_extractor = BillingDocumentExtractor(
            api_client=api_client,
            output_directory=output_directory,
            save_json=save_json,
            update_mode=update_mode,
            max_consecutive_failures=max_consecutive_failures
        )

    def search_billing_documents(
        self,
        start_date: str,
        end_date: str,
        page_size: int = 50  # API returns array when pageSize > 1, single object when pageSize = 1
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

        all_billing_documents = []
        page_number = 1
        total_pages = None

        while True:
            logger.info(f"Fetching page {page_number}" + (f" of {total_pages}" if total_pages else ""))

            result = self.api_client.search_billing_documents(
                customer_ids=self.customer_ids,
                start_date=start_date,
                end_date=end_date,
                page_size=page_size,
                page_number=page_number,
                billing_status=self.billing_status
            )

            if result is None:
                logger.error(f"Failed to fetch page {page_number}")
                break

            # Debug: Log result structure in detail
            logger.debug(f"Search result structure: {list(result.keys()) if isinstance(result, dict) else type(result)}")
            if isinstance(result, dict):
                logger.debug(f"Result keys: {list(result.keys())}")
                # Check if result has nested 'result' key (common in Aura responses)
                if 'result' in result:
                    nested_result = result['result']
                    logger.debug(f"Nested 'result' type: {type(nested_result)}")
                    if isinstance(nested_result, dict):
                        logger.debug(f"Nested 'result' keys: {list(nested_result.keys())}")
                        # Log all keys and their types/lengths
                        for key, value in nested_result.items():
                            if isinstance(value, (list, dict)):
                                logger.debug(f"  {key}: {type(value).__name__} with {len(value)} items")
                            else:
                                logger.debug(f"  {key}: {type(value).__name__} = {str(value)[:100]}")
                        if 'billingDocumentRecords' in nested_result:
                            records_list = nested_result.get('billingDocumentRecords', [])
                            logger.debug(f"Found billingDocumentRecords in nested result: {len(records_list)} items")
                            if len(records_list) > 0:
                                logger.debug(f"  First billing document record keys: {list(records_list[0].keys()) if isinstance(records_list[0], dict) else type(records_list[0])}")
                        if 'records' in nested_result:
                            records_list = nested_result.get('records', [])
                            logger.debug(f"Found records in nested result: {len(records_list)} items")
                            if len(records_list) > 0:
                                logger.debug(f"  First record keys: {list(records_list[0].keys()) if isinstance(records_list[0], dict) else type(records_list[0])}")
                    elif isinstance(nested_result, list):
                        logger.debug(f"Nested 'result' is a list with {len(nested_result)} items")
                if 'billingDocumentRecords' in result:
                    logger.debug(f"billingDocumentRecords type: {type(result.get('billingDocumentRecords'))}, length: {len(result.get('billingDocumentRecords', []))}")
                if 'records' in result:
                    logger.debug(f"records type: {type(result.get('records'))}, length: {len(result.get('records', []))}")
                # Also check pageInfo
                if 'pageInfo' in result:
                    page_info = result.get('pageInfo', {})
                    logger.debug(f"pageInfo: {page_info}")
                if 'success' in result:
                    logger.debug(f"success: {result.get('success')}")

            # Extract billing document records from result
            # The API response structure when pageSize > 1 should be an array in result.result
            # When pageSize = 1, it returns a single object (which we saw in debug response)
            # When pageSize > 1, it should return an array of billing document objects
            
            if isinstance(result, dict) and 'result' in result:
                nested_result = result['result']
                
                # If nested_result is a list, that's the billing documents array (expected when pageSize > 1)
                if isinstance(nested_result, list):
                    logger.debug(f"Nested 'result' is a list with {len(nested_result)} billing documents")
                    billing_documents = nested_result
                elif isinstance(nested_result, dict):
                    # Check if it's a single billing document object (has billingDocumentNumber, billingDocumentDate, etc.)
                    # This happens when pageSize=1 - the API returns a single object instead of array
                    if 'billingDocumentNumber' in nested_result or 'billingDocumentDate' in nested_result:
                        logger.warning(f"API returned single billing document object instead of array (pageSize may be too small or API limitation)")
                        logger.warning(f"  This suggests the API may not support pageSize > 1, or there's a different endpoint for bulk results")
                        # It's a single billing document object, wrap it in an array
                        billing_documents = [nested_result]
                    else:
                        # Try standard keys for arrays
                        billing_documents = nested_result.get("billingDocumentRecords", [])
                        if not billing_documents:
                            billing_documents = nested_result.get("records", [])
                        # Also check for totalRecords in nested result
                        if not billing_documents and 'totalRecords' in nested_result:
                            logger.debug(f"Nested result has totalRecords={nested_result.get('totalRecords')} but no billingDocumentRecords/records")
                            # Maybe billing documents are in a different key - log all keys
                            logger.debug(f"All nested result keys: {list(nested_result.keys())}")
                else:
                    billing_documents = []
            else:
                # Try top-level keys
                billing_documents = result.get("billingDocumentRecords", [])
                if not billing_documents:
                    billing_documents = result.get("records", [])
                    # Also check if result itself is a single billing document object
                    if not billing_documents and isinstance(result, dict) and ('billingDocumentNumber' in result or 'billingDocumentDate' in result):
                        logger.debug(f"Result is a single billing document object - wrapping in array")
                        billing_documents = [result]

            if not billing_documents:
                logger.debug(f"No billing documents found on page {page_number}")
                # If we still have no billing documents, dump the full result structure for debugging
                if page_number == 1:
                    logger.warning("No billing documents found - dumping full result structure for debugging")
                    import json
                    logger.debug(f"Full result structure (first 2000 chars): {json.dumps(result, indent=2, default=str)[:2000]}")
                # Check if this is the first page with no results
                if page_number == 1:
                    logger.info("No billing documents found for the given date range")
                break

            all_billing_documents.extend(billing_documents)
            logger.info(f"Found {len(billing_documents)} billing documents on page {page_number}")

            # Check pagination info
            # First check nested result if it exists
            if isinstance(result, dict) and 'result' in result and isinstance(result['result'], dict):
                nested_result = result['result']
                total_records = nested_result.get("totalRecords", 0)
                if total_records == 0:
                    total_records = nested_result.get("totalCount", 0)
                # Also check pageInfo if available
                if total_records == 0 and 'pageInfo' in result:
                    page_info = result.get('pageInfo', {})
                    total_records = page_info.get("totalRecords", 0)
            else:
                total_records = result.get("totalRecords", 0)
                if total_records == 0:
                    total_records = result.get("totalCount", 0)
            
            # Fallback to count of billing documents found if still 0
            if total_records == 0:
                total_records = len(all_billing_documents)
            
            if total_records > 0:
                total_pages = (total_records + page_size - 1) // page_size
                logger.debug(f"Total records: {total_records}, total pages: {total_pages}")

            # Check if we've fetched all pages
            if len(all_billing_documents) >= total_records or len(billing_documents) < page_size:
                break

            page_number += 1

        logger.info(f"Search complete. Found {len(all_billing_documents)} total billing documents")
        return all_billing_documents

    def extract_billing_document_ids(self, billing_documents: List[Dict[str, Any]]) -> List[str]:
        """Extract billing document IDs from search results.

        Args:
            billing_documents: List of billing document records from search

        Returns:
            List of billing document IDs
        """
        billing_document_ids = []
        for doc in billing_documents:
            # Try different possible field names for billing document ID
            doc_id = doc.get("billingDocumentNumber") or doc.get("billingDocumentId") or doc.get("invoiceId")
            if doc_id:
                billing_document_ids.append(str(doc_id))
            else:
                logger.warning(f"Could not extract billing document ID from record: {list(doc.keys())}")
        
        return billing_document_ids

    def extract_billing_documents(
        self,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """Search and extract billing documents for a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            Dict with extraction statistics
        """
        logger.info(f"Starting bulk billing document extraction from {start_date} to {end_date}")

        # Search for billing documents
        billing_documents = self.search_billing_documents(start_date, end_date)

        if not billing_documents:
            logger.info("No billing documents to download")
            return {
                "total": 0,
                "processed": 0,
                "successful": 0,
                "failed": 0,
                "failed_billing_document_ids": [],
                "elapsed_seconds": 0,
                "avg_request_time": 0,
                "stopped_early": False
            }

        # Extract billing document IDs
        billing_document_ids = self.extract_billing_document_ids(billing_documents)
        logger.info(f"Found {len(billing_document_ids)} billing document IDs to download")

        # Download billing documents
        return self.billing_document_extractor.extract_billing_documents(billing_document_ids)

    def get_search_summary(
        self,
        start_date: str,
        end_date: str
    ) -> Optional[Dict[str, Any]]:
        """Get summary of billing documents found in search (without downloading).

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            Dict with search summary, or None if search fails
        """
        logger.info(f"Getting search summary for {start_date} to {end_date}")

        result = self.api_client.search_billing_documents(
            customer_ids=self.customer_ids,
            start_date=start_date,
            end_date=end_date,
            page_size=50,
            page_number=1,
            billing_status=self.billing_status
        )

        if result is None:
            return None

        # Extract billing documents from result (same logic as search_billing_documents)
        if isinstance(result, dict) and 'result' in result:
            nested_result = result['result']
            if isinstance(nested_result, list):
                billing_documents = nested_result
            elif isinstance(nested_result, dict):
                if 'billingDocumentNumber' in nested_result or 'billingDocumentDate' in nested_result:
                    billing_documents = [nested_result]
                else:
                    billing_documents = nested_result.get("billingDocumentRecords", [])
                    if not billing_documents:
                        billing_documents = nested_result.get("records", [])
            else:
                billing_documents = []
        else:
            billing_documents = result.get("billingDocumentRecords", [])
            if not billing_documents:
                billing_documents = result.get("records", [])

        # Get total records
        if isinstance(result, dict) and 'result' in result and isinstance(result['result'], dict):
            nested_result = result['result']
            total_records = nested_result.get("totalRecords", len(billing_documents))
        else:
            total_records = result.get("totalRecords", len(billing_documents))

        return {
            "start_date": start_date,
            "end_date": end_date,
            "total_billing_documents": total_records,
            "customer_ids_count": len(self.customer_ids)
        }

    def close(self) -> None:
        """Close database connection via billing document extractor."""
        # BillingDocumentExtractor inherits from BaseExtractor which handles database cleanup
        if hasattr(self.billing_document_extractor, 'close'):
            self.billing_document_extractor.close()

    def __enter__(self):
        """Context manager entry - returns self."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes database connection."""
        self.close()
        return False  # Don't suppress exceptions

