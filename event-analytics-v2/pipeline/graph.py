"""
LangGraph Pipeline State Machine — Smart Event Analytics Agent v2.

7 explicit nodes connected in a directed graph with conditional branching:

    query_understanding
         │
    [clarification_needed?]──Yes──▶ clarification_gate (terminal)
         │ No
    data_ingestion
         │
    missing_data_analysis
         │
    metrics_computation
         │
    ranking
         │
    report_generation
         │
    ── SUCCESS (terminal)

This module also exposes a `run_v2_pipeline()` convenience function that
wraps the LangGraph execution and returns a standardised output dict
compatible with the comparison harness.
"""

from __future__ import annotations
import logging
import sys
import os
import time
from typing import Any, Dict, List, Optional

import pandas as pd

# Add v2 root to path for relative imports
_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _V2_ROOT not in sys.path:
    sys.path.insert(0, _V2_ROOT)

from pipeline.state import AgentState
from pipeline.query_parser import parse_query
from pipeline.validator import (
    fetch_events, fetch_registrations, fetch_attendance,
    fetch_feedback, fetch_club_plans, DEFAULT_DB,
)
from engine.metrics import compute_club_metrics_v2, load_rubric
from engine.ranking import rank_clubs_v2
from reporting.report_generator import generate_grounded_narrative
from llm.adapter import BaseLLMAdapter, get_v2_adapter

logger = logging.getLogger(__name__)


# ─── Pipeline Nodes ────────────────────────────────────────────────────────────

def node_query_understanding(state: AgentState, llm: BaseLLMAdapter) -> Dict[str, Any]:
    """Node 1: Parse natural language query into structured parameters."""
    logger.info("[Node 1] Query Understanding")
    params = parse_query(state["user_query"], llm)
    update: Dict[str, Any] = {
        "parsed_params": params,
        "clarification_needed": params.get("clarification_needed", False),
        "clarification_question": params.get("clarification_question"),
    }
    _log(state, "Query Understanding", f"Parsed params: {params}")
    return update


def node_data_ingestion(state: AgentState, db_path: str) -> Dict[str, Any]:
    """Node 2: Fetch and Pydantic-validate all required tables from isolated v2 DB."""
    logger.info("[Node 2] Data Ingestion")
    params = state.get("parsed_params", {})

    all_errors: List[Dict] = []

    events_df, errs = fetch_events(
        start_date=params.get("start_date"),
        end_date=params.get("end_date"),
        category=params.get("event_category"),
        db_path=db_path,
    )
    all_errors.extend(errs)

    if events_df.empty:
        _log(state, "Data Ingestion", "No events found for the given parameters.")
        return {
            "events_df": events_df, "registrations_df": pd.DataFrame(),
            "attendance_df": pd.DataFrame(), "feedback_df": pd.DataFrame(),
            "club_plans_df": pd.DataFrame(), "validation_errors": all_errors,
        }

    event_ids = events_df["event_id"].tolist()

    regs_df, errs = fetch_registrations(event_ids, db_path=db_path)
    all_errors.extend(errs)

    att_df, errs = fetch_attendance(event_ids, db_path=db_path)
    all_errors.extend(errs)

    fb_df, errs = fetch_feedback(event_ids, db_path=db_path)
    all_errors.extend(errs)

    plans_df, errs = fetch_club_plans(db_path=db_path)
    all_errors.extend(errs)

    _log(
        state, "Data Ingestion",
        f"Events: {len(events_df)}, Regs: {len(regs_df)}, "
        f"Att: {len(att_df)}, Feedback: {len(fb_df)}, "
        f"Validation errors: {len(all_errors)}"
    )

    return {
        "events_df": events_df,
        "registrations_df": regs_df,
        "attendance_df": att_df,
        "feedback_df": fb_df,
        "club_plans_df": plans_df,
        "validation_errors": all_errors,
    }


def node_missing_data_analysis(state: AgentState) -> Dict[str, Any]:
    """Node 3: Compute per-club completeness & confidence scores; log all data gaps."""
    logger.info("[Node 3] Missing Data Analysis")
    # This runs as part of compute_club_metrics_v2; just log summary here
    _log(state, "Missing Data Analysis", "Completeness scoring deferred to metrics node.")
    return {}


def _get_df(state: AgentState, key: str) -> pd.DataFrame:
    """Safely retrieve a DataFrame from state, returning empty DF instead of None."""
    val = state.get(key)
    if val is None:
        return pd.DataFrame()
    return val


def node_metrics_computation(state: AgentState, rubric: Dict) -> Dict[str, Any]:
    """Node 4: Pure Python/pandas deterministic metric computation."""
    logger.info("[Node 4] Metrics Computation")
    metrics_df, completeness_flags = compute_club_metrics_v2(
        events_df=_get_df(state, "events_df"),
        registrations_df=_get_df(state, "registrations_df"),
        attendance_df=_get_df(state, "attendance_df"),
        feedback_df=_get_df(state, "feedback_df"),
        club_plans_df=_get_df(state, "club_plans_df"),
        rubric=rubric,
    )
    _log(state, "Metrics Computation", f"Computed metrics for {len(metrics_df)} clubs")
    return {"metrics_df": metrics_df, "completeness_flags": completeness_flags}



