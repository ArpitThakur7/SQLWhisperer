"""Zero-Setup SQLite Demo Database Generator for SQLWhisperer.

Creates and seeds an embedded SQLite e-commerce database with realistic
customers, products, orders, and order items. Enables SQLWhisperer to run
out of the box with zero external database setup.

Usage:
    python -m scripts.seed_sqlite
"""

import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SQLITE_DB_PATH = DATA_DIR / "demo_ecommerce.db"

# Sample Data Archetypes
PRODUCT_ADJECTIVES = [
    "Premium", "Classic", "Ultra", "Eco", "Smart", "Turbo",
    "Elite", "Mini", "Max", "Nano", "Pro", "Lite",
]
PRODUCT_NOUNS = [
    "Widget", "Gadget", "Device", "Tool", "Kit", "Pack",
    "Sensor", "Module", "Hub", "Dock", "Pad", "Band",
]
CATEGORIES = [
    "Electronics", "Clothing", "Home & Garden",
    "Books", "Sports", "Food & Beverage",
]
COUNTRIES = ["US", "UK", "DE", "FR", "JP", "IN", "BR", "CA", "AU", "KR"]
TIERS = ["free", "pro", "enterprise"]
FIRST_NAMES = [
    "Alice", "Bob", "Carlos", "Diana", "Emil", "Faye",
    "George", "Hannah", "Ivan", "Julia", "Kevin", "Luna",
    "Marco", "Nina", "Oscar", "Priya", "Quinn", "Rosa",
    "Sam", "Tina",
]
LAST_NAMES = [
    "Smith", "Johnson", "Lee", "Garcia", "Mueller", "Kim",
    "Singh", "Brown", "Wilson", "Chen", "Patel", "Davis",
    "Martinez", "Taylor", "Thomas", "White", "Lopez", "Clark",
]
STATUSES = ["confirmed", "shipped", "delivered", "cancelled"]


def create_sqlite_schema(conn: sqlite3.Connection):
    """Create SQLite tables matching the e-commerce schema."""
    cursor = conn.cursor()

    cursor.executescript("""
    DROP TABLE IF EXISTS order_items;
    DROP TABLE IF EXISTS orders;
    DROP TABLE IF EXISTS products;
    DROP TABLE IF EXISTS customers;

    CREATE TABLE customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        country TEXT NOT NULL,
        tier TEXT DEFAULT 'free',
        created_at TEXT NOT NULL
    );

    CREATE TABLE products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        price REAL NOT NULL,
        cost REAL NOT NULL,
        stock_quantity INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        status TEXT DEFAULT 'confirmed',
        total_amount REAL NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customers(id)
    );

    CREATE TABLE order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );

    CREATE INDEX idx_customers_tier ON customers(tier);
    CREATE INDEX idx_orders_customer ON orders(customer_id);
    CREATE INDEX idx_orders_created ON orders(created_at);
    CREATE INDEX idx_order_items_order ON order_items(order_id);
    """)
    conn.commit()


def seed_sqlite(db_path: Path = SQLITE_DB_PATH):
    """Populate SQLite database with realistic mock data."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    random.seed(42)

    conn = sqlite3.connect(str(db_path))
    create_sqlite_schema(conn)
    cursor = conn.cursor()

    # 1. Customers
    customers = []
    base_date = datetime(2024, 1, 1)
    for i in range(1, 201):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        email = f"{first.lower()}.{last.lower()}{i}@example.com"
        country = random.choice(COUNTRIES)
        tier = random.choices(TIERS, weights=[0.6, 0.3, 0.1])[0]
        created = base_date + timedelta(days=random.randint(0, 300))
        customers.append((name, email, country, tier, created.isoformat()))

    cursor.executemany(
        "INSERT INTO customers (name, email, country, tier, created_at) VALUES (?, ?, ?, ?, ?)",
        customers,
    )

    # 2. Products
    products = []
    for i in range(1, 61):
        name = f"{random.choice(PRODUCT_ADJECTIVES)} {random.choice(PRODUCT_NOUNS)} {i}"
        category = random.choice(CATEGORIES)
        price = round(random.uniform(9.99, 499.99), 2)
        cost = round(price * random.uniform(0.3, 0.6), 2)
        stock = random.randint(10, 500)
        created = (base_date + timedelta(days=random.randint(0, 60))).isoformat()
        products.append((name, category, price, cost, stock, created))

    cursor.executemany(
        "INSERT INTO products (name, category, price, cost, stock_quantity, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        products,
    )

    # 3. Orders & Order Items
    cursor.execute("SELECT id FROM customers")
    customer_ids = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT id, price FROM products")
    product_rows = cursor.fetchall()

    orders = []
    order_items = []
    order_id = 1

    for _ in range(600):
        cust_id = random.choice(customer_ids)
        status = random.choices(STATUSES, weights=[0.2, 0.25, 0.45, 0.1])[0]
        order_date = base_date + timedelta(
            days=random.randint(30, 330),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )

        num_items = random.randint(1, 4)
        chosen_products = random.sample(product_rows, num_items)

        total = 0.0
        for p_id, p_price in chosen_products:
            qty = random.randint(1, 3)
            item_total = round(p_price * qty, 2)
            total += item_total
            order_items.append((order_id, p_id, qty, p_price))

        orders.append((cust_id, status, round(total, 2), order_date.isoformat()))
        order_id += 1

    cursor.executemany(
        "INSERT INTO orders (customer_id, status, total_amount, created_at) VALUES (?, ?, ?, ?)",
        orders,
    )

    cursor.executemany(
        "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
        order_items,
    )

    conn.commit()
    conn.close()
    print(f"[*] SQLite demo database successfully created at:\n    {db_path}")
    print(f"    - Customers: {len(customers)}")
    print(f"    - Products:  {len(products)}")
    print(f"    - Orders:    {len(orders)}")
    print(f"    - Items:     {len(order_items)}")


if __name__ == "__main__":
    seed_sqlite()
