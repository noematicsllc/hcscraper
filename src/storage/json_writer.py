"""JSON storage for order data."""

import json
import logging
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Tuple, List, Optional, Callable

try:
    import psycopg
except ImportError:
    psycopg = None


logger = logging.getLogger(__name__)


class JSONWriter:
    """Handles writing order data to JSON files."""

    def __init__(self, output_directory: Path, db_connection: Optional[Any] = None):
        """Initialize JSON writer.

        Args:
            output_directory: Directory to write JSON files
            db_connection: Optional database connection (psycopg.Connection) for store number lookup
        """
        self.output_directory = Path(output_directory)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.db_connection = db_connection

    def _camel_to_snake(self, name: str) -> str:
        """Convert camelCase to snake_case.
        
        Args:
            name: camelCase string
            
        Returns:
            snake_case string
        """
        # Insert an underscore before any uppercase letter that follows a lowercase letter or digit
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        # Insert an underscore before any uppercase letter that follows a lowercase letter
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def _convert_dict_keys_to_snake_case(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively convert dictionary keys from camelCase to snake_case.
        
        Args:
            data: Dictionary with camelCase keys
            
        Returns:
            Dictionary with snake_case keys
        """
        result = {}
        for key, value in data.items():
            snake_key = self._camel_to_snake(key)
            if isinstance(value, dict):
                result[snake_key] = self._convert_dict_keys_to_snake_case(value)
            elif isinstance(value, list):
                result[snake_key] = [
                    self._convert_dict_keys_to_snake_case(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[snake_key] = value
        return result

    def _extract_date_parts(self, order_data: Dict[str, Any]) -> Tuple[str, str]:
        """Extract year and month from order or billing document data.

        Args:
            order_data: The order or billing document data dictionary (either nested returnValue or flattened)

        Returns:
            Tuple of (year, month) as strings (e.g., ("2025", "01"))
        """
        date_str = None
        
        # Try flattened structure first (order and billing document date fields)
        for date_field in ['order_creation_date', 'order_date', 'creation_date', 'requested_delivery_date', 
                           'billing_document_date', 'invoice_due_date', 'document_date']:
            if date_field in order_data and order_data[date_field]:
                date_str = order_data[date_field]
                break
        
        # Try nested structure (orderHeader.orderCreationDate) for backwards compatibility during migration
        if not date_str:
            order_header = order_data.get('orderHeader', {})
            if isinstance(order_header, dict):
                for date_field in ['orderCreationDate', 'orderDate', 'createdDate', 'requestedDeliveryDate']:
                    if date_field in order_header and order_header[date_field]:
                        date_str = order_header[date_field]
                        break
        
        # Try top-level camelCase (for backwards compatibility)
        if not date_str:
            for date_field in ['orderCreationDate', 'orderDate', 'creationDate']:
                if date_field in order_data and order_data[date_field]:
                    date_str = order_data[date_field]
                    break

        if date_str:
            try:
                # Try parsing various date formats
                if isinstance(date_str, str):
                    # Handle MM/DD/YYYY format: "09/01/2025"
                    if '/' in date_str and len(date_str.split('/')) == 3:
                        date_obj = datetime.strptime(date_str, '%m/%d/%Y')
                    # Handle ISO format: "2025-01-15T10:30:00" or "2025-01-15"
                    elif 'T' in date_str:
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

    def _get_store_number_from_db(self, customer_id: Optional[int]) -> Optional[int]:
        """Get canonical store_number from stores table using customer_id.
        
        Args:
            customer_id: Customer ID from order data
            
        Returns:
            Store number if found, None otherwise
        """
        if not customer_id or not self.db_connection:
            return None
        
        try:
            with self.db_connection.cursor() as cur:
                cur.execute("SELECT store_number FROM stores WHERE customer_id = %s", (customer_id,))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.debug(f"Failed to lookup store_number for customer_id {customer_id}: {e}")
            return None

    def _extract_customer_id(self, order_data: Dict[str, Any]) -> Optional[int]:
        """Extract customer_id from order data.
        
        Args:
            order_data: The order data dictionary (either nested returnValue or flattened)
            
        Returns:
            Customer ID as int, or None if not found
        """
        # Try flattened structure first (customer_id)
        if 'customer_id' in order_data and order_data['customer_id']:
            try:
                return int(order_data['customer_id'])
            except (ValueError, TypeError):
                pass
        
        # Try nested structure (orderHeader.customerId) for backwards compatibility
        order_header = order_data.get('orderHeader', {})
        if isinstance(order_header, dict):
            for store_field in ['customerId', 'customerID']:
                if store_field in order_header and order_header[store_field]:
                    try:
                        return int(order_header[store_field])
                    except (ValueError, TypeError):
                        pass
        
        # Try top-level camelCase (for backwards compatibility)
        for store_field in ['customerId', 'customerID']:
            if store_field in order_data and order_data[store_field]:
                try:
                    return int(order_data[store_field])
                except (ValueError, TypeError):
                    pass
        
        return None

    def _extract_store_id(self, order_data: Dict[str, Any]) -> str:
        """Extract store ID from order data, using canonical store_number if available.

        Args:
            order_data: The order data dictionary (either nested returnValue or flattened)

        Returns:
            Store ID as string (canonical store_number if available, otherwise customer_id)
        """
        # First, try to get customer_id
        customer_id = self._extract_customer_id(order_data)
        
        # If we have a database connection, try to lookup canonical store_number
        if customer_id:
            store_number = self._get_store_number_from_db(customer_id)
            if store_number is not None:
                return str(store_number)
            # Fall back to customer_id if store_number not found
            return str(customer_id)
        
        # Try flattened structure (store_number, store_id) - fallback if no customer_id
        for store_field in ['store_number', 'store_id']:
            if store_field in order_data and order_data[store_field]:
                return str(order_data[store_field])
        
        # Try nested structure (orderHeader.storeNumber) for backwards compatibility
        order_header = order_data.get('orderHeader', {})
        if isinstance(order_header, dict):
            for store_field in ['storeNumber', 'storeId', 'storeID']:
                if store_field in order_header and order_header[store_field]:
                    return str(order_header[store_field])
        
        # Try top-level camelCase (for backwards compatibility)
        for store_field in ['storeNumber', 'storeId', 'storeID']:
            if store_field in order_data and order_data[store_field]:
                return str(order_data[store_field])

        # Fallback to "unknown" if no store ID found
        logger.warning("No store ID found in order data, using 'unknown'")
        return "unknown"

    def _get_order_directory(self, order_data: Dict[str, Any]) -> Path:
        """Get the hierarchical directory path for an order.

        Args:
            order_data: The order data dictionary

        Returns:
            Path to the order's directory (e.g., /data/2025/01/store_1000055874)
        """
        year, month = self._extract_date_parts(order_data)
        store_id = self._extract_store_id(order_data)

        directory = self.output_directory / year / month / f"store_{store_id}"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _file_exists_in_directory_tree(self, filename: str, entity_data: Optional[Dict[str, Any]] = None) -> bool:
        """Check if a file exists, either at exact path or by searching directory tree.
        
        Args:
            filename: The filename to search for (e.g., "order_123.json")
            entity_data: Optional data to determine exact directory path.
                        If None, searches all possible locations.
        
        Returns:
            True if file exists, False otherwise
        """
        if entity_data:
            # Use provided data to determine exact path
            directory = self._get_order_directory(entity_data)
            filepath = directory / filename
            return filepath.exists()
        else:
            # Search all possible locations (slower but works without entity data)
            # Search in all year/month/store directories
            for year_dir in self.output_directory.iterdir():
                if not year_dir.is_dir():
                    continue
                for month_dir in year_dir.iterdir():
                    if not month_dir.is_dir():
                        continue
                    for store_dir in month_dir.iterdir():
                        if not store_dir.is_dir() or not store_dir.name.startswith('store_'):
                            continue
                        filepath = store_dir / filename
                        if filepath.exists():
                            return True
            return False

    def order_file_exists(self, order_id: str, order_data: Optional[Dict[str, Any]] = None) -> bool:
        """Check if an order file already exists.

        Args:
            order_id: The order ID
            order_data: Optional order data to determine directory structure.
                       If None, searches all possible locations.

        Returns:
            True if file exists, False otherwise
        """
        return self._file_exists_in_directory_tree(f"order_{order_id}.json", order_data)

    def billing_document_file_exists(self, billing_document_id: str, billing_data: Optional[Dict[str, Any]] = None) -> bool:
        """Check if a billing document file already exists.

        Args:
            billing_document_id: The billing document ID
            billing_data: Optional billing data to determine directory structure.
                         If None, searches all possible locations.

        Returns:
            True if file exists, False otherwise
        """
        return self._file_exists_in_directory_tree(f"billing_{billing_document_id}.json", billing_data)

    def _flatten_order_data(self, order_id: str, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten order data structure from API format to simplified format.
        
        Args:
            order_id: The order ID
            order_data: The returnValue from API (contains orderHeader and orderLines)
            
        Returns:
            Flattened dictionary with order_id and all orderHeader fields at top level,
            plus order_lines array with snake_case keys
            
        Raises:
            ValueError: If order_data is invalid or missing required orderHeader
        """
        # Validate input data
        if not order_data or not isinstance(order_data, dict):
            raise ValueError(
                f"Invalid order_data for order {order_id}: expected dict, got {type(order_data)}"
            )
        
        # Validate that orderHeader exists and is not empty
        order_header = order_data.get('orderHeader', {})
        if not order_header or not isinstance(order_header, dict):
            raise ValueError(
                f"Missing or invalid orderHeader in order {order_id}. "
                f"order_data keys: {list(order_data.keys())}"
            )
        
        if len(order_header) == 0:
            raise ValueError(
                f"Empty orderHeader in order {order_id}. "
                f"This usually indicates an API error or authentication failure."
            )
        
        order_lines = order_data.get('orderLines', [])
        
        # Start with order_id
        flattened = {'order_id': order_id}
        
        # Flatten all orderHeader fields to top level with snake_case keys
        if isinstance(order_header, dict):
            for key, value in order_header.items():
                snake_key = self._camel_to_snake(key)
                flattened[snake_key] = value
        
        # Convert orderLines to order_lines with snake_case keys in each item
        if isinstance(order_lines, list):
            flattened['order_lines'] = [
                self._convert_dict_keys_to_snake_case(item) if isinstance(item, dict) else item
                for item in order_lines
            ]
        else:
            flattened['order_lines'] = []
        
        return flattened

    def _flatten_billing_document_data(self, billing_document_id: str, billing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten billing document data structure from API format to simplified format.
        
        Args:
            billing_document_id: The billing document ID
            billing_data: The returnValue from API (likely contains billingDocumentHeader and billingLines or similar)
            
        Returns:
            Flattened dictionary with billing_document_id and all header fields at top level,
            plus billing_lines array with snake_case keys
        """
        # Handle nested returnValue wrapper (billing documents have an extra layer)
        # The API returns: { returnValue: { invoiceHeader: {...}, ... }, cacheable: false }
        if isinstance(billing_data, dict) and 'returnValue' in billing_data:
            billing_data = billing_data['returnValue']
            logger.debug(f"Billing document {billing_document_id}: Unwrapped nested returnValue")
        
        # Log the actual structure we receive for debugging (can be removed later)
        logger.debug(f"Billing document {billing_document_id} API response type: {type(billing_data)}")
        if isinstance(billing_data, dict):
            logger.debug(f"Billing document {billing_document_id} API response keys: {list(billing_data.keys())}")
        
        # billing_data is the returnValue from API
        # Try to find header and lines - structure may vary, so check multiple possibilities
        billing_header = (
            billing_data.get('billingDocumentHeader') or
            billing_data.get('billingHeader') or
            billing_data.get('documentHeader') or
            billing_data.get('invoiceHeader') or
            {}
        )
        # invoiceDetails can be either a single object or an array
        # Handle both cases - if it's a single object, wrap it in an array
        invoice_details_raw = (
            billing_data.get('invoiceDetails') or
            billing_data.get('billingLines') or
            billing_data.get('billingDocumentLines') or
            billing_data.get('documentLines') or
            billing_data.get('invoiceLines') or
            billing_data.get('lineItems') or
            None
        )
        
        # Convert to array format - handle both single object and array cases
        if invoice_details_raw is None:
            billing_lines = []
        elif isinstance(invoice_details_raw, list):
            billing_lines = invoice_details_raw
        elif isinstance(invoice_details_raw, dict):
            # Single object - wrap it in an array
            billing_lines = [invoice_details_raw]
        else:
            billing_lines = []
        
        # Start with billing_document_id
        flattened = {'billing_document_id': billing_document_id}
        
        # Flatten all header fields to top level with snake_case keys
        if isinstance(billing_header, dict):
            for key, value in billing_header.items():
                snake_key = self._camel_to_snake(key)
                flattened[snake_key] = value
        elif not billing_header:
            # If no header found, try to flatten top-level fields directly
            # (excluding known line item and metadata fields)
            line_item_keys = {'invoiceDetails', 'billingLines', 'billingDocumentLines', 'documentLines', 'invoiceLines', 'lineItems'}
            metadata_keys = {'pageInfo', 'success', 'cacheable'}
            exclude_keys = line_item_keys | metadata_keys
            logger.debug(f"Flattening top-level fields, excluding: {exclude_keys}")
            for key, value in billing_data.items():
                if key not in exclude_keys:
                    snake_key = self._camel_to_snake(key)
                    flattened[snake_key] = value
                    logger.debug(f"Added top-level field: {key} -> {snake_key}")
        
        # Convert billingLines to billing_lines with snake_case keys in each item
        flattened['billing_lines'] = [
            self._convert_dict_keys_to_snake_case(item) if isinstance(item, dict) else item
            for item in billing_lines
        ]
        
        return flattened

    def save_order(self, order_id: str, order_data: Dict[str, Any]) -> Path:
        """Save order data to JSON file in hierarchical directory structure.

        Args:
            order_id: The order ID
            order_data: The returnValue from API (contains orderHeader and orderLines)

        Returns:
            Path to the saved file

        Raises:
            IOError: If file write fails
        """
        # Flatten the structure first (needed for directory extraction)
        flattened = self._flatten_order_data(order_id, order_data)
        
        # Validate that we have minimum required fields
        required_fields = ['order_id']
        missing_fields = [field for field in required_fields if field not in flattened]
        if missing_fields:
            raise ValueError(
                f"Missing required fields in flattened order data for order {order_id}: {missing_fields}"
            )
        
        # Check that we have actual data beyond just order_id and order_lines
        # A valid order should have at least some header fields (customer_id, order_creation_date, etc.)
        data_fields = [k for k in flattened.keys() if k not in ['order_id', 'order_lines']]
        if len(data_fields) == 0:
            raise ValueError(
                f"Incomplete order data for order {order_id}: only has order_id and order_lines, "
                f"missing all header fields. This usually indicates an API error or authentication failure."
            )
        
        # Get hierarchical directory based on date and store
        order_dir = self._get_order_directory(flattened)
        filename = f"order_{order_id}.json"
        filepath = order_dir / filename

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(flattened, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved order {order_id} to {filepath}")
            return filepath

        except IOError as e:
            logger.error(f"Failed to write JSON file {filepath}: {e}")
            raise

    def save_billing_document(self, billing_document_id: str, billing_data: Dict[str, Any]) -> Path:
        """Save billing document data to JSON file in hierarchical directory structure.

        Args:
            billing_document_id: The billing document ID
            billing_data: The returnValue from API (contains billingDocumentHeader and billingLines or similar)

        Returns:
            Path to the saved file

        Raises:
            IOError: If file write fails
        """
        # Flatten the structure first (needed for directory extraction)
        flattened = self._flatten_billing_document_data(billing_document_id, billing_data)
        
        # Get hierarchical directory based on date and store (reuse order method)
        document_dir = self._get_order_directory(flattened)
        filename = f"billing_{billing_document_id}.json"
        filepath = document_dir / filename

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(flattened, f, indent=2, ensure_ascii=False)

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
