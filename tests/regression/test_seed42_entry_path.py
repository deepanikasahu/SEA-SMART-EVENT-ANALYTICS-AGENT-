"""
Regression test for seed 42 complete main.py entry path.
Verifies that the entire pipeline output matches the golden baseline in
tests/fixtures/seed42_entry_path_baseline.json, with documented tie-breaking order.
"""

import os
import json
import tempfile
import pandas as pd
import pytest

from data_generation.generate_dummy_data import generate_data
from agent.orchestrator import EventAnalyticsAgent


@pytest.fixture
def baseline_entry_output():
    baseline_path = os.path.join(
        os.path.dirname(__file__), "..", "fixtures", "seed42_entry_path_baseline.json"
    )
    with open(baseline_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_seed42_full_entry_path_regression(baseline_entry_output):
    """
    Run the exact main.py entry path on seed 42 and assert complete reproducibility.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "seed42_test.db")
        generate_data(db_path=db_path, seed=42)

        agent = EventAnalyticsAgent(
            db_path=db_path,
            weights_path="weights_config.json",
            provider="mock",
            impute_missing=False
        )
        query = "Analyze all technical events conducted last semester and tell me which clubs performed best."
        actual = agent.run(user_query=query)

    expected = baseline_entry_output

    # 1. In-scope events count
    assert actual["in_scope_events_count"] == expected["in_scope_events_count"]
    assert actual["in_scope_events_count"] == 27

    # 2. Ranked leaderboard (NaN-aware DataFrame exact match)
    df_actual_ranked = pd.DataFrame(actual["ranked_clubs"])
    df_expected_ranked = pd.DataFrame(expected["ranked_clubs"])
    pd.testing.assert_frame_equal(df_actual_ranked, df_expected_ranked, check_exact=True)

    # 3. Event stats for all 27 events (NaN-aware DataFrame match)
    df_actual_events = pd.DataFrame(actual["event_stats"])
    df_expected_events = pd.DataFrame(expected["event_stats"])
    pd.testing.assert_frame_equal(df_actual_events, df_expected_events, check_exact=True)

    # 4. Grounded narrative
    assert actual["grounded_narrative"] == expected["grounded_narrative"]

    # 5. Number grounding audit
    assert actual["number_grounding_audit"] == expected["number_grounding_audit"]

    # 6. Audit disclosures
    assert actual["audit_disclosures"] == expected["audit_disclosures"]

    # 7. Ranking metadata: Documented tie-break order is verified explicitly
    actual_meta = actual["ranking_metadata"]
    expected_meta = expected["ranking_metadata"]
    assert actual_meta["tie_break_order"] == [
        "composite_score", "attendance_rate", "engagement_quality", "club_name"
    ]
    for key in ("weights_used", "rationale", "total_clubs_evaluated", "top_performer", "top_score"):
        assert actual_meta[key] == expected_meta[key]

    # 8. Execution log keys check: assert golden baseline keys are preserved in every entry
    assert "execution_log" in expected
    assert "execution_log" in actual
    golden_keys = set(expected["execution_log"][0].keys())
    for entry in actual["execution_log"]:
        assert golden_keys.issubset(set(entry.keys())), (
            f"Entry missing baseline keys. Expected at least {golden_keys}, found {set(entry.keys())}"
        )
