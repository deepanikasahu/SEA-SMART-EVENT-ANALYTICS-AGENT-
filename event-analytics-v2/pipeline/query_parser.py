"""
Query Understanding Node — Smart Event Analytics Agent v2.

Converts natural language into a structured ParsedQueryParams dict using
LLM function-calling. If the temporal scope is missing, sets
clarification_needed=True so the graph can branch and surface the
clarification question to the user — never silently assumes dates.
"""

from __future__ import annotations
import json
import logging
import re
from typing import Any, Dict, Optional
from llm.adapter import BaseLLMAdapter

logger = logging.getLogger(__name__)

# ─── Structured extraction tool schema ────────────────────────────────────────

QUERY_PARSE_TOOL = {
    "type": "function",
    "function": {
        "name": "parse_event_query",
        "description": (
            "Extract structured parameters from a natural language analytics request. "
            "If the user does not specify any time period, set clarification_needed=true "
            "and provide a clarification_question asking for the semester or date range."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format. Use '2024-01-15' for 'last semester'.",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format. Use '2024-05-30' for 'last semester'.",
                },
                "event_category": {
                    "type": "string",
                    "description": "Event category filter (e.g. 'Technical', 'Cultural'). Omit or null for all categories.",
                },
                "clarification_needed": {
                    "type": "boolean",
                    "description": "True if temporal scope is missing and user must clarify.",
                },
                "clarification_question": {
                    "type": "string",
                    "description": "Question to ask the user when clarification_needed is true.",
                },
            },
            "required": ["clarification_needed"],
        },
    },
}

SYSTEM_PROMPT = """You are a precise query parser for a college event analytics system.
Your ONLY job is to call the `parse_event_query` function with structured parameters
extracted from the user's natural language request.

DATE RULES:
- "last semester" → start_date=2024-01-15, end_date=2024-05-30
- "Spring 2024" → start_date=2024-01-15, end_date=2024-05-30
- "Fall 2024" or "Autumn 2024" → start_date=2024-08-01, end_date=2024-12-15
- If NO time period is mentioned at all → set clarification_needed=true

CATEGORY RULES:
- "technical events" → event_category=Technical
- "cultural events"  → event_category=Cultural
- No specific category → omit event_category (null)

Always call the tool. Do not respond with plain text."""


def _has_time_indication(query: str) -> bool:
    """Quick pre-check to detect obvious temporal tokens before calling LLM."""
    tokens = [
        "semester", "term", "202", "month", "last", "from", "between",
        "spring", "fall", "autumn", "summer",
        "jan", "feb", "mar", "apr", "may", "jun",
        "jul", "aug", "sep", "oct", "nov", "dec",
    ]
    q_lower = query.lower()
    return any(t in q_lower for t in tokens)


def parse_query(user_query: str, llm: BaseLLMAdapter) -> Dict[str, Any]:
    """
    Parse a natural language query into structured params via LLM function calling.

    Returns a dict compatible with ParsedQueryParams fields:
      start_date, end_date, event_category, clarification_needed, clarification_question
    """
    # Fast-path: if obviously no time indication, skip LLM call and return clarification directly
    if not _has_time_indication(user_query):
        logger.info("No temporal indicator detected — requesting clarification without LLM call.")
        return {
            "start_date": None,
            "end_date": None,
            "event_category": None,
            "clarification_needed": True,
            "clarification_question": (
                "Could you please specify the time period you want to analyze? "
                "(e.g., 'last semester', 'Spring 2024', or a date range like '2024-01-15 to 2024-05-30')"
            ),
        }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query},
    ]

    response = llm.call_with_tools(
        messages=messages,
        tools=[QUERY_PARSE_TOOL],
        tool_choice={"type": "function", "function": {"name": "parse_event_query"}},
    )

    if response.tool_calls:
        tc = response.tool_calls[0]
        args = tc.arguments
        logger.info(f"Query parsed: {args}")
        return {
            "start_date": args.get("start_date"),
            "end_date": args.get("end_date"),
            "event_category": args.get("event_category"),
            "clarification_needed": bool(args.get("clarification_needed", False)),
            "clarification_question": args.get("clarification_question"),
        }

    # Fallback: LLM returned text instead of a tool call
    logger.warning("LLM did not call parse_event_query tool — using fallback parser.")
    return _fallback_parse(user_query)


def _fallback_parse(query: str) -> Dict[str, Any]:
    """Regex-based fallback when LLM fails to produce a tool call."""
    q = query.lower()
    start, end = None, None

    if "last semester" in q or "spring 2024" in q:
        start, end = "2024-01-15", "2024-05-30"
    elif "fall 2024" in q or "autumn 2024" in q:
        start, end = "2024-08-01", "2024-12-15"
    else:
        # Try to extract YYYY-MM-DD patterns
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", query)
        if len(dates) >= 2:
            start, end = dates[0], dates[1]
        elif len(dates) == 1:
            start = dates[0]

    category = None
    if "technical" in q:
        category = "Technical"
    elif "cultural" in q:
        category = "Cultural"

    clarification_needed = start is None

    return {
        "start_date": start,
        "end_date": end,
        "event_category": category,
        "clarification_needed": clarification_needed,
        "clarification_question": (
            "Please specify the time period (e.g., 'last semester' or a date range)."
            if clarification_needed else None
        ),
    }
