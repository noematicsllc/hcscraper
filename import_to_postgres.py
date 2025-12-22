#!/usr/bin/env python3
"""Import order data from JSON files into PostgreSQL database."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

import psycopg
from psycopg.rows import dict_row


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string in various formats.
    
    Args:
        date_str: Date string (MM/DD/YYYY, YYYY-MM-DD, etc.)
        
    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None
    
    try:
        # Try MM/DD/YYYY format first
        if '/' in date_str and len(date_str.split('/')) == 3:
            return datetime.strptime(date_str, '%m/%d/%Y')
        # Try ISO format
        elif 'T' in date_str:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        # Try YYYY-MM-DD
        else:
            return datetime.strptime(date_str[:10], '%Y-%m-%d')
    except (ValueError, AttributeError):
        return None


def parse_decimal(value: str) -> Optional[float]:
    """Parse decimal string to float.
    
    Args:
        value: Decimal string (may have trailing spaces)
        
    Returns:
        float or None if parsing fails
    """
    if not value:
        return None
    try:
        # Remove trailing spaces and parse
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


def find_json_files(directory: Path) -> List[Path]:
    """Find all JSON files recursively (orders and billing documents).
    
    Args:
        directory: Root directory to search
        
    Returns:
        List of JSON file paths
    """
    pattern = "**/*.json"
    files = list(directory.glob(pattern))
    return sorted(files)


def load_order_file(json_file: Path) -> Optional[Dict[str, Any]]:
    """Load and parse an order JSON file.
    
    Args:
        json_file: Path to JSON file
        
    Returns:
        Parsed order data or None if loading fails
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load {json_file}: {e}")
        return None


