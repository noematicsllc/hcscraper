"""JSON storage for order data."""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Tuple


logger = logging.getLogger(__name__)


class JSONWriter:
    """Handles writing order data to JSON files."""

    def __init__(self, output_directory: Path):
        """Initialize JSON writer.

        Args:
            output_directory: Directory to write JSON files
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
        """Save order data to JSON file in hierarchical directory structure.

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
        filename = f"order_{order_id}_meta.json"
        filepath = order_dir / filename

        # Wrap data with metadata
        output = {
            "order_id": order_id,
            "extracted_at": datetime.now().isoformat(),
            "data": order_data
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved order {order_id} to {filepath}")
            return filepath

        except IOError as e:
            logger.error(f"Failed to write JSON file {filepath}: {e}")
            raise

    def save_billing_document(self, billing_document_id: str, billing_data: Dict[str, Any]) -> Path:
        """Save billing document data to JSON file in hierarchical directory structure.

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
        filename = f"billing_{billing_document_id}_meta.json"
        filepath = document_dir / filename

        # Wrap data with metadata
        output = {
            "billing_document_id": billing_document_id,
            "extracted_at": datetime.now().isoformat(),
            "data": billing_data
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved billing document {billing_document_id} to {filepath}")
            return filepath

        except IOError as e:
            logger.error(f"Failed to write JSON file {filepath}: {e}")
            raise

    def save_delivery(self, delivery_id: str, delivery_data: Dict[str, Any]) -> Path:
        """Save delivery data to JSON file.

        Args:
            delivery_id: The delivery ID
            delivery_data: The delivery data to save

        Returns:
            Path to the saved file

        Raises:
            IOError: If file write fails
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"delivery_{delivery_id}_{timestamp}.json"
        filepath = self.output_directory / filename

        # Wrap data with metadata
        output = {
            "delivery_id": delivery_id,
            "extracted_at": datetime.now().isoformat(),
            "data": delivery_data
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved delivery {delivery_id} to {filepath}")
            return filepath

        except IOError as e:
            logger.error(f"Failed to write JSON file {filepath}: {e}")
            raise
