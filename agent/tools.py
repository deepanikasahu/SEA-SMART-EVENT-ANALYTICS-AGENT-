"""
Deterministic Data Collection Tools for Smart Event Analytics Agent.
All tools query the SQLite database directly using parameterized SQL queries.
No LLM reasoning or calculations occur here — strictly raw data retrieval.
"""

import os
import re
import datetime
import sqlite3
from typing import List, Optional, Dict, Any, Union
import pandas as pd


DEFAULT_DB_PATH = os.getenv("DATABASE_PATH", "data/sea_agent.db")


def _get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Helper to obtain SQLite connection with foreign keys enabled."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"Database file not found at '{db_path}'. Please run "
            f"`python data_generation/generate_dummy_data.py` to generate sample data."
        )
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def validate_date_format(date_str: Optional[str]) -> Optional[Dict[str, str]]:
    """Validate ISO date string format YYYY-MM-DD and calendar validity."""
    if date_str is None:
        return None
    if not isinstance(date_str, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str.strip()):
        return {
            "error": "INVALID_DATE_FORMAT",
            "message": f"Invalid date format '{date_str}'. Expected 'YYYY-MM-DD'."
        }
    try:
        datetime.datetime.strptime(date_str.strip(), "%Y-%m-%d")
    except ValueError as e:
        return {
            "error": "INVALID_DATE_FORMAT",
            "message": f"Invalid date value '{date_str}': {e}."
        }
    return None


def validate_date_range(start_date: Optional[str], end_date: Optional[str]) -> Optional[Dict[str, str]]:
    """Validate that start_date <= end_date."""
    if start_date and end_date:
        if start_date > end_date:
            return {
                "error": "INVALID_DATE_RANGE",
                "message": f"start_date '{start_date}' cannot be after end_date '{end_date}'."
            }
    return None


def validate_category(category: Optional[str], db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, str]]:
    """Validate category against database and known categories."""
    if category is None or category.strip().lower() == "all":
        return None

    valid_categories = {"Technical", "Cultural", "Sports", "Academic", "Community"}
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT category FROM events WHERE category IS NOT NULL;")
            db_cats = {row[0] for row in cur.fetchall() if row[0]}
            conn.close()
            valid_categories.update(db_cats)
        except Exception:
            pass

    if category.strip().lower() not in {c.lower() for c in valid_categories}:
        return {
            "error": "INVALID_CATEGORY",
            "message": f"Invalid category '{category}'. Valid categories are: {sorted(list(valid_categories))}."
        }
    return None


def validate_club_id(club_id: Optional[str], db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, str]]:
    """Validate club ID or club name against database club_plans."""
    if club_id is None:
        return None
    if not isinstance(club_id, str) or not club_id.strip():
        return {
            "error": "INVALID_CLUB_ID",
            "message": f"Invalid club ID '{club_id}'. Must be a non-empty string."
        }

    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT club_name FROM club_plans;")
            clubs = [row[0] for row in cur.fetchall()]
            conn.close()
            if club_id.strip().lower() not in [c.lower() for c in clubs]:
                return {
                    "error": "INVALID_CLUB_ID",
                    "message": f"Club ID '{club_id}' not found in database. Available clubs: {clubs}."
                }
        except Exception:
            pass

    return None


def _validate_event_ids(event_ids: Optional[List[str]]) -> Optional[Dict[str, str]]:
    """Validate event_ids list."""
    if event_ids is not None:
        if not isinstance(event_ids, list):
            return {
                "error": "INVALID_EVENT_IDS",
                "message": "event_ids must be a list of strings."
            }
        if any(not isinstance(eid, str) or not eid.strip() for eid in event_ids):
            return {
                "error": "INVALID_EVENT_IDS",
                "message": "All event_ids must be non-empty strings."
            }
    return None