def create_schema(conn: psycopg.Connection) -> None:
    """Create database tables if they don't exist.
    
    Args:
        conn: Database connection
    """
    with conn.cursor() as cur:
        # Orders table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id VARCHAR(50) PRIMARY KEY,
                customer_id BIGINT,
                store_name VARCHAR(255),
                ship_to_location TEXT,
                season_description VARCHAR(255),
                po_number VARCHAR(100),
                order_reason VARCHAR(255),
                order_source VARCHAR(100),
                planogram_description VARCHAR(255),
                order_status VARCHAR(100),
                order_total DECIMAL(15, 2),
                order_creation_date DATE,
                actual_delivery_date DATE,
                requested_delivery_date DATE,
                comment_description TEXT,
                source_system_id VARCHAR(100),
                raw_data JSONB
            )
        """)
        
        # Order items table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id SERIAL PRIMARY KEY,
                order_id VARCHAR(50) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
                line_item_number INTEGER,
                location_id VARCHAR(100),
                material_number VARCHAR(100),
                stock_number VARCHAR(100),  -- Can be numeric or alphanumeric (e.g., "459GR6409")
                upc VARCHAR(100),
                material_description TEXT,
                wholesales DECIMAL(15, 2),
                retailsin1_wholesale INTEGER,
                raw_data JSONB
            )
        """)
        
        # Create indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_creation_date ON orders(order_creation_date)")
        
        # Junction tables for many-to-many relationships
        cur.execute("""
            CREATE TABLE IF NOT EXISTS order_deliveries (
                order_id VARCHAR(50) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
                delivery_id VARCHAR(50) NOT NULL,
                PRIMARY KEY (order_id, delivery_id)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS order_billing_documents (
                order_id VARCHAR(50) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
                billing_document_number VARCHAR(50) NOT NULL,
                PRIMARY KEY (order_id, billing_document_number)
            )
        """)
        
        # Indexes for junction tables
        cur.execute("CREATE INDEX IF NOT EXISTS idx_order_deliveries_delivery_id ON order_deliveries(delivery_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_order_billing_documents_billing_doc ON order_billing_documents(billing_document_number)")
        
        # Billing documents table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS billing_documents (
                billing_document_id VARCHAR(50) PRIMARY KEY,
                customer_id BIGINT,
                store_name VARCHAR(255),
                customer_address TEXT,
                billing_document_number BIGINT,
                billing_document_date DATE,
                invoice_terms VARCHAR(100),
                po_number VARCHAR(100),
                invoice_due_date DATE,
                total DECIMAL(15, 2),
                associated_check_in_document VARCHAR(100),
                resale_merchandise_total DECIMAL(15, 2),
                non_resale_merchandise_total DECIMAL(15, 2),
                total_tax DECIMAL(15, 2),
                transportation DECIMAL(15, 2),
                sub_total DECIMAL(15, 2),
                non_resale_total DECIMAL(15, 2),
                invoice_comments TEXT,
                bill_of_lading VARCHAR(100),
                gst_hst_tax DECIMAL(15, 2),
                pst_tax DECIMAL(15, 2),
                sub_total_before_gst DECIMAL(15, 2),
                weight DECIMAL(15, 3),
                carrier VARCHAR(100),
                discount_date DATE,
                calculated_prompt_pay_discount DECIMAL(15, 2),
                billing_document_type VARCHAR(100),
                order_id BIGINT,
                delivery_id VARCHAR(50),
                clearing_date DATE,
                paid_amount DECIMAL(15, 2),
                status VARCHAR(100),
                raw_data JSONB
            )
        """)
        
        # Billing document items table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS billing_document_items (
                id SERIAL PRIMARY KEY,
                billing_document_id VARCHAR(50) NOT NULL REFERENCES billing_documents(billing_document_id) ON DELETE CASCADE,
                line_item_number INTEGER,
                material_number VARCHAR(100),
                material_description TEXT,
                wholesales DECIMAL(15, 2),
                upc VARCHAR(100),
                price_per_wholesale_unit DECIMAL(15, 2),
                number_in DECIMAL(15, 2),
                retail_units DECIMAL(15, 2),
                price_per_retail_unit DECIMAL(15, 2),
                amount DECIMAL(15, 2),
                discount_amount DECIMAL(15, 2),
                tax_code VARCHAR(100),
                raw_data JSONB
            )
        """)
        
        # Indexes for billing documents
        cur.execute("CREATE INDEX IF NOT EXISTS idx_billing_document_items_billing_document_id ON billing_document_items(billing_document_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_billing_documents_customer_id ON billing_documents(customer_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_billing_documents_billing_document_date ON billing_documents(billing_document_date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_billing_documents_store_name ON billing_documents(store_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_billing_documents_billing_document_number ON billing_documents(billing_document_number)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_billing_documents_order_id ON billing_documents(order_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_billing_documents_delivery_id ON billing_documents(delivery_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_billing_documents_status ON billing_documents(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_billing_documents_billing_document_type ON billing_documents(billing_document_type)")
        
        # GIN indexes for JSONB queries on raw_data
        cur.execute("CREATE INDEX IF NOT EXISTS idx_billing_documents_raw_data ON billing_documents USING GIN (raw_data)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_billing_document_items_raw_data ON billing_document_items USING GIN (raw_data)")
        
        conn.commit()
        print("✓ Database schema created/verified")


def get_canonical_store_name(conn: psycopg.Connection, customer_id: Optional[int]) -> Optional[str]:
    """Get canonical store name from stores table for a given customer_id.
    
    Args:
        conn: Database connection
        customer_id: Customer ID from order
        
    Returns:
        Canonical store name if found, None otherwise
    """
    if not customer_id:
        return None
    
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT store_name FROM stores WHERE customer_id = %s", (customer_id,))
            result = cur.fetchone()
            return result[0] if result else None
    except Exception:
        return None


