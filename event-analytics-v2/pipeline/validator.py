"""
Data Validation & Missing-Data Handling — Smart Event Analytics Agent v2.

v2 design principle: EXPLICIT DISCLOSURE over silent imputation.
Every ingested record is validated against Pydantic schemas.
Every data gap is tracked and surfaced in the final report.
"""

from __future__ import annotations
import logging
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from pydantic import ValidationError

# Import v2 schemas
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from models.schemas import (
    ClubPlanRecord, EventRecord, RegistrationRecord,
    AttendanceRecord, FeedbackRecord,
)

logger = logging.getLogger(__name__)

DEFAULT_DB = os.path.join(
    os.path.dirname(__file__), "..", "data", "sea_agent_v2.db"
)


# ─── SQLite Connectors (read-only access to isolated v2 DB) ───────────────────

def _conn(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"v2 database not found at '{db_path}'. "
            "Run the data copy step or regenerate with generate_dummy_data.py."
        )
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _sanitize_row(row: dict) -> dict:
    """Convert NaN/float-nan values to None so Pydantic Optional[str] accepts them."""
    import math
    result = {}
    for k, v in row.items():
        if isinstance(v, float) and math.isnan(v):
            result[k] = None
        else:
            result[k] = v
    return result


def _load_and_validate(
    df: pd.DataFrame,
    schema_cls,
    table_name: str,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    Validate each row of a DataFrame against a Pydantic schema.
    Invalid rows are excluded; a structured error log is returned.
    NaN values from SQLite NULLs are converted to None before validation.
    """
    valid_rows, errors = [], []
    for i, row in df.iterrows():
        try:
            schema_cls(**_sanitize_row(row.to_dict()))
            valid_rows.append(row)
        except ValidationError as e:
            errors.append({
                "table": table_name,
                "row_index": int(i),
                "row_data": row.to_dict(),
                "errors": e.errors(),
            })
    if errors:
        logger.warning(f"[{table_name}] {len(errors)} validation error(s) — rows excluded.")
    return pd.DataFrame(valid_rows) if valid_rows else pd.DataFrame(columns=df.columns), errors



# ─── Per-Table Fetchers ────────────────────────────────────────────────────────

def fetch_events(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None,
    db_path: str = DEFAULT_DB,
) -> Tuple[pd.DataFrame, List[Dict]]:
    conn = _conn(db_path)
    q = "SELECT event_id, event_name, club_name, date, category, capacity FROM events WHERE 1=1"
    params = []
    if start_date:
        q += " AND date >= ?"; params.append(start_date)
    if end_date:
        q += " AND date <= ?"; params.append(end_date)
    if category and category.lower() != "all":
        q += " AND LOWER(category) = LOWER(?)"; params.append(category)
    q += " ORDER BY date ASC;"
    df = pd.read_sql_query(q, conn, params=params)
    conn.close()
    return _load_and_validate(df, EventRecord, "events")


def fetch_registrations(
    event_ids: List[str],
    db_path: str = DEFAULT_DB,
) -> Tuple[pd.DataFrame, List[Dict]]:
    if not event_ids:
        return pd.DataFrame(), []
    conn = _conn(db_path)
    placeholders = ",".join("?" * len(event_ids))
    df = pd.read_sql_query(
        f"SELECT registration_id, event_id, student_id, registered_at "
        f"FROM registrations WHERE event_id IN ({placeholders});",
        conn, params=event_ids,
    )
    conn.close()
    return _load_and_validate(df, RegistrationRecord, "registrations")


def fetch_attendance(
    event_ids: List[str],
    db_path: str = DEFAULT_DB,
) -> Tuple[pd.DataFrame, List[Dict]]:
    if not event_ids:
        return pd.DataFrame(), []
    conn = _conn(db_path)
    placeholders = ",".join("?" * len(event_ids))
    df = pd.read_sql_query(
        f"SELECT event_id, student_id, attended, check_in_time "
        f"FROM attendance WHERE event_id IN ({placeholders});",
        conn, params=event_ids,
    )
    conn.close()
    return _load_and_validate(df, AttendanceRecord, "attendance")


def fetch_feedback(
    event_ids: List[str],
    db_path: str = DEFAULT_DB,
) -> Tuple[pd.DataFrame, List[Dict]]:
    if not event_ids:
        return pd.DataFrame(), []
    conn = _conn(db_path)
    placeholders = ",".join("?" * len(event_ids))
    df = pd.read_sql_query(
        f"SELECT feedback_id, event_id, student_id, rating, comment, submitted_at "
        f"FROM feedback WHERE event_id IN ({placeholders});",
        conn, params=event_ids,
    )
    conn.close()
    return _load_and_validate(df, FeedbackRecord, "feedback")


def fetch_club_plans(db_path: str = DEFAULT_DB) -> Tuple[pd.DataFrame, List[Dict]]:
    conn = _conn(db_path)
    df = pd.read_sql_query(
        "SELECT club_name, planned_events, faculty_lead, founded_year FROM club_plans;",
        conn,
    )
    conn.close()
    return _load_and_validate(df, ClubPlanRecord, "club_plans")
