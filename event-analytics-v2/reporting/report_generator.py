"""
Grounded Report Generator — Smart Event Analytics Agent v2.

Generates an LLM narrative strictly anchored to the pre-computed metrics JSON.
Uses the same anti-hallucination regex audit as v1's explain.py, but with
improved prompt engineering and explicit grounding verification before returning.
"""

from __future__ import annotations
import json
import logging
import re
from typing import Any, Dict, List, Tuple
from llm.adapter import BaseLLMAdapter

logger = logging.getLogger(__name__)

REPORT_SYSTEM_PROMPT = """You are the Senior Analytics Reasoning Specialist for a university event board.

You are given a PRE-COMPUTED ranked metrics table as structured JSON.

STRICT GROUNDING RULES (violation = audit failure):
1. NEVER calculate, estimate, or invent any number.
2. Every percentage, rating, and score you mention MUST be copied EXACTLY from the JSON.
3. Do NOT cite any club name or metric not in the JSON.
4. Highlight Top 3 clubs: primary strengths, attendance turnout, and participant feedback.
5. If any club has data_status containing "Partial" or "Significant Gaps", explicitly acknowledge this.
6. Explain performance tradeoffs (e.g. high engagement vs lower consistency).
7. Structure using markdown: ## heading, bullet points, **bold club names**.
8. Keep response under 500 words."""


def _extract_numbers(text: str) -> List[float]:
    pattern = r"(?<![A-Za-z_])(\d+(?:\.\d+)?%?)(?![A-Za-z_])"
    numbers = []
    for m in re.findall(pattern, text):
        clean = m.replace("%", "")
        try:
            numbers.append(float(clean))
        except ValueError:
            pass
    return numbers


def _build_allowed_set(ranked_clubs: List[Dict[str, Any]]) -> set:
    allowed = {0.0, 1.0, 5.0, 100.0}
    safe_ints = set(range(0, 101)) | set(range(1, 13)) | {2024, 2025, 2026}
    allowed.update(float(x) for x in safe_ints)

    for club in ranked_clubs:
        for v in club.values():
            if v is None:
                continue
            try:
                fv = float(v)
                allowed.update({round(fv, d) for d in range(5)})
                allowed.add(round(fv * 100, 2))  # percentage form
            except (TypeError, ValueError):
                pass
    return allowed


def generate_grounded_narrative(
    ranked_clubs: List[Dict[str, Any]],
    llm: BaseLLMAdapter,
) -> Tuple[str, Dict[str, Any]]:
    """
    Generate a number-grounded narrative from the ranked metrics.

    Returns:
        (narrative_text, audit_report_dict)
    """
    # Build compact summary — strip internal fields the LLM doesn't need
    summary = []
    for c in ranked_clubs:
        summary.append({
            "rank": c.get("rank"),
            "club_name": c.get("club_name"),
            "composite_score": c.get("composite_score"),
            "attendance_rate_pct": c.get("attendance_rate_pct"),
            "engagement_quality": c.get("engagement_quality"),
            "consistency_raw_pct": (
                round(c["consistency_raw"] * 100, 1)
                if c.get("consistency_raw") is not None else None
            ),
            "reach": c.get("reach"),
            "activity_volume": c.get("activity_volume"),
            "planned_events": c.get("planned_events"),
            "data_status": c.get("data_status"),
            "completeness_score": c.get("completeness_score"),
        })

    metrics_json = json.dumps(summary, indent=2, default=str)
    messages = [
        {"role": "system", "content": REPORT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Generate the executive performance summary using ONLY these "
                f"pre-computed club metrics:\n\n```json\n{metrics_json}\n```"
            ),
        },
    ]

    narrative = llm.call_text(messages)

    # Anti-hallucination audit
    extracted = _extract_numbers(narrative)
    allowed = _build_allowed_set(ranked_clubs)
    suspicious = []
    for n in extracted:
        variants = {round(n, d) for d in range(5)}
        if not any(rv in allowed for rv in variants):
            suspicious.append(n)

    is_valid = len(suspicious) == 0
    audit = {
        "verdict": "FULLY_GROUNDED" if is_valid else "SUSPICIOUS_NUMBERS_DETECTED",
        "is_valid": is_valid,
        "total_numbers_checked": len(extracted),
        "grounded_numbers_count": len(extracted) - len(suspicious),
        "suspicious_count": len(suspicious),
        "suspicious_numbers": suspicious,
    }

    if suspicious:
        logger.warning(f"Hallucination audit failed — suspicious numbers: {suspicious}")
    else:
        logger.info(f"Hallucination audit passed — {len(extracted)}/{len(extracted)} grounded.")

    return narrative, audit
