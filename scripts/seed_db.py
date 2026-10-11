"""Seed the PostgreSQL database with realistic e-commerce sample data.

Run with:
    python -m scripts.seed_db

Generates:
    - 500 customers (spread across 2024)
    - 100 products (6 categories)
    - 2000 orders with 1-5 items each
"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import settings

# ── Constants ─────────────────────────────────────────────────────

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


def seed():
    """Populate the database with sample data."""
    engine = create_engine(settings.database_url)

    with engine.begin() as conn:
        # ── Customers ─────────────────────────────────────────────
        print("Seeding 500 customers...")
        for i in range(500):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            signup = datetime(2024, 1, 1) + timedelta(
                days=random.randint(0, 364)
            )
            conn.execute(
                text(
                    """
                    INSERT INTO customers (email, full_name, signup_date, country, tier)
                    VALUES (:email, :name, :signup, :country, :tier)
                    ON CONFLICT (email) DO NOTHING
                    """
                ),
                {
                    "email": f"{first.lower()}.{last.lower()}.{i}@example.com",
                    "name": f"{first} {last}",
                    "signup": signup,
                    "country": random.choice(COUNTRIES),
                    "tier": random.choices(TIERS, weights=[60, 30, 10])[0],
                },
            )

        # ── Products ──────────────────────────────────────────────
        print("Seeding 100 products...")
        for i in range(100):
            adj = random.choice(PRODUCT_ADJECTIVES)
            noun = random.choice(PRODUCT_NOUNS)
            price = round(random.uniform(9.99, 499.99), 2)
            conn.execute(
                text(
                    """
                    INSERT INTO products (name, category, price, cost, stock_quantity)
                    VALUES (:name, :cat, :price, :cost, :stock)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "name": f"{adj} {noun} {i + 1}",
                    "cat": random.choice(CATEGORIES),
                    "price": price,
                    "cost": round(price * random.uniform(0.3, 0.7), 2),
                    "stock": random.randint(0, 500),
                },
            )

        # ── Orders + Order Items ──────────────────────────────────
        print("Seeding 2000 orders with items...")
        for _ in range(2000):
            cust_id = random.randint(1, 500)
            order_date = datetime(2024, 1, 1) + timedelta(
                days=random.randint(0, 364),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            status = random.choices(
                STATUSES, weights=[15, 25, 50, 10]
            )[0]

            result = conn.execute(
                text(
                    """
                    INSERT INTO orders (
                        customer_id, order_date, status,
                        discount_pct, shipping_country
                    )
                    VALUES (:cust, :date, :status, :disc, :country)
                    RETURNING id
                    """
                ),
                {
                    "cust": cust_id,
                    "date": order_date,
                    "status": status,
                    "disc": round(random.uniform(0, 20), 2),
                    "country": random.choice(COUNTRIES),
                },
            )
            order_id = result.scalar()

            # 1–5 line items per order
            total = 0.0
            num_items = random.randint(1, 5)
            for _ in range(num_items):
                prod_id = random.randint(1, 100)
                qty = random.randint(1, 4)
                unit_price = round(random.uniform(9.99, 499.99), 2)
                total += qty * unit_price
                conn.execute(
                    text(
                        """
                        INSERT INTO order_items (
                            order_id, product_id, quantity, unit_price
                        )
                        VALUES (:oid, :pid, :qty, :price)
                        """
                    ),
                    {
                        "oid": order_id,
                        "pid": prod_id,
                        "qty": qty,
                        "price": unit_price,
                    },
                )

            # Update order total
            conn.execute(
                text(
                    "UPDATE orders SET total_amount = :total WHERE id = :oid"
                ),
                {"total": round(total, 2), "oid": order_id},
            )

    print("✅ Seeded: 500 customers, 100 products, 2000 orders")


if __name__ == "__main__":
    seed()
