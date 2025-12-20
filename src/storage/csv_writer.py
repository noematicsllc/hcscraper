"""CSV storage for order data."""

import csv
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple


logger = logging.getLogger(__name__)


class CSVWriter:
    """Handles writing order data to CSV files."""

    def __init__(self, output_directory: Path):
        """Initialize CSV writer.

        Args:
            output_directory: Directory to write CSV files
        """
        self.output_directory = Path(output_directory)
        self.output_directory.mkdir(parents=True, exist_ok=True)

    def _extract_date_parts(self, order_data: Dict[str, Any]) -> Tuple[str, str]:
        """Extract year and month from order data.

        Args:
            order_data: The order data dictionary

        Returns:
            Tuple of (year, month) as strings (e.g., ("2025", "01"))
        """
        # Try various date field names
        date_str = None
        for date_field in ['orderDate', 'orderCreationDate', 'creationDate', 'date']:
            if date_field in order_data and order_data[date_field]:
                date_str = order_data[date_field]
                break

        if date_str:
            try:
                # Try parsing various date formats
                if isinstance(date_str, str):
                    # Handle ISO format: "2025-01-15T10:30:00" or "2025-01-15"
                    if 'T' in date_str:
                        date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    else:
                        date_obj = datetime.strptime(date_str[:10], '%Y-%m-%d')
                elif isinstance(date_str, (int, float)):
                    # Handle timestamp
                    date_obj = datetime.fromtimestamp(date_str)
                else:
                    raise ValueError(f"Unknown date format: {type(date_str)}")

                year = date_obj.strftime('%Y')
                month = date_obj.strftime('%m')
                return year, month
            except (ValueError, AttributeError) as e:
                logger.warning(f"Failed to parse date '{date_str}': {e}, using current date")

        # Fallback to current date
        now = datetime.now()
        return now.strftime('%Y'), now.strftime('%m')

    def _extract_store_id(self, order_data: Dict[str, Any]) -> str:
        """Extract store ID from order data.

        Args:
            order_data: The order data dictionary

        Returns:
            Store ID as string (e.g., "101")
        """
        # Try various store ID field names
        for store_field in ['storeNumber', 'storeId', 'storeID', 'customerId', 'customerID']:
            if store_field in order_data and order_data[store_field]:
                store_id = str(order_data[store_field])
                # Remove leading "1000" if present (some IDs like "1000055874" -> "55874")
                if store_id.startswith('1000'):
                    store_id = store_id[4:]
                return store_id

        # Fallback to "unknown" if no store ID found
        logger.warning("No store ID found in order data, using 'unknown'")
        return "unknown"

    def _get_order_directory(self, order_data: Dict[str, Any]) -> Path:
        """Get the hierarchical directory path for an order.

        Args:
            order_data: The order data dictionary

        Returns:
            Path to the order's directory (e.g., /data/2025/01/store_101)
        """
        year, month = self._extract_date_parts(order_data)
        store_id = self._extract_store_id(order_data)

        directory = self.output_directory / year / month / f"store_{store_id}"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def save_order(self, order_id: str, order_data: Dict[str, Any]) -> Path:
        """Save order line items to CSV file in hierarchical directory structure.

        Args:
            order_id: The order ID
            order_data: The order data to save

        Returns:
            Path to the saved file

        Raises:
            IOError: If file write fails
        """
        # Get hierarchical directory based on date and store
        order_dir = self._get_order_directory(order_data)
        filename = f"order_{order_id}_items.csv"
        filepath = order_dir / filename

        try:
            # Extract only line items (not full metadata)
            rows = self._flatten_order_data(order_id, order_data)

            if not rows:
                logger.warning(f"No line items to write for order {order_id}")
                # Still create the file (empty) so structure is consistent
                filepath.touch()
                return filepath

            # Write CSV
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)

            logger.info(f"Saved order {order_id} items to {filepath}")
            return filepath

        except IOError as e:
            logger.error(f"Failed to write CSV file {filepath}: {e}")
            raise

    def _flatten_order_data(self, order_id: str, order_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract line items from order data into CSV rows.

        Only extracts line items (not full order metadata).

        Args:
            order_id: The order ID
            order_data: The order data

        Returns:
            List of dicts representing CSV rows (one per line item)
        """
        rows = []

        if isinstance(order_data, dict):
            # Extract line items - try various field names
            line_items = (
                order_data.get('lineItems') or
                order_data.get('items') or
                order_data.get('orderItems') or
                []
            )

            if line_items and isinstance(line_items, list):
                # Create one row per line item
                for item in line_items:
                    if isinstance(item, dict):
                        row = {
                            'order_id': order_id,
                            **item
                        }
                        rows.append(row)
            # Note: If no line items, return empty list (don't save order metadata to CSV)

        return rows

    def save_billing_document(self, billing_document_id: str, billing_data: Dict[str, Any]) -> Path:
        """Save billing document line items to CSV file in hierarchical directory structure.

        Args:
            billing_document_id: The billing document ID
            billing_data: The billing document data to save

        Returns:
            Path to the saved file

        Raises:
            IOError: If file write fails
        """
        # Get hierarchical directory based on date and store (reuse order method)
        document_dir = self._get_order_directory(billing_data)
        filename = f"billing_{billing_document_id}_items.csv"
        filepath = document_dir / filename

        try:
            # Extract only line items (not full metadata)
            rows = self._flatten_billing_data(billing_document_id, billing_data)

            if not rows:
                logger.warning(f"No line items to write for billing document {billing_document_id}")
                # Still create the file (empty) so structure is consistent
                filepath.touch()
                return filepath

            # Write CSV
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)

            logger.info(f"Saved billing document {billing_document_id} items to {filepath}")
            return filepath

        except IOError as e:
            logger.error(f"Failed to write CSV file {filepath}: {e}")
            raise

    def _flatten_billing_data(self, billing_document_id: str, billing_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract line items from billing document data into CSV rows.

        Only extracts line items (not full document metadata).

        Args:
            billing_document_id: The billing document ID
            billing_data: The billing document data

        Returns:
            List of dicts representing CSV rows (one per line item)
        """
        rows = []

        if isinstance(billing_data, dict):
            # Extract line items - try various field names
            line_items = (
                billing_data.get('lineItems') or
                billing_data.get('items') or
                billing_data.get('invoiceItems') or
                []
            )

            if line_items and isinstance(line_items, list):
                # Create one row per line item
                for item in line_items:
                    if isinstance(item, dict):
                        row = {
                            'billing_document_id': billing_document_id,
                            **item
                        }
                        rows.append(row)
            # Note: If no line items, return empty list (don't save document metadata to CSV)

        return rows

    def save_delivery(self, delivery_id: str, delivery_data: Dict[str, Any]) -> Path:
        """Save delivery data to CSV file (flattened format).

        Args:
            delivery_id: The delivery ID
            delivery_data: The delivery data to save

        Returns:
            Path to the saved file

        Raises:
            IOError: If file write fails
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"delivery_{delivery_id}_{timestamp}.csv"
        filepath = self.output_directory / filename

        try:
            # Extract line items if available
            rows = self._flatten_delivery_data(delivery_id, delivery_data)

            if not rows:
                logger.warning(f"No data to write for delivery {delivery_id}")
                return filepath

            # Write CSV
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)

            logger.info(f"Saved delivery {delivery_id} to {filepath}")
            return filepath

        except IOError as e:
            logger.error(f"Failed to write CSV file {filepath}: {e}")
            raise

    def _flatten_delivery_data(self, delivery_id: str, delivery_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Flatten delivery data into CSV rows.

        Args:
            delivery_id: The delivery ID
            delivery_data: The delivery data

        Returns:
            List of dicts representing CSV rows
        """
        rows = []

        if isinstance(delivery_data, dict):
            # If there are line items, create one row per item
            line_items = delivery_data.get('lineItems', delivery_data.get('items', []))

            if line_items and isinstance(line_items, list):
                for item in line_items:
                    if isinstance(item, dict):
                        row = {
                            'delivery_id': delivery_id,
                            'extracted_at': datetime.now().isoformat(),
                            **item
                        }
                        rows.append(row)
            else:
                # No line items, just save delivery-level data
                row = {
                    'delivery_id': delivery_id,
                    'extracted_at': datetime.now().isoformat(),
                    **delivery_data
                }
                rows.append(row)

        return rows
