"""CSV storage for order data."""

import csv
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List


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

    def save_order(self, order_id: str, order_data: Dict[str, Any]) -> Path:
        """Save order data to CSV file (flattened format).

        Args:
            order_id: The order ID
            order_data: The order data to save

        Returns:
            Path to the saved file

        Raises:
            IOError: If file write fails
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"order_{order_id}_{timestamp}.csv"
        filepath = self.output_directory / filename

        try:
            # Extract line items if available
            rows = self._flatten_order_data(order_id, order_data)

            if not rows:
                logger.warning(f"No data to write for order {order_id}")
                return filepath

            # Write CSV
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)

            logger.info(f"Saved order {order_id} to {filepath}")
            return filepath

        except IOError as e:
            logger.error(f"Failed to write CSV file {filepath}: {e}")
            raise

    def _flatten_order_data(self, order_id: str, order_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Flatten order data into CSV rows.

        Args:
            order_id: The order ID
            order_data: The order data

        Returns:
            List of dicts representing CSV rows
        """
        # This is a simple implementation - you may need to adjust based on actual data structure
        rows = []

        # Try to extract line items or other list data
        # The exact structure will depend on the API response
        if isinstance(order_data, dict):
            # If there are line items, create one row per item
            line_items = order_data.get('lineItems', order_data.get('items', []))

            if line_items and isinstance(line_items, list):
                for item in line_items:
                    if isinstance(item, dict):
                        row = {
                            'order_id': order_id,
                            'extracted_at': datetime.now().isoformat(),
                            **item
                        }
                        rows.append(row)
            else:
                # No line items, just save order-level data
                row = {
                    'order_id': order_id,
                    'extracted_at': datetime.now().isoformat(),
                    **order_data
                }
                rows.append(row)

        return rows

    def save_billing_document(self, billing_document_id: str, billing_data: Dict[str, Any]) -> Path:
        """Save billing document data to CSV file (flattened format).

        Args:
            billing_document_id: The billing document ID
            billing_data: The billing document data to save

        Returns:
            Path to the saved file

        Raises:
            IOError: If file write fails
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"billing_{billing_document_id}_{timestamp}.csv"
        filepath = self.output_directory / filename

        try:
            # Extract line items if available
            rows = self._flatten_billing_data(billing_document_id, billing_data)

            if not rows:
                logger.warning(f"No data to write for billing document {billing_document_id}")
                return filepath

            # Write CSV
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)

            logger.info(f"Saved billing document {billing_document_id} to {filepath}")
            return filepath

        except IOError as e:
            logger.error(f"Failed to write CSV file {filepath}: {e}")
            raise

    def _flatten_billing_data(self, billing_document_id: str, billing_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Flatten billing document data into CSV rows.

        Args:
            billing_document_id: The billing document ID
            billing_data: The billing document data

        Returns:
            List of dicts representing CSV rows
        """
        rows = []

        if isinstance(billing_data, dict):
            # If there are line items, create one row per item
            line_items = billing_data.get('lineItems', billing_data.get('items', []))

            if line_items and isinstance(line_items, list):
                for item in line_items:
                    if isinstance(item, dict):
                        row = {
                            'billing_document_id': billing_document_id,
                            'extracted_at': datetime.now().isoformat(),
                            **item
                        }
                        rows.append(row)
            else:
                # No line items, just save document-level data
                row = {
                    'billing_document_id': billing_document_id,
                    'extracted_at': datetime.now().isoformat(),
                    **billing_data
                }
                rows.append(row)

        return rows
