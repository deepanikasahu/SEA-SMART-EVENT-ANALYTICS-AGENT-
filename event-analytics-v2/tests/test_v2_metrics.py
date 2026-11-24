"""
Unit Tests — Deterministic Metrics Engine (v2)
All tests are LLM-free. They validate pure Python/pandas calculations.
Run with: pytest event-analytics-v2/tests/test_v2_metrics.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pandas as pd
import numpy as np

from engine.metrics import (
    compute_attendance_rate,
    compute_engagement_quality,
    compute_reach,
    compute_consistency,
    compute_completeness_score,
    compute_club_metrics_v2,
    load_rubric,
)
from engine.ranking import rank_clubs_v2, _min_max_normalise


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def clean_events():
    return pd.DataFrame([
        {"event_id": "E001", "event_name": "Hackathon", "club_name": "AI Club", "date": "2024-02-01", "category": "Technical", "capacity": 100},
        {"event_id": "E002", "event_name": "Workshop",  "club_name": "AI Club", "date": "2024-03-01", "category": "Technical", "capacity": 80},
    ])

@pytest.fixture
def clean_attendance():
    rows = []
    for eid, n_attend, n_total in [("E001", 80, 100), ("E002", 60, 80)]:
        for i in range(n_total):
            rows.append({"event_id": eid, "student_id": f"STU_{i:04d}", "attended": 1 if i < n_attend else 0, "check_in_time": None})
    return pd.DataFrame(rows)

@pytest.fixture
def clean_feedback():
    rows = []
    for eid, avg_rating, n in [("E001", 4.0, 50), ("E002", 3.5, 40)]:
        for i in range(n):
            rows.append({"feedback_id": f"FB_{eid}_{i}", "event_id": eid, "student_id": f"STU_{i:04d}", "rating": int(avg_rating), "comment": "", "submitted_at": "2024-02-01"})
    return pd.DataFrame(rows)

@pytest.fixture
def clean_registrations():
    rows = []
    for eid, n in [("E001", 100), ("E002", 80)]:
        for i in range(n):
            rows.append({"registration_id": f"R_{eid}_{i}", "event_id": eid, "student_id": f"STU_{i:04d}", "registered_at": "2024-01-01"})
    return pd.DataFrame(rows)

@pytest.fixture
def clean_club_plans():
    return pd.DataFrame([
        {"club_name": "AI Club", "planned_events": 2, "faculty_lead": "Dr. Smith", "founded_year": 2018}
    ])

@pytest.fixture
def rubric():
    return load_rubric()


# ─── compute_attendance_rate ──────────────────────────────────────────────────

class TestComputeAttendanceRate:
    def test_clean_data(self, clean_attendance):
        """80/100 = 80%, 60/80 = 75% → mean = 77.5%"""
        rate, missing = compute_attendance_rate(["E001", "E002"], clean_attendance)
        assert rate == pytest.approx(77.5, abs=0.5)
        assert missing == []

    def test_all_missing(self):
        """No attendance rows → returns None and all event_ids as missing."""
        rate, missing = compute_attendance_rate(["E001", "E002"], pd.DataFrame())
        assert rate is None
        assert set(missing) == {"E001", "E002"}

    def test_partial_missing(self, clean_attendance):
        """Only E001 has attendance data."""
        att = clean_attendance[clean_attendance["event_id"] == "E001"]
        rate, missing = compute_attendance_rate(["E001", "E002"], att)
        assert rate is not None
        assert "E002" in missing
        assert "E001" not in missing

    def test_empty_event_ids(self, clean_attendance):
        rate, missing = compute_attendance_rate([], clean_attendance)
        assert rate is None
        assert missing == []

    def test_rate_capped_at_100(self):
        """Walk-ins: more attendees than registrations → capped at 100%."""
        att = pd.DataFrame([
            {"event_id": "E001", "student_id": "STU_0001", "attended": 1},
            {"event_id": "E001", "student_id": "STU_0002", "attended": 1},
            {"event_id": "E001", "student_id": "STU_0003", "attended": 1},
        ])
        rate, _ = compute_attendance_rate(["E001"], att)
        assert rate <= 100.0


# ─── compute_engagement_quality ───────────────────────────────────────────────

class TestComputeEngagementQuality:
    def test_clean_feedback(self, clean_feedback):
        quality, missing = compute_engagement_quality(["E001", "E002"], clean_feedback)
        assert quality is not None
        assert 1.0 <= quality <= 5.0

    def test_no_feedback(self):
        quality, missing = compute_engagement_quality(["E001"], pd.DataFrame())
        assert quality is None
        assert "E001" in missing

    def test_rating_bounds(self):
        fb = pd.DataFrame([
            {"feedback_id": "F1", "event_id": "E001", "student_id": "STU_0001", "rating": 5, "comment": "", "submitted_at": "2024-01-01"},
            {"feedback_id": "F2", "event_id": "E001", "student_id": "STU_0002", "rating": 1, "comment": "", "submitted_at": "2024-01-01"},
        ])
        quality, _ = compute_engagement_quality(["E001"], fb)
        assert quality == pytest.approx(3.0, abs=0.01)


# ─── compute_reach ────────────────────────────────────────────────────────────

class TestComputeReach:
    def test_clean(self, clean_registrations):
        reach = compute_reach(["E001", "E002"], clean_registrations)
        # 100 + 80 registrations, all unique students (0–99 and 0–79 — some overlap)
        assert reach > 0

    def test_empty(self):
        assert compute_reach(["E001"], pd.DataFrame()) == 0

    def test_unique_count(self):
        """Same student registered for two events — counts as 1 unique."""
        regs = pd.DataFrame([
            {"registration_id": "R1", "event_id": "E001", "student_id": "STU_0001", "registered_at": "2024-01-01"},
            {"registration_id": "R2", "event_id": "E002", "student_id": "STU_0001", "registered_at": "2024-01-01"},
        ])
        assert compute_reach(["E001", "E002"], regs) == 1


# ─── compute_consistency ──────────────────────────────────────────────────────

class TestComputeConsistency:
    def test_perfect(self):
        """2/2 events delivered, zero variance → 1.0"""
        c = compute_consistency(2, 2, [0.75, 0.75])
        assert c == pytest.approx(1.0, abs=0.01)

    def test_zero_delivery(self):
        c = compute_consistency(0, 4, [])
        assert c < 0.6

    def test_overcounting_capped(self):
        """3 events but only 2 planned → delivery capped at 1.0"""
        c = compute_consistency(3, 2, [0.8, 0.8, 0.8])
        assert c <= 1.0

    def test_high_variance(self):
        """Wildly varying turnout → lower consistency."""
        low_var = compute_consistency(2, 2, [0.8, 0.8])
        high_var = compute_consistency(2, 2, [0.1, 0.9])
        assert low_var > high_var


# ─── compute_completeness_score ───────────────────────────────────────────────

class TestComputeCompletenessScore:
    def test_perfect(self):
        comp, conf = compute_completeness_score(4, 4, 4)
        assert comp == 1.0
        assert conf == 1.0

    def test_zero(self):
        comp, conf = compute_completeness_score(4, 0, 0)
        assert comp == 0.0
        assert conf == 0.0

    def test_partial(self):
        comp, conf = compute_completeness_score(4, 2, 4)
        assert 0.0 < comp < 1.0
        assert 0.0 < conf <= 1.0


# ─── compute_club_metrics_v2 (integration) ────────────────────────────────────

class TestComputeClubMetricsV2:
    def test_returns_df_and_flags(
        self, clean_events, clean_registrations, clean_attendance, clean_feedback, clean_club_plans, rubric
    ):
        df, flags = compute_club_metrics_v2(
            clean_events, clean_registrations, clean_attendance, clean_feedback, clean_club_plans, rubric=rubric
        )
        assert not df.empty
        assert len(flags) == 1
        assert df.iloc[0]["club_name"] == "AI Club"

    def test_complete_data_status(
        self, clean_events, clean_registrations, clean_attendance, clean_feedback, clean_club_plans, rubric
    ):
        df, _ = compute_club_metrics_v2(
            clean_events, clean_registrations, clean_attendance, clean_feedback, clean_club_plans, rubric=rubric
        )
        assert df.iloc[0]["data_status"] == "Complete Data"

    def test_missing_attendance(
        self, clean_events, clean_registrations, clean_feedback, clean_club_plans, rubric
    ):
        """With no attendance data, completeness_score < 1 and data_status flagged."""
        df, flags = compute_club_metrics_v2(
            clean_events, clean_registrations, pd.DataFrame(), clean_feedback, clean_club_plans, rubric=rubric
        )
        assert df.iloc[0]["completeness_score"] < 1.0
        assert df.iloc[0]["attendance_rate_pct"] is None
        assert flags[0]["events_with_attendance"] == 0

    def test_empty_events(self, rubric):
        df, flags = compute_club_metrics_v2(
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), rubric=rubric
        )
        assert df.empty
        assert flags == []


# ─── rank_clubs_v2 ────────────────────────────────────────────────────────────

class TestRankClubsV2:
    def _make_df(self):
        return pd.DataFrame([
            {"club_name": "Club A", "attendance_rate_pct": 80.0, "engagement_quality": 4.2, "consistency_raw": 0.9, "reach": 400, "activity_volume": 5, "planned_events": 5, "completeness_score": 1.0, "confidence_score": 1.0, "data_status": "Complete Data", "composite_score": 0.0, "rank": 0},
            {"club_name": "Club B", "attendance_rate_pct": 70.0, "engagement_quality": 3.8, "consistency_raw": 0.7, "reach": 300, "activity_volume": 4, "planned_events": 5, "completeness_score": 0.8, "confidence_score": 0.8, "data_status": "Partial Data", "composite_score": 0.0, "rank": 0},
        ])

    def test_higher_metrics_rank_first(self):
        df = self._make_df()
        ranked, meta = rank_clubs_v2(df)
        assert ranked.iloc[0]["club_name"] == "Club A"
        assert ranked.iloc[0]["rank"] == 1

    def test_rank_column_sequential(self):
        df = self._make_df()
        ranked, _ = rank_clubs_v2(df)
        assert list(ranked["rank"]) == list(range(1, len(ranked) + 1))

    def test_composite_score_in_range(self):
        df = self._make_df()
        ranked, _ = rank_clubs_v2(df)
        assert all(0 <= s <= 100 for s in ranked["composite_score"])

    def test_single_club_no_nan(self):
        """Single club → min==max → should return 50.0, not NaN."""
        df = pd.DataFrame([{
            "club_name": "Solo Club", "attendance_rate_pct": 75.0, "engagement_quality": 4.0,
            "consistency_raw": 0.8, "reach": 200, "activity_volume": 3, "planned_events": 3,
            "completeness_score": 1.0, "confidence_score": 1.0, "data_status": "Complete Data",
            "composite_score": 0.0, "rank": 0,
        }])
        ranked, _ = rank_clubs_v2(df)
        assert not ranked["composite_score"].isna().any()


# ─── _min_max_normalise edge cases ────────────────────────────────────────────

class TestMinMaxNormalise:
    def test_all_same_returns_50(self):
        s = pd.Series([5.0, 5.0, 5.0])
        result = _min_max_normalise(s)
        assert all(v == 50.0 for v in result)

    def test_normal_range(self):
        s = pd.Series([0.0, 50.0, 100.0])
        result = _min_max_normalise(s)
        assert result.iloc[0] == pytest.approx(0.0)
        assert result.iloc[-1] == pytest.approx(100.0)
