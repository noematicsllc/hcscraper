-- PostgreSQL schema for Hallmark Connect order data

-- Orders table
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
);

-- Order items table
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
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_creation_date ON orders(order_creation_date);
CREATE INDEX IF NOT EXISTS idx_orders_store_name ON orders(store_name);

-- GIN index for JSONB queries on raw_data
CREATE INDEX IF NOT EXISTS idx_orders_raw_data ON orders USING GIN (raw_data);
CREATE INDEX IF NOT EXISTS idx_order_items_raw_data ON order_items USING GIN (raw_data);

-- Junction tables for many-to-many relationships
CREATE TABLE IF NOT EXISTS order_deliveries (
    order_id VARCHAR(50) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    delivery_id VARCHAR(50) NOT NULL,
    PRIMARY KEY (order_id, delivery_id)
);

CREATE TABLE IF NOT EXISTS order_billing_documents (
    order_id VARCHAR(50) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    billing_document_number VARCHAR(50) NOT NULL,
    PRIMARY KEY (order_id, billing_document_number)
);

-- Indexes for junction tables
CREATE INDEX IF NOT EXISTS idx_order_deliveries_delivery_id ON order_deliveries(delivery_id);
CREATE INDEX IF NOT EXISTS idx_order_billing_documents_billing_doc ON order_billing_documents(billing_document_number);

-- Foreign key constraints for billing documents
-- Note: order_id and delivery_id may be NULL, so we don't add NOT NULL constraints
-- The junction table order_billing_documents handles many-to-many relationships

-- Billing documents table
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
);

-- Billing document items table
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
);

-- Indexes for billing documents
CREATE INDEX IF NOT EXISTS idx_billing_document_items_billing_document_id ON billing_document_items(billing_document_id);
CREATE INDEX IF NOT EXISTS idx_billing_documents_customer_id ON billing_documents(customer_id);
CREATE INDEX IF NOT EXISTS idx_billing_documents_billing_document_date ON billing_documents(billing_document_date);
CREATE INDEX IF NOT EXISTS idx_billing_documents_store_name ON billing_documents(store_name);
CREATE INDEX IF NOT EXISTS idx_billing_documents_billing_document_number ON billing_documents(billing_document_number);
CREATE INDEX IF NOT EXISTS idx_billing_documents_order_id ON billing_documents(order_id);
CREATE INDEX IF NOT EXISTS idx_billing_documents_delivery_id ON billing_documents(delivery_id);
CREATE INDEX IF NOT EXISTS idx_billing_documents_status ON billing_documents(status);
CREATE INDEX IF NOT EXISTS idx_billing_documents_billing_document_type ON billing_documents(billing_document_type);

-- GIN indexes for JSONB queries on raw_data
CREATE INDEX IF NOT EXISTS idx_billing_documents_raw_data ON billing_documents USING GIN (raw_data);
CREATE INDEX IF NOT EXISTS idx_billing_document_items_raw_data ON billing_document_items USING GIN (raw_data);

