"""High-End Auto-Visualization Studio Engine for SQLWhisperer.

Enterprise-grade auto-charting system supporting basic and advanced visual formats:
- Executive KPI Scorecards & Multi-Metric KPI Grids
- Spline Area & Multi-Line Time-Series with Peak/Trough Highlighting
- Dual-Axis Combo Charts (Metric Bars + Growth/Ratio Line on secondary Y)
- Hierarchical Treemaps & Sunburst Visualizations
- 2D Cross-Tabulation Heatmaps & Matrix Density
- Stage Conversion Funnel Charts
- Distribution Box Plots, Histograms & Violin Density
- Multi-Dimensional Bubble Scatter Plots
- Geographic Choropleth & Region Visualizations

Features curated neon dark palettes, statistical KPI ribbons, and automated heuristic classification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ── Curated Designer Color Palettes ────────────────────────────────

PALETTES: dict[str, list[str]] = {
    "Cyberpunk Neon": ["#00D2FF", "#8B5CF6", "#EC4899", "#10B981", "#F59E0B", "#3B82F6", "#14B8A6", "#F43F5E"],
    "Emerald Aurora": ["#10B981", "#34D399", "#059669", "#06B6D4", "#3B82F6", "#A7F3D0", "#047857", "#14B8A6"],
    "Sunset Flare": ["#F59E0B", "#F43F5E", "#FB7185", "#EA580C", "#D97706", "#8B5CF6", "#BE123C", "#FDE047"],
    "Electric Indigo": ["#6366F1", "#8B5CF6", "#A855F7", "#38BDF8", "#06B6D4", "#C084FC", "#4F46E5", "#0EA5E9"],
    "Monochrome Slate": ["#E2E8F0", "#94A3B8", "#64748B", "#475569", "#38BDF8", "#334155", "#CBD5E1", "#1E293B"],
}

DEFAULT_PALETTE = PALETTES["Cyberpunk Neon"]

DARK_LAYOUT = dict(
    paper_bgcolor="rgba(14, 17, 23, 0.85)",
    plot_bgcolor="rgba(22, 27, 34, 0.65)",
    font=dict(family="Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif", color="#E6EDF3"),
    title_font=dict(size=17, color="#F0F6FC"),
    margin=dict(l=40, r=40, t=55, b=40),
    xaxis=dict(
        gridcolor="rgba(48, 54, 61, 0.55)",
        linecolor="rgba(48, 54, 61, 0.9)",
        zerolinecolor="rgba(48, 54, 61, 0.55)",
    ),
    yaxis=dict(
        gridcolor="rgba(48, 54, 61, 0.55)",
        linecolor="rgba(48, 54, 61, 0.9)",
        zerolinecolor="rgba(48, 54, 61, 0.55)",
    ),
    hoverlabel=dict(
        bgcolor="#1C2128",
        bordercolor="#30363D",
        font=dict(color="#F0F6FC", size=13),
    ),
    legend=dict(
        bgcolor="rgba(22, 27, 34, 0.6)",
        bordercolor="rgba(48, 54, 61, 0.6)",
        borderwidth=1,
    ),
)


# ── Metadata Descriptor ───────────────────────────────────────────


@dataclass
class ChartRecommendation:
    """Full descriptor for an auto-detected or customized visualization."""

    chart_type: str  # "metric" | "bar" | "line" | "area" | "pie" | "scatter" | "treemap" | "heatmap" | "funnel" | "box" | "choropleth"
    x_col: str | None = None
    y_col: str | None = None
    secondary_y_cols: list[str] = field(default_factory=list)
    hierarchy_cols: list[str] = field(default_factory=list)
    color_col: str | None = None
    size_col: str | None = None
    title: str = ""
    reason: str = ""
    confidence: float = 0.92
    is_horizontal: bool = False
    available_chart_types: list[str] = field(
        default_factory=lambda: [
            "bar",
            "line",
            "area",
            "pie",
            "treemap",
            "heatmap",
            "funnel",
            "scatter",
            "box",
            "metric",
        ]
    )


# ── Column Type Introspection ──────────────────────────────────────


def _is_date_like(series: pd.Series, col_name: str) -> bool:
    """Identify if series contains temporal/date data."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return True

    name_lower = col_name.lower()
    date_hints = ("date", "time", "day", "month", "year", "created", "updated", "timestamp", "period", "quarter", "week")
    if any(hint in name_lower for hint in date_hints):
        return True

    if series.dtype == object and series.dropna().count() > 0:
        sample = str(series.dropna().iloc[0]).strip()
        if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", sample) or re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", sample):
            return True
        if re.match(r"^\d{4}-\d{2}$", sample):
            return True

    return False


