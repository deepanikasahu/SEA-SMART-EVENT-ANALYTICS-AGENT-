"""
Synthetic Data Generation Script for Smart Event Analytics Agent
Generates an SQLite database (data/sea_agent.db) with enforced referential integrity,
realistic distributions, parameterized seeds, and deliberate data gaps for testing.
"""

import argparse
import datetime
import os
import random
import sqlite3
from typing import List, Dict, Any
from faker import Faker
import numpy as np


def create_schema(conn: sqlite3.Connection):
    """Create relational database schema with enforced foreign key constraints."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Drop existing tables in reverse dependency order
    cursor.execute("DROP TABLE IF EXISTS feedback;")
    cursor.execute("DROP TABLE IF EXISTS attendance;")
    cursor.execute("DROP TABLE IF EXISTS registrations;")
    cursor.execute("DROP TABLE IF EXISTS events;")
    cursor.execute("DROP TABLE IF EXISTS club_plans;")
    
    # 1. Club Plans (planned events and metadata)
    cursor.execute("""
    CREATE TABLE club_plans (
        club_name TEXT PRIMARY KEY,
        planned_events INTEGER NOT NULL,
        faculty_lead TEXT NOT NULL,
        founded_year INTEGER NOT NULL
    );
    """)
    
    # 2. Events Table
    cursor.execute("""
    CREATE TABLE events (
        event_id TEXT PRIMARY KEY,
        event_name TEXT NOT NULL,
        club_name TEXT NOT NULL,
        date TEXT NOT NULL,
        category TEXT NOT NULL,
        capacity INTEGER NOT NULL,
        FOREIGN KEY (club_name) REFERENCES club_plans(club_name) ON DELETE CASCADE
    );
    """)
    
    # 3. Registrations Table
    cursor.execute("""
    CREATE TABLE registrations (
        registration_id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        registered_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
    );
    """)
    
    # 4. Attendance Table
    cursor.execute("""
    CREATE TABLE attendance (
        event_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        attended INTEGER NOT NULL CHECK (attended IN (0, 1)),
        check_in_time TEXT,
        PRIMARY KEY (event_id, student_id),
        FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
    );
    """)
    
    # 5. Feedback Table
    cursor.execute("""
    CREATE TABLE feedback (
        feedback_id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        student_id TEXT NOT NULL,
        rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
        comment TEXT,
        submitted_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
    );
    """)
    
    conn.commit()


def generate_data(
    db_path: str = "data/sea_agent.db",
    seed: int = 42,
    num_clubs: int = 6,
    events_per_club_min: int = 3,
    events_per_club_max: int = 6,
    semester_start: str = "2024-01-15",
    semester_end: str = "2024-05-30"
) -> Dict[str, Any]:
    """Generate synthetic database with deterministic distributions and deliberate omissions."""
    random.seed(seed)
    np.random.seed(seed)
    Faker.seed(seed)
    fake = Faker()

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    # If DB exists, remove it to start clean
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    create_schema(conn)
    cursor = conn.cursor()

    # Parse semester date bounds
    start_dt = datetime.datetime.strptime(semester_start, "%Y-%m-%d").date()
    end_dt = datetime.datetime.strptime(semester_end, "%Y-%m-%d").date()
    total_days = (end_dt - start_dt).days

    # Curated club domains & names to feel authentic
    club_templates = [
        ("ACM Student Chapter", "Prof. Robert Vance"),
        ("AI & Machine Learning Club", "Dr. Elena Rostova"),
        ("Google Developer Student Club", "Prof. Kevin Patel"),
        ("CyberSecurity & Ethical Hacking Guild", "Dr. Marcus Thorne"),
        ("Web Development & Cloud Society", "Prof. Sarah Jenkins"),
        ("Robotics & IoT Innovation Lab", "Dr. Anil Sharma"),
        ("Competitive Coding Cell", "Prof. Maya Lin"),
        ("Open Source & Linux Users Group", "Dr. David Becker"),
    ]
    selected_clubs = club_templates[:num_clubs]

    # Technical and cultural event topic generators
    tech_topics = [
        "Hackathon", "Hands-on Workshop", "Bootcamp", "Paper Presentation",
        "Code Sprint", "Deep Dive Seminar", "Capture The Flag (CTF)", "Tech Talk",
        "Kaggle Challenge Prep", "Cloud Architecture Clinic", "Open Source Sprint"
    ]
    tech_domains = [
        "LLMs & Generative AI", "Rust & Systems Programming", "Kubernetes & DevOps",
        "Applied Cryptography", "Computer Vision with PyTorch", "React & Next.js",
        "Smart Contracts & Web3", "Autonomous Navigation & ROS", "Quantum Algorithms"
    ]
    cultural_events = [
        ("Annual Cultural Jam Night", "Cultural"),
        ("Spring Unplugged Acoustic Fest", "Cultural"),
        ("Street Theater Showcase", "Cultural"),
        ("Inter-College Dance Face-off", "Cultural")
    ]

    # Generate Student Population pool
    num_students = 350
    student_ids = [f"STU_{1000 + i:04d}" for i in range(num_students)]

    club_plans_data = []
    events_data = []
    registrations_data = []
    attendance_data = []
    feedback_data = []

    event_counter = 1
    reg_counter = 1
    fb_counter = 1

    feedback_comments_positive = [
        "Outstanding speaker and very clear live coding examples!",
        "Gained practical skills I can use for my resume project immediately.",
        "Well organized, high energy, and great Q&A session.",
        "The problem statements were challenging and engaging.",
        "Hands-on exercises helped cement the theory perfectly."
    ]
    feedback_comments_neutral = [
        "Good content, but ran slightly over the scheduled time.",
        "Solid presentation, though the introductory section felt a bit rushed.",
        "Useful material, would have appreciated more time for debugging exercises.",
        "Decent event, venue was a bit crowded."
    ]
    feedback_comments_critical = [
        "Pace was too fast for beginners; slides were hard to follow.",
        "Experienced technical difficulties with the projector and Wi-Fi.",
        "Prerequisites were not clearly communicated in advance."
    ]

    # Track missing data events explicitly for audit validation
    missing_attendance_events = []
    missing_feedback_events = []

    for club_name, faculty in selected_clubs:
        # Planned events: random between 4 and 6
        planned = random.randint(4, 6)
        founded = random.randint(2014, 2021)
        club_plans_data.append((club_name, planned, faculty, founded))

        # Actual events conducted: between events_per_club_min and events_per_club_max
        actual_count = random.randint(events_per_club_min, min(events_per_club_max, planned + 1))

        # Distinct dates for this club
        day_offsets = sorted(random.sample(range(5, total_days - 5), actual_count))

        for idx, offset in enumerate(day_offsets):
            event_id = f"EVT_{event_counter:03d}"
            event_date = (start_dt + datetime.timedelta(days=offset)).strftime("%Y-%m-%d")
            
            # Occasionally introduce a cultural event (e.g. ~10% chance) to test category filtering
            is_cultural = (random.random() < 0.12 and len(cultural_events) > 0)
            if is_cultural:
                cult_title, cat = cultural_events.pop(0)
                event_name = f"{club_name}: {cult_title}"
                category = "Cultural"
            else:
                topic = random.choice(tech_topics)
                domain = random.choice(tech_domains)
                event_name = f"{domain} {topic}"
                category = "Technical"

            capacity = random.choice([60, 80, 100, 120, 150])
            events_data.append((event_id, event_name, club_name, event_date, category, capacity))

            # Generate registrations (50% to 110% of capacity)
            reg_count = int(capacity * random.uniform(0.55, 1.10))
            registered_students = random.sample(student_ids, min(reg_count, len(student_ids)))

            for s_id in registered_students:
                reg_id = f"REG_{reg_counter:05d}"
                reg_dt = (start_dt + datetime.timedelta(days=max(0, offset - random.randint(2, 10)))).strftime("%Y-%m-%d %H:%M")
                registrations_data.append((reg_id, event_id, s_id, reg_dt))
                reg_counter += 1

            # Deliberate Missing Data Rules:
            # Event EVT_003 and EVT_008 have NO attendance records generated
            # Event EVT_005 has NO feedback records generated
            is_missing_attendance = (event_counter in [3, 8])
            is_missing_feedback = (event_counter in [5])

            if is_missing_attendance:
                missing_attendance_events.append(event_id)
            else:
                # Normal attendance generation
                # Base attendance rate varies by club reputation and event type
                base_turnout = random.uniform(0.58, 0.90)
                actual_attendees = []
                for s_id in registered_students:
                    attended = 1 if random.random() < base_turnout else 0
                    check_in = f"{event_date} {random.randint(14, 18)}:{random.randint(10, 59):02d}" if attended else None
                    attendance_data.append((event_id, s_id, attended, check_in))
                    if attended:
                        actual_attendees.append(s_id)

                # Feedback generation (only from actual attendees)
                if is_missing_feedback:
                    missing_feedback_events.append(event_id)
                elif actual_attendees:
                    # 30% to 75% response rate
                    feedback_ratio = random.uniform(0.35, 0.75)
                    respondents = random.sample(actual_attendees, max(1, int(len(actual_attendees) * feedback_ratio)))

                    # Club quality modifier for ratings
                    quality_bias = random.choice([0.7, 0.8, 0.85, 0.9, 0.95])
                    for s_id in respondents:
                        fb_id = f"FB_{fb_counter:05d}"
                        r_roll = random.random()
                        if r_roll < (0.15 * (1 - quality_bias)):
                            rating = random.choice([1, 2])
                            comment = random.choice(feedback_comments_critical)
                        elif r_roll < (0.45 * (1 - quality_bias) + 0.3):
                            rating = 3
                            comment = random.choice(feedback_comments_neutral)
                        else:
                            rating = random.choice([4, 5])
                            comment = random.choice(feedback_comments_positive)

                        fb_dt = f"{event_date} {random.randint(19, 23)}:{random.randint(10, 59):02d}"
                        feedback_data.append((fb_id, event_id, s_id, rating, comment, fb_dt))
                        fb_counter += 1

            event_counter += 1

    # Insert into SQLite
    cursor.executemany("INSERT INTO club_plans VALUES (?, ?, ?, ?);", club_plans_data)
    cursor.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?);", events_data)
    cursor.executemany("INSERT INTO registrations VALUES (?, ?, ?, ?);", registrations_data)
    cursor.executemany("INSERT INTO attendance VALUES (?, ?, ?, ?);", attendance_data)
    cursor.executemany("INSERT INTO feedback VALUES (?, ?, ?, ?, ?, ?);", feedback_data)

    conn.commit()
    conn.close()

    summary = {
        "db_path": db_path,
        "seed": seed,
        "clubs_count": len(club_plans_data),
        "events_count": len(events_data),
        "registrations_count": len(registrations_data),
        "attendance_rows_count": len(attendance_data),
        "feedback_rows_count": len(feedback_data),
        "missing_attendance_events": missing_attendance_events,
        "missing_feedback_events": missing_feedback_events
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic SQLite data for Smart Event Analytics Agent.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible generation")
    parser.add_argument("--db-path", type=str, default="data/sea_agent.db", help="Path to output SQLite database")
    parser.add_argument("--num-clubs", type=int, default=6, help="Number of clubs to generate (5-8)")
    parser.add_argument("--events-per-club-min", type=int, default=3, help="Min events per club")
    parser.add_argument("--events-per-club-max", type=int, default=5, help="Max events per club")
    parser.add_argument("--semester-start", type=str, default="2024-01-15", help="Semester start date (YYYY-MM-DD)")
    parser.add_argument("--semester-end", type=str, default="2024-05-30", help="Semester end date (YYYY-MM-DD)")

    args = parser.parse_args()
    summary = generate_data(
        db_path=args.db_path,
        seed=args.seed,
        num_clubs=args.num_clubs,
        events_per_club_min=args.events_per_club_min,
        events_per_club_max=args.events_per_club_max,
        semester_start=args.semester_start,
        semester_end=args.semester_end
    )

    print(f"=== Synthetic SQLite Database Generated Successfully ===")
    print(f"Database File: {summary['db_path']}")
    print(f"Seed: {summary['seed']}")
    print(f"Clubs: {summary['clubs_count']}")
    print(f"Total Events: {summary['events_count']}")
    print(f"Total Registrations: {summary['registrations_count']}")
    print(f"Attendance Rows: {summary['attendance_rows_count']}")
    print(f"Feedback Rows: {summary['feedback_rows_count']}")
    print(f"Events Intentionally Missing Attendance Data: {summary['missing_attendance_events']}")
    print(f"Events Intentionally Missing Feedback Data: {summary['missing_feedback_events']}")


if __name__ == "__main__":
    main()
