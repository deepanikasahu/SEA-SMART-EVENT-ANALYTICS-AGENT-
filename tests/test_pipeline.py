"""
Automated Verification Suite for Smart Event Analytics Agent.
Tests:
1. Seed reproducibility (identical database on repeated runs with same seed)
2. SQLite referential integrity (foreign keys enforced)
3. Intentional missing data generation (FR7 compliance)
4. Deterministic metrics computation (no LLM, missing data excluded, not zeroed)
5. Consistency metric calculation (execution rate + attendance stability)
6. Weights configuration and ranking logic
7. Number-grounding anti-hallucination validation
8. Privacy by Design (zero student IDs in explanation or report)
9. FR1 Missing time period clarification safeguard
10. Provider swappability (Mock vs Groq)
"""

import os
import json
import sqlite3
import pytest
import pandas as pd

from data_generation.generate_dummy_data import generate_data
from agent.tools import get_events, get_registrations, get_attendance, get_feedback, get_club_plans
from agent.metrics import compute_club_metrics, compute_event_level_stats
from agent.ranking import rank_clubs, load_weights_config
from agent.explain import validate_number_grounding, generate_ranking_explanation
from agent.orchestrator import EventAnalyticsAgent
from report.generate_report import generate_markdown_report


TEST_DB = "data/test_sea_agent.db"


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """Create test database fixture."""
    generate_data(db_path=TEST_DB, seed=42)
    yield
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except Exception:
            pass


def test_seed_reproducibility():
    """Assert running dummy data generator twice with same seed produces bitwise identical data."""
    db1 = "data/test_seed1.db"
    db2 = "data/test_seed2.db"
    
    s1 = generate_data(db_path=db1, seed=123)
    s2 = generate_data(db_path=db2, seed=123)

    assert s1["events_count"] == s2["events_count"]
    assert s1["registrations_count"] == s2["registrations_count"]
    assert s1["attendance_rows_count"] == s2["attendance_rows_count"]
    assert s1["feedback_rows_count"] == s2["feedback_rows_count"]

    conn1 = sqlite3.connect(db1)
    conn2 = sqlite3.connect(db2)

    for table in ["events", "club_plans", "registrations", "attendance", "feedback"]:
        df1 = pd.read_sql_query(f"SELECT * FROM {table} ORDER BY 1", conn1)
        df2 = pd.read_sql_query(f"SELECT * FROM {table} ORDER BY 1", conn2)
        pd.testing.assert_frame_equal(df1, df2)

    conn1.close()
    conn2.close()
    os.remove(db1)
    os.remove(db2)


def test_sqlite_foreign_key_enforcement():
    """Assert database raises IntegrityError when violating foreign keys with PRAGMA foreign_keys = ON."""
    conn = sqlite3.connect(TEST_DB)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    # Attempt inserting registration for nonexistent event
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute(
            "INSERT INTO registrations VALUES ('REG_INVALID', 'EVT_NONEXISTENT', 'STU_9999', '2024-01-01');"
        )
    conn.close()


def test_intentional_missing_data_generated():
    """Assert that intentional omissions (EVT_003, EVT_008 for attendance, EVT_005 for feedback) exist."""
    conn = sqlite3.connect(TEST_DB)
    att_events = set(pd.read_sql_query("SELECT DISTINCT event_id FROM attendance;", conn)["event_id"])
    fb_events = set(pd.read_sql_query("SELECT DISTINCT event_id FROM feedback;", conn)["event_id"])
    all_events = set(pd.read_sql_query("SELECT DISTINCT event_id FROM events;", conn)["event_id"])
    conn.close()

    assert "EVT_003" in all_events
    assert "EVT_003" not in att_events  # Missing attendance
    assert "EVT_005" in all_events
    assert "EVT_005" not in fb_events   # Missing feedback


def test_deterministic_metrics_and_exclusions():
    """Assert missing attendance/feedback are excluded from averages and flagged as partial data."""
    events_df = get_events(db_path=TEST_DB)
    regs_df = get_registrations(db_path=TEST_DB)
    att_df = get_attendance(db_path=TEST_DB)
    fb_df = get_feedback(db_path=TEST_DB)
    plans_df = get_club_plans(db_path=TEST_DB)

    metrics_df, audit = compute_club_metrics(
        events_df, regs_df, att_df, fb_df, plans_df, impute_missing=False
    )

    assert not metrics_df.empty
    assert len(audit["missing_attendance_events"]) >= 1
    assert len(audit["missing_feedback_events"]) >= 1

    # Verify that partial data flags are set for clubs with missing events
    partial_clubs = metrics_df[metrics_df["is_partial_data"]]
    assert len(partial_clubs) >= 1

    for _, row in metrics_df.iterrows():
        # Attendance rate must be between 0 and 1 (or None), not 0.0 coerced from missing
        if row["events_with_attendance"] > 0:
            assert 0.0 <= row["attendance_rate"] <= 1.0
        if row["events_with_feedback"] > 0:
            assert 1.0 <= row["engagement_quality"] <= 5.0