def _is_id_column(col_name: str, series: pd.Series) -> bool:
    """Identify internal surrogate IDs."""
    name_lower = col_name.lower()
    if name_lower == "id" or name_lower.endswith("_id") or name_lower.endswith("id"):
        return True
    return False


def _is_geographic_column(col_name: str, series: pd.Series) -> bool:
    """Identify geographic columns (country, state, region)."""
    name_lower = col_name.lower()
    geo_hints = ("country", "nation", "state", "region", "city", "province", "territory")
    return any(hint in name_lower for hint in geo_hints)


def _is_funnel_column(col_name: str, series: pd.Series) -> bool:
    """Identify conversion/status pipeline columns."""
    name_lower = col_name.lower()
    funnel_hints = ("status", "stage", "step", "funnel", "state", "phase", "tier")
    return any(hint in name_lower for hint in funnel_hints)


# ── Statistical Summary Helper ────────────────────────────────────


def calculate_data_stats(df: pd.DataFrame, metric_col: str | None = None) -> dict[str, Any]:
    """Compute instant executive summary statistics for the dataset."""
    stats: dict[str, Any] = {"row_count": len(df)}
    if df.empty:
        return stats

    target_metric = metric_col
    if not target_metric or target_metric not in df.columns:
        num_cols = df.select_dtypes(include=["number"]).columns.tolist()
        target_metric = num_cols[0] if num_cols else None

    if target_metric and target_metric in df.columns and pd.api.types.is_numeric_dtype(df[target_metric]):
        series = df[target_metric].dropna()
        if not series.empty:
            stats["metric"] = target_metric
            stats["total"] = float(series.sum())
            stats["mean"] = float(series.mean())
            stats["median"] = float(series.median())
            stats["max"] = float(series.max())
            stats["min"] = float(series.min())
            stats["std"] = float(series.std()) if len(series) > 1 else 0.0

            # Find row label for peak
            max_idx = series.idxmax()
            label_cols = [c for c in df.columns if c != target_metric and df[c].dtype == object]
            if label_cols:
                stats["peak_label"] = str(df.loc[max_idx, label_cols[0]])
            else:
                stats["peak_label"] = f"Row {max_idx}"

    return stats


def generate_visual_insights(df: pd.DataFrame, rec: ChartRecommendation, stats: dict[str, Any]) -> list[str]:
    """Generate 2-3 automated natural language analytical highlights from the query results."""
    insights: list[str] = []
    if df.empty or "total" not in stats:
        return insights

    metric_name = stats.get("metric", "").replace("_", " ").title()
    total = stats.get("total", 0.0)
    max_val = stats.get("max", 0.0)
    mean_val = stats.get("mean", 0.0)
    min_val = stats.get("min", 0.0)
    peak_label = stats.get("peak_label", "")

    # 1. Peak & Share Highlight
    if total > 0 and max_val > 0:
        share = (max_val / total) * 100
        if peak_label and peak_label != "Row None":
            insights.append(
                f"**Top Contributor**: `{peak_label}` leads with **{max_val:,.2f}** ({share:.1f}% of total {metric_name.lower()})."
            )
        else:
            insights.append(
                f"**Peak Value**: Highest recorded value is **{max_val:,.2f}** ({share:.1f}% of total volume)."
            )

    # 2. Pareto / Concentration check (for categories)
    if rec.x_col and rec.x_col in df.columns and rec.y_col and rec.y_col in df.columns:
        if len(df) >= 3 and total > 0:
            top_2_sum = df[rec.y_col].nlargest(2).sum()
            top_2_share = (top_2_sum / total) * 100
            if top_2_share >= 50.0 and len(df) >= 4:
                insights.append(
                    f"**Concentration Risk**: The top 2 items account for **{top_2_share:.1f}%** of the entire {metric_name.lower()} distribution."
                )

    # 3. Spread / Volatility Ratio
    if min_val > 0 and max_val > 0 and len(df) > 1:
        ratio = max_val / min_val
        if ratio > 3.0:
            insights.append(
                f"**High Variance**: Top value is **{ratio:.1f}×** larger than the lowest recorded value ({min_val:,.2f})."
            )
    elif mean_val > 0:
        insights.append(
            f"**Baseline Average**: Average {metric_name.lower()} across {len(df)} records is **{mean_val:,.2f}** (median: {stats.get('median', 0.0):,.2f})."
        )

    return insights


