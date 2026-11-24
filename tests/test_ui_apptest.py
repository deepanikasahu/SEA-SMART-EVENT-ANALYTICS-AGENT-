"""
UI verification test using streamlit.testing.v1.AppTest.
Verifies Task 8 UI components:
a. Results table with rank, club, composite score, five component metrics, data-quality flag.
b. Audit panel with pass/fail and flagged items ("No flagged items" on clean run).
c. Tool Execution Trajectory expander listing tool calls in order with name, args, records, duration.
d. Idle state single-sentence guidance.
"""

import json
import os
import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture
def app_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))


@pytest.fixture
def seed42_results():
    fixture_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "fixtures", "seed42_entry_path_baseline.json")
    )
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_app_idle_state_ui(app_path):
    """Test Task 8d: Single sentence in empty/idle state."""
    at = AppTest.from_file(app_path)
    at.run(timeout=10)
    assert len(at.exception) == 0

    info_messages = [info.value for info in at.info]
    expected_sentence = "Pick a preset query from the right panel and click Run Analysis to begin."
    assert any(expected_sentence in msg for msg in info_messages)


def test_app_results_state_ui_elements(app_path, seed42_results):
    """Test Task 8a, 8b, 8c with seed 42 results."""
    at = AppTest.from_file(app_path)
    at.run(timeout=10)
    at.session_state["latest_results"] = seed42_results
    at.session_state["pending_clarification"] = False
    at.run(timeout=10)
    assert len(at.exception) == 0

    # a. Results table above narrative
    assert len(at.dataframe) >= 1
    leaderboard_df = at.dataframe[0].value
    required_cols = [
        "rank", "club", "composite_score", "engagement_quality",
        "attendance_rate", "consistency", "reach", "activity_volume", "data_quality_flag"
    ]
    for col in required_cols:
        assert col in leaderboard_df.columns, f"Missing required column {col} in UI dataframe"
    assert len(leaderboard_df) == 6

    # b. Audit panel
    audit_expanders = [exp for exp in at.expander if "Anti-Hallucination" in exp.label]
    assert len(audit_expanders) == 1
    info_messages = [info.value for info in at.info]
    assert any("No flagged items" in msg for msg in info_messages)

    # c. Tool Execution Trajectory expander
    tool_expanders = [exp for exp in at.expander if "Tool Execution" in exp.label]
    assert len(tool_expanders) == 1
    assert len(tool_expanders[0].markdown) >= 4
    rendered_calls = [m for m in tool_expanders[0].markdown if "Tool Call:**" in m.value]
    assert len(rendered_calls) == len(seed42_results["execution_log"])


def test_app_click_run_analysis_button_preset(app_path):
    """Test Item 5: Trigger real analysis through UI preset and Run Analysis button."""
    at = AppTest.from_file(app_path)
    at.run(timeout=15)

    # Click preset Technical Events (Standard)
    preset_btn = next(b for b in at.button if "Technical Events (Standard)" in b.label)
    preset_btn.click().run(timeout=15)

    # Click Run Analysis
    run_btn = next(b for b in at.button if "Run Analysis" in b.label)
    run_btn.click().run(timeout=15)
    assert len(at.exception) == 0

    # a. Results table above narrative
    assert len(at.dataframe) >= 1
    leaderboard_df = at.dataframe[0].value
    required_cols = [
        "rank", "club", "composite_score", "engagement_quality",
        "attendance_rate", "consistency", "reach", "activity_volume", "data_quality_flag"
    ]
    for col in required_cols:
        assert col in leaderboard_df.columns, f"Missing required column {col} in UI dataframe"
    assert len(leaderboard_df) == 6

    # b. Audit panel
    audit_expanders = [exp for exp in at.expander if "Anti-Hallucination" in exp.label]
    assert len(audit_expanders) == 1
    assert any("PASS" in md.value for md in audit_expanders[0].markdown)
    info_messages = [info.value for info in at.info]
    assert any("No flagged items" in msg for msg in info_messages)

    # c. Tool Execution Trajectory: assert rendered count matches execution_log
    tool_expanders = [exp for exp in at.expander if "Tool Execution" in exp.label]
    assert len(tool_expanders) == 1
    rendered_calls = [m for m in tool_expanders[0].markdown if "Tool Call:**" in m.value]
    latest_res = at.session_state["latest_results"]
    assert len(rendered_calls) == len(latest_res["execution_log"])
    assert len(rendered_calls) == 5