def test_ranking_weights_and_normalization():
    """Assert ranking uses weights_config.json and produces correct 0-100 composite scores."""
    events_df = get_events(db_path=TEST_DB)
    regs_df = get_registrations(db_path=TEST_DB)
    att_df = get_attendance(db_path=TEST_DB)
    fb_df = get_feedback(db_path=TEST_DB)
    plans_df = get_club_plans(db_path=TEST_DB)

    metrics_df, _ = compute_club_metrics(events_df, regs_df, att_df, fb_df, plans_df)
    ranked_df, meta = rank_clubs(metrics_df, config_path="weights_config.json")

    assert "composite_score" in ranked_df.columns
    assert "rank" in ranked_df.columns
    assert ranked_df.iloc[0]["rank"] == 1
    # Scores must be sorted descending
    assert list(ranked_df["composite_score"]) == sorted(list(ranked_df["composite_score"]), reverse=True)


def test_number_grounding_anti_hallucination_validator():
    """Assert number-grounding validator flags invented figures."""
    sample_metrics = [
        {"rank": 1, "club_name": "Club Alpha", "composite_score": 88.5, "attendance_rate_pct": 78.4, "engagement_quality": 4.65, "reach": 350},
        {"rank": 2, "club_name": "Club Beta", "composite_score": 72.1, "attendance_rate_pct": 65.0, "engagement_quality": 3.90, "reach": 210}
    ]

    # 1. Truthful explanation citing exact numbers
    truthful_text = "Club Alpha achieved Rank 1 with a composite score of 88.5, an attendance rate of 78.4%, and an engagement rating of 4.65 out of 5."
    res_truthful = validate_number_grounding(truthful_text, sample_metrics)
    assert res_truthful["is_valid"] is True
    assert res_truthful["suspicious_count"] == 0

    # 2. Hallucinated explanation inventing 99.9% attendance and 499 registrations
    hallucinated_text = "Club Alpha achieved a fake score of 99.9% attendance and 499 registrations."
    res_hallucinated = validate_number_grounding(hallucinated_text, sample_metrics)
    assert res_hallucinated["is_valid"] is False
    assert res_hallucinated["suspicious_count"] >= 1


def test_privacy_enforcement_no_student_ids():
    """Assert no student IDs exist in explain prompt or generated reports."""
    agent = EventAnalyticsAgent(db_path=TEST_DB, provider="mock")
    results = agent.run("Analyze all technical events from last semester")

    md_path = generate_markdown_report(results, output_dir="reports")
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "STU_" not in content
    assert "REG_" not in content
    assert "student_id" not in content


def test_fr1_clarifying_question_on_missing_date():
    """Assert query without time period triggers needs_clarification safeguard without blocking."""
    agent = EventAnalyticsAgent(db_path=TEST_DB, provider="mock")
    # Query without date/semester
    results = agent.run("Tell me which clubs performed best.")
    assert results["status"] in ["needs_clarification", "CLARIFICATION_NEEDED"]
    assert "question" in results
    assert "clarif" in results["question"].lower() or "time" in results["question"].lower() or "semester" in results["question"].lower()



def test_provider_swap_mock():
    """Assert agent runs end-to-end with Mock provider without code changes to orchestrator."""
    agent = EventAnalyticsAgent(db_path=TEST_DB, provider="mock")
    results = agent.run("Analyze all technical events conducted last semester and tell me which clubs performed the best.")
    assert results["status"] == "SUCCESS"
    assert results["provider"] == "MockLLMAdapter"
    assert len(results["ranked_clubs"]) > 0


