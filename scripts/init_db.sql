-- ============================================================
-- SQLWhisperer: Sample E-Commerce Schema
-- ============================================================
-- This schema is used for the demo instance.  It models a
-- simple e-commerce platform with customers, products, orders,
-- and order line items.
-- ============================================================

-- Customers
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    signup_date DATE NOT NULL,
    country VARCHAR(100),
    tier VARCHAR(20) DEFAULT 'free'
        CHECK (tier IN ('free', 'pro', 'enterprise')),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Products
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    cost DECIMAL(10, 2),
    stock_quantity INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    order_date TIMESTAMP NOT NULL DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled')),
    total_amount DECIMAL(10, 2),
    discount_pct DECIMAL(5, 2) DEFAULT 0,
    shipping_country VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Order Items (line items)
CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(10, 2) NOT NULL,
    line_total DECIMAL(10, 2) GENERATED ALWAYS AS (quantity * unit_price) STORED
);

-- ─── Indexes for common query patterns ───────────────────────
CREATE INDEX IF NOT EXISTS idx_customers_signup    ON customers(signup_date);
CREATE INDEX IF NOT EXISTS idx_customers_country   ON customers(country);
CREATE INDEX IF NOT EXISTS idx_orders_date         ON orders(order_date);
CREATE INDEX IF NOT EXISTS idx_orders_customer     ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status       ON orders(status);
CREATE INDEX IF NOT EXISTS idx_order_items_order   ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_products_category   ON products(category);
