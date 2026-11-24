"""
Pytest integration for Task 9 Evaluation Suite.
Runs run_eval.py and asserts zero unexpected failures.
"""

import os
import sys
import importlib.util
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

run_eval_path = os.path.join(os.path.dirname(__file__), "run_eval.py")
spec = importlib.util.spec_from_file_location("tests.eval.run_eval", run_eval_path)
run_eval_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_eval_mod)
run_evaluation_suite = run_eval_mod.run_evaluation_suite


def test_evaluation_suite_zero_unexpected_failures():
    """
    Execute the full evaluation suite across all 8+ test cases.
    Assert zero unexpected failures.
    """
    results, passed_count, failed_count = run_evaluation_suite()

    failed_cases = [r for r in results if r["outcome"] not in ("PASS", "EXPECTED_FAIL")]
    assert failed_count == 0, f"Evaluation suite had {failed_count} failures: {failed_cases}"
    assert passed_count >= 8, f"Expected at least 8 passed evaluation cases, got {passed_count}"
