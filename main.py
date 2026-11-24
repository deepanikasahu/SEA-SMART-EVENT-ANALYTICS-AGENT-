"""
Main CLI Entry Point for Smart Event Analytics Agent.
Runs the complete autonomous agent pipeline from natural language prompt to final audit report.
Displays real-time step execution logs, deterministic leaderboard, reasoning summary, and anti-hallucination checks.
"""

import argparse
import io
import os
import sys
import tabulate
from agent.orchestrator import EventAnalyticsAgent
from report.generate_report import generate_all_reports

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


def print_banner():
    print("\n" + "="*80)
    print(" [*] SMART EVENT ANALYTICS AGENT (SEA Agent) - COLLEGE JURY DEMO")
    print(" Architecture: Native Tool Calling | Pure Python Metrics | Grounded LLM Reasoning")
    print("="*80 + "\n")



def display_results(results: dict):
    """Format and print the agent results clearly on the terminal for the jury."""
    if results.get("status") in ["needs_clarification", "CLARIFICATION_NEEDED"]:
        print("\n" + "!"*80)
        print(" [?] AGENT REQUESTS CLARIFICATION (FR1 Safeguard):")
        print(f" {results.get('question') or results.get('message')}")
        print("!"*80 + "\n")
        return

    if results.get("status") != "SUCCESS":
        print(f"\n[!] Execution Failed: {results.get('message')}\n")
        return

    print("\n" + "-"*80)
    print(" [>] 1. AGENT TOOL-CALLING TRAJECTORY")
    print("-"*80)
    for log_item in results.get("execution_log", []):
        step_name = log_item.get("step")
        if "Tool Execution" in step_name:
            args = log_item.get("arguments")
            recs = log_item.get("records_fetched")
            dur = log_item.get("duration_seconds")
            print(f"  --> {step_name} | Args: {args} | Retrieved: {recs} rows ({dur}s)")
        else:
            print(f"  --> {step_name}: {log_item.get('detail')}")

    print("\n" + "-"*80)
    print(f" [*] 2. DETERMINISTIC CLUB LEADERBOARD (In-Scope Events: {results.get('in_scope_events_count')})")
    print("-"*80)
    
    ranked_clubs = results.get("ranked_clubs", [])
    table_rows = []
    for c in ranked_clubs:
        att_str = f"{c.get('attendance_rate_pct'):.1f}%" if c.get('attendance_rate_pct') is not None else "N/A*"
        fb_str = f"{c.get('engagement_quality'):.2f}/5" if c.get('engagement_quality') is not None else "N/A*"
        cons_str = f"{c.get('consistency_raw')*100:.1f}%"
        table_rows.append([
            f"#{c.get('rank')}",
            c.get('club_name'),
            f"{c.get('composite_score'):.2f}",
            att_str,
            fb_str,
            cons_str,
            c.get('reach'),
            f"{c.get('activity_volume')}/{c.get('planned_events')}",
            c.get('data_status')
        ])

    headers = ["Rank", "Club Name", "Score", "Turnout %", "Feedback", "Consistency", "Reach", "Events", "Integrity Status"]
    print(tabulate.tabulate(table_rows, headers=headers, tablefmt="fancy_grid"))

    print("\n" + "-"*80)
    print(" [*] 3. QUALITATIVE REASONING & TOP FINDINGS (LLM Generative Layer)")
    print("-"*80)
    print(results.get("grounded_narrative", "").strip())

    print("\n" + "-"*80)
    print(" [*] 4. ANTI-HALLUCINATION NUMBER-GROUNDING AUDIT")
    print("-"*80)
    audit = results.get("number_grounding_audit", {})
    print(f"  * Verdict: {audit.get('verdict')}")
    print(f"  * Total Numbers Inspected in LLM Output: {audit.get('total_numbers_checked')}")
    print(f"  * Fully Grounded Numbers in Raw Table:   {audit.get('grounded_numbers_count')}")
    print(f"  * Suspicious / Hallucinated Numbers:     {audit.get('suspicious_count')}")
    if audit.get("suspicious_numbers"):
        print(f"  [!] WARNING: Suspicious numbers flagged: {audit.get('suspicious_numbers')}")

    print("\n" + "-"*80)
    print(" [*] 5. MISSING DATA DISCLOSURE (FR7 Compliance)")
    print("-"*80)
    disclosures = results.get("audit_disclosures", {})
    partial_clubs = disclosures.get("clubs_with_partial_data", [])
    excluded_count = disclosures.get("excluded_event_count", 0)
    imputed_fields = disclosures.get("imputed_fields", [])
    imputation_applied = disclosures.get("imputation_applied", False)

    print(f"  [i] Total Excluded Events: {excluded_count} event(s) missing attendance or feedback records.")
    if imputation_applied and imputed_fields:
        print(f"  [i] Imputed Field Substitutions ({len(imputed_fields)}):")
        for imp in imputed_fields:
            print(f"      - {imp.get('club_name')}: {imp.get('field')} = {imp.get('substituted_value')}")
    else:
        print(f"  [i] Imputation Applied: {imputation_applied} (no substitutions)")

    if partial_clubs:
        for p in partial_clubs:
            print(f"  [!] {p.get('club_name')}:")
            print(f"      - Attendance Sheets: {p.get('events_with_attendance')}/{p.get('total_events')} submitted (Missing: {p.get('missing_attendance_events')})")
            print(f"      - Feedback Forms:    {p.get('events_with_feedback')}/{p.get('total_events')} submitted (Missing: {p.get('missing_feedback_events')})")
    else:
        print("  [+] All evaluated clubs had 100% complete attendance sheets and feedback records.")