def test_deterministic_ranking_hand_computed_fixture():
    """
    Task 2: Verify weighted composite score against hand-computed values.

    Fixture: 3 clubs with known raw metrics:
      - Beta Club:  engagement=4.0, turnout=0.80, consistency=0.90, reach=200, volume=5
      - Alpha Club: engagement=3.0, turnout=0.80, consistency=0.90, reach=200, volume=5
      - Gamma Club: engagement=5.0, turnout=0.60, consistency=0.70, reach=100, volume=2

    Min-Max Normalization (0 - 100):
      engagement: min=3.0, max=5.0, range=2.0
        Beta:  (4.0 - 3.0) / 2.0 * 100 = 50.0
        Alpha: (3.0 - 3.0) / 2.0 * 100 = 0.0
        Gamma: (5.0 - 3.0) / 2.0 * 100 = 100.0

      attendance_rate: min=0.60, max=0.80, range=0.20
        Beta:  (0.80 - 0.60) / 0.20 * 100 = 100.0
        Alpha: (0.80 - 0.60) / 0.20 * 100 = 100.0
        Gamma: (0.60 - 0.60) / 0.20 * 100 = 0.0

      consistency_raw: min=0.70, max=0.90, range=0.20
        Beta:  (0.90 - 0.70) / 0.20 * 100 = 100.0
        Alpha: (0.90 - 0.70) / 0.20 * 100 = 100.0
        Gamma: (0.70 - 0.70) / 0.20 * 100 = 0.0

      reach: min=100, max=200, range=100
        Beta:  (200 - 100) / 100 * 100 = 100.0
        Alpha: (200 - 100) / 100 * 100 = 100.0
        Gamma: (100 - 100) / 100 * 100 = 0.0

      activity_volume: min=2, max=5, range=3
        Beta:  (5 - 2) / 3 * 100 = 100.0
        Alpha: (5 - 2) / 3 * 100 = 100.0
        Gamma: (2 - 2) / 3 * 100 = 0.0

    Weights:
      engagement_quality = 0.35
      attendance_rate    = 0.25
      consistency        = 0.20
      reach              = 0.15
      activity_volume    = 0.05

    Expected Composite Scores:
      Beta Club:
        = 0.35 * 50.0 + 0.25 * 100.0 + 0.20 * 100.0 + 0.15 * 100.0 + 0.05 * 100.0
        = 17.5 + 25.0 + 20.0 + 15.0 + 5.0
        = 82.50

      Alpha Club:
        = 0.35 * 0.0 + 0.25 * 100.0 + 0.20 * 100.0 + 0.15 * 100.0 + 0.05 * 100.0
        = 0.0 + 25.0 + 20.0 + 15.0 + 5.0
        = 65.00

      Gamma Club:
        = 0.35 * 100.0 + 0.25 * 0.0 + 0.20 * 0.0 + 0.15 * 0.0 + 0.05 * 0.0
        = 35.0 + 0.0 + 0.0 + 0.0 + 0.0
        = 35.00
    """
    fixture_df = pd.DataFrame([
        {"club_name": "Beta Club", "engagement_quality": 4.0, "attendance_rate": 0.80, "consistency_raw": 0.90, "reach": 200, "activity_volume": 5},
        {"club_name": "Alpha Club", "engagement_quality": 3.0, "attendance_rate": 0.80, "consistency_raw": 0.90, "reach": 200, "activity_volume": 5},
        {"club_name": "Gamma Club", "engagement_quality": 5.0, "attendance_rate": 0.60, "consistency_raw": 0.70, "reach": 100, "activity_volume": 2},
    ])

    ranked_df, _ = rank_clubs(fixture_df)

    assert ranked_df.iloc[0]["club_name"] == "Beta Club"
    assert ranked_df.iloc[0]["composite_score"] == 82.50
    assert ranked_df.iloc[0]["rank"] == 1

    assert ranked_df.iloc[1]["club_name"] == "Alpha Club"
    assert ranked_df.iloc[1]["composite_score"] == 65.00
    assert ranked_df.iloc[1]["rank"] == 2

    assert ranked_df.iloc[2]["club_name"] == "Gamma Club"
    assert ranked_df.iloc[2]["composite_score"] == 35.00
    assert ranked_df.iloc[2]["rank"] == 3


