"""
Unit tests for missing-data imputation branches in agent/metrics.py.
Uses isolated in-memory SQLite fixtures to verify behavior without mutating
the persistent database or depending on seed 42 dataset characteristics.
"""

import sqlite3
import pandas as pd
import pytest

from agent.metrics import compute_club_metrics


def _create_base_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE club_plans (
        club_name TEXT PRIMARY KEY,
        planned_events INTEGER NOT NULL,
        faculty_lead TEXT NOT NULL,
        founded_year INTEGER NOT NULL
    );
    """)
    cur.execute("""
    CREATE TABLE events (
        event_id TEXT PRIMARY KEY,
        event_name TEXT NOT NULL,
        club_name TEXT NOT NULL,
        date TEXT NOT NULL,
        category TEXT NOT NULL,
        capacity INTEGER NOT NULL
    );
    """)
    cur.execute("""
    CREATE TABLE registrations (
        registration_id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        registered_at TEXT NOT NULL
    );
    """)
    cur.execute("""
    CREATE TABLE attendance (
        event_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        attended INTEGER NOT NULL,
        check_in_time TEXT,
        PRIMARY KEY (event_id, student_id)
    );
    """)
    cur.execute("""
    CREATE TABLE feedback (
        feedback_id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        rating INTEGER NOT NULL,
        comments TEXT,
        submitted_at TEXT
    );
    """)


def test_zero_data_club_substitution():
    """
    Assert that when a club has zero attendance and zero feedback rows:
    - impute_missing=False yields NaN for attendance_rate and engagement_quality
    - impute_missing=True substitutes dataset benchmark values
    """
    conn = sqlite3.connect(":memory:")
    _create_base_schema(conn)
    cur = conn.cursor()

    # Alpha Club: Complete data to establish benchmark averages
    cur.execute("INSERT INTO club_plans VALUES ('Alpha Club', 1, 'Dr. Alpha', 2020);")
    cur.execute("INSERT INTO events VALUES ('EVT_1', 'Event Alpha', 'Alpha Club', '2024-02-01', 'Technical', 100);")
    cur.execute("INSERT INTO registrations VALUES ('REG_1', 'EVT_1', 'STU_1', '2024-01-20');")
    cur.execute("INSERT INTO attendance VALUES ('EVT_1', 'STU_1', 1, '2024-02-01 10:00');")
    cur.execute("INSERT INTO feedback VALUES ('FB_1', 'EVT_1', 'STU_1', 5, 'Great', '2024-02-01 12:00');")

    # Zero Data Club: 1 event, 1 registration, 0 attendance rows, 0 feedback rows
    cur.execute("INSERT INTO club_plans VALUES ('Zero Data Club', 1, 'Dr. Zero', 2021);")
    cur.execute("INSERT INTO events VALUES ('EVT_2', 'Event Zero', 'Zero Data Club', '2024-03-01', 'Technical', 100);")
    cur.execute("INSERT INTO registrations VALUES ('REG_2', 'EVT_2', 'STU_2', '2024-02-20');")
    conn.commit()

    df_events = pd.read_sql_query("SELECT * FROM events", conn)
    df_regs = pd.read_sql_query("SELECT * FROM registrations", conn)
    df_att = pd.read_sql_query("SELECT * FROM attendance", conn)
    df_fb = pd.read_sql_query("SELECT * FROM feedback", conn)
    df_plans = pd.read_sql_query("SELECT * FROM club_plans", conn)
    conn.close()

    # 1. impute_missing=False: Zero Data Club must have NaN metrics
    metrics_off, audit_off = compute_club_metrics(
        df_events, df_regs, df_att, df_fb, df_plans, impute_missing=False
    )
    zero_club_off = metrics_off[metrics_off["club_name"] == "Zero Data Club"].iloc[0]
    assert pd.isna(zero_club_off["attendance_rate"])
    assert pd.isna(zero_club_off["engagement_quality"])
    assert audit_off["imputation_applied"] is False
    assert audit_off["excluded_event_count"] == 1

    # 2. impute_missing=True: Zero Data Club must receive dataset benchmark values
    metrics_on, audit_on = compute_club_metrics(
        df_events, df_regs, df_att, df_fb, df_plans, impute_missing=True
    )
    zero_club_on = metrics_on[metrics_on["club_name"] == "Zero Data Club"].iloc[0]
    assert zero_club_on["attendance_rate"] == audit_on["benchmark_attendance_rate"]
    assert zero_club_on["engagement_quality"] == audit_on["benchmark_feedback_rating"]
    assert audit_on["imputation_applied"] is True


def test_imputation_applied_false_when_nothing_substituted():
    """
    When every club has complete attendance and feedback data, no values are substituted.
    imputation_applied must be False, and imputed_fields must be empty, even if impute_missing=True.
    """
    conn = sqlite3.connect(":memory:")
    _create_base_schema(conn)
    cur = conn.cursor()

    # Alpha Club: 100% complete data
    cur.execute("INSERT INTO club_plans VALUES ('Alpha Club', 1, 'Dr. Alpha', 2020);")
    cur.execute("INSERT INTO events VALUES ('EVT_1', 'Event Alpha', 'Alpha Club', '2024-02-01', 'Technical', 100);")
    cur.execute("INSERT INTO registrations VALUES ('REG_1', 'EVT_1', 'STU_1', '2024-01-20');")
    cur.execute("INSERT INTO attendance VALUES ('EVT_1', 'STU_1', 1, '2024-02-01 10:00');")
    cur.execute("INSERT INTO feedback VALUES ('FB_1', 'EVT_1', 'STU_1', 5, 'Great', '2024-02-01 12:00');")
    conn.commit()

    df_events = pd.read_sql_query("SELECT * FROM events", conn)
    df_regs = pd.read_sql_query("SELECT * FROM registrations", conn)
    df_att = pd.read_sql_query("SELECT * FROM attendance", conn)
    df_fb = pd.read_sql_query("SELECT * FROM feedback", conn)
    df_plans = pd.read_sql_query("SELECT * FROM club_plans", conn)
    conn.close()

    metrics_df, audit_disclosures = compute_club_metrics(
        df_events, df_regs, df_att, df_fb, df_plans, impute_missing=True
    )

    # When zero values were substituted, imputation_applied must be False and imputed_fields empty
    assert audit_disclosures["imputation_applied"] is False
    assert audit_disclosures.get("imputed_fields", []) == []
    assert audit_disclosures["excluded_event_count"] == 0


def test_imputed_fields_tags_zero_data_club():
    """
    Verify that audit_disclosures['imputed_fields'] explicitly records the club, field,
    and substituted value for both attendance_rate and engagement_quality.
    """
    conn = sqlite3.connect(":memory:")
    _create_base_schema(conn)
    cur = conn.cursor()

    # Alpha Club: complete data establishes benchmarks (att=1.0, rating=4.5)
    cur.execute("INSERT INTO club_plans VALUES ('Alpha Club', 1, 'Dr. Alpha', 2020);")
    cur.execute("INSERT INTO events VALUES ('EVT_1', 'Event Alpha', 'Alpha Club', '2024-02-01', 'Technical', 100);")
    cur.execute("INSERT INTO registrations VALUES ('REG_1', 'EVT_1', 'STU_1', '2024-01-20');")
    cur.execute("INSERT INTO attendance VALUES ('EVT_1', 'STU_1', 1, '2024-02-01 10:00');")
    cur.execute("INSERT INTO feedback VALUES ('FB_1', 'EVT_1', 'STU_1', 4.5, 'Good', '2024-02-01 12:00');")

    # Zero Data Club: missing both attendance and feedback
    cur.execute("INSERT INTO club_plans VALUES ('Zero Data Club', 1, 'Dr. Zero', 2021);")
    cur.execute("INSERT INTO events VALUES ('EVT_2', 'Event Zero', 'Zero Data Club', '2024-03-01', 'Technical', 100);")
    cur.execute("INSERT INTO registrations VALUES ('REG_2', 'EVT_2', 'STU_2', '2024-02-20');")
    conn.commit()

    df_events = pd.read_sql_query("SELECT * FROM events", conn)
    df_regs = pd.read_sql_query("SELECT * FROM registrations", conn)
    df_att = pd.read_sql_query("SELECT * FROM attendance", conn)
    df_fb = pd.read_sql_query("SELECT * FROM feedback", conn)
    df_plans = pd.read_sql_query("SELECT * FROM club_plans", conn)
    conn.close()

    metrics_df, audit_disclosures = compute_club_metrics(
        df_events, df_regs, df_att, df_fb, df_plans, impute_missing=True
    )

    assert audit_disclosures["imputation_applied"] is True
    imputed_fields = audit_disclosures["imputed_fields"]
    assert len(imputed_fields) == 2

    # Check attendance_rate substitution entry
    att_entry = next((e for e in imputed_fields if e["field"] == "attendance_rate"), None)
    assert att_entry is not None
    assert att_entry["club_name"] == "Zero Data Club"
    assert att_entry["substituted_value"] == audit_disclosures["benchmark_attendance_rate"]

    # Check engagement_quality substitution entry
    fb_entry = next((e for e in imputed_fields if e["field"] == "engagement_quality"), None)
    assert fb_entry is not None
    assert fb_entry["club_name"] == "Zero Data Club"
    assert fb_entry["substituted_value"] == audit_disclosures["benchmark_feedback_rating"]
