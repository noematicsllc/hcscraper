"""Bulk order extraction - search and download orders by date range."""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from ..api.client import HallmarkAPIClient
from ..utils.config import BANNER_HALLMARK_CUSTOMER_IDS
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
        save_csv: bool = True
    ):
        """Initialize bulk order extractor.

        Args:
            api_client: Configured API client
            output_directory: Directory for output files
            customer_ids: Customer IDs to search for (default: Banner's Hallmark stores)
            save_json: Whether to save JSON files (default: True)
            save_csv: Whether to save CSV files (default: True)
        """
        self.api_client = api_client
        self.output_directory = Path(output_directory)
        self.save_json = save_json
        self.save_csv = save_csv

        # Use Banner's Hallmark customer IDs as default
        if customer_ids is None:
            self.customer_ids = BANNER_HALLMARK_CUSTOMER_IDS
        elif isinstance(customer_ids, str):
            self.customer_ids = customer_ids.split(",")
        else:
            self.customer_ids = customer_ids

        # Initialize the single order extractor for downloading
        self.order_extractor = OrderExtractor(
            api_client=api_client,
            output_directory=output_directory,
            save_json=save_json,
            save_csv=save_csv
        )

    def search_orders(
        self,
        start_date: str,
        end_date: str,
        page_size: int = 50
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

            # Extract order records from result
            orders = result.get("orderRecords", [])
            if not orders:
                orders = result.get("records", [])

            if not orders:
                logger.debug(f"No orders found on page {page_number}")
                # Check if this is the first page with no results
                if page_number == 1:
                    logger.info("No orders found for the given date range")
                break

            all_orders.extend(orders)
            logger.info(f"Found {len(orders)} orders on page {page_number}")

            # Check pagination info
            total_records = result.get("totalRecords", 0)
            if total_records == 0:
                total_records = result.get("totalCount", len(all_orders))

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
