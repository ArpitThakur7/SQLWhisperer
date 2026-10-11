"""Seed ChromaDB with curated few-shot SQL examples.

Run with:
    python -m scripts.seed_few_shots

These examples teach the model your schema's patterns —
JOINs, date filtering, aggregations, subqueries, and
edge cases specific to the e-commerce schema.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.memory.few_shot_store import FewShotStore


SEED_EXAMPLES = [
    {
        "question": "How many customers signed up each month in 2024?",
        "sql": (
            "SELECT DATE_TRUNC('month', signup_date) AS month, "
            "COUNT(*) AS signups "
            "FROM customers "
            "WHERE signup_date >= '2024-01-01' AND signup_date < '2025-01-01' "
            "GROUP BY DATE_TRUNC('month', signup_date) "
            "ORDER BY month;"
        ),
        "explanation": "Monthly signup counts for calendar year 2024.",
    },
    {
        "question": "What are the top 5 best-selling products by total quantity sold?",
        "sql": (
            "SELECT p.name, p.category, SUM(oi.quantity) AS total_sold "
            "FROM products p "
            "JOIN order_items oi ON p.id = oi.product_id "
            "GROUP BY p.id, p.name, p.category "
            "ORDER BY total_sold DESC "
            "LIMIT 5;"
        ),
        "explanation": "Top 5 products ranked by total units sold across all orders.",
    },
    {
        "question": "Show revenue by product category for the last 30 days",
        "sql": (
            "SELECT p.category, SUM(oi.line_total) AS revenue "
            "FROM products p "
            "JOIN order_items oi ON p.id = oi.product_id "
            "JOIN orders o ON oi.order_id = o.id "
            "WHERE o.order_date >= CURRENT_DATE - INTERVAL '30 days' "
            "GROUP BY p.category "
            "ORDER BY revenue DESC;"
        ),
        "explanation": "Category-level revenue for the trailing 30-day window.",
    },
    {
        "question": "Which customers have spent more than $1000 total?",
        "sql": (
            "SELECT c.full_name, c.email, SUM(o.total_amount) AS total_spent "
            "FROM customers c "
            "JOIN orders o ON c.id = o.customer_id "
            "WHERE o.status != 'cancelled' "
            "GROUP BY c.id, c.full_name, c.email "
            "HAVING SUM(o.total_amount) > 1000 "
            "ORDER BY total_spent DESC;"
        ),
        "explanation": "High-value customers who have spent over $1000 (excluding cancelled orders).",
    },
    {
        "question": "Average order value by customer tier",
        "sql": (
            "SELECT c.tier, "
            "ROUND(AVG(o.total_amount), 2) AS avg_order_value, "
            "COUNT(o.id) AS order_count "
            "FROM customers c "
            "JOIN orders o ON c.id = o.customer_id "
            "WHERE o.status != 'cancelled' "
            "GROUP BY c.tier "
            "ORDER BY avg_order_value DESC;"
        ),
        "explanation": "Compares average order values across free, pro, and enterprise tiers.",
    },
    {
        "question": "Show monthly revenue trend for 2024",
        "sql": (
            "SELECT DATE_TRUNC('month', o.order_date) AS month, "
            "SUM(o.total_amount) AS revenue, "
            "COUNT(DISTINCT o.id) AS order_count "
            "FROM orders o "
            "WHERE o.order_date >= '2024-01-01' AND o.order_date < '2025-01-01' "
            "AND o.status != 'cancelled' "
            "GROUP BY DATE_TRUNC('month', o.order_date) "
            "ORDER BY month;"
        ),
        "explanation": "Month-by-month revenue and order count for 2024.",
    },
    {
        "question": "Products with low stock that have been ordered recently",
        "sql": (
            "SELECT p.name, p.category, p.stock_quantity, "
            "COUNT(DISTINCT oi.order_id) AS recent_orders "
            "FROM products p "
            "JOIN order_items oi ON p.id = oi.product_id "
            "JOIN orders o ON oi.order_id = o.id "
            "WHERE p.stock_quantity < 10 "
            "AND o.order_date >= CURRENT_DATE - INTERVAL '30 days' "
            "GROUP BY p.id, p.name, p.category, p.stock_quantity "
            "ORDER BY recent_orders DESC;"
        ),
        "explanation": "Low-stock products still seeing demand — restock candidates.",
    },
    {
        "question": "Customer retention: how many customers placed more than one order?",
        "sql": (
            "SELECT COUNT(*) AS repeat_customers, "
            "ROUND(COUNT(*)::NUMERIC / (SELECT COUNT(*) FROM customers) * 100, 2) "
            "AS retention_pct "
            "FROM ("
            "  SELECT customer_id "
            "  FROM orders "
            "  WHERE status != 'cancelled' "
            "  GROUP BY customer_id "
            "  HAVING COUNT(*) > 1"
            ") AS repeats;"
        ),
        "explanation": "Percentage of customers who are repeat buyers.",
    },
    {
        "question": "What is the cancellation rate by shipping country?",
        "sql": (
            "SELECT shipping_country, "
            "COUNT(*) AS total_orders, "
            "SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled, "
            "ROUND("
            "  SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END)::NUMERIC "
            "  / COUNT(*) * 100, 2"
            ") AS cancel_rate_pct "
            "FROM orders "
            "GROUP BY shipping_country "
            "ORDER BY cancel_rate_pct DESC;"
        ),
        "explanation": "Cancellation rates per country — useful for logistics analysis.",
    },
    {
        "question": (
            "Top 10 products by revenue for customers who signed up in Q3 2024"
        ),
        "sql": (
            "SELECT p.name, p.category, SUM(oi.line_total) AS revenue "
            "FROM products p "
            "JOIN order_items oi ON p.id = oi.product_id "
            "JOIN orders o ON oi.order_id = o.id "
            "JOIN customers c ON o.customer_id = c.id "
            "WHERE c.signup_date >= '2024-07-01' AND c.signup_date < '2024-10-01' "
            "GROUP BY p.id, p.name, p.category "
            "ORDER BY revenue DESC "
            "LIMIT 10;"
        ),
        "explanation": (
            "Revenue-ranked products purchased by Q3 2024 cohort customers."
        ),
    },
]


def seed():
    """Load curated few-shot examples into ChromaDB."""
    store = FewShotStore()
    existing = store.count
    if existing > 0:
        print(f"⚠️ ChromaDB already has {existing} examples. Skipping seed.")
        print("   Delete the chroma directory to re-seed.")
        return

    store.seed_examples(SEED_EXAMPLES)
    print(f"✅ Seeded {len(SEED_EXAMPLES)} few-shot examples into ChromaDB")


if __name__ == "__main__":
    seed()
