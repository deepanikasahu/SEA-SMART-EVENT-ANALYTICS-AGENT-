"""
Pipeline State — Smart Event Analytics Agent v2.

The AgentState TypedDict is the single shared object passed between
every LangGraph node. Using TypedDict (not a mutable class) ensures
each node receives a snapshot and returns an update dict, keeping the
graph's state transitions explicit and testable.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict

import pandas as pd


class AgentState(TypedDict, total=False):
    """
    Immutable snapshot passed between LangGraph pipeline nodes.
    Each node receives the current state and returns a *partial* update dict.
    """

    # ── Input ──────────────────────────────────────────────────────────────────
    user_query: str                          # Raw natural language query
    provider: str                            # LLM provider name for audit trail

    # ── Query Understanding Stage ──────────────────────────────────────────────
    parsed_params: Optional[Dict[str, Any]]  # ParsedQueryParams as dict
    clarification_needed: bool               # True → pipeline halts for user input
    clarification_question: Optional[str]    # Question to surface to user

    # ── Data Ingestion Stage ───────────────────────────────────────────────────
    events_df: Optional[Any]                 # pd.DataFrame
    registrations_df: Optional[Any]          # pd.DataFrame
    attendance_df: Optional[Any]             # pd.DataFrame
    feedback_df: Optional[Any]               # pd.DataFrame
    club_plans_df: Optional[Any]             # pd.DataFrame
    validation_errors: List[Dict[str, Any]]  # Records that failed Pydantic validation

    # ── Missing-Data Stage ─────────────────────────────────────────────────────
    completeness_flags: List[Dict[str, Any]] # DataCompletenessFlag dicts

    # ── Metrics & Ranking Stage ────────────────────────────────────────────────
    metrics_df: Optional[Any]                # pd.DataFrame (raw metrics, pre-ranking)
    ranked_clubs: List[Dict[str, Any]]       # ClubMetrics dicts, sorted by rank
    ranking_meta: Dict[str, Any]             # Weights, tie-break info

    # ── Report Stage ───────────────────────────────────────────────────────────
    grounded_narrative: str                  # LLM-generated, number-verified text
    number_grounding_audit: Dict[str, Any]   # Regex verification results

    # ── Execution Metadata ─────────────────────────────────────────────────────
    execution_log: List[Dict[str, Any]]      # Timestamped step-by-step audit trail
    start_time: float                        # Unix timestamp
    total_duration_seconds: float
    status: str                              # "SUCCESS" | "CLARIFICATION_NEEDED" | "ERROR"
    error_message: Optional[str]
