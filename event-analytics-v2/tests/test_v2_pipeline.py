"""
End-to-End Pipeline Integration Test — v2
Tests the full run_v2_pipeline() with Mock LLM provider.
Run with: pytest event-analytics-v2/tests/test_v2_pipeline.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pipeline.graph import run_v2_pipeline
from pipeline.validator import DEFAULT_DB


MOCK_QUERY = "Analyze all technical events conducted last semester and tell me which clubs performed best."


@pytest.fixture
def v2_result():
    """Run v2 pipeline with mock LLM on the isolated v2 DB."""
    return run_v2_pipeline(
        user_query=MOCK_QUERY,
        provider="mock",
        db_path=DEFAULT_DB,
    )


class TestV2PipelineSuccess:
    def test_status_success(self, v2_result):
        assert v2_result["status"] == "SUCCESS"

    def test_version_is_v2(self, v2_result):
        assert v2_result["version"] == "v2"

    def test_ranked_clubs_not_empty(self, v2_result):
        assert len(v2_result["ranked_clubs"]) > 0

    def test_ranks_are_sequential(self, v2_result):
        ranks = [c["rank"] for c in v2_result["ranked_clubs"]]
        assert ranks == list(range(1, len(ranks) + 1))

    def test_composite_scores_in_range(self, v2_result):
        scores = [c["composite_score"] for c in v2_result["ranked_clubs"]]
        assert all(0 <= s <= 100 for s in scores)

    def test_no_nan_scores(self, v2_result):
        import math
        scores = [c["composite_score"] for c in v2_result["ranked_clubs"]]
        assert all(not math.isnan(s) for s in scores)

    def test_clubs_ranked_descending(self, v2_result):
        scores = [c["composite_score"] for c in v2_result["ranked_clubs"]]
        assert scores == sorted(scores, reverse=True)

    def test_completeness_flags_present(self, v2_result):
        assert "completeness_flags" in v2_result

    def test_execution_log_has_entries(self, v2_result):
        assert len(v2_result.get("execution_log", [])) > 0

    def test_in_scope_events_count_positive(self, v2_result):
        assert v2_result["in_scope_events_count"] > 0

    def test_narrative_is_string(self, v2_result):
        assert isinstance(v2_result["grounded_narrative"], str)

    def test_audit_dict_present(self, v2_result):
        audit = v2_result.get("number_grounding_audit", {})
        assert "is_valid" in audit

    def test_duration_positive(self, v2_result):
        assert v2_result["total_duration_seconds"] > 0


class TestV2ClarificationFlow:
    def test_missing_timeframe_triggers_clarification(self):
        result = run_v2_pipeline(
            user_query="Tell me which clubs performed best.",
            provider="mock",
            db_path=DEFAULT_DB,
        )
        assert result["status"] == "CLARIFICATION_NEEDED"
        assert result.get("clarification_needed") is True
        assert result.get("clarification_question") is not None


class TestV2DataQualityTransparency:
    def test_completeness_score_in_range(self, v2_result):
        for flag in v2_result.get("completeness_flags", []):
            assert 0.0 <= flag["completeness_score"] <= 1.0
            assert 0.0 <= flag["confidence_score"] <= 1.0

    def test_data_status_label_present(self, v2_result):
        for club in v2_result["ranked_clubs"]:
            assert "data_status" in club
            assert club["data_status"] in {
                "Complete Data",
            } or "Partial Data" in club["data_status"] or "Significant Gaps" in club["data_status"]

    def test_no_pii_in_output(self, v2_result):
        """Student IDs must never appear in the public output fields."""
        output_str = str(v2_result.get("ranked_clubs", ""))
        output_str += str(v2_result.get("grounded_narrative", ""))
        assert "STU_" not in output_str