def node_ranking(state: AgentState, rubric: Dict) -> Dict[str, Any]:
    """Node 5: Deterministic sorting with explicit tie-break hierarchy."""
    logger.info("[Node 5] Ranking")
    metrics_df = state.get("metrics_df")
    if metrics_df is None or (hasattr(metrics_df, "empty") and metrics_df.empty):
        _log(state, "Ranking", "No metrics to rank.")
        return {"ranked_clubs": [], "ranking_meta": {}}

    ranked_df, ranking_meta = rank_clubs_v2(metrics_df, rubric=rubric)
    _log(
        state, "Ranking",
        f"#{1} club: {ranked_df.iloc[0]['club_name']} "
        f"(score: {ranked_df.iloc[0]['composite_score']:.2f})"
    )
    return {
        "ranked_clubs": ranked_df.to_dict(orient="records"),
        "ranking_meta": ranking_meta,
    }


def node_report_generation(state: AgentState, llm: BaseLLMAdapter) -> Dict[str, Any]:
    """Node 6: LLM generates grounded narrative; regex audit verifies all numbers."""
    logger.info("[Node 6] Report Generation")
    ranked_clubs = state.get("ranked_clubs", [])
    if not ranked_clubs:
        return {"grounded_narrative": "", "number_grounding_audit": {}}

    narrative, audit = generate_grounded_narrative(ranked_clubs, llm)
    _log(
        state, "Report Generation",
        f"Narrative generated. Audit: {audit.get('grounded_numbers_count')}/"
        f"{audit.get('total_numbers_checked')} grounded."
    )
    return {"grounded_narrative": narrative, "number_grounding_audit": audit}


# ─── Logging helper ────────────────────────────────────────────────────────────

def _log(state: AgentState, step: str, detail: str):
    log = state.get("execution_log")
    if log is not None:
        log.append({"step": step, "detail": detail, "timestamp": time.time()})


# ─── Main Pipeline Entry Point ────────────────────────────────────────────────

def run_v2_pipeline(
    user_query: str,
    provider: Optional[str] = None,
    db_path: str = DEFAULT_DB,
    rubric_path: str = "event-analytics-v2/config/rubric.yaml",
) -> Dict[str, Any]:
    """
    Execute the full v2 pipeline and return a standardised result dict.

    The output schema is backward-compatible with v1's result dict so the
    comparison harness can diff them without special-casing.
    """
    start_time = time.time()
    llm = get_v2_adapter(provider)
    # Reset per-run telemetry
    from llm.adapter import get_tracker
    tracker = get_tracker()
    tracker.reset()
    rubric = load_rubric(rubric_path)

    state: AgentState = {
        "user_query": user_query,
        "provider": llm.provider_name,
        "execution_log": [],
        "start_time": start_time,
        "clarification_needed": False,
        "validation_errors": [],
        "completeness_flags": [],
        "ranked_clubs": [],
        "ranking_meta": {},
        "grounded_narrative": "",
        "number_grounding_audit": {},
        "status": "ERROR",
        "error_message": None,
    }

    try:
        # Node 1: Query Understanding
        state.update(node_query_understanding(state, llm))

        if state.get("clarification_needed"):
            state["status"] = "CLARIFICATION_NEEDED"
            state["total_duration_seconds"] = round(time.time() - start_time, 2)
            return _format_output(state)

        # Node 2: Data Ingestion
        state.update(node_data_ingestion(state, db_path))

        events_df = state.get("events_df")
        if events_df is None or (hasattr(events_df, "empty") and events_df.empty):
            state["status"] = "ERROR"
            state["error_message"] = "No matching events found for the given query parameters."
            state["total_duration_seconds"] = round(time.time() - start_time, 2)
            return _format_output(state)

        # Node 3: Missing Data Analysis (runs inside metrics)
        state.update(node_missing_data_analysis(state))

        # Node 4: Metrics Computation
        state.update(node_metrics_computation(state, rubric))

        # Node 5: Ranking
        state.update(node_ranking(state, rubric))

        # Node 6: Report Generation
        state.update(node_report_generation(state, llm))

        state["status"] = "SUCCESS"

    except Exception as exc:
        logger.exception(f"v2 pipeline error: {exc}")
        state["status"] = "ERROR"
        state["error_message"] = str(exc)

    state["total_duration_seconds"] = round(time.time() - start_time, 2)
    return _format_output(state)


def _format_output(state: AgentState) -> Dict[str, Any]:
    """Convert internal AgentState to the standardised output dict."""
    from llm.adapter import get_tracker
    events_df = state.get("events_df")
    events_count = len(events_df) if events_df is not None and not (
        hasattr(events_df, "empty") and events_df.empty
    ) else 0

    return {
        "status": state.get("status", "ERROR"),
        "query": state.get("user_query", ""),
        "provider": state.get("provider", "Unknown"),
        "total_duration_seconds": state.get("total_duration_seconds", 0.0),
        "execution_log": state.get("execution_log", []),
        "in_scope_events_count": events_count,
        "ranked_clubs": state.get("ranked_clubs", []),
        "ranking_meta": state.get("ranking_meta", {}),
        "completeness_flags": state.get("completeness_flags", []),
        "validation_errors": state.get("validation_errors", []),
        "grounded_narrative": state.get("grounded_narrative", ""),
        "number_grounding_audit": state.get("number_grounding_audit", {}),
        "error_message": state.get("error_message"),
        # v2-specific extras
        "clarification_needed": state.get("clarification_needed", False),
        "clarification_question": state.get("clarification_question"),
        "version": "v2",
        # LLM cost/latency telemetry
        "llm_usage": get_tracker().summary(),
    }