def extract_order_data(order_json: Dict[str, Any], conn: Optional[psycopg.Connection] = None) -> Optional[Dict[str, Any]]:
    """Extract order header data from flattened JSON structure.
    
    Args:
        order_json: Flattened order JSON structure (all fields at top level with snake_case)
        conn: Optional database connection to lookup canonical store names
        
    Returns:
        Dictionary with order fields or None if structure invalid
    """
    order_id = order_json.get('order_id')
    if not order_id:
        return None
    
    customer_id = order_json.get('customer_id')
    
    # Get canonical store name from stores table if available
    store_name = None
    if conn and customer_id:
        store_name = get_canonical_store_name(conn, customer_id)
    
    # Fall back to source store_name if canonical name not found
    if not store_name:
        store_name = order_json.get('store_name')
    
    # Build order data dict from flattened structure
    order_data = {
        'order_id': order_id,
        'customer_id': customer_id,
        'store_name': store_name,  # Use canonical name if available, otherwise source name
        'ship_to_location': order_json.get('ship_to_location'),
        'season_description': order_json.get('season_description'),
        'po_number': order_json.get('po_number'),
        'order_reason': order_json.get('order_reason'),
        'order_source': order_json.get('order_source'),
        'planogram_description': order_json.get('planogram_description'),
        'order_status': order_json.get('order_status'),
        'order_total': parse_decimal(str(order_json.get('order_total', ''))) if order_json.get('order_total') else None,
        'order_creation_date': parse_date(order_json.get('order_creation_date')),
        'actual_delivery_date': parse_date(order_json.get('actual_delivery_date')),
        'requested_delivery_date': parse_date(order_json.get('requested_delivery_date')),
        'comment_description': order_json.get('comment_description'),
        'source_system_id': order_json.get('source_system_id'),
        'raw_data': json.dumps(order_json)  # Store full flattened JSON (includes original store_name)
    }
    
    return order_data


def parse_stock_number(value: Any) -> Optional[str]:
    """Parse stock number - can be integer or string.
    
    Args:
        value: Stock number (int or string)
        
    Returns:
        String representation or None
    """
    if value is None:
        return None
    return str(value)


def extract_order_items(order_json: Dict[str, Any], order_id: str) -> List[Dict[str, Any]]:
    """Extract order line items from flattened JSON structure.
    
    Args:
        order_json: Flattened order JSON structure (has order_lines array with snake_case keys)
        order_id: Order ID
        
    Returns:
        List of order item dictionaries
    """
    order_lines = order_json.get('order_lines', [])
    
    items = []
    for line_item in order_lines:
        if not isinstance(line_item, dict):
            continue
        
        items.append({
            'order_id': order_id,
            'line_item_number': line_item.get('line_item_number'),
            'location_id': line_item.get('location_id'),
            'material_number': line_item.get('material_number'),
            'stock_number': parse_stock_number(line_item.get('stock_number')),
            'upc': line_item.get('upc'),
            'material_description': line_item.get('material_description'),
            'wholesales': parse_decimal(str(line_item.get('wholesales', ''))) if line_item.get('wholesales') else None,
            'retailsin1_wholesale': line_item.get('retailsin1_wholesale'),
            'raw_data': json.dumps(line_item)  # Store full item as JSONB
        })
    
    return items