def get_events(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None,
    club_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Union[pd.DataFrame, Dict[str, Any]]:
    """
    Fetch events matching date boundaries and category filter.
    
    Args:
        start_date: ISO date string 'YYYY-MM-DD' (inclusive)
        end_date: ISO date string 'YYYY-MM-DD' (inclusive)
        category: Event category (e.g., 'Technical', 'Cultural')
        club_id: Optional club ID or name to filter events
        db_path: Path to SQLite database file
        
    Returns:
        pd.DataFrame or Dict[str, str]: Columns [event_id, event_name, club_name, date, category, capacity]
            or {"error": code, "message": text} on validation failure.
    """
    for d in (start_date, end_date):
        err = validate_date_format(d)
        if err:
            return err

    err = validate_date_range(start_date, end_date)
    if err:
        return err

    err = validate_category(category, db_path)
    if err:
        return err

    err = validate_club_id(club_id, db_path)
    if err:
        return err

    conn = _get_connection(db_path)
    query = "SELECT event_id, event_name, club_name, date, category, capacity FROM events WHERE 1=1"
    params = []

    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    if category and category.lower() != "all":
        query += " AND LOWER(category) = LOWER(?)"
        params.append(category)
    if club_id:
        query += " AND LOWER(club_name) = LOWER(?)"
        params.append(club_id)

    query += " ORDER BY date ASC;"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df



def get_registrations(
    event_ids: Optional[List[str]] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Union[pd.DataFrame, Dict[str, Any]]:
    """
    Fetch registration records for specified event IDs.
    
    Args:
        event_ids: List of event_id strings. If None, returns all registrations.
        db_path: Path to SQLite database file
        
    Returns:
        pd.DataFrame or Dict[str, str]: Columns [registration_id, event_id, student_id, registered_at]
    """
    err = _validate_event_ids(event_ids)
    if err:
        return err
    if event_ids is not None and len(event_ids) == 0:
        return pd.DataFrame(columns=["registration_id", "event_id", "student_id", "registered_at"])

    conn = _get_connection(db_path)
    if event_ids:
        placeholders = ",".join(["?"] * len(event_ids))
        query = f"SELECT registration_id, event_id, student_id, registered_at FROM registrations WHERE event_id IN ({placeholders});"
        df = pd.read_sql_query(query, conn, params=event_ids)
    else:
        query = "SELECT registration_id, event_id, student_id, registered_at FROM registrations;"
        df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_attendance(
    event_ids: Optional[List[str]] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Union[pd.DataFrame, Dict[str, Any]]:
    """
    Fetch attendance records for specified event IDs.
    
    Args:
        event_ids: List of event_id strings.
        db_path: Path to SQLite database file
        
    Returns:
        pd.DataFrame or Dict[str, str]: Columns [event_id, student_id, attended, check_in_time]
    """
    err = _validate_event_ids(event_ids)
    if err:
        return err
    if event_ids is not None and len(event_ids) == 0:
        return pd.DataFrame(columns=["event_id", "student_id", "attended", "check_in_time"])

    conn = _get_connection(db_path)
    if event_ids:
        placeholders = ",".join(["?"] * len(event_ids))
        query = f"SELECT event_id, student_id, attended, check_in_time FROM attendance WHERE event_id IN ({placeholders});"
        df = pd.read_sql_query(query, conn, params=event_ids)
    else:
        query = "SELECT event_id, student_id, attended, check_in_time FROM attendance;"
        df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_feedback(
    event_ids: Optional[List[str]] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Union[pd.DataFrame, Dict[str, Any]]:
    """
    Fetch feedback records for specified event IDs.
    
    Args:
        event_ids: List of event_id strings.
        db_path: Path to SQLite database file
        
    Returns:
        pd.DataFrame or Dict[str, str]: Columns [feedback_id, event_id, student_id, rating, comment, submitted_at]
    """
    err = _validate_event_ids(event_ids)
    if err:
        return err
    if event_ids is not None and len(event_ids) == 0:
        return pd.DataFrame(columns=["feedback_id", "event_id", "student_id", "rating", "comment", "submitted_at"])

    conn = _get_connection(db_path)
    if event_ids:
        placeholders = ",".join(["?"] * len(event_ids))
        query = f"SELECT feedback_id, event_id, student_id, rating, comment, submitted_at FROM feedback WHERE event_id IN ({placeholders});"
        df = pd.read_sql_query(query, conn, params=event_ids)
    else:
        query = "SELECT feedback_id, event_id, student_id, rating, comment, submitted_at FROM feedback;"
        df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_club_plans(
    club_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Union[pd.DataFrame, Dict[str, Any]]:
    """
    Fetch club planning targets and metadata.
    
    Args:
        club_id: Optional club ID or name filter
        db_path: Path to SQLite database file
        
    Returns:
        pd.DataFrame or Dict[str, str]: Columns [club_name, planned_events, faculty_lead, founded_year]
    """
    err = validate_club_id(club_id, db_path)
    if err:
        return err

    conn = _get_connection(db_path)
    if club_id:
        query = "SELECT club_name, planned_events, faculty_lead, founded_year FROM club_plans WHERE LOWER(club_name) = LOWER(?);"
        df = pd.read_sql_query(query, conn, params=[club_id])
    else:
        query = "SELECT club_name, planned_events, faculty_lead, founded_year FROM club_plans;"
        df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def get_database_summary(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """
    Retrieve quick overview of available date ranges, categories, and clubs in the database.
    Useful for orchestrator time resolution and context priming.
    """
    conn = _get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT MIN(date), MAX(date), COUNT(DISTINCT category), COUNT(DISTINCT club_name) FROM events;")
    min_d, max_d, cat_count, club_count = cursor.fetchone()
    
    cursor.execute("SELECT DISTINCT category FROM events;")
    categories = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT club_name FROM club_plans;")
    clubs = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return {
        "min_date": min_d,
        "max_date": max_d,
        "categories": categories,
        "clubs": clubs,
        "total_clubs": club_count
    }


# Tool Definitions schema for LLM function calling (OpenAI / Groq / OpenRouter standard format)
AGENT_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_events",
            "description": "Fetch events from the database filtered by date range and category. Use this tool first to discover relevant events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date in 'YYYY-MM-DD' format (e.g., '2024-01-15' for beginning of last semester)."
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in 'YYYY-MM-DD' format (e.g., '2024-05-30' for end of last semester)."
                    },
                    "category": {
                        "type": "string",
                        "description": "Event category filter, such as 'Technical' or 'Cultural'. Defaults to None for all."
                    },
                    "club_id": {
                        "type": "string",
                        "description": "Optional club ID or name filter (e.g. 'ACM Student Chapter'). Defaults to None for all."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_registrations",
            "description": "Fetch registration records for a given list of event IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of event_id strings (e.g., ['EVT_001', 'EVT_002'])."
                    }
                },
                "required": ["event_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_attendance",
            "description": "Fetch attendance and check-in records for a given list of event IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of event_id strings."
                    }
                },
                "required": ["event_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_feedback",
            "description": "Fetch attendee satisfaction ratings (1-5) and comments for a given list of event IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of event_id strings."
                    }
                },
                "required": ["event_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_club_plans",
            "description": "Fetch semester planned event targets and club metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "club_id": {
                        "type": "string",
                        "description": "Optional club ID or name to retrieve plans for a specific club."
                    }
                },
                "required": []
            }
        }
    }
]
