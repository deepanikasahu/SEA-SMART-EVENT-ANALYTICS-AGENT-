"""
Plotly Visualization Charts — Smart Event Analytics Agent v2.

Generates two publication-quality charts from ranked club metrics:
  1. Horizontal bar chart: composite score comparison with rank badges.
  2. Radar chart: multi-dimensional per-club performance profile.

Both charts require only Python dicts — no DataFrames — so they work
cleanly in CLI, API (returning JSON), and Streamlit environments.
"""

from __future__ import annotations
import json
from typing import Any, Dict, List, Optional


def _ensure_plotly():
    try:
        import plotly.graph_objects as go
        import plotly.express as px
        return go, px
    except ImportError:
        raise ImportError(
            "Plotly is required for chart generation. "
            "Install with: pip install plotly"
        )


def bar_chart_rankings(
    ranked_clubs: List[Dict[str, Any]],
    title: str = "Club Performance Rankings — Composite Score",
    output_path: Optional[str] = None,
) -> str:
    """
    Generate a horizontal bar chart comparing composite scores across clubs.

    Args:
        ranked_clubs: List of ClubMetrics dicts sorted by rank.
        title:        Chart title.
        output_path:  If given, save the chart as an HTML file at this path.

    Returns:
        Plotly figure as JSON string (embed anywhere).
    """
    go, px = _ensure_plotly()

    clubs = [c["club_name"] for c in reversed(ranked_clubs)]
    scores = [round(c.get("composite_score", 0), 2) for c in reversed(ranked_clubs)]
    statuses = [c.get("data_status", "Complete Data") for c in reversed(ranked_clubs)]

    colors = []
    for s in statuses:
        if "Significant" in s:
            colors.append("#F43F5E")   # Rose — significant gaps
        elif "Partial" in s:
            colors.append("#F59E0B")   # Peach — partial data
        else:
            colors.append("#10B981")   # Mint — complete data

    fig = go.Figure(go.Bar(
        x=scores,
        y=clubs,
        orientation="h",
        marker_color=colors,
        text=[f"{s:.1f}" for s in scores],
        textposition="outside",
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Composite Score: %{x:.2f}/100<br>"
            "Data Status: %{customdata}<extra></extra>"
        ),
        customdata=statuses,
    ))

    fig.update_layout(
        title={"text": title, "font": {"size": 18, "color": "#0F172A"}},
        xaxis={"title": "Composite Score (0–100)", "range": [0, 105]},
        yaxis={"title": ""},
        plot_bgcolor="#F8FAFC",
        paper_bgcolor="#FFFFFF",
        height=max(300, len(ranked_clubs) * 60 + 100),
        margin={"l": 200, "r": 80, "t": 60, "b": 40},
        font={"family": "Inter, sans-serif", "size": 13},
    )

    if output_path:
        fig.write_html(output_path)

    return fig.to_json()


def radar_chart_clubs(
    ranked_clubs: List[Dict[str, Any]],
    top_n: int = 5,
    title: str = "Multi-Dimensional Club Performance Radar",
    output_path: Optional[str] = None,
) -> str:
    """
    Generate a radar (spider) chart comparing multiple metric dimensions
    for the top N clubs.

    Args:
        ranked_clubs: List of ClubMetrics dicts sorted by rank.
        top_n:        Maximum number of clubs to include (default top 5).
        title:        Chart title.
        output_path:  If given, save the chart as an HTML file.

    Returns:
        Plotly figure as JSON string.
    """
    go, _ = _ensure_plotly()

    categories = [
        "Attendance Rate (%)",
        "Engagement Quality (/5×20)",
        "Consistency (×100)",
        "Reach (norm)",
        "Composite Score",
    ]

    palette = [
        "#0284C7",  # sky
        "#10B981",  # mint
        "#7C3AED",  # lavender
        "#F59E0B",  # peach
        "#F43F5E",  # rose
    ]

    clubs_subset = ranked_clubs[:top_n]
    max_reach = max((c.get("reach", 0) or 0) for c in clubs_subset) or 1

    fig = go.Figure()

    for i, club in enumerate(clubs_subset):
        att = club.get("attendance_rate_pct") or 0.0
        quality = (club.get("engagement_quality") or 0.0) * 20  # scale 1–5 → 0–100
        consistency = (club.get("consistency_raw") or 0.0) * 100
        reach_norm = ((club.get("reach") or 0) / max_reach) * 100
        score = club.get("composite_score") or 0.0

        values = [att, quality, consistency, reach_norm, score]
        values_closed = values + [values[0]]  # Close the polygon
        cats_closed = categories + [categories[0]]

        fig.add_trace(go.Scatterpolar(
            r=values_closed,
            theta=cats_closed,
            fill="toself",
            name=f"#{club.get('rank')} {club.get('club_name')}",
            line_color=palette[i % len(palette)],
            opacity=0.75,
            hovertemplate=(
                f"<b>{club.get('club_name')}</b><br>"
                "Dimension: %{theta}<br>"
                "Score: %{r:.1f}<extra></extra>"
            ),
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], tickfont={"size": 11}),
            angularaxis=dict(tickfont={"size": 12}),
        ),
        showlegend=True,
        title={"text": title, "font": {"size": 16, "color": "#0F172A"}},
        height=520,
        paper_bgcolor="#FFFFFF",
        font={"family": "Inter, sans-serif"},
    )

    if output_path:
        fig.write_html(output_path)

    return fig.to_json()
