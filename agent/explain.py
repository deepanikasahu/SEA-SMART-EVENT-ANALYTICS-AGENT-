"""
LLM Reasoning Layer and Grounding Validation for Smart Event Analytics Agent.
The LLM receives ONLY the pre-computed aggregate metrics JSON (no raw rows, no student PII).
Every numerical claim in the generated text is programmatically validated against the input table.
"""

import json
import re
from typing import Dict, List, Any, Tuple, Optional
from agent.llm_client import BaseLLMAdapter, get_llm_adapter


EXPLANATION_SYSTEM_PROMPT = """You are the Senior Analytics Reasoning Specialist for a university event management board.
Your task is to write a concise, professional executive narrative explaining the ranking of student clubs.

CRITICAL CONSTRAINTS (STRICT GROUNDING RULES):
1. You are given a PRE-COMPUTED metrics table as structured JSON.
2. You must NEVER calculate, estimate, or invent any numbers.
3. Every number, percentage, or rating you mention MUST be copied EXACTLY from the provided JSON table.
4. Do NOT cite any club name or metric not present in the JSON.
5. Highlight the Top 3 performing clubs: their primary strengths, attendance turnout, and participant feedback.
6. Explicitly mention any data integrity notes (e.g., partial data, missing attendance sheets) if present in the data_status.
7. Explain the performance tradeoffs (e.g., high engagement quality vs lower consistency).
8. Keep your response structured using markdown headings, bullet points, and bold club names.
"""


def extract_numbers_with_context(text: str) -> List[Tuple[float, str]]:
    """
    Extract numbers from text categorized by kind: 'rank' or 'metric'.
    """
    results: List[Tuple[float, str]] = []
    lines = text.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check for leading list bullet: "1. ", "2. ", etc.
        m_bullet = re.match(r"^(\d+)\.\s+", stripped)
        if m_bullet:
            results.append((float(m_bullet.group(1)), "rank"))
            stripped = stripped[m_bullet.end():]

        # Check for explicit rank references like "rank 1", "Rank 2", "#1"
        for m_rank in re.finditer(r"(?:rank|#)\s*(\d+)", stripped, flags=re.IGNORECASE):
            results.append((float(m_rank.group(1)), "rank"))

        # Strip explicit rank tokens and ISO dates before metric extraction
        stripped_metrics = re.sub(r"(?:rank|#)\s*\d+", "", stripped, flags=re.IGNORECASE)
        stripped_metrics = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", stripped_metrics)

        pattern = r'(?<![A-Za-z_])(\d+(?:\.\d+)?%?)(?![A-Za-z_])'
        for m in re.findall(pattern, stripped_metrics):
            clean_m = m.replace("%", "").strip()
            try:
                val = float(clean_m)
                results.append((val, "metric"))
            except ValueError:
                pass

    return results


def extract_numbers_from_text(text: str) -> List[float]:
    """
    Extract all numeric values (integers, floats, percentages) from a text string.
    Filters out common non-metric tokens like markdown bullet indices.
    """
    return [num for num, _ in extract_numbers_with_context(text)]


def build_allowed_number_set(
    metrics_summary: List[Dict[str, Any]],
    weights_config: Optional[Dict[str, Any]] = None
) -> set:
    """
    Build a comprehensive set of allowed ground-truth numbers from the computed metrics table.
    Includes raw numbers, rounded variants, percentages, and safe contextual constants (e.g. 100, 5, 2024).
    """
    allowed = set()

    # Standard safe context constants (scale bounds, ranks 1-10, calendar days 1-31, years 2020-2030)
    safe_constants = {0.0, 5.0, 50.0, 100.0}
    safe_constants.update(float(i) for i in range(1, 32))  # Days and ranks 1-31
    safe_constants.update(float(y) for y in range(2020, 2031))  # Calendar years
    allowed.update(safe_constants)

    if weights_config and "weights" in weights_config:
        for w in weights_config["weights"].values():
            allowed.add(float(w))
            allowed.add(round(float(w) * 100, 1))

    for row in metrics_summary:
        for key, val in row.items():
            if isinstance(val, (int, float)) and val is not None:
                f_val = float(val)
                allowed.add(round(f_val, 2))
                allowed.add(round(f_val, 1))
                allowed.add(round(f_val, 0))
                # For rates between 0 and 1, add the 100x percentage equivalent
                if 0.0 <= f_val <= 1.0:
                    pct = round(f_val * 100, 1)
                    allowed.add(pct)
                    allowed.add(round(pct, 0))

    return allowed


