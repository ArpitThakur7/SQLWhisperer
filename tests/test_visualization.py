"""Tests for the High-End Auto-Visualization Studio Engine."""

import pandas as pd
import pytest
from src.visualization.auto_chart import (
    detect_best_chart,
    create_plotly_figure,
    calculate_data_stats,
    generate_visual_insights,
    PALETTES,
)


def test_kpi_card_detection():
    df = pd.DataFrame([{"total_sales": 150000.75}])
    rec = detect_best_chart(df, "what is our total sales?")
    assert rec.chart_type == "metric"
    fig = create_plotly_figure(df, rec)
    assert fig is not None


def test_treemap_hierarchy_detection():
    df = pd.DataFrame({
        "category": ["Electronics", "Electronics", "Furniture", "Furniture"],
        "product": ["Laptop", "Mouse", "Desk", "Chair"],
        "revenue": [50000, 3000, 20000, 15000],
    })
    rec = detect_best_chart(df, "show category and product breakdown")
    assert rec.chart_type == "treemap"
    fig = create_plotly_figure(df, rec)
    assert fig is not None


def test_funnel_detection():
    df = pd.DataFrame({
        "status": ["Created", "Processing", "Shipped", "Delivered"],
        "count": [1000, 850, 700, 680],
    })
    rec = detect_best_chart(df, "order status conversion funnel")
    assert rec.chart_type == "funnel"
    fig = create_plotly_figure(df, rec)
    assert fig is not None


def test_choropleth_map_detection():
    df = pd.DataFrame({
        "country": ["United States", "Germany", "United Kingdom", "Canada"],
        "sales": [45000, 23000, 19000, 12000],
    })
    rec = detect_best_chart(df, "show global sales country map")
    assert rec.chart_type == "choropleth"
    fig = create_plotly_figure(df, rec)
    assert fig is not None


def test_time_series_area_with_trendline():
    df = pd.DataFrame({
        "order_date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
        "revenue": [1200, 2400, 1800, 3100, 2900],
    })
    rec = detect_best_chart(df, "show revenue growth over time")
    assert rec.chart_type in ("area", "line")
    fig = create_plotly_figure(df, rec, show_trendline=True, palette_name="Emerald Aurora")
    assert fig is not None


def test_donut_composition():
    df = pd.DataFrame({
        "tier": ["Gold", "Silver", "Bronze"],
        "member_count": [400, 800, 1500],
    })
    rec = detect_best_chart(df, "distribution of customer tiers")
    assert rec.chart_type == "pie"
    fig = create_plotly_figure(df, rec, palette_name="Sunset Flare")
    assert fig is not None


def test_ranked_horizontal_bar():
    df = pd.DataFrame({
        "product_name": [
            "Ultra Ergonomic Wireless Mechanical Keyboard",
            "Curved Ultrawide 49-inch Gaming Display",
            "Active Noise Cancelling Studio Headphones",
        ],
        "units_sold": [1400, 320, 890],
    })
    rec = detect_best_chart(df, "top selling products ranking")
    assert rec.chart_type == "bar"
    assert rec.is_horizontal is True
    fig = create_plotly_figure(df, rec)
    assert fig is not None


def test_statistical_ribbon_and_analytical_insights():
    df = pd.DataFrame({
        "category": ["Laptops", "Smartphones", "Audio", "Accessories", "Wearables"],
        "revenue": [85000, 72000, 12000, 8000, 5000],
    })
    stats = calculate_data_stats(df, "revenue")
    assert stats["total"] == 182000.0
    assert stats["peak_label"] == "Laptops"

    rec = detect_best_chart(df, "sales by category")
    insights = generate_visual_insights(df, rec, stats)
    assert len(insights) >= 2
    assert any("Laptops" in ins for ins in insights)
    assert any("Concentration Risk" in ins or "Top Contributor" in ins for ins in insights)
