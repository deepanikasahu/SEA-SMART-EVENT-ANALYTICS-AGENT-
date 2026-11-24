"""
Explainability Node — Smart Event Analytics Agent v2.

Answers 'Why did Club X rank #1?' by:
  1. Fetching that club's raw metric breakdown from the metrics engine.
  2. Constructing a strict prompt that forces the LLM to narrate ONLY the
     provided numbers — zero generation-only answers.
  3. Running the anti-hallucination regex audit on the response.
"""

from __future__ import annotations
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from llm.adapter import BaseLLMAdapter

logger = logging.getLogger(__name__)


EXPLAIN_SYSTEM_PROMPT = """You are the Explainability Specialist for a university analytics platform.
You have been given a structured breakdown of metrics for a SINGLE CLUB.

STRICT RULES (do NOT violate):
1. ONLY reference numbers, percentages, and ratings present in the JSON data you are given.
2. Do NOT invent, estimate, or generate any figure not in that JSON.
3. Do NOT compare this club to others unless their exact metrics are included in the data.
4. Use bullet points and bold the club name.
5. Briefly explain what each metric means (e.g. Consistency = delivery of planned events + turnout stability).
6. Keep the response under 300 words."""


def _extract_numbers(text: str) -> List[float]:
    """Extract all numeric values from a text string for grounding checks."""
    pattern = r"(?<![A-Za-z_])(\d+(?:\.\d+)?%?)(?![A-Za-z_])"
    numbers = []
    for m in re.findall(pattern, text):
        clean = m.replace("%", "")
        try:
            numbers.append(float(clean))
        except ValueError:
            pass
    return numbers


def _build_allowed_set(club_data: Dict[str, Any]) -> set:
    """Build the set of allowed ground-truth numbers from the club's metrics dict."""
    allowed = {0.0, 1.0, 5.0, 100.0}
    for v in club_data.values():
        if v is None:
            continue
        try:
            fv = float(v)
            allowed.update({round(fv, d) for d in range(5)})
            allowed.add(round(fv * 100, 2))  # percentage form
        except (TypeError, ValueError):
            pass
    return allowed


def explain_club_ranking(
    club_name: str,
    ranked_clubs: List[Dict[str, Any]],
    llm: BaseLLMAdapter,
) -> Tuple[str, Dict[str, Any]]:
    """
    Generate a grounded explanation for why `club_name` received its rank.

    Args:
        club_name:    The club to explain.
        ranked_clubs: Full list of ranked ClubMetrics dicts.
        llm:          Active LLM adapter.

    Returns:
        (narrative_text, grounding_audit_dict)
    """
    # Find the club's data
    club_data = next(
        (c for c in ranked_clubs if c.get("club_name") == club_name),
        None,
    )
    if club_data is None:
        return (
            f"No data found for club '{club_name}'.",
            {"verdict": "NO_DATA", "is_valid": False, "suspicious_count": 0},
        )

    # Construct grounded prompt
    club_json = json.dumps(club_data, indent=2, default=str)
    messages = [
        {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Explain why **{club_name}** received Rank #{club_data.get('rank', '?')}.\n\n"
                f"Club Metrics Data (use ONLY these numbers):\n```json\n{club_json}\n```"
            ),
        },
    ]

    narrative = llm.call_text(messages)

    # Anti-hallucination audit
    extracted = _extract_numbers(narrative)
    allowed = _build_allowed_set(club_data)

    suspicious = []
    for n in extracted:
        rounded_variants = {round(n, d) for d in range(5)}
        if not any(rv in allowed for rv in rounded_variants):
            suspicious.append(n)

    is_valid = len(suspicious) == 0
    audit = {
        "verdict": "GROUNDED" if is_valid else "SUSPICIOUS",
        "is_valid": is_valid,
        "total_numbers_checked": len(extracted),
        "grounded_numbers_count": len(extracted) - len(suspicious),
        "suspicious_count": len(suspicious),
        "suspicious_numbers": suspicious,
    }

    logger.info(
        f"Explainability audit for '{club_name}': "
        f"{audit['grounded_numbers_count']}/{audit['total_numbers_checked']} grounded"
    )
    return narrative, audit