def validate_number_grounding(
    explanation_text: str,
    metrics_summary: List[Dict[str, Any]],
    weights_config: Optional[Dict[str, Any]] = None,
    tolerance: float = 0.5,
    in_scope_event_dates: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Programmatically verify that citations in the LLM's explanation are grounded:
    - Number citations are validated against allowed targets (segregating rank from metrics).
    - Club names are validated against actual club names in the evaluated table.
    - Dates (YYYY-MM-DD) are validated against in-scope event dates.
    Untraceable claims are added to 'flagged_items'.
    """
    tagged_numbers = extract_numbers_with_context(explanation_text)

    # Allowed ranks strictly from the rank column
    allowed_ranks = set()
    for row in metrics_summary:
        if "rank" in row and isinstance(row["rank"], (int, float)):
            allowed_ranks.add(float(row["rank"]))

    # Allowed metric targets with field-specific tolerances
    allowed_metrics_with_tol: List[Tuple[float, float]] = []

    # Safe constants: scale bounds and calendar years
    for c in [0.0, 5.0, 50.0, 100.0]:
        allowed_metrics_with_tol.append((c, 0.01))
    for y in range(2020, 2031):
        allowed_metrics_with_tol.append((float(y), 0.01))

    if weights_config and "weights" in weights_config:
        for w in weights_config["weights"].values():
            fw = float(w)
            allowed_metrics_with_tol.append((round(fw, 2), 0.01))
            allowed_metrics_with_tol.append((round(fw * 100, 1), 0.1))

    for row in metrics_summary:
        for key, val in row.items():
            if key == "rank":
                continue  # Rank numbers handled separately
            if isinstance(val, (int, float)) and val is not None:
                f_val = float(val)
                s_val = str(val)
                if "." in s_val and len(s_val.split(".")[1]) >= 2:
                    allowed_metrics_with_tol.append((round(f_val, 2), 0.01))
                elif "." in s_val:
                    allowed_metrics_with_tol.append((round(f_val, 1), 0.1))
                else:
                    allowed_metrics_with_tol.append((f_val, 0.01))

                # If rate between 0 and 1, percentage equivalent
                if 0.0 <= f_val <= 1.0:
                    allowed_metrics_with_tol.append((round(f_val * 100, 2), 0.01))
                    allowed_metrics_with_tol.append((round(f_val * 100, 1), 0.1))

    grounded_numbers = []
    suspicious_numbers = []

    for num, kind in tagged_numbers:
        if kind == "rank":
            if num in allowed_ranks:
                grounded_numbers.append(num)
            else:
                suspicious_numbers.append(num)
        else:
            is_grounded = any(abs(num - allowed) <= tol for allowed, tol in allowed_metrics_with_tol)
            if is_grounded:
                grounded_numbers.append(num)
            else:
                suspicious_numbers.append(num)

    # Club name verification
    allowed_club_names = {row.get("club_name") for row in metrics_summary if row.get("club_name")}
    untraceable_clubs = []

    # 1. Bold entity mentions: **Club Name**
    bold_mentions = re.findall(r"\*\*([^*]+)\*\*", explanation_text)
    for mention in bold_mentions:
        mention_clean = mention.strip()
        if any(mention_clean.endswith(s) for s in ["Club", "Society", "Chapter", "Guild", "Lab", "Branch", "Association", "Team", "Council"]):
            if mention_clean not in allowed_club_names and mention_clean not in untraceable_clubs:
                untraceable_clubs.append(mention_clean)

    # 2. Free-text club phrases
    club_phrases = re.findall(r"\b([A-Z][A-Za-z0-9&'\s]+?\s+(?:Club|Society|Chapter|Guild|Lab|Branch|Association|Team|Council))\b", explanation_text)
    for phrase in club_phrases:
        phrase_clean = phrase.strip()
        if phrase_clean not in allowed_club_names and phrase_clean not in untraceable_clubs:
            untraceable_clubs.append(phrase_clean)

    # Date verification (YYYY-MM-DD)
    allowed_dates = set(in_scope_event_dates or [])
    extracted_dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", explanation_text)
    untraceable_dates = []
    for d in extracted_dates:
        if d not in allowed_dates and d not in untraceable_dates:
            untraceable_dates.append(d)

    flagged_items = []
    for s in suspicious_numbers:
        flagged_items.append(s)
    for c in untraceable_clubs:
        flagged_items.append(c)
    for d in untraceable_dates:
        flagged_items.append(d)

    is_clean = (len(suspicious_numbers) == 0 and len(untraceable_clubs) == 0 and len(untraceable_dates) == 0)
    verdict = "PASSED: All numerical citations are strictly grounded." if is_clean else f"WARNING: {len(flagged_items)} ungrounded or untraceable citations detected."

    return {
        "is_valid": is_clean,
        "verdict": verdict,
        "total_numbers_checked": len(tagged_numbers),
        "grounded_numbers_count": len(grounded_numbers),
        "suspicious_numbers": suspicious_numbers,
        "suspicious_count": len(suspicious_numbers),
        "flagged_items": flagged_items
    }


def generate_ranking_explanation(
    ranked_metrics: List[Dict[str, Any]],
    weights_config: Dict[str, Any],
    llm_adapter: Optional[BaseLLMAdapter] = None,
    audit_disclosures: Optional[Dict[str, Any]] = None,
    in_scope_event_dates: Optional[List[str]] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Invoke LLM reasoning layer to generate natural language analysis of pre-computed metrics,
    followed by automated anti-hallucination number validation.
    
    Args:
        ranked_metrics: List of club metric dictionaries (pre-aggregated, no student IDs)
        weights_config: The active scoring weights configuration
        llm_adapter: Optional LLM adapter instance
        
    Returns:
        Tuple of (explanation_markdown_text, validation_report)
    """
    if not llm_adapter:
        llm_adapter = get_llm_adapter()

    # Sanitize input: only pass aggregate club fields (Strict Privacy NFR)
    sanitized_table = []
    for row in ranked_metrics:
        sanitized_table.append({
            "rank": row.get("rank"),
            "club_name": row.get("club_name"),
            "composite_score": row.get("composite_score"),
            "reach_registrations": row.get("reach"),
            "activity_volume_events": row.get("activity_volume"),
            "planned_events": row.get("planned_events"),
            "attendance_rate_pct": row.get("attendance_rate_pct"),
            "engagement_quality_rating": row.get("engagement_quality"),
            "consistency_score": row.get("consistency_raw"),
            "data_status": row.get("data_status")
        })

    imputation_notice = ""
    if audit_disclosures:
        imp_fields = audit_disclosures.get("imputed_fields", [])
        excl_count = audit_disclosures.get("excluded_event_count", 0)
        imputation_notice = (
            f"\n\nData Imputation & Exclusion Disclosure:\n"
            f"- Total events excluded from averages due to missing attendance or feedback: {excl_count}\n"
            f"- Imputed field substitutions: {json.dumps(imp_fields) if imp_fields else 'None (Clean Exclusion Policy)'}"
        )

    user_prompt = f"""Here is the deterministic metrics and ranking table for the evaluated clubs:

```json
{json.dumps(sanitized_table, indent=2)}
```

Scoring Weights Applied:
{json.dumps(weights_config.get("weights", {}), indent=2)}{imputation_notice}

Please write the executive performance narrative. Explain why the top clubs placed where they did, citing their exact attendance rates, ratings, and consistency scores from the table. Also call out any clubs operating under partial data."""

    messages = [{"role": "user", "content": user_prompt}]
    explanation_text = llm_adapter.call_text(messages, system_prompt=EXPLANATION_SYSTEM_PROMPT)

    # Perform automated number-grounding check
    validation_report = validate_number_grounding(
        explanation_text,
        ranked_metrics,
        weights_config,
        in_scope_event_dates=in_scope_event_dates
    )

    return explanation_text, validation_report