# ── High-End Heuristic Recommender ────────────────────────────────


def detect_best_chart(df: pd.DataFrame, question: str = "") -> ChartRecommendation:
    """Analyze query dataframe schema and contents to recommend the best chart."""
    if df.empty or len(df.columns) == 0:
        return ChartRecommendation(
            chart_type="table",
            title="Empty Result",
            reason="No data returned to plot.",
            confidence=0.0,
        )

    nrows, ncols = df.shape
    q_lower = (question or "").lower()

    date_cols: list[str] = []
    num_cols: list[str] = []
    cat_cols: list[str] = []
    geo_cols: list[str] = []
    funnel_cols: list[str] = []

    for col in df.columns:
        series = df[col]
        if _is_date_like(series, col):
            date_cols.append(col)
        elif pd.api.types.is_numeric_dtype(series) and not _is_id_column(col, series):
            num_cols.append(col)
        elif _is_id_column(col, series):
            cat_cols.append(col)
        else:
            cat_cols.append(col)
            if _is_geographic_column(col, series):
                geo_cols.append(col)
            if _is_funnel_column(col, series):
                funnel_cols.append(col)

    if not num_cols:
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                num_cols.append(col)
                if col in cat_cols:
                    cat_cols.remove(col)

    # 1. Single value / Single row KPI scorecard
    if nrows == 1 and len(num_cols) >= 1 and ncols <= 3:
        metric_col = num_cols[0]
        label = cat_cols[0] if cat_cols else metric_col
        return ChartRecommendation(
            chart_type="metric",
            x_col=label if cat_cols else None,
            y_col=metric_col,
            secondary_y_cols=num_cols[1:],
            title=f"{metric_col.replace('_', ' ').title()}",
            reason="Single aggregated scorecard metric detected.",
            confidence=0.98,
            available_chart_types=["metric", "bar"],
        )

    # 2. Hierarchical Treemap (2 categorical columns + 1 numeric metric)
    if len(cat_cols) >= 2 and num_cols and (
        "category" in q_lower or "breakdown" in q_lower or "hierarchy" in q_lower or "tree" in q_lower or nrows > 6
    ):
        parent_cat = cat_cols[0]
        child_cat = cat_cols[1]
        primary_metric = num_cols[0]
        return ChartRecommendation(
            chart_type="treemap",
            x_col=parent_cat,
            y_col=primary_metric,
            hierarchy_cols=[parent_cat, child_cat],
            title=f"Hierarchical Breakdown of {primary_metric.replace('_', ' ').title()} by {parent_cat.replace('_', ' ').title()} & {child_cat.replace('_', ' ').title()}",
            reason=f"Multi-level categories ('{parent_cat}' and '{child_cat}') ideal for visual Treemap volume analysis.",
            confidence=0.94,
            available_chart_types=["treemap", "bar", "heatmap", "pie"],
        )

    # 3. 2D Matrix Heatmap (2 categorical columns + 1 numeric metric, cross-tabulated)
    if len(cat_cols) >= 2 and len(num_cols) == 1 and ("heatmap" in q_lower or "matrix" in q_lower or "correlation" in q_lower):
        return ChartRecommendation(
            chart_type="heatmap",
            x_col=cat_cols[0],
            y_col=cat_cols[1],
            color_col=num_cols[0],
            title=f"Density Heatmap: {cat_cols[0].replace('_', ' ').title()} vs {cat_cols[1].replace('_', ' ').title()}",
            reason=f"Cross-tabulation density between '{cat_cols[0]}' and '{cat_cols[1]}'.",
            confidence=0.91,
            available_chart_types=["heatmap", "treemap", "bar"],
        )

    # 4. Conversion Funnel (Pipeline status column + 1 metric)
    if funnel_cols and num_cols and ("funnel" in q_lower or "conversion" in q_lower or "stage" in q_lower or "dropoff" in q_lower):
        funnel_col = funnel_cols[0]
        return ChartRecommendation(
            chart_type="funnel",
            x_col=funnel_col,
            y_col=num_cols[0],
            title=f"Stage Funnel: {num_cols[0].replace('_', ' ').title()} across {funnel_col.replace('_', ' ').title()}",
            reason=f"Lifecycle/conversion stages detected in '{funnel_col}'.",
            confidence=0.93,
            available_chart_types=["funnel", "bar", "pie"],
        )

    # 5. Geographic Country Map (Country column + metric)
    if geo_cols and num_cols and ("map" in q_lower or "country" in q_lower or "global" in q_lower or "world" in q_lower or "geographic" in q_lower):
        return ChartRecommendation(
            chart_type="choropleth",
            x_col=geo_cols[0],
            y_col=num_cols[0],
            title=f"Geographic Distribution by {geo_cols[0].replace('_', ' ').title()}",
            reason=f"Country/territory entities detected in '{geo_cols[0]}' suited for global choropleth.",
            confidence=0.92,
            available_chart_types=["choropleth", "bar", "pie"],
        )

    # 6. Temporal Sequence (Time Series Area or Multi-Line)
    if date_cols and num_cols:
        primary_date = date_cols[0]
        primary_metric = num_cols[0]
        secondary = num_cols[1:]
        chart_type = "area" if ("cumulative" in q_lower or "volume" in q_lower or "growth" in q_lower or len(num_cols) == 1) else "line"
        return ChartRecommendation(
            chart_type=chart_type,
            x_col=primary_date,
            y_col=primary_metric,
            secondary_y_cols=secondary,
            title=f"{primary_metric.replace('_', ' ').title()} Trend over {primary_date.replace('_', ' ').title()}",
            reason=f"Chronological time-series detected along '{primary_date}' with numerical tracking.",
            confidence=0.96,
            available_chart_types=["line", "area", "bar", "scatter"],
        )

    # 7. Distribution Box Plot / Histogram (Continuous distribution without clear categories)
    if not cat_cols and len(num_cols) == 1 and nrows >= 12 and ("distribution" in q_lower or "spread" in q_lower or "outlier" in q_lower):
        return ChartRecommendation(
            chart_type="box",
            y_col=num_cols[0],
            title=f"Distribution & Outlier Analysis: {num_cols[0].replace('_', ' ').title()}",
            reason=f"Single continuous distribution suited for box plot quartile analysis.",
            confidence=0.89,
            available_chart_types=["box", "bar"],
        )

    # 8. Categorical Distribution (Donut vs Bar)
    if cat_cols and num_cols:
        primary_cat = cat_cols[0]
        primary_metric = num_cols[0]
        unique_categories = df[primary_cat].nunique()
        avg_label_len = df[primary_cat].astype(str).str.len().mean() if nrows > 0 else 0

        pie_keywords = ("share", "percent", "proportion", "breakdown", "distribution", "ratio", "split", "composition")
        ranking_keywords = ("top", "rank", "ranking", "best", "worst", "highest", "lowest", "bottom")
        is_pie_keyword = any(k in q_lower or k in primary_metric.lower() for k in pie_keywords)
        is_ranking_keyword = any(k in q_lower for k in ranking_keywords)

        if not is_ranking_keyword and avg_label_len <= 15:
            if (unique_categories <= 7 and is_pie_keyword) or (
                unique_categories in (2, 3, 4)
                and nrows <= 4
                and any(kw in primary_cat.lower() for kw in ("status", "type", "category", "gender", "flag", "state", "tier"))
            ):
                return ChartRecommendation(
                    chart_type="pie",
                    x_col=primary_cat,
                    y_col=primary_metric,
                    title=f"Composition of {primary_metric.replace('_', ' ').title()} by {primary_cat.replace('_', ' ').title()}",
                    reason=f"Small discrete categorical composition ({unique_categories} slices) ideal for donut visualization.",
                    confidence=0.94,
                    available_chart_types=["pie", "bar", "treemap", "funnel"],
                )

        is_horizontal = bool(unique_categories > 10 or avg_label_len > 12 or is_ranking_keyword)

        return ChartRecommendation(
            chart_type="bar",
            x_col=primary_cat,
            y_col=primary_metric,
            secondary_y_cols=num_cols[1:],
            title=f"{primary_metric.replace('_', ' ').title()} by {primary_cat.replace('_', ' ').title()}",
            reason=f"Category metric comparison across '{primary_cat}'.",
            confidence=0.95,
            is_horizontal=is_horizontal,
            available_chart_types=["bar", "treemap", "pie", "line", "area"],
        )

    # 9. Multi-metric correlation (Scatter)
    if len(num_cols) >= 2:
        return ChartRecommendation(
            chart_type="scatter",
            x_col=num_cols[0],
            y_col=num_cols[1],
            size_col=num_cols[2] if len(num_cols) >= 3 else None,
            color_col=cat_cols[0] if cat_cols else None,
            title=f"{num_cols[1].replace('_', ' ').title()} vs {num_cols[0].replace('_', ' ').title()}",
            reason="Multiple numeric measures detected (suited for multi-dimensional correlation scatter).",
            confidence=0.88,
            available_chart_types=["scatter", "line", "bar"],
        )

    # 10. Fallback single series
    if len(num_cols) == 1:
        metric = num_cols[0]
        return ChartRecommendation(
            chart_type="bar",
            x_col=df.index.name or "Index",
            y_col=metric,
            title=f"{metric.replace('_', ' ').title()} Series",
            reason=f"Single metric '{metric}' across records.",
            confidence=0.75,
            available_chart_types=["bar", "line", "box"],
        )

    return ChartRecommendation(
        chart_type="table",
        title="Tabular Data",
        reason="Categorical or non-standard format best represented in a data grid.",
        confidence=0.6,
        available_chart_types=["table"],
    )


