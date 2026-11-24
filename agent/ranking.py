"""
Deterministic Normalization and Composite Ranking Layer for Smart Event Analytics Agent.
Reads configuration from weights_config.json.
All ranking and math is computed here — never via the LLM.
"""

import json
import os
from typing import Dict, Any, Tuple, Optional
import pandas as pd
import numpy as np


DEFAULT_WEIGHTS_PATH = os.getenv("WEIGHTS_CONFIG_PATH", "weights_config.json")


def load_weights_config(config_path: str = DEFAULT_WEIGHTS_PATH) -> Dict[str, Any]:
    """Load scoring weights and rationale from JSON configuration file and validate."""
    if not os.path.exists(config_path):
        # Fallback default configuration if file is missing
        config = {
            "version": "1.0",
            "weights": {
                "engagement_quality": 0.35,
                "attendance_rate": 0.25,
                "consistency": 0.20,
                "reach": 0.15,
                "activity_volume": 0.05
            },
            "rationale": "Prioritizes student satisfaction and turnout stability over raw volume."
        }
    else:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

    # Startup assertion: the five weights must sum to 1.0 within 1e-9 tolerance
    weights = config.get("weights", {})
    expected_keys = {"engagement_quality", "attendance_rate", "consistency", "reach", "activity_volume"}
    if not expected_keys.issubset(weights.keys()):
        missing = expected_keys - set(weights.keys())
        raise ValueError(f"Weights configuration missing required keys: {missing}")

    weight_sum = sum(weights[k] for k in expected_keys)
    assert abs(weight_sum - 1.0) <= 1e-9, f"Weights must sum to 1.0, got {weight_sum} (diff={abs(weight_sum - 1.0)})"

    return config


def _min_max_scale(series: pd.Series, default_val: float = 75.0) -> pd.Series:
    """
    Min-max normalize a numeric pandas Series to 0-100 scale.
    Handles NaN values and zero-variance series gracefully without crashing.
    """
    # Replace NaN with minimum or 0 for scaling calculations
    valid_series = series.dropna()
    if valid_series.empty:
        return pd.Series(default_val, index=series.index)

    min_val = valid_series.min()
    max_val = valid_series.max()

    if max_val == min_val:
        # All clubs achieved identical score in this metric; grant base 100 or 50
        return series.apply(lambda x: 100.0 if pd.notna(x) else default_val)

    scaled = ((series - min_val) / (max_val - min_val)) * 100.0
    # For missing values that weren't imputed, fill with median/default
    scaled = scaled.fillna(default_val)
    return scaled.round(2)


def rank_clubs(
    metrics_df: pd.DataFrame,
    config_path: str = DEFAULT_WEIGHTS_PATH,
    custom_weights: Optional[Dict[str, float]] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Compute normalized scores and weighted composite rankings for all clubs.

    Ties are broken deterministically by the following documented hierarchy:
      1. Higher attendance rate (turnout percentage descending)
      2. Higher engagement quality (average feedback rating descending)
      3. Club name alphabetically ascending (A-Z)
    
    Args:
        metrics_df: Computed club metrics dataframe from metrics.py
        config_path: Path to weights_config.json
        custom_weights: Optional override for weights dict
        
    Returns:
        Tuple of (ranked_df, ranking_metadata)
    """
    if metrics_df.empty:
        return pd.DataFrame(), {"error": "Empty metrics dataframe provided."}

    config = load_weights_config(config_path)
    weights = custom_weights or config.get("weights", {
        "engagement_quality": 0.35,
        "attendance_rate": 0.25,
        "consistency": 0.20,
        "reach": 0.15,
        "activity_volume": 0.05
    })

    # Validate that weights sum to approximately 1.0
    total_weight = sum(weights.values())
    if not (0.99 <= total_weight <= 1.01):
        # Normalize weights to sum to 1.0
        weights = {k: v / total_weight for k, v in weights.items()}

    df = metrics_df.copy()

    # Min-max normalization for each dimension (0 - 100 scale)
    # 1. Engagement Quality (Feedback score 1-5)
    df["norm_engagement_quality"] = _min_max_scale(df["engagement_quality"])
    
    # 2. Attendance Rate (0.0 - 1.0)
    df["norm_attendance_rate"] = _min_max_scale(df["attendance_rate"])
    
    # 3. Consistency (0.0 - 1.0)
    df["norm_consistency"] = _min_max_scale(df["consistency_raw"])
    
    # 4. Reach (Total student registrations)
    df["norm_reach"] = _min_max_scale(df["reach"])
    
    # 5. Activity Volume (Events count)
    df["norm_activity_volume"] = _min_max_scale(df["activity_volume"])

    # Calculate Weighted Composite Score
    df["composite_score"] = (
        weights["engagement_quality"] * df["norm_engagement_quality"] +
        weights["attendance_rate"] * df["norm_attendance_rate"] +
        weights["consistency"] * df["norm_consistency"] +
        weights["reach"] * df["norm_reach"] +
        weights["activity_volume"] * df["norm_activity_volume"]
    ).round(2)

    # Sort descending by composite score, with documented tie-breakers:
    # 1. Higher turnout (attendance_rate desc)
    # 2. Higher feedback (engagement_quality desc)
    # 3. Club name alphabetical (club_name asc)
    df = df.sort_values(
        by=["composite_score", "attendance_rate", "engagement_quality", "club_name"],
        ascending=[False, False, False, True]
    ).reset_index(drop=True)

    # Assign 1-indexed ranks
    df["rank"] = df.index + 1

    ranking_meta = {
        "weights_used": weights,
        "tie_break_order": ["composite_score", "attendance_rate", "engagement_quality", "club_name"],
        "rationale": config.get("rationale", ""),
        "total_clubs_evaluated": len(df),
        "top_performer": df.iloc[0]["club_name"] if not df.empty else None,
        "top_score": float(df.iloc[0]["composite_score"]) if not df.empty else 0.0
    }

    return df, ranking_meta