def insert_order(conn: psycopg.Connection, order_data: Dict[str, Any]) -> bool:
    """Insert order into database.
    
    Args:
        conn: Database connection
        order_data: Order data dictionary
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO orders (
                    order_id, customer_id, store_name, ship_to_location,
                    season_description, po_number, order_reason, order_source,
                    planogram_description, order_status, order_total, order_creation_date,
                    actual_delivery_date, requested_delivery_date, comment_description,
                    source_system_id, raw_data
                ) VALUES (
                    %(order_id)s, %(customer_id)s, %(store_name)s,
                    %(ship_to_location)s, %(season_description)s, %(po_number)s,
                    %(order_reason)s, %(order_source)s, %(planogram_description)s,
                    %(order_status)s, %(order_total)s, %(order_creation_date)s,
                    %(actual_delivery_date)s, %(requested_delivery_date)s,
                    %(comment_description)s, %(source_system_id)s, %(raw_data)s
                )
                ON CONFLICT (order_id) DO UPDATE SET
                    customer_id = EXCLUDED.customer_id,
                    store_name = EXCLUDED.store_name,
                    ship_to_location = EXCLUDED.ship_to_location,
                    season_description = EXCLUDED.season_description,
                    po_number = EXCLUDED.po_number,
                    order_reason = EXCLUDED.order_reason,
                    order_source = EXCLUDED.order_source,
                    planogram_description = EXCLUDED.planogram_description,
                    order_status = EXCLUDED.order_status,
                    order_total = EXCLUDED.order_total,
                    order_creation_date = EXCLUDED.order_creation_date,
                    actual_delivery_date = EXCLUDED.actual_delivery_date,
                    requested_delivery_date = EXCLUDED.requested_delivery_date,
                    comment_description = EXCLUDED.comment_description,
                    source_system_id = EXCLUDED.source_system_id,
                    raw_data = EXCLUDED.raw_data
            """, order_data)
        return True
    except Exception as e:
        print(f"Error inserting order {order_data.get('order_id')}: {e}")
        return False


