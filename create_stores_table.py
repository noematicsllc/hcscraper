#!/usr/bin/env python3
"""One-time script to create stores table and map store numbers/names to customer_id.

This script:
1. Creates a stores table with store_number, store_name, and customer_id
2. Extracts store numbers from order store_name fields (if present)
3. Maps stores to their customer_id from orders
4. Populates the table with data from the provided store list
"""

import sys
import os
import re
from typing import Dict, Set, Tuple, Optional

import psycopg


# Store data from the image/CSV
# Store numbers as integers (no leading zeros)
STORE_DATA = [
    (9, "Reston"),
    (15, "Dulles"),
    (22, "Fair Oaks Mall"),
    (29, "Ashburn"),
    (32, "Gainesville"),
    (33, "Warrenton"),
    (40, "South Riding"),
    (44, "Stafford"),
    (45, "Oakton"),
    (46, "Bradlee"),
    (47, "Fair Lakes"),
    (48, "Woodbridge"),
    (49, "Williamsburg"),
    (50, "Newport News"),
    (51, "Commonwealth"),
    (52, "Village Marketplace"),
    (53, "Fairfield"),
    (54, "Hilltop"),
    (56, "Central Park"),
    (57, "Cosner's Corner"),
    (60, "Hayes"),
    (61, "Lynchburg"),
    (62, "Harrisonburg"),
    (64, "Winchester"),
    (68, "Christiansburg"),
    (523, "Chesapeake"),
    (824, "Columbus Village"),
    (1403, "Burke"),
    (1620, "Fair City Mall"),
    (1818, "Little Suffolk"),
    (1822, "Suffolk"),
    (1825, "Henrico"),
    (1828, "Waynesboro"),
    (1938, "Roanoke"),
    (1940, "Rocky Mount"),
    (1941, "Manassas"),
    (1948, "Charlottesville"),
    (36, "Kingstowne"),
    (38, "Leesburg"),
    # Add any missing stores from your list
]


def extract_store_number_from_name(store_name: str) -> Optional[int]:
    """Extract store number from store name.
    
    Store names typically end with store numbers, e.g., "BANNER'S HALLMARK SHOP 64"
    or "BANNER'S HALLMARK SHOP 22". We look for numbers at the end.
    
    Args:
        store_name: Store name string
        
    Returns:
        Store number as integer or None
    """
    if not store_name:
        return None
    
    # Look for number(s) at the end of the string
    match = re.search(r'(\d+)$', store_name.strip())
    if match:
        return int(match.group(1))
    
    return None


def create_stores_table(conn: psycopg.Connection) -> None:
    """Create stores table with customer_id as primary key."""
    with conn.cursor() as cur:
        # Create stores table with customer_id as primary key
        # This allows orders, billing documents, and deliveries to reference stores via customer_id
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stores (
                customer_id BIGINT PRIMARY KEY,
                store_number BIGINT NOT NULL,
                store_name VARCHAR(255) NOT NULL
            )
        """)
        
        # Indexes for common lookups
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stores_store_number ON stores(store_number)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stores_store_name ON stores(store_name)")
        
        conn.commit()
        print("✓ Stores table created/verified")


def extract_store_mappings_from_orders(conn: psycopg.Connection) -> Dict[Tuple[Optional[int], Optional[str]], Set[int]]:
    """Extract store number/name to customer_id mappings from orders.
    
    Args:
        conn: Database connection
        
    Returns:
        Dictionary mapping (store_number, store_name) -> set of customer_ids
    """
    mappings: Dict[Tuple[Optional[int], Optional[str]], Set[int]] = {}
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT store_name, customer_id
            FROM orders
            WHERE store_name IS NOT NULL AND customer_id IS NOT NULL
        """)
        
        for store_name, customer_id in cur.fetchall():
            store_number = extract_store_number_from_name(store_name)
            key = (store_number, store_name)
            
            if key not in mappings:
                mappings[key] = set()
            mappings[key].add(customer_id)
    
    return mappings