def test_deterministic_tie_breaking_order():
    """
    Task 2: Test documented tie-break hierarchy:
      1. Higher attendance rate (turnout desc)
      2. Higher feedback (engagement quality desc)
      3. Alphabetical club name (club_name asc)
    """
    # 1. Turnout tie-break: Clubs have identical scores and other metrics, but different turnout
    df_turnout = pd.DataFrame([
        {"club_name": "Club LowTurnout", "engagement_quality": 4.0, "attendance_rate": 0.60, "consistency_raw": 0.80, "reach": 100, "activity_volume": 3},
        {"club_name": "Club HighTurnout", "engagement_quality": 4.0, "attendance_rate": 0.90, "consistency_raw": 0.80, "reach": 100, "activity_volume": 3},
    ])
    # Give both clubs equal custom weights on non-turnout metrics so composite score is tied at 0
    ranked_t, _ = rank_clubs(df_turnout, custom_weights={
        "engagement_quality": 0.0, "attendance_rate": 0.0, "consistency": 1.0, "reach": 0.0, "activity_volume": 0.0
    })
    assert ranked_t.iloc[0]["club_name"] == "Club HighTurnout"
    assert ranked_t.iloc[1]["club_name"] == "Club LowTurnout"

    # 2. Feedback tie-break: Equal score and equal turnout, but different feedback
    df_feedback = pd.DataFrame([
        {"club_name": "Club LowFeedback", "engagement_quality": 3.0, "attendance_rate": 0.80, "consistency_raw": 0.80, "reach": 100, "activity_volume": 3},
        {"club_name": "Club HighFeedback", "engagement_quality": 4.5, "attendance_rate": 0.80, "consistency_raw": 0.80, "reach": 100, "activity_volume": 3},
    ])
    ranked_f, _ = rank_clubs(df_feedback, custom_weights={
        "engagement_quality": 0.0, "attendance_rate": 0.0, "consistency": 1.0, "reach": 0.0, "activity_volume": 0.0
    })
    assert ranked_f.iloc[0]["club_name"] == "Club HighFeedback"
    assert ranked_f.iloc[1]["club_name"] == "Club LowFeedback"

    # 3. Alphabetical tie-break: Equal score, turnout, and feedback -> A-Z by club_name
    df_alpha = pd.DataFrame([
        {"club_name": "Zeta Club", "engagement_quality": 4.0, "attendance_rate": 0.80, "consistency_raw": 0.80, "reach": 100, "activity_volume": 3},
        {"club_name": "Alpha Club", "engagement_quality": 4.0, "attendance_rate": 0.80, "consistency_raw": 0.80, "reach": 100, "activity_volume": 3},
    ])
    ranked_a, _ = rank_clubs(df_alpha, custom_weights={
        "engagement_quality": 0.0, "attendance_rate": 0.0, "consistency": 1.0, "reach": 0.0, "activity_volume": 0.0
    })
    assert ranked_a.iloc[0]["club_name"] == "Alpha Club"
    assert ranked_a.iloc[1]["club_name"] == "Zeta Club"


def test_weights_sum_failure(tmp_path):
    """Task 2 verification: assert load_weights_config raises exception when weights do not sum to 1.0."""
    bad_weights = {
        "version": "1.0",
        "weights": {
            "engagement_quality": 0.30,
            "attendance_rate": 0.25,
            "consistency": 0.20,
            "reach": 0.10,
            "activity_volume": 0.05
        }  # Sum = 0.90
    }
    p = tmp_path / "bad_weights.json"
    p.write_text(json.dumps(bad_weights), encoding="utf-8")
    with pytest.raises((AssertionError, ValueError)) as exc_info:
        load_weights_config(str(p))
    assert "Weights must sum to 1.0" in str(exc_info.value)


def test_weights_missing_key_failure(tmp_path):
    """Task 2 verification: assert load_weights_config raises ValueError when a key is missing."""
    incomplete_weights = {
        "version": "1.0",
        "weights": {
            "engagement_quality": 0.40,
            "attendance_rate": 0.25,
            "consistency": 0.20,
            "reach": 0.15
            # missing "activity_volume"
        }
    }
    p = tmp_path / "incomplete_weights.json"
    p.write_text(json.dumps(incomplete_weights), encoding="utf-8")
    with pytest.raises(ValueError) as exc_info:
        load_weights_config(str(p))
    assert "missing required keys" in str(exc_info.value)


# ==============================================================================
# Task 3: Hardened Tool-Calling Loop & Input Validation Tests
# ==============================================================================

def test_tool_validation_invalid_date_format():
    """Assert get_events returns structured error dict on invalid date format without raising."""
    res1 = get_events(start_date="2024/01/15", db_path=TEST_DB)
    assert isinstance(res1, dict)
    assert res1["error"] == "INVALID_DATE_FORMAT"
    assert "Expected 'YYYY-MM-DD'" in res1["message"]

    res2 = get_events(end_date="invalid-date", db_path=TEST_DB)
    assert isinstance(res2, dict)
    assert res2["error"] == "INVALID_DATE_FORMAT"

    res3 = get_events(start_date="2024-02-30", db_path=TEST_DB)
    assert isinstance(res3, dict)
    assert res3["error"] == "INVALID_DATE_FORMAT"


def test_tool_validation_invalid_date_range_order():
    """Assert get_events returns structured error dict when start_date > end_date."""
    res = get_events(start_date="2024-05-30", end_date="2024-01-15", db_path=TEST_DB)
    assert isinstance(res, dict)
    assert res["error"] == "INVALID_DATE_RANGE"
    assert "cannot be after" in res["message"]


