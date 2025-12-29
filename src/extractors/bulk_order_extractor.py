"""Bulk order extraction - search and download orders by date range."""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from ..api.client import HallmarkAPIClient
from ..utils.config import BANNER_HALLMARK_CUSTOMER_IDS, DEFAULT_MAX_CONSECUTIVE_FAILURES
from .order_extractor import OrderExtractor


logger = logging.getLogger(__name__)


class BulkOrderExtractor:
    """Search for orders by date range and download all results."""

    def __init__(
        self,
        api_client: HallmarkAPIClient,
        output_directory: Path,
        customer_ids: Optional[Union[List[str], str]] = None,
        save_json: bool = True,
        update_mode: bool = False,
        max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES
    ):
        """Initialize bulk order extractor.

        Args:
            api_client: Configured API client
            output_directory: Directory for output files
            customer_ids: Customer IDs to search for (default: Banner's Hallmark stores)
            save_json: Whether to save JSON files (default: True)
            update_mode: If True, re-download existing files. If False, skip existing files (default: False)
            max_consecutive_failures: Maximum consecutive failures before stopping (default: DEFAULT_MAX_CONSECUTIVE_FAILURES)
        """
        self.api_client = api_client
        self.output_directory = Path(output_directory)
        self.save_json = save_json
        self.update_mode = update_mode
        self.max_consecutive_failures = max_consecutive_failures

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

        # Initialize the single order extractor for downloading
        self.order_extractor = OrderExtractor(
            api_client=api_client,
            output_directory=output_directory,
            save_json=save_json,
            update_mode=update_mode,
            max_consecutive_failures=max_consecutive_failures
        )

    def search_orders(
        self,
        start_date: str,
        end_date: str,
        page_size: int = 50  # API returns array when pageSize > 1, single object when pageSize = 1
    ) -> List[Dict[str, Any]]:
        """Search for all orders in the date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            page_size: Number of results per page (default: 50)

        Returns:
            List of order records from search results
        """
        logger.info(f"Searching for orders from {start_date} to {end_date}")
        logger.info(f"Searching with {len(self.customer_ids)} customer IDs: {self.customer_ids[:5]}{'...' if len(self.customer_ids) > 5 else ''}")

        all_orders = []
        page_number = 1
        total_pages = None

        while True:
            logger.info(f"Fetching page {page_number}" + (f" of {total_pages}" if total_pages else ""))

            result = self.api_client.search_orders(
                customer_ids=self.customer_ids,
                start_date=start_date,
                end_date=end_date,
                page_size=page_size,
                page_number=page_number
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
                        if 'orderRecords' in nested_result:
                            orders_list = nested_result.get('orderRecords', [])
                            logger.debug(f"Found orderRecords in nested result: {len(orders_list)} items")
                            if len(orders_list) > 0:
                                logger.debug(f"  First order record keys: {list(orders_list[0].keys()) if isinstance(orders_list[0], dict) else type(orders_list[0])}")
                        if 'records' in nested_result:
                            records_list = nested_result.get('records', [])
                            logger.debug(f"Found records in nested result: {len(records_list)} items")
                            if len(records_list) > 0:
                                logger.debug(f"  First record keys: {list(records_list[0].keys()) if isinstance(records_list[0], dict) else type(records_list[0])}")
                    elif isinstance(nested_result, list):
                        logger.debug(f"Nested 'result' is a list with {len(nested_result)} items")
                if 'orderRecords' in result:
                    logger.debug(f"orderRecords type: {type(result.get('orderRecords'))}, length: {len(result.get('orderRecords', []))}")
                if 'records' in result:
                    logger.debug(f"records type: {type(result.get('records'))}, length: {len(result.get('records', []))}")
                # Also check pageInfo
                if 'pageInfo' in result:
                    page_info = result.get('pageInfo', {})
                    logger.debug(f"pageInfo: {page_info}")
                if 'success' in result:
                    logger.debug(f"success: {result.get('success')}")

            # Extract order records from result
            # The API response structure is: result.result (single object) or result.result (array)
            # Based on debug response, result.result can be:
            # 1. A single order object (when pagesize=1)
            # 2. An array of order objects (when pagesize>1)
            # 3. A dict with orderRecords/records keys
            
            if isinstance(result, dict) and 'result' in result:
                nested_result = result['result']
                
                # If nested_result is a list, that's the orders array
                if isinstance(nested_result, list):
                    logger.debug(f"Nested 'result' is a list with {len(nested_result)} orders")
                    orders = nested_result
                elif isinstance(nested_result, dict):
                    # Check if it's a single order object (has orderId, orderStatus, etc.)
                    if 'orderId' in nested_result or 'orderStatus' in nested_result:
                        logger.debug(f"Nested 'result' is a single order object - wrapping in array")
                        # It's a single order object, wrap it in an array
                        orders = [nested_result]
                    else:
                        # Try standard keys for arrays
                        orders = nested_result.get("orderRecords", [])
                        if not orders:
                            orders = nested_result.get("records", [])
                        # Also check for totalRecords in nested result
                        if not orders and 'totalRecords' in nested_result:
                            logger.debug(f"Nested result has totalRecords={nested_result.get('totalRecords')} but no orderRecords/records")
                            # Maybe orders are in a different key - log all keys
                            logger.debug(f"All nested result keys: {list(nested_result.keys())}")
                else:
                    orders = []
            else:
                # Try top-level keys
                orders = result.get("orderRecords", [])
                if not orders:
                    orders = result.get("records", [])
                    # Also check if result itself is a single order object
                    if not orders and isinstance(result, dict) and ('orderId' in result or 'orderStatus' in result):
                        logger.debug(f"Result is a single order object - wrapping in array")
                        orders = [result]

            if not orders:
                logger.debug(f"No orders found on page {page_number}")
                # If we still have no orders, dump the full result structure for debugging
                if page_number == 1:
                    logger.warning("No orders found - dumping full result structure for debugging")
                    import json
                    logger.debug(f"Full result structure (first 2000 chars): {json.dumps(result, indent=2, default=str)[:2000]}")
                # Check if this is the first page with no results
                if page_number == 1:
                    logger.info("No orders found for the given date range")
                break

            all_orders.extend(orders)
            logger.info(f"Found {len(orders)} orders on page {page_number}")

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
            
            # Fallback to count of orders found if still 0
            if total_records == 0:
                total_records = len(all_orders)

            if total_records > 0:
                total_pages = (total_records + page_size - 1) // page_size
                logger.debug(f"Total records: {total_records}, total pages: {total_pages}")

            # Check if we've fetched all pages
            if len(all_orders) >= total_records or len(orders) < page_size:
                break

            page_number += 1

        logger.info(f"Search complete. Found {len(all_orders)} total orders")
        return all_orders

    def extract_order_ids(self, orders: List[Dict[str, Any]]) -> List[str]:
        """Extract order IDs from search results.

        Args:
            orders: List of order records from search

        Returns:
            List of order IDs
        """
        order_ids = []
        for order in orders:
            # Try different possible field names for order ID
            order_id = order.get("orderId") or order.get("orderNumber") or order.get("Id")
            if order_id:
                order_ids.append(str(order_id))
            else:
                logger.warning(f"Could not extract order ID from record: {order}")

        logger.info(f"Extracted {len(order_ids)} order IDs")
        return order_ids

    def search_and_download(
        self,
        start_date: str,
        end_date: str,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """Search for orders and download all results.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            page_size: Number of results per page (default: 50)

        Returns:
            Dict with extraction statistics
        """
        logger.info(f"Starting bulk order extraction from {start_date} to {end_date}")

        # Step 1: Search for all orders
        orders = self.search_orders(start_date, end_date, page_size)

        if not orders:
            logger.info("No orders to download")
            return {
                "total_found": 0,
                "total_downloaded": 0,
                "successful": 0,
                "failed": 0,
                "failed_order_ids": []
            }

        # Step 2: Extract order IDs
        order_ids = self.extract_order_ids(orders)

        if not order_ids:
            logger.error("No order IDs could be extracted from search results")
            return {
                "total_found": len(orders),
                "total_downloaded": 0,
                "successful": 0,
                "failed": 0,
                "failed_order_ids": []
            }

        logger.info(f"Found {len(order_ids)} orders to download")

        # Step 3: Download each order using the single order extractor
        stats = self.order_extractor.extract_orders(order_ids)

        # Add search stats
        stats["total_found"] = len(orders)
        stats["total_downloaded"] = stats["total"]

        return stats

    def get_search_summary(
        self,
        start_date: str,
        end_date: str
    ) -> Optional[Dict[str, Any]]:
        """Get a summary of orders matching the search criteria without downloading.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            Dict with search summary, or None if search fails
        """
        logger.info(f"Getting search summary for {start_date} to {end_date}")

        # Just fetch the first page to get total count
        result = self.api_client.search_orders(
            customer_ids=self.customer_ids,
            start_date=start_date,
            end_date=end_date,
            page_size=1,
            page_number=1
        )

        if result is None:
            logger.error("Failed to get search summary")
            return None

        total_records = result.get("totalRecords", 0)
        if total_records == 0:
            total_records = result.get("totalCount", 0)

        return {
            "start_date": start_date,
            "end_date": end_date,
            "total_orders": total_records,
            "customer_ids_count": len(self.customer_ids)
        }

    def close(self) -> None:
        """Close database connection in the internal order extractor.
        
        Should be called when done with the extractor to prevent connection leaks.
        """
        if hasattr(self, 'order_extractor'):
            self.order_extractor.close()

    def __enter__(self):
        """Context manager entry - returns self."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes database connection."""
        self.close()
        return False  # Don't suppress exceptions