def main():
    parser = argparse.ArgumentParser(description="Smart Event Analytics Agent CLI Runner")
    parser.add_argument(
        "query",
        type=str,
        nargs="?",
        default="Analyze all technical events conducted last semester and tell me which clubs performed the best.",
        help="Natural language user request"
    )
    parser.add_argument("--provider", type=str, default=None, help="LLM Provider override: 'groq', 'gemini', 'openrouter', 'mock'")
    parser.add_argument("--db-path", type=str, default="data/sea_agent.db", help="Path to SQLite database")
    parser.add_argument("--weights-path", type=str, default="weights_config.json", help="Path to weights_config.json")
    parser.add_argument("--impute-missing", action="store_true", help="Opt-in category-average imputation flag (default: False)")
    parser.add_argument("--output-dir", type=str, default="reports", help="Output directory for reports")

    args = parser.parse_args()
    print_banner()

    # Check if database exists; if not, automatically generate dummy data
    if not os.path.exists(args.db_path):
        print(f"[*] Database '{args.db_path}' not found. Generating fresh synthetic database with seed=42...")
        from data_generation.generate_dummy_data import generate_data
        generate_data(db_path=args.db_path, seed=42)

    # Initialize Agent
    agent = EventAnalyticsAgent(
        db_path=args.db_path,
        weights_path=args.weights_path,
        provider=args.provider,
        impute_missing=args.impute_missing
    )

    current_query = args.query

    # Run Agent Loop
    results = agent.run(user_query=current_query)
    display_results(results)

    # If clarification requested, allow interactive CLI input
    if results.get("status") in ["needs_clarification", "CLARIFICATION_NEEDED"]:
        try:
            clarif_reply = input("[?] Enter clarification (e.g., 'last semester', 'Spring 2024'): ").strip()
            if clarif_reply:
                merged_query = f"{current_query} (Time period: {clarif_reply})"
                print(f"\n[*] Re-invoking agent with clarified query: '{merged_query}'...\n")
                results = agent.run(user_query=merged_query)
                display_results(results)
        except (EOFError, KeyboardInterrupt):
            pass

    # Generate Reports if successful
    if results.get("status") == "SUCCESS":
        md_path, docx_path = generate_all_reports(results, output_dir=args.output_dir)
        print("\n" + "="*80)
        print(" [*] AUDIT REPORTS GENERATED SUCCESSFULLY:")
        print(f"  * Markdown Report: {md_path}")
        if docx_path:
            print(f"  * Word Report:     {docx_path}")
        print("="*80 + "\n")


if __name__ == "__main__":
    main()