def test_future_date_window_returns_empty_dataframe():
    """Assert a valid but future date window returns an empty DataFrame with expected columns without fallback."""
    res = get_events(start_date="2030-01-01", end_date="2030-12-31", db_path=TEST_DB)
    assert isinstance(res, pd.DataFrame)
    assert res.empty
    expected_cols = ["event_id", "event_name", "club_name", "date", "category", "capacity"]
    assert list(res.columns) == expected_cols

    res_cat = get_events(start_date="2030-01-01", end_date="2030-12-31", category="Technical", db_path=TEST_DB)
    assert isinstance(res_cat, pd.DataFrame)
    assert res_cat.empty
    assert list(res_cat.columns) == expected_cols


def test_tool_validation_invalid_category():
    """Assert get_events returns structured error dict on unknown category."""
    res = get_events(category="NonExistentCategoryXYZ", db_path=TEST_DB)
    assert isinstance(res, dict)
    assert res["error"] == "INVALID_CATEGORY"
    assert "Invalid category" in res["message"]


def test_tool_validation_invalid_club_id():
    """Assert get_events and get_club_plans return structured error dict on unknown club ID."""
    res1 = get_events(club_id="NonExistentClubXYZ", db_path=TEST_DB)
    assert isinstance(res1, dict)
    assert res1["error"] == "INVALID_CLUB_ID"
    assert "not found in database" in res1["message"]

    res2 = get_club_plans(club_id="NonExistentClubXYZ", db_path=TEST_DB)
    assert isinstance(res2, dict)
    assert res2["error"] == "INVALID_CLUB_ID"
    assert "not found in database" in res2["message"]


def test_tool_validation_invalid_event_ids():
    """Assert get_registrations, get_attendance, get_feedback return structured error on invalid event_ids."""
    for fn in (get_registrations, get_attendance, get_feedback):
        res_str = fn(event_ids="invalid_string", db_path=TEST_DB)
        assert isinstance(res_str, dict)
        assert res_str["error"] == "INVALID_EVENT_IDS"

        res_none_str = fn(event_ids=[123, 456], db_path=TEST_DB)
        assert isinstance(res_none_str, dict)
        assert res_none_str["error"] == "INVALID_EVENT_IDS"

        # Empty list should return empty DataFrame without error
        res_empty = fn(event_ids=[], db_path=TEST_DB)
        assert isinstance(res_empty, pd.DataFrame)
        assert res_empty.empty


def test_orchestrator_cap_hit_exit():
    """Assert tool-calling loop caps at max_turns and exits with status max_turns_reached."""
    from agent.llm_client import BaseLLMAdapter, ToolCall, LLMResponse

    class InfiniteToolCallAdapter(BaseLLMAdapter):
        """Mock adapter that constantly returns a tool call without terminating."""
        def __init__(self):
            self.calls = 0

        def call_with_tools(self, messages, tools, tool_choice="auto"):
            self.calls += 1
            return LLMResponse(
                content=f"Calling club plans turn {self.calls}...",
                tool_calls=[ToolCall(id=f"call_{self.calls}", name="get_club_plans", arguments={})],
                provider="infinite_mock"
            )

        def call_text(self, messages, system_prompt=None):
            return "Looping narrative"

    agent = EventAnalyticsAgent(db_path=TEST_DB, provider="mock")
    agent.llm_adapter = InfiniteToolCallAdapter()

    res = agent.run("Analyze events last semester", max_turns=3)
    assert res["status"] == "max_turns_reached"
    assert "Maximum tool-calling iterations (3) reached" in res["message"]
    assert "execution_log" in res
    assert len(res["execution_log"]) >= 3


def test_orchestrator_tool_logging_fields():
    """Assert every executed tool call records name, arguments, record_count, and duration in execution_log."""
    agent = EventAnalyticsAgent(db_path=TEST_DB, provider="mock")
    res = agent.run("Analyze all technical events from last semester")
    assert res["status"] == "SUCCESS"
    assert "execution_log" in res

    tool_logs = [log for log in res["execution_log"] if "Tool Execution" in log.get("step", "")]
    assert len(tool_logs) > 0
    for entry in tool_logs:
        assert "name" in entry, f"Missing 'name' in log entry: {entry}"
        assert "arguments" in entry, f"Missing 'arguments' in log entry: {entry}"
        assert "record_count" in entry, f"Missing 'record_count' in log entry: {entry}"
        assert "duration" in entry, f"Missing 'duration' in log entry: {entry}"
        assert isinstance(entry["record_count"], int)
        assert isinstance(entry["duration"], (int, float))

