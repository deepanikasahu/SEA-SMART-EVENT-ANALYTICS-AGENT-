"""
Deterministic Metrics Calculation Layer for Smart Event Analytics Agent.
All mathematical and statistical computations are strictly performed here using Python and pandas.
NO LLM is ever used for computing, averaging, or aggregating these values.
"""

from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np


def compute_event_level_stats(
    events_df: pd.DataFrame,
    registrations_df: pd.DataFrame,
    attendance_df: pd.DataFrame,
    feedback_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Compute intermediate event-level statistics and detect missing data per event.
    
    Returns:
        pd.DataFrame: Event-level stats containing registrations count, attendees count,
                      attendance rate, feedback count, avg feedback rating, and missing flags.
    """
    if events_df.empty:
        return pd.DataFrame()

    event_stats = []

    # Pre-index for performance
    reg_counts = registrations_df.groupby("event_id").size().to_dict() if not registrations_df.empty else {}
    
    # Attendance breakdown: check if event has any rows in attendance_df
    events_with_att_data = set(attendance_df["event_id"].unique()) if not attendance_df.empty else set()
    attendees_counts = {}
    if not attendance_df.empty:
        attendees_counts = attendance_df[attendance_df["attended"] == 1].groupby("event_id").size().to_dict()

    # Feedback breakdown: check if event has any rows in feedback_df
    events_with_fb_data = set(feedback_df["event_id"].unique()) if not feedback_df.empty else set()
    fb_counts = feedback_df.groupby("event_id").size().to_dict() if not feedback_df.empty else {}
    fb_avg_ratings = feedback_df.groupby("event_id")["rating"].mean().to_dict() if not feedback_df.empty else {}

    for _, event in events_df.iterrows():
        e_id = event["event_id"]
        club = event["club_name"]
        cat = event["category"]
        cap = event["capacity"]
        date = event["date"]
        e_name = event["event_name"]

        n_regs = reg_counts.get(e_id, 0)
        has_att = e_id in events_with_att_data
        n_attendees = attendees_counts.get(e_id, 0) if has_att else None
        
        # Calculate event attendance rate only if attendance data was submitted
        att_rate = None
        if has_att:
            att_rate = (n_attendees / n_regs) if n_regs > 0 else 0.0
            # Cap at 1.0 in case of walk-ins
            att_rate = min(1.0, att_rate)

        has_fb = e_id in events_with_fb_data
        n_fb = fb_counts.get(e_id, 0) if has_fb else 0
        avg_fb = fb_avg_ratings.get(e_id, None) if has_fb else None

        event_stats.append({
            "event_id": e_id,
            "event_name": e_name,
            "club_name": club,
            "date": date,
            "category": cat,
            "capacity": cap,
            "registrations": n_regs,
            "has_attendance_data": has_att,
            "attendees": n_attendees,
            "attendance_rate": att_rate,
            "has_feedback_data": has_fb,
            "feedback_count": n_fb,
            "avg_feedback_rating": avg_fb
        })

    return pd.DataFrame(event_stats)


def compute_club_metrics(
    events_df: pd.DataFrame,
    registrations_df: pd.DataFrame,
    attendance_df: pd.DataFrame,
    feedback_df: pd.DataFrame,
    club_plans_df: Optional[pd.DataFrame] = None,
    impute_missing: bool = False
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Compute deterministic club-level performance metrics and missing-data audit flags.
    
    Args:
        events_df: In-scope events dataframe
        registrations_df: Registrations for in-scope events
        attendance_df: Attendance records for in-scope events
        feedback_df: Feedback records for in-scope events
        club_plans_df: Planned events targets per club
        impute_missing: If True, uses category-average substitution; if False (default),
                        excludes missing events from averages and flags them transparently.
                        
    Returns:
        Tuple of (metrics_df, audit_metadata)
    """
    if events_df.empty:
        return pd.DataFrame(), {"error": "No in-scope events provided."}

    event_stats_df = compute_event_level_stats(events_df, registrations_df, attendance_df, feedback_df)
    
    # Map planned events from club_plans
    planned_map = {}
    faculty_map = {}
    if club_plans_df is not None and not club_plans_df.empty:
        planned_map = dict(zip(club_plans_df["club_name"], club_plans_df["planned_events"]))
        faculty_map = dict(zip(club_plans_df["club_name"], club_plans_df.get("faculty_lead", "N/A")))

    # Calculate dataset-wide baseline averages for imputation if requested
    valid_att_rates = event_stats_df[event_stats_df["has_attendance_data"]]["attendance_rate"].dropna()
    benchmark_att_rate = float(valid_att_rates.mean()) if not valid_att_rates.empty else 0.70

    valid_fb_ratings = event_stats_df[event_stats_df["has_feedback_data"]]["avg_feedback_rating"].dropna()
    benchmark_fb_rating = float(valid_fb_ratings.mean()) if not valid_fb_ratings.empty else 3.80

    club_records = []
    audit_disclosures = {
        "imputation_applied": False,
        "benchmark_attendance_rate": round(benchmark_att_rate, 4),
        "benchmark_feedback_rating": round(benchmark_fb_rating, 2),
        "clubs_with_partial_data": [],
        "missing_attendance_events": [],
        "missing_feedback_events": [],
        "imputed_fields": [],
    }

    for club_name, group in event_stats_df.groupby("club_name"):
        total_events = len(group)
        planned_events = planned_map.get(club_name, total_events)
        faculty_lead = faculty_map.get(club_name, "N/A")

        # 1. Reach: Total registrations across all events
        total_reach = int(group["registrations"].sum())
        avg_regs_per_event = round(float(group["registrations"].mean()), 2) if total_events > 0 else 0.0

        # 2. Attendance Analysis & Missing Data Handling (FR7)
        att_group = group[group["has_attendance_data"]]
        events_with_att = len(att_group)
        missing_att_events = group[~group["has_attendance_data"]]["event_id"].tolist()

        if events_with_att > 0:
            total_attendees = int(att_group["attendees"].sum())
            total_att_regs = int(att_group["registrations"].sum())
            # Weighted overall attendance rate across attended events
            attendance_rate = float(total_attendees / total_att_regs) if total_att_regs > 0 else 0.0
            attendance_rate = min(1.0, attendance_rate)
            # Per-event attendance variance
            att_rates_series = att_group["attendance_rate"]
            att_std = float(att_rates_series.std(ddof=0)) if len(att_rates_series) > 1 else 0.0
        else:
            if impute_missing:
                attendance_rate = benchmark_att_rate
                att_std = 0.15
                audit_disclosures["imputed_fields"].append({
                    "club_name": club_name,
                    "field": "attendance_rate",
                    "substituted_value": round(benchmark_att_rate, 4)
                })
            else:
                attendance_rate = None
                att_std = 0.0

        # 3. Consistency Metric:
        # 50% execution rate (actual vs planned events) + 50% attendance stability (1 - std dev)
        execution_rate = min(1.0, float(total_events / planned_events)) if planned_events > 0 else 1.0
        # Attendance stability: higher when variance is lower (capped between 0.0 and 1.0)
        attendance_stability = max(0.0, 1.0 - (att_std * 2.0))
        consistency_score = round(0.5 * execution_rate + 0.5 * attendance_stability, 4)

        # 4. Engagement Quality & Feedback Handling (FR7)
        fb_group = group[group["has_feedback_data"]]
        events_with_fb = len(fb_group)
        missing_fb_events = group[~group["has_feedback_data"]]["event_id"].tolist()

        if events_with_fb > 0:
            # Average rating across feedback responses for the club
            avg_feedback = float(fb_group["avg_feedback_rating"].mean())
        else:
            if impute_missing:
                avg_feedback = benchmark_fb_rating
                audit_disclosures["imputed_fields"].append({
                    "club_name": club_name,
                    "field": "engagement_quality",
                    "substituted_value": round(benchmark_fb_rating, 2)
                })
            else:
                avg_feedback = None

        # 5. Activity Volume
        activity_volume = total_events

        # 6. Missing Data Audit Flags
        is_partial = (events_with_att < total_events) or (events_with_fb < total_events)
        majority_missing = (events_with_att <= total_events / 2) or (events_with_fb <= total_events / 2)
        
        status_label = "Complete Data"
        if majority_missing:
            status_label = f"Significant Gaps ({events_with_att}/{total_events} att, {events_with_fb}/{total_events} fb)"
        elif is_partial:
            status_label = f"Partial Data ({events_with_att}/{total_events} att, {events_with_fb}/{total_events} fb)"

        if is_partial:
            audit_disclosures["clubs_with_partial_data"].append({
                "club_name": club_name,
                "total_events": total_events,
                "events_with_attendance": events_with_att,
                "events_with_feedback": events_with_fb,
                "missing_attendance_events": missing_att_events,
                "missing_feedback_events": missing_fb_events
            })

        for m_att in missing_att_events:
            audit_disclosures["missing_attendance_events"].append({"event_id": m_att, "club_name": club_name})
        for m_fb in missing_fb_events:
            audit_disclosures["missing_feedback_events"].append({"event_id": m_fb, "club_name": club_name})

        club_records.append({
            "club_name": club_name,
            "faculty_lead": faculty_lead,
            "activity_volume": activity_volume,
            "planned_events": planned_events,
            "events_with_attendance": events_with_att,
            "events_with_feedback": events_with_fb,
            "reach": total_reach,
            "avg_registrations_per_event": avg_regs_per_event,
            "attendance_rate": round(attendance_rate, 4) if attendance_rate is not None else None,
            "attendance_rate_pct": round(attendance_rate * 100, 2) if attendance_rate is not None else None,
            "attendance_std": round(att_std, 4),
            "consistency_raw": consistency_score,
            "engagement_quality": round(avg_feedback, 2) if avg_feedback is not None else None,
            "is_partial_data": is_partial,
            "majority_missing": majority_missing,
            "data_status": status_label,
            "missing_attendance_events": missing_att_events,
            "missing_feedback_events": missing_fb_events
        })

    audit_disclosures["imputation_applied"] = len(audit_disclosures["imputed_fields"]) > 0
    missing_att_ids = {item["event_id"] for item in audit_disclosures["missing_attendance_events"]}
    missing_fb_ids = {item["event_id"] for item in audit_disclosures["missing_feedback_events"]}
    audit_disclosures["excluded_event_count"] = len(missing_att_ids | missing_fb_ids)

    metrics_df = pd.DataFrame(club_records)
    return metrics_df, audit_disclosures
