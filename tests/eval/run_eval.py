"""
Evaluation Suite Runner for SEA Agent (Task 9).
Executes test cases defined in eval_queries.json against EventAnalyticsAgent.
"""

import json
import os
import sys
import tempfile
from typing import Any, Dict, List, Tuple

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from data_generation.generate_dummy_data import generate_data
from agent.orchestrator import EventAnalyticsAgent


def run_evaluation_suite(
    cases_path: str = None,
    seed: int = 42
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Run all evaluation cases from eval_queries.json and verify outcomes.

    Returns:
        (case_results, passed_count, failed_count)
    """
    if cases_path is None:
        cases_path = os.path.join(os.path.dirname(__file__), "eval_queries.json")

    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    results = []
    passed = 0
    failed = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "eval_runner.db")
        generate_data(db_path=db_path, seed=seed)

        weights_path = os.path.join(REPO_ROOT, "weights_config.json")

        for tc in cases:
            tc_id = tc["id"]
            desc = tc["description"]
            query = tc["query"]
            impute = tc.get("impute_missing", False)
            expected_fail = tc.get("expected_fail", False)
            fail_reason = tc.get("fail_reason", None)

            agent = EventAnalyticsAgent(
                db_path=db_path,
                weights_path=weights_path,
                provider="mock",
                impute_missing=impute
            )

            res = agent.run(query)

            # Evaluate assertions
            actual_status = res.get("status")
            expected_status = tc.get("expected_status")

            actual_imp = res.get("audit_disclosures", {}).get("imputation_applied", False)
            expected_imp = tc.get("expected_imputation_applied", False)

            ranked_clubs = res.get("ranked_clubs", [])
            actual_ranked_count = len(ranked_clubs)
            expected_ranked_count = tc.get("expected_ranked_clubs_count")

            actual_events = res.get("in_scope_events_count")
            expected_events = tc.get("expected_events_count")

            actual_top_club = ranked_clubs[0].get("club_name") if ranked_clubs else None
            expected_top_club = tc.get("expected_top_club")

            mismatches = []
            if actual_status != expected_status:
                mismatches.append(f"Status mismatch: expected '{expected_status}', got '{actual_status}'")
            if actual_imp != expected_imp:
                mismatches.append(f"Imputation mismatch: expected {expected_imp}, got {actual_imp}")
            if expected_ranked_count is not None and actual_ranked_count != expected_ranked_count:
                mismatches.append(f"Ranked clubs count mismatch: expected {expected_ranked_count}, got {actual_ranked_count}")
            if expected_events is not None and actual_events != expected_events:
                mismatches.append(f"Events count mismatch: expected {expected_events}, got {actual_events}")
            if expected_top_club is not None and actual_top_club != expected_top_club:
                mismatches.append(f"Top club mismatch: expected '{expected_top_club}', got '{actual_top_club}'")

            is_pass = (len(mismatches) == 0)

            if expected_fail:
                if not fail_reason:
                    outcome = "FAIL"
                    details = "Marked expected_fail but missing required named reason"
                    failed += 1
                elif is_pass:
                    outcome = "UNEXPECTED_PASS"
                    details = f"Expected failure due to '{fail_reason}', but passed unexpectedly"
                    failed += 1
                else:
                    outcome = "EXPECTED_FAIL"
                    details = f"Expected failure: {fail_reason}"
                    passed += 1
            else:
                if is_pass:
                    outcome = "PASS"
                    details = "All assertions satisfied"
                    passed += 1
                else:
                    outcome = "FAIL"
                    details = "; ".join(mismatches)
                    failed += 1

            results.append({
                "id": tc_id,
                "description": desc,
                "outcome": outcome,
                "details": details,
                "expected_outcome": tc.get("expected_outcome"),
                "actual_status": actual_status,
                "actual_events_count": actual_events,
                "actual_ranked_count": actual_ranked_count,
                "actual_top_club": actual_top_club,
                "imputation_applied": actual_imp
            })

    return results, passed, failed


if __name__ == "__main__":
    case_results, p_count, f_count = run_evaluation_suite()
    print("=" * 80)
    print(f" SEA AGENT EVALUATION SUITE: {p_count} PASSED, {f_count} FAILED (Total: {len(case_results)})")
    print("=" * 80)
    for r in case_results:
        print(f"[{r['outcome']:10s}] {r['id']}: {r['description']}")
        if r.get("expected_outcome"):
            print(f"             Expected Outcome: {r['expected_outcome']} (actual status: '{r['actual_status']}', imputation_applied: {r['imputation_applied']})")
        if r['outcome'] != "PASS":
            print(f"             Details: {r['details']}")
    print("=" * 80)
    if f_count > 0:
        sys.exit(1)
