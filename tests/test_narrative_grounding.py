"""
Tests for narrative grounding and superlative factual consistency against pre-computed metrics.
"""

import os
import tempfile
import pytest

from data_generation.generate_dummy_data import generate_data
from agent.orchestrator import EventAnalyticsAgent
from agent.explain import validate_number_grounding


def test_mock_narrative_superlatives_match_metrics():
    """
    (a) Build the ranked table via the seed 42 pipeline.
    (b) Derive max/min clubs for turnout, score, and feedback from that table.
    (c) Assert every superlative in the rendered mock narrative matches.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "seed42_narrative_test.db")
        generate_data(db_path=db_path, seed=42)

        agent = EventAnalyticsAgent(
            db_path=db_path,
            weights_path="weights_config.json",
            provider="mock",
            impute_missing=False
        )
        query = "Analyze all technical events conducted last semester and tell me which clubs performed best."
        results = agent.run(user_query=query)

    ranked_clubs = results["ranked_clubs"]
    narrative = results["grounded_narrative"]

    # (b) Derive max/min clubs for score, turnout, and feedback
    top3 = ranked_clubs[:3]
    max_score_club = max(top3, key=lambda c: c["composite_score"])["club_name"]
    max_turnout_club = max(top3, key=lambda c: c["attendance_rate_pct"])["club_name"]
    max_feedback_club = max(top3, key=lambda c: c["engagement_quality"])["club_name"]

    # (c) Assert every superlative in the rendered mock narrative matches
    for line in narrative.splitlines():
        if "highest overall score" in line:
            assert max_score_club in line, (
                f"Superlative mismatch: 'highest overall score' claimed in line '{line}', "
                f"but true max score among top 3 is held by '{max_score_club}'"
            )
        if "highest turnout" in line:
            assert max_turnout_club in line, (
                f"Superlative mismatch: 'highest turnout' claimed in line '{line}', "
                f"but true max turnout among top 3 is held by '{max_turnout_club}'"
            )
        if "highest feedback rating" in line:
            assert max_feedback_club in line, (
                f"Superlative mismatch: 'highest feedback rating' claimed in line '{line}', "
                f"but true max feedback among top 3 is held by '{max_feedback_club}'"
            )


def test_rank_numbers_must_not_ground_against_non_rank_fields():
    """
    Assert that rank numbers in narrative are checked against rank column alone
    and cannot be falsely validated by matching non-rank metric fields (e.g. planned_events).
    """
    table = [
        {"rank": 1, "club_name": "Alpha Club", "composite_score": 75.0, "planned_events": 5}
    ]
    # Narrative cites rank 5, which does not exist in rank column but exists in planned_events
    narrative = "Alpha Club achieved rank 5 with composite score of 75.0."
    audit = validate_number_grounding(narrative, table)

    # Defect: current validator marks this valid because 5 matches planned_events
    # Fix expectation: rank 5 must be rejected as an ungrounded rank
    assert not audit["is_valid"], "Rank number 5 was falsely grounded against non-rank metric field"
    assert 5.0 in audit["suspicious_numbers"]


def test_rounded_precision_rejected_for_two_decimal_metrics():
    """
    Assert that rounded metric values (e.g. 81.3) are rejected when table stores exact
    two-decimal precision (81.34), rather than silently accepted by tolerance=0.5.
    """
    table = [
        {"rank": 1, "club_name": "ACM", "composite_score": 58.70, "attendance_rate_pct": 81.34}
    ]
    # Narrative cites 81.3% instead of 81.34%
    narrative = "1. **ACM** achieved rank 1 with score 58.70 and turnout of 81.3%."
    audit = validate_number_grounding(narrative, table)

    # Defect: current validator accepts 81.3 because abs(81.3 - 81.34) = 0.04 <= 0.5
    # Fix expectation: 81.3 must be flagged as ungrounded due to precision loss
    assert not audit["is_valid"], "Truncated/rounded value 81.3 was falsely accepted for 81.34"
    assert 81.3 in audit["suspicious_numbers"]


def test_untraceable_club_names_and_dates_flagged_in_audit():
    """
    Assert that invented club names (e.g. Quantum Robotics Society) and untraceable dates
    (YYYY-MM-DD not in in-scope event dates) are flagged in flagged_items and mark audit invalid.
    """
    table = [
        {"rank": 1, "club_name": "AI & Machine Learning Club", "composite_score": 73.14}
    ]

    # 1. Invented club name in narrative
    fake_narrative = "1. **Quantum Robotics Society** achieved rank 1 with an overall score of 73.14."
    audit = validate_number_grounding(fake_narrative, table)
    assert not audit["is_valid"]
    assert "Quantum Robotics Society" in audit["flagged_items"]

    # 2. Untraceable event date in narrative
    date_narrative = "1. **AI & Machine Learning Club** achieved rank 1 on 2029-12-31 with an overall score of 73.14."
    audit_date = validate_number_grounding(
        date_narrative,
        table,
        in_scope_event_dates=["2024-02-15", "2024-03-20"]
    )
    assert not audit_date["is_valid"]
    assert "2029-12-31" in audit_date["flagged_items"]

    # 3. Completely grounded narrative
    valid_narrative = "1. **AI & Machine Learning Club** achieved rank 1 on 2024-02-15 with an overall score of 73.14."
    audit_valid = validate_number_grounding(
        valid_narrative,
        table,
        in_scope_event_dates=["2024-02-15", "2024-03-20"]
    )
    assert audit_valid["is_valid"]
    assert len(audit_valid["flagged_items"]) == 0


def test_fake_adapter_with_invented_club_name_fails_audit():
    """
    Assert that when an adapter returns an invented club name ("Quantum Robotics Society"),
    EventAnalyticsAgent's number_grounding_audit marks is_valid as False and includes
    the invented name in flagged_items.
    """
    import os
    import tempfile
    from data_generation.generate_dummy_data import generate_data
    from agent.orchestrator import EventAnalyticsAgent
    from agent.llm_client import MockLLMAdapter

    class InventedClubLLMAdapter(MockLLMAdapter):
        def call_text(self, messages, system_prompt=None):
            return "1. **Quantum Robotics Society** achieved rank 1 with an overall score of 73.14."

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_invented.db")
        generate_data(db_path=db_path, seed=42)

        agent = EventAnalyticsAgent(
            db_path=db_path,
            weights_path="weights_config.json",
            provider="mock"
        )
        agent.llm_adapter = InventedClubLLMAdapter()

        res = agent.run("Analyze all technical events conducted last semester and tell me which clubs performed best.")
        audit = res["number_grounding_audit"]

        assert not audit["is_valid"]
        assert "Quantum Robotics Society" in audit["flagged_items"]
