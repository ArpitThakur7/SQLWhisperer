"""Auto-Visualization Studio Engine for SQLWhisperer."""

from src.visualization.auto_chart import (
    ChartRecommendation,
    detect_best_chart,
    create_plotly_figure,
    calculate_data_stats,
    generate_visual_insights,
    PALETTES,
)

__all__ = [
    "ChartRecommendation",
    "detect_best_chart",
    "create_plotly_figure",
    "calculate_data_stats",
    "generate_visual_insights",
    "PALETTES",
]