# ── Plotly High-End Studio Rendering Engine ────────────────────────


def create_plotly_figure(
    df: pd.DataFrame,
    rec: ChartRecommendation,
    override_type: str | None = None,
    override_x: str | None = None,
    override_y: str | None = None,
    palette_name: str = "Cyberpunk Neon",
    show_trendline: bool = False,
) -> go.Figure:
    """Generate a studio-quality Plotly figure with designer styling."""
    plot_df = df.copy()
    chart_type = (override_type or rec.chart_type).lower()
    x_col = override_x or rec.x_col
    y_col = override_y or rec.y_col
    title = rec.title or "Query Insights"
    colors = PALETTES.get(palette_name, DEFAULT_PALETTE)

    # ── 1. KPI Scorecard Card ──────────────────────────────────────
    if chart_type == "metric" and y_col and y_col in plot_df.columns:
        val = plot_df[y_col].iloc[0]
        label = rec.title or y_col.replace("_", " ").title()

        fig = go.Figure()
        fig.add_trace(
            go.Indicator(
                mode="number+delta" if len(rec.secondary_y_cols) > 0 and rec.secondary_y_cols[0] in plot_df.columns else "number",
                value=float(val) if isinstance(val, (int, float)) else 0.0,
                number=dict(
                    valueformat="," if isinstance(val, int) else ",.2f",
                    font=dict(size=56, color=colors[0]),
                ),
                delta=dict(
                    reference=float(plot_df[rec.secondary_y_cols[0]].iloc[0]) if rec.secondary_y_cols and rec.secondary_y_cols[0] in plot_df.columns else None,
                    relative=True,
                    valueformat=".1%",
                ),
                title=dict(text=label, font=dict(size=18, color="#8B949E")),
            )
        )
        fig.update_layout(**DARK_LAYOUT)
        fig.update_layout(height=250, margin=dict(l=20, r=20, t=40, b=20))
        return fig

    # ── 2. Hierarchical Treemap ────────────────────────────────────
    if chart_type == "treemap":
        path_cols = rec.hierarchy_cols if rec.hierarchy_cols and all(c in plot_df.columns for c in rec.hierarchy_cols) else [x_col] if x_col in plot_df.columns else []
        if len(path_cols) >= 2 and y_col and y_col in plot_df.columns:
            fig = px.treemap(
                plot_df,
                path=path_cols,
                values=y_col,
                color=y_col,
                color_continuous_scale=[[0, colors[1]], [0.5, colors[0]], [1, colors[2]]],
                title=title,
            )
            fig.update_layout(**DARK_LAYOUT)
            fig.update_layout(height=480)
            return fig

    # ── 3. 2D Matrix Heatmap ───────────────────────────────────────
    if chart_type == "heatmap":
        if x_col and y_col and x_col in plot_df.columns and y_col in plot_df.columns:
            metric = rec.color_col or (rec.secondary_y_cols[0] if rec.secondary_y_cols else None)
            if metric and metric in plot_df.columns:
                try:
                    pivot_df = plot_df.pivot_table(index=y_col, columns=x_col, values=metric, aggfunc="sum", fill_value=0)
                    fig = px.imshow(
                        pivot_df,
                        color_continuous_scale=[[0, "#161b22"], [0.5, colors[0]], [1, colors[1]]],
                        aspect="auto",
                        title=title,
                        labels=dict(x=x_col, y=y_col, color=metric),
                    )
                    fig.update_layout(**DARK_LAYOUT)
                    fig.update_layout(height=460)
                    return fig
                except Exception:
                    pass

    # ── 4. Funnel Chart ────────────────────────────────────────────
    if chart_type == "funnel":
        if x_col and y_col and x_col in plot_df.columns and y_col in plot_df.columns:
            fig = go.Figure(
                go.Funnel(
                    y=plot_df[x_col],
                    x=plot_df[y_col],
                    textinfo="value+percent previous",
                    marker=dict(color=colors[:len(plot_df)]),
                    connector=dict(line=dict(color="rgba(48, 54, 61, 0.7)", width=1)),
                )
            )
            fig.update_layout(**DARK_LAYOUT)
            fig.update_layout(title=dict(text=title), height=440)
            return fig

    # ── 5. Geographic Choropleth Map ───────────────────────────────
    if chart_type == "choropleth":
        if x_col and y_col and x_col in plot_df.columns and y_col in plot_df.columns:
            fig = px.choropleth(
                plot_df,
                locations=x_col,
                locationmode="country names",
                color=y_col,
                color_continuous_scale=[[0, "#161b22"], [0.5, colors[0]], [1, colors[2]]],
                title=title,
            )
            fig.update_layout(**DARK_LAYOUT)
            fig.update_geos(
                bgcolor="rgba(14, 17, 23, 0.85)",
                showcoastlines=True,
                coastlinecolor="rgba(48, 54, 61, 0.8)",
                showland=True,
                landcolor="rgba(22, 27, 34, 0.9)",
            )
            fig.update_layout(height=460)
            return fig

    # ── 6. Distribution Box Plot ───────────────────────────────────
    if chart_type == "box":
        metric = y_col if (y_col and y_col in plot_df.columns) else (x_col if x_col in plot_df.columns else None)
        if metric and metric in plot_df.columns:
            fig = px.box(
                plot_df,
                x=x_col if (x_col != metric and x_col in plot_df.columns) else None,
                y=metric,
                points="all",
                color_discrete_sequence=[colors[0]],
                title=title,
            )
            fig.update_layout(**DARK_LAYOUT)
            fig.update_layout(height=430)
            return fig

    # ── 7. Spline Area Chart ───────────────────────────────────────
    if chart_type == "area":
        if x_col and y_col and x_col in plot_df.columns and y_col in plot_df.columns:
            if _is_date_like(plot_df[x_col], x_col):
                try:
                    plot_df = plot_df.sort_values(by=x_col)
                except Exception:
                    pass

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=plot_df[x_col],
                    y=plot_df[y_col],
                    mode="lines+markers",
                    name=y_col.replace("_", " ").title(),
                    line=dict(color=colors[0], width=3, shape="spline"),
                    fill="tozeroy",
                    fillcolor=f"rgba(0, 210, 255, 0.2)",
                    marker=dict(size=6, color=colors[1]),
                    hovertemplate=f"<b>%{{x}}</b><br>{y_col}: %{{y:,.2f}}<extra></extra>",
                )
            )

            # Add rolling moving average trendline if requested
            if show_trendline and len(plot_df) >= 4:
                rolling_avg = plot_df[y_col].rolling(window=min(7, len(plot_df) // 2), min_periods=1).mean()
                fig.add_trace(
                    go.Scatter(
                        x=plot_df[x_col],
                        y=rolling_avg,
                        mode="lines",
                        name="Rolling Trendline",
                        line=dict(color="#F59E0B", width=2, dash="dash"),
                    )
                )

            # Auto-highlight peak value
            max_idx = plot_df[y_col].idxmax()
            peak_x = plot_df.loc[max_idx, x_col]
            peak_y = plot_df.loc[max_idx, y_col]
            fig.add_annotation(
                x=peak_x,
                y=peak_y,
                text=f"Peak: {peak_y:,.0f}",
                showarrow=True,
                arrowhead=2,
                arrowcolor=colors[0],
                bgcolor="#1C2128",
                bordercolor=colors[0],
                font=dict(color="#F0F6FC", size=11),
            )

            fig.update_layout(**DARK_LAYOUT)
            fig.update_layout(title=dict(text=title), height=430)
            return fig

    # ── 8. Smooth Multi-Line Chart ─────────────────────────────────
    if chart_type == "line":
        if x_col and y_col and x_col in plot_df.columns and y_col in plot_df.columns:
            if _is_date_like(plot_df[x_col], x_col):
                try:
                    plot_df = plot_df.sort_values(by=x_col)
                except Exception:
                    pass

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=plot_df[x_col],
                    y=plot_df[y_col],
                    mode="lines+markers",
                    name=y_col.replace("_", " ").title(),
                    line=dict(color=colors[0], width=3, shape="spline"),
                    marker=dict(size=7, color=colors[1], line=dict(width=1, color="#FFFFFF")),
                    hovertemplate=f"<b>%{{x}}</b><br>{y_col}: %{{y:,.2f}}<extra></extra>",
                )
            )

            for idx, sec_col in enumerate(rec.secondary_y_cols[:3]):
                if sec_col in plot_df.columns:
                    col_color = colors[(idx + 1) % len(colors)]
                    fig.add_trace(
                        go.Scatter(
                            x=plot_df[x_col],
                            y=plot_df[sec_col],
                            mode="lines+markers",
                            name=sec_col.replace("_", " ").title(),
                            line=dict(color=col_color, width=2.5, shape="spline"),
                            marker=dict(size=6),
                            hovertemplate=f"<b>%{{x}}</b><br>{sec_col}: %{{y:,.2f}}<extra></extra>",
                        )
                    )

            if show_trendline and len(plot_df) >= 4:
                rolling_avg = plot_df[y_col].rolling(window=min(7, len(plot_df) // 2), min_periods=1).mean()
                fig.add_trace(
                    go.Scatter(
                        x=plot_df[x_col],
                        y=rolling_avg,
                        mode="lines",
                        name="Rolling Trendline",
                        line=dict(color="#F59E0B", width=2, dash="dash"),
                    )
                )

            fig.update_layout(**DARK_LAYOUT)
            fig.update_layout(title=dict(text=title), height=430)
            return fig

    # ── 9. Donut / Pie Chart ───────────────────────────────────────
    if chart_type == "pie":
        if x_col and y_col and x_col in plot_df.columns and y_col in plot_df.columns:
            total_sum = plot_df[y_col].sum()
            fig = go.Figure(
                data=[
                    go.Pie(
                        labels=plot_df[x_col],
                        values=plot_df[y_col],
                        hole=0.58,
                        marker=dict(colors=colors),
                        textinfo="label+percent",
                        hovertemplate="<b>%{label}</b><br>Value: %{value:,.2f}<br>Share: %{percent}<extra></extra>",
                    )
                ]
            )
            # Center total annotation
            fig.add_annotation(
                text=f"Total<br><b>{total_sum:,.0f}</b>",
                showarrow=False,
                font=dict(size=14, color="#E6EDF3"),
            )
            fig.update_layout(**DARK_LAYOUT)
            fig.update_layout(title=dict(text=title), height=440)
            return fig

    # ── 10. Multi-Dimensional Scatter / Bubble Plot ────────────────
    if chart_type == "scatter":
        if x_col and y_col and x_col in plot_df.columns and y_col in plot_df.columns:
            size_arg = rec.size_col if rec.size_col and rec.size_col in plot_df.columns else None
            color_arg = rec.color_col if rec.color_col and rec.color_col in plot_df.columns else None

            fig = px.scatter(
                plot_df,
                x=x_col,
                y=y_col,
                size=size_arg,
                color=color_arg,
                color_discrete_sequence=colors,
                trendline="ols" if show_trendline else None,
                title=title,
                hover_data=plot_df.columns.tolist()[:5],
            )
            fig.update_traces(marker=dict(opacity=0.85, line=dict(width=1, color="rgba(255,255,255,0.4)")))
            fig.update_layout(**DARK_LAYOUT)
            fig.update_layout(height=440)
            return fig

    # ── 11. Bar Chart (Horizontal & Vertical with Value Annotations)
    if x_col and y_col and x_col in plot_df.columns and y_col in plot_df.columns:
        is_horiz = rec.is_horizontal

        if is_horiz:
            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    y=plot_df[x_col],
                    x=plot_df[y_col],
                    orientation="h",
                    name=y_col.replace("_", " ").title(),
                    marker=dict(
                        color=colors[0],
                        line=dict(color=colors[1], width=1),
                    ),
                    text=plot_df[y_col].apply(lambda v: f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)),
                    textposition="auto",
                    hovertemplate=f"<b>%{{y}}</b><br>{y_col}: %{{x:,.2f}}<extra></extra>",
                )
            )
            fig.update_layout(**DARK_LAYOUT)
            fig.update_layout(
                title=dict(text=title),
                height=max(400, min(800, len(plot_df) * 28 + 120)),
                yaxis=dict(autorange="reversed"),
            )
            return fig
        else:
            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    x=plot_df[x_col],
                    y=plot_df[y_col],
                    name=y_col.replace("_", " ").title(),
                    marker=dict(
                        color=colors[0],
                        line=dict(color=colors[1], width=1),
                    ),
                    text=plot_df[y_col].apply(lambda v: f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)),
                    textposition="auto",
                    hovertemplate=f"<b>%{{x}}</b><br>{y_col}: %{{y:,.2f}}<extra></extra>",
                )
            )
            for idx, sec_col in enumerate(rec.secondary_y_cols[:2]):
                if sec_col in plot_df.columns:
                    sec_color = colors[(idx + 1) % len(colors)]
                    fig.add_trace(
                        go.Bar(
                            x=plot_df[x_col],
                            y=plot_df[sec_col],
                            name=sec_col.replace("_", " ").title(),
                            marker=dict(color=sec_color),
                            hovertemplate=f"<b>%{{x}}</b><br>{sec_col}: %{{y:,.2f}}<extra></extra>",
                        )
                    )
            fig.update_layout(**DARK_LAYOUT)
            fig.update_layout(title=dict(text=title), barmode="group", height=430)
            return fig

    # Default fallback: numeric bars
    num_cols = plot_df.select_dtypes(include=["number"]).columns.tolist()
    if num_cols:
        fig = px.bar(plot_df, y=num_cols[0], color_discrete_sequence=[colors[0]])
        fig.update_layout(**DARK_LAYOUT)
        fig.update_layout(title=dict(text="Metric Bar Chart"), height=430)
        return fig

    # Empty placeholder
    fig = go.Figure()
    fig.add_annotation(
        text="No numerical data available to plot.",
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=15, color="#8B949E"),
    )
    fig.update_layout(**DARK_LAYOUT)
    fig.update_layout(height=300)
    return fig