def parse_comma_separated(value: Any) -> List[str]:
    """Parse comma-separated string into list of values.
    
    Args:
        value: Can be string (comma-separated), list, int, or None
        
    Returns:
        List of string values
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, str):
        # Split by comma and strip whitespace
        return [v.strip() for v in value.split(',') if v.strip()]
    return []


def insert_order_relationships(conn: psycopg.Connection, order_id: str, order_json: Dict[str, Any]) -> None:
    """Insert order relationships (deliveries and billing documents) into junction tables.
    
    Args:
        conn: Database connection
        order_id: Order ID
        order_json: Full order JSON structure
    """
    with conn.cursor() as cur:
        # Delete existing relationships for this order
        cur.execute("DELETE FROM order_deliveries WHERE order_id = %s", (order_id,))
        cur.execute("DELETE FROM order_billing_documents WHERE order_id = %s", (order_id,))
        
        # Parse and insert delivery IDs
        delivery_ids = parse_comma_separated(order_json.get('delivery_id'))
        for delivery_id in delivery_ids:
            cur.execute("""
                INSERT INTO order_deliveries (order_id, delivery_id)
                VALUES (%s, %s)
                ON CONFLICT (order_id, delivery_id) DO NOTHING
            """, (order_id, delivery_id))
        
        # Parse and insert billing document numbers
        billing_docs = parse_comma_separated(order_json.get('billing_document_number'))
        for billing_doc in billing_docs:
            cur.execute("""
                INSERT INTO order_billing_documents (order_id, billing_document_number)
                VALUES (%s, %s)
                ON CONFLICT (order_id, billing_document_number) DO NOTHING
            """, (order_id, billing_doc))


def insert_order_items(conn: psycopg.Connection, items: List[Dict[str, Any]]) -> int:
    """Insert order items into database.
    
    Args:
        conn: Database connection
        items: List of order item dictionaries
        
    Returns:
        Number of items successfully inserted
    """
    if not items:
        return 0
    
    try:
        with conn.cursor() as cur:
            # Delete existing items for this order first
            order_id = items[0]['order_id']
            cur.execute("DELETE FROM order_items WHERE order_id = %s", (order_id,))
            
            # Insert new items
            for item in items:
                cur.execute("""
                    INSERT INTO order_items (
                        order_id, line_item_number, location_id, material_number,
                        stock_number, upc, material_description, wholesales,
                        retailsin1_wholesale, raw_data
                    ) VALUES (
                        %(order_id)s, %(line_item_number)s, %(location_id)s,
                        %(material_number)s, %(stock_number)s, %(upc)s,
                        %(material_description)s, %(wholesales)s,
                        %(retailsin1_wholesale)s, %(raw_data)s
                    )
                """, item)
        
        return len(items)
    except Exception as e:
        print(f"Error inserting items for order {items[0].get('order_id') if items else 'unknown'}: {e}")
        return 0


def extract_billing_document_data(billing_document_json: Dict[str, Any], conn: Optional[psycopg.Connection] = None) -> Optional[Dict[str, Any]]:
    """Extract billing document header data from flattened JSON structure.
    
    Args:
        billing_document_json: Flattened billing document JSON structure (all fields at top level with snake_case)
        conn: Optional database connection to lookup canonical store names
        
    Returns:
        Dictionary with billing document fields or None if structure invalid
    """
    billing_document_id = billing_document_json.get('billing_document_id')
    if not billing_document_id:
        return None
    
    customer_id = billing_document_json.get('customer_id')
    
    # Get canonical store name from stores table if available
    store_name = None
    if conn and customer_id:
        store_name = get_canonical_store_name(conn, customer_id)
    
    # Fall back to source store_name if canonical name not found
    if not store_name:
        store_name = billing_document_json.get('store_name')
    
    # Build billing document data dict from flattened structure
    billing_document_data = {
        'billing_document_id': billing_document_id,
        'customer_id': customer_id,
        'store_name': store_name,  # Use canonical name if available
        'customer_address': billing_document_json.get('customer_address'),
        'billing_document_number': billing_document_json.get('billing_document_number'),
        'billing_document_date': parse_date(billing_document_json.get('billing_document_date')),
        'invoice_terms': billing_document_json.get('invoice_terms'),
        'po_number': billing_document_json.get('po_number'),
        'invoice_due_date': parse_date(billing_document_json.get('invoice_due_date')),
        'total': parse_decimal(str(billing_document_json.get('total', '')).strip()) if billing_document_json.get('total') else None,
        'associated_check_in_document': billing_document_json.get('associated_check_in_document'),
        'resale_merchandise_total': parse_decimal(str(billing_document_json.get('resale_merchandise_total', '')).strip()) if billing_document_json.get('resale_merchandise_total') else None,
        'non_resale_merchandise_total': parse_decimal(str(billing_document_json.get('non_resale_merchandise_total', '')).strip()) if billing_document_json.get('non_resale_merchandise_total') else None,
        'total_tax': parse_decimal(str(billing_document_json.get('total_tax', '')).strip()) if billing_document_json.get('total_tax') else None,
        'transportation': parse_decimal(str(billing_document_json.get('transportation', '')).strip()) if billing_document_json.get('transportation') else None,
        'sub_total': parse_decimal(str(billing_document_json.get('sub_total', '')).strip()) if billing_document_json.get('sub_total') else None,
        'non_resale_total': parse_decimal(str(billing_document_json.get('non_resale_total', '')).strip()) if billing_document_json.get('non_resale_total') else None,
        'invoice_comments': billing_document_json.get('invoice_comments'),
        'bill_of_lading': billing_document_json.get('bill_of_lading'),
        'gst_hst_tax': parse_decimal(str(billing_document_json.get('gst_hst_tax', '')).strip()) if billing_document_json.get('gst_hst_tax') else None,
        'pst_tax': parse_decimal(str(billing_document_json.get('pst_tax', '')).strip()) if billing_document_json.get('pst_tax') else None,
        'sub_total_before_gst': parse_decimal(str(billing_document_json.get('sub_total_before_gst', '')).strip()) if billing_document_json.get('sub_total_before_gst') else None,
        'weight': parse_decimal(str(billing_document_json.get('weight', '')).strip()) if billing_document_json.get('weight') else None,
        'carrier': billing_document_json.get('carrier'),
        'discount_date': parse_date(billing_document_json.get('discount_date')),
        'calculated_prompt_pay_discount': parse_decimal(str(billing_document_json.get('calculated_prompt_pay_discount', '')).strip()) if billing_document_json.get('calculated_prompt_pay_discount') else None,
        'billing_document_type': billing_document_json.get('billing_document_type'),
        'order_id': billing_document_json.get('order_id'),
        'delivery_id': billing_document_json.get('delivery_id') or None,  # Empty string to None
        'clearing_date': parse_date(billing_document_json.get('clearing_date')),
        'paid_amount': parse_decimal(str(billing_document_json.get('paid_amount', '')).strip()) if billing_document_json.get('paid_amount') else None,
        'status': billing_document_json.get('status'),
        'raw_data': json.dumps(billing_document_json)  # Store full flattened JSON as JSONB
    }
    
    return billing_document_data


def extract_billing_document_items(billing_document_json: Dict[str, Any], billing_document_id: str) -> List[Dict[str, Any]]:
    """Extract billing document line items from flattened JSON structure.
    
    Args:
        billing_document_json: Flattened billing document JSON structure (has billing_lines array with snake_case keys)
        billing_document_id: Billing document ID
        
    Returns:
        List of billing document item dictionaries
    """
    billing_lines = billing_document_json.get('billing_lines', [])
    
    items = []
    for line_item in billing_lines:
        if not isinstance(line_item, dict):
            continue
        
        items.append({
            'billing_document_id': billing_document_id,
            'line_item_number': line_item.get('line_item_number'),
            'material_number': line_item.get('material_number'),
            'material_description': line_item.get('material_description'),
            'wholesales': parse_decimal(str(line_item.get('wholesales', '')).strip()) if line_item.get('wholesales') else None,
            'upc': line_item.get('upc'),
            'price_per_wholesale_unit': parse_decimal(str(line_item.get('price_per_wholesale_unit', '')).strip()) if line_item.get('price_per_wholesale_unit') else None,
            'number_in': parse_decimal(str(line_item.get('number_in', '')).strip()) if line_item.get('number_in') else None,
            'retail_units': parse_decimal(str(line_item.get('retail_units', '')).strip()) if line_item.get('retail_units') else None,
            'price_per_retail_unit': parse_decimal(str(line_item.get('price_per_retail_unit', '')).strip()) if line_item.get('price_per_retail_unit') else None,
            'amount': parse_decimal(str(line_item.get('amount', '')).strip()) if line_item.get('amount') else None,
            'discount_amount': parse_decimal(str(line_item.get('discount_amount', '')).strip()) if line_item.get('discount_amount') else None,
            'tax_code': line_item.get('tax_code'),
            'raw_data': json.dumps(line_item)  # Store full item as JSONB
        })
    
    return items


def insert_billing_document(conn: psycopg.Connection, billing_document_data: Dict[str, Any]) -> bool:
    """Insert billing document into database.
    
    Args:
        conn: Database connection
        billing_document_data: Billing document data dictionary
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO billing_documents (
                    billing_document_id, customer_id, store_name, customer_address,
                    billing_document_number, billing_document_date, invoice_terms,
                    po_number, invoice_due_date, total, associated_check_in_document,
                    resale_merchandise_total, non_resale_merchandise_total, total_tax,
                    transportation, sub_total, non_resale_total, invoice_comments,
                    bill_of_lading, gst_hst_tax, pst_tax, sub_total_before_gst,
                    weight, carrier, discount_date, calculated_prompt_pay_discount,
                    billing_document_type, order_id, delivery_id, clearing_date,
                    paid_amount, status, raw_data
                ) VALUES (
                    %(billing_document_id)s, %(customer_id)s, %(store_name)s,
                    %(customer_address)s, %(billing_document_number)s,
                    %(billing_document_date)s, %(invoice_terms)s, %(po_number)s,
                    %(invoice_due_date)s, %(total)s, %(associated_check_in_document)s,
                    %(resale_merchandise_total)s, %(non_resale_merchandise_total)s,
                    %(total_tax)s, %(transportation)s, %(sub_total)s,
                    %(non_resale_total)s, %(invoice_comments)s, %(bill_of_lading)s,
                    %(gst_hst_tax)s, %(pst_tax)s, %(sub_total_before_gst)s,
                    %(weight)s, %(carrier)s, %(discount_date)s,
                    %(calculated_prompt_pay_discount)s, %(billing_document_type)s,
                    %(order_id)s, %(delivery_id)s, %(clearing_date)s,
                    %(paid_amount)s, %(status)s, %(raw_data)s
                )
                ON CONFLICT (billing_document_id) DO UPDATE SET
                    customer_id = EXCLUDED.customer_id,
                    store_name = EXCLUDED.store_name,
                    customer_address = EXCLUDED.customer_address,
                    billing_document_number = EXCLUDED.billing_document_number,
                    billing_document_date = EXCLUDED.billing_document_date,
                    invoice_terms = EXCLUDED.invoice_terms,
                    po_number = EXCLUDED.po_number,
                    invoice_due_date = EXCLUDED.invoice_due_date,
                    total = EXCLUDED.total,
                    associated_check_in_document = EXCLUDED.associated_check_in_document,
                    resale_merchandise_total = EXCLUDED.resale_merchandise_total,
                    non_resale_merchandise_total = EXCLUDED.non_resale_merchandise_total,
                    total_tax = EXCLUDED.total_tax,
                    transportation = EXCLUDED.transportation,
                    sub_total = EXCLUDED.sub_total,
                    non_resale_total = EXCLUDED.non_resale_total,
                    invoice_comments = EXCLUDED.invoice_comments,
                    bill_of_lading = EXCLUDED.bill_of_lading,
                    gst_hst_tax = EXCLUDED.gst_hst_tax,
                    pst_tax = EXCLUDED.pst_tax,
                    sub_total_before_gst = EXCLUDED.sub_total_before_gst,
                    weight = EXCLUDED.weight,
                    carrier = EXCLUDED.carrier,
                    discount_date = EXCLUDED.discount_date,
                    calculated_prompt_pay_discount = EXCLUDED.calculated_prompt_pay_discount,
                    billing_document_type = EXCLUDED.billing_document_type,
                    order_id = EXCLUDED.order_id,
                    delivery_id = EXCLUDED.delivery_id,
                    clearing_date = EXCLUDED.clearing_date,
                    paid_amount = EXCLUDED.paid_amount,
                    status = EXCLUDED.status,
                    raw_data = EXCLUDED.raw_data
            """, billing_document_data)
        return True
    except Exception as e:
        print(f"Error inserting billing document {billing_document_data.get('billing_document_id')}: {e}")
        return False


def insert_billing_document_items(conn: psycopg.Connection, items: List[Dict[str, Any]]) -> int:
    """Insert billing document items into database.
    
    Args:
        conn: Database connection
        items: List of billing document item dictionaries
        
    Returns:
        Number of items inserted
    """
    if not items:
        return 0
    
    try:
        with conn.cursor() as cur:
            billing_document_id = items[0]['billing_document_id']
            # Delete existing items for this billing document
            cur.execute("DELETE FROM billing_document_items WHERE billing_document_id = %s", (billing_document_id,))
            
            # Insert all items
            for item in items:
                cur.execute("""
                    INSERT INTO billing_document_items (
                        billing_document_id, line_item_number, material_number,
                        material_description, wholesales, upc, price_per_wholesale_unit,
                        number_in, retail_units, price_per_retail_unit, amount,
                        discount_amount, tax_code, raw_data
                    ) VALUES (
                        %(billing_document_id)s, %(line_item_number)s, %(material_number)s,
                        %(material_description)s, %(wholesales)s, %(upc)s,
                        %(price_per_wholesale_unit)s, %(number_in)s, %(retail_units)s,
                        %(price_per_retail_unit)s, %(amount)s, %(discount_amount)s,
                        %(tax_code)s, %(raw_data)s
                    )
                """, item)
        
        return len(items)
    except Exception as e:
        print(f"Error inserting billing document items for billing document {items[0].get('billing_document_id') if items else 'unknown'}: {e}")
        return 0


def main():
    """Main entry point."""
    import os
    
    # Get database connection string from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("Error: DATABASE_URL environment variable not set")
        print("Example: postgresql://user:password@localhost:5432/dbname")
        return 1
    
    # Get data directory
    data_dir = Path(os.getenv('DATA_DIRECTORY', './data'))
    if not data_dir.exists():
        print(f"Error: Data directory does not exist: {data_dir}")
        return 1
    
    print("=" * 60)
    print("PostgreSQL Data Import")
    print("=" * 60)
    print(f"Data directory: {data_dir}")
    print()
    
    # Connect to database
    try:
        conn = psycopg.connect(database_url)
        print("✓ Connected to database")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return 1
    
    try:
        # Create schema
        create_schema(conn)
        
        # Find all order JSON files
        print("Finding order JSON files...")
        order_files = [f for f in find_json_files(data_dir) if f.name.startswith('order_')]
        print(f"  Found {len(order_files)} order files")
        
        # Find all billing document JSON files
        print("Finding billing document JSON files...")
        billing_files = [f for f in find_json_files(data_dir) if f.name.startswith('billing_')]
        print(f"  Found {len(billing_files)} billing document files")
        
        if not order_files and not billing_files:
            print("  ✗ No order or billing document files found")
            return 1
        
        # Process order files
        orders_inserted = 0
        order_items_inserted = 0
        order_errors = 0
        
        if order_files:
            print(f"\nProcessing {len(order_files)} order files...")
            for i, json_file in enumerate(order_files, 1):
                if i % 50 == 0:
                    print(f"  Processed {i}/{len(order_files)} order files...")
                
                # Load order JSON
                order_json = load_order_file(json_file)
                if not order_json:
                    order_errors += 1
                    continue
                
                # Extract order data (pass conn to lookup canonical store names)
                order_data = extract_order_data(order_json, conn)
                if not order_data:
                    order_errors += 1
                    continue
                
                # Insert order
                if insert_order(conn, order_data):
                    orders_inserted += 1
                    
                    # Insert order relationships (deliveries and billing documents)
                    insert_order_relationships(conn, order_data['order_id'], order_json)
                    
                    # Extract and insert order items
                    items = extract_order_items(order_json, order_data['order_id'])
                    order_items_inserted += insert_order_items(conn, items)
                    
                    conn.commit()
                else:
                    order_errors += 1
                    conn.rollback()
        
        # Process billing document files
        billing_documents_inserted = 0
        billing_items_inserted = 0
        billing_errors = 0
        
        if billing_files:
            print(f"\nProcessing {len(billing_files)} billing document files...")
            for i, json_file in enumerate(billing_files, 1):
                if i % 50 == 0:
                    print(f"  Processed {i}/{len(billing_files)} billing document files...")
                
                # Load billing document JSON
                billing_json = load_order_file(json_file)  # Reuse same loader
                if not billing_json:
                    billing_errors += 1
                    continue
                
                # Extract billing document data (pass conn to lookup canonical store names)
                billing_data = extract_billing_document_data(billing_json, conn)
                if not billing_data:
                    billing_errors += 1
                    continue
                
                # Insert billing document
                if insert_billing_document(conn, billing_data):
                    billing_documents_inserted += 1
                    
                    # Extract and insert billing document items
                    items = extract_billing_document_items(billing_json, billing_data['billing_document_id'])
                    billing_items_inserted += insert_billing_document_items(conn, items)
                    
                    conn.commit()
                else:
                    billing_errors += 1
                    conn.rollback()
        
        print()
        print("=" * 60)
        print("Import Summary")
        print("=" * 60)
        if order_files:
            print(f"Orders inserted: {orders_inserted}")
            print(f"Order items inserted: {order_items_inserted}")
            print(f"Order errors: {order_errors}")
        if billing_files:
            print(f"Billing documents inserted: {billing_documents_inserted}")
            print(f"Billing document items inserted: {billing_items_inserted}")
            print(f"Billing document errors: {billing_errors}")
        print()
        
    finally:
        conn.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