def populate_stores_table(conn: psycopg.Connection) -> None:
    """Populate stores table with customer_id to store_number/store_name mappings."""
    # Get mappings from orders
    print("Extracting store mappings from orders...")
    order_mappings = extract_store_mappings_from_orders(conn)
    print(f"  Found {len(order_mappings)} unique store_name/customer_id combinations")
    
    # Build customer_id -> (store_number, canonical_name) mapping
    # Start by mapping store_number -> canonical_name from STORE_DATA
    store_number_to_name: Dict[int, str] = {}
    for store_number, store_name in STORE_DATA:
        store_number_to_name[store_number] = store_name
    
    # Build customer_id -> (store_number, store_name) mapping from orders
    customer_id_to_store: Dict[int, Tuple[int, str]] = {}
    for (store_number, store_name), customer_ids in order_mappings.items():
        if store_number:
            # Use canonical name if available, otherwise use name from orders
            canonical_name = store_number_to_name.get(store_number, store_name or f"Store {store_number}")
            
            for customer_id in customer_ids:
                # If customer_id already mapped, check for conflicts
                if customer_id in customer_id_to_store:
                    existing_number, existing_name = customer_id_to_store[customer_id]
                    if existing_number != store_number:
                        print(f"⚠ Warning: customer_id {customer_id} maps to multiple store_numbers: {existing_number} and {store_number}")
                else:
                    customer_id_to_store[customer_id] = (store_number, canonical_name)
    
    # Insert/update stores table
    print(f"\nPopulating stores table with {len(customer_id_to_store)} stores...")
    stores_inserted = 0
    stores_updated = 0
    
    with conn.cursor() as cur:
        for customer_id, (store_number, store_name) in customer_id_to_store.items():
            cur.execute("""
                INSERT INTO stores (customer_id, store_number, store_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (customer_id) DO UPDATE SET
                    store_number = EXCLUDED.store_number,
                    store_name = EXCLUDED.store_name
            """, (customer_id, store_number, store_name))
            
            if cur.rowcount == 1:
                stores_inserted += 1
            else:
                stores_updated += 1
    
    conn.commit()
    print(f"  Stores inserted: {stores_inserted}")
    print(f"  Stores updated: {stores_updated}")


def add_foreign_key_constraint(conn: psycopg.Connection) -> None:
    """Add foreign key constraint from orders.customer_id to stores.customer_id."""
    with conn.cursor() as cur:
        # Check if constraint already exists
        cur.execute("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = 'orders'
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%customer_id%'
        """)
        
        if cur.fetchone():
            print("✓ Foreign key constraint already exists")
            return
        
        # Check if there are customer_ids in orders that don't exist in stores
        cur.execute("""
            SELECT COUNT(DISTINCT o.customer_id)
            FROM orders o
            LEFT JOIN stores s ON o.customer_id = s.customer_id
            WHERE o.customer_id IS NOT NULL
            AND s.customer_id IS NULL
        """)
        unmapped_count = cur.fetchone()[0]
        
        if unmapped_count > 0:
            print(f"⚠ {unmapped_count} customer_ids in orders don't have matching stores")
            print("  Skipping foreign key constraint (add it manually after all stores are mapped)")
            return
        
        # Try to add constraint
        try:
            cur.execute("""
                ALTER TABLE orders
                ADD CONSTRAINT fk_orders_customer_id
                FOREIGN KEY (customer_id) REFERENCES stores(customer_id)
            """)
            conn.commit()
            print("✓ Foreign key constraint added (orders.customer_id -> stores.customer_id)")
        except Exception as e:
            print(f"⚠ Could not add foreign key constraint: {e}")
            conn.rollback()


def main():
    """Main entry point."""
    # Get database connection string from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("Error: DATABASE_URL environment variable not set")
        print("Example: postgresql://user:password@localhost:5432/dbname")
        return 1
    
    print("=" * 60)
    print("Store Table Creation Script")
    print("=" * 60)
    print()
    
    # Connect to database
    try:
        conn = psycopg.connect(database_url)
        print("✓ Connected to database")
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return 1
    
    try:
        # Create table
        create_stores_table(conn)
        
        # Populate table
        populate_stores_table(conn)
        
        # Optionally add foreign key constraint
        print("\nAttempting to add foreign key constraint...")
        add_foreign_key_constraint(conn)
        
        # Show summary
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM stores")
            total_stores = cur.fetchone()[0]
            
            print(f"Total stores: {total_stores}")
        
        print("\n✓ Done!")
        
    finally:
        conn.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

