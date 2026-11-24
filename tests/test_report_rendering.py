"""
Tests for Markdown report rendering of missing data disclosures (FR7 compliance).
"""

import os
import tempfile
import pytest

from data_generation.generate_dummy_data import generate_data
from agent.orchestrator import EventAnalyticsAgent
from report.generate_report import generate_markdown_report


def test_report_renders_excluded_count_and_imputed_fields():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_render_seed42.db")
        generate_data(db_path=db_path, seed=42)

        agent = EventAnalyticsAgent(
            db_path=db_path,
            weights_path="weights_config.json",
            provider="mock",
            impute_missing=False
        )
        query = "Analyze all technical events conducted last semester and tell me which clubs performed best."
        results = agent.run(user_query=query)

        rep_path = generate_markdown_report(results, output_dir=tmpdir)
        with open(rep_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Assert excluded-event line is present
        assert "- **Total Excluded Events:** 3 event(s) with missing attendance or feedback records." in content
        # Assert imputed-fields block is absent when imputed_fields is empty
        assert "Imputed Field Substitutions" not in content
