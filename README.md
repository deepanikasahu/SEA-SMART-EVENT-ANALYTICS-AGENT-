[README.md](https://github.com/user-attachments/files/35373182/README.md)
# SEA-SMART-EVENT-ANALYTICS-AGENT-
Evaluating college club performance through deterministic scoring and an explainable language-model layer
# 📊 Smart Event Analytics Agent (SEA Agent)
> **Autonomous AI Agent for College Student Club & Event Performance Evaluation**  
> Built for the *AI Agent Design Jury Exam* — Defensible line-by-line with zero framework abstractions.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Database](https://img.shields.io/badge/Database-SQLite3%20(Foreign%20Keys)-green.svg)](https://www.sqlite.org/)
[![LLM Provider](https://img.shields.io/badge/LLM-Groq%20%7C%20Gemini%20%7C%20OpenRouter%20%7C%20Mock-orange.svg)](#-llm-provider-swapping)
[![Tests](https://img.shields.io/badge/Tests-9%2F9%20Passed-brightgreen.svg)](#-automated-verification-suite)

---

## 🎯 1. Project Overview

Given a natural language request such as:
> *"Analyze all technical events conducted last semester and tell me which clubs performed the best."*

The **Smart Event Analytics Agent** autonomously:
1. **Understands Intent & Scope (FR1):** Parses time period, entity (`clubs`), and category (`Technical`). If no time period is provided, asks a clarifying question rather than guessing.
2. **Collects Data via Tool Calling (FR2):** Dynamically invokes tools (`get_events`, `get_registrations`, `get_attendance`, `get_feedback`, `get_club_plans`) querying a local SQLite database (`data/sea_agent.db`).
3. **Computes Deterministic Metrics (FR3):** Pure Python/pandas calculations for Reach, Attendance Rate, Variance, Engagement Quality, Consistency (Execution + Turnout Stability), and Volume. **The LLM never calculates, sorts, or aggregates numbers.**
4. **Performs Normalized Composite Ranking (FR4):** Loads inspectable weights from `weights_config.json` and ranks clubs on a transparent 0–100 scale.
5. **Generates Grounded Qualitative Insights (FR5/FR6):** The LLM receives **only** the pre-computed aggregate metrics JSON (zero student PII) to write an executive analysis.
6. **Validates Against Hallucinations (FR6):** A programmatic regex validator checks every number in the LLM's explanation against the source table.
7. **Discloses Missing Data Transparently (FR7):** Excludes missing attendance sheets and missing feedback from club averages instead of penalizing them as zero.
8. **Produces Multi-Format Audit Reports:** Outputs comprehensive Markdown (`.md`) and Microsoft Word (`.docx`) reports with full audit trails.

---

## 🏛️ 2. Architecture & Design Principles

```
User NL Request ("Analyze technical events from last semester...")
                    │
                    ▼
┌────────────────────────────────────────────────────────┐
│  Agent Orchestrator (orchestrator.py + llm_client.py)   │
│  - Native tool-calling loop (Groq/Gemini/OpenRouter)   │
│  - FR1: Request intent & date range parsing            │
│  - Clarification trigger if time period missing        │
│  - Executes tools: get_events, get_registrations, etc. │
└────────────────────────────────────────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────────────────────┐
│  Deterministic Data & Metrics Layer (Python / pandas)  │
│  - tools.py: File-backed loaders (data/sea_agent.db)   │
│  - metrics.py: Reach, Attendance Rate, Variance, Qual, │
│    Execution vs Planned (from club_plans table)        │
│  - ranking.py: Min-Max normalizer + weights_config.json│
│  - Output: Aggregated Metrics Table (JSON / dict)      │
└────────────────────────────────────────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────────────────────┐
│  Reasoning & Grounding Validation Layer (explain.py)   │
│  - LLM receives ONLY aggregate metrics JSON (no PII)   │
│  - Generates club strengths/weaknesses commentary      │
│  - Regex/AST number-grounding validator checks every   │
│    number in LLM text against the metrics table        │
└────────────────────────────────────────────────────────┘
                    │
                    ▼
┌────────────────────────────────────────────────────────┐
│  Report Generator (generate_report.py)                 │
│  - Jinja2 Template (Markdown / HTML) & python-docx     │
│  - Strict Aggregated Data only (zero student IDs)      │
│  - Transparent Missing-Data Disclosures & Audit Trail  │
└────────────────────────────────────────────────────────┘
```

---

## 🎓 3. Viva Defense Guide (Jury Questions & Answers)

### Q1: What makes this an "Agent" rather than a regular Python script?
> **Answer:** A script executes a hardcoded, predetermined sequence of operations. In contrast, this agent:
> 1. Accepts open-ended natural language requests.
> 2. Dynamically decides **which tools to call and with what parameters** based on query context.
> 3. Implements **goal-directed error recovery & clarification**: if the user omits a time period, the agent halts and requests clarification rather than crashing or guessing.
> 4. Inspects intermediate outputs across multi-turn reasoning loops.

### Q2: Why is metric computation strictly separated from the LLM?
> **Answer:** Large Language Models are probabilistic next-token predictors prone to arithmetic errors, floating-point drift, and hallucination. In our architecture:
> - **Arithmetic Reliability:** All statistical computations (sums, standard deviations, min-max normalizations, composite scores) are handled by pure Python/pandas functions with 100% mathematical determinism.
> - **Generative Reasoning:** The LLM is used exclusively where language capabilities shine — synthesizing natural language summaries, identifying qualitative performance tradeoffs, and contextualizing rankings.

### Q3: Where does the "Consistency" metric get its planned events baseline?
> **Answer:** In our relational database (`data/sea_agent.db`), the `club_plans` table stores semester targets (`planned_events`) submitted by club faculty leads. Consistency is calculated as:
> $$\text{Consistency} = 0.5 \times \min\left(1.0, \frac{\text{Actual Events Conducted}}{\text{Planned Events}}\right) + 0.5 \times (1.0 - 2 \times \text{Turnout StdDev})$$
> This rewards both commitment delivery (execution rate) and audience turnout stability (low attendance variance).

### Q4: How does the system handle missing or incomplete data (FR7)?
> **Answer:** 
> - If an event has no attendance records (e.g. `EVT_003`, `EVT_008`), it is excluded from the attendance rate calculation rather than being penalized as 0%.
> - If an event has zero feedback (e.g. `EVT_005`), it is excluded from the rating average.
> - The affected club is explicitly flagged in the leaderboard as `Partial Data (X/Y att, Z/Y fb)` and detailed in the audit disclosure section of the report.
> - An opt-in flag (`--impute-missing`) allows category-average substitution when explicitly requested.

### Q5: How do you guarantee student privacy (NFR)?
> **Answer:** **Privacy by Design**. Raw student IDs (`STU_xxxx`) and registration timestamps reside solely in the SQLite query layer. The LLM reasoning prompt and Jinja2 report templates strictly accept aggregated club metrics dictionaries, making PII leaks impossible by construction.

---

## 🗄️ 4. Database Schema & Inspection

The system uses a relational SQLite database (`data/sea_agent.db`) with foreign keys enabled:

```sql
PRAGMA foreign_keys = ON;

-- 1. Club targets
CREATE TABLE club_plans (
    club_name TEXT PRIMARY KEY,
    planned_events INTEGER NOT NULL,
    faculty_lead TEXT NOT NULL,
    founded_year INTEGER NOT NULL
);

-- 2. Events table
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    event_name TEXT NOT NULL,
    club_name TEXT NOT NULL,
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    FOREIGN KEY (club_name) REFERENCES club_plans(club_name)
);

-- 3. Registrations table
CREATE TABLE registrations (
    registration_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    FOREIGN KEY (event_id) REFERENCES events(event_id)
);

-- 4. Attendance table
CREATE TABLE attendance (
    event_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    attended INTEGER NOT NULL CHECK (attended IN (0, 1)),
    check_in_time TEXT,
    PRIMARY KEY (event_id, student_id),
    FOREIGN KEY (event_id) REFERENCES events(event_id)
);

-- 5. Feedback table
CREATE TABLE feedback (
    feedback_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    submitted_at TEXT NOT NULL,
    FOREIGN KEY (event_id) REFERENCES events(event_id)
);
```

> 💡 **Tip for Jury Demo:** Inspect the generated SQLite tables live using **DB Browser for SQLite** or the **VS Code SQLite Viewer** extension.

---

## ⚖️ 5. Scoring Weights Configuration (`weights_config.json`)

Scoring weights are completely transparent, inspectable, and editable without touching code or prompts:

```json
{
  "version": "1.0",
  "weights": {
    "engagement_quality": 0.35,
    "attendance_rate": 0.25,
    "consistency": 0.20,
    "reach": 0.15,
    "activity_volume": 0.05
  },
  "rationale": "Prioritizes student satisfaction and event quality (35%) and actual community turn-out (25%) combined with organizational reliability (20%) over raw registration reach (15%) and pure event quantity spam (5%)."
}
```

---

## 🔄 6. LLM Provider Swapping

The agent features a provider-agnostic adapter (`agent/llm_client.py`). You can switch providers by editing `.env` with zero code modifications:

### Option A: Groq (Default - High Speed Free Tier)
```env
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

### Option B: Google Gemini
```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash
```

### Option C: OpenRouter
```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free
```

### Option D: Deterministic Offline Mock (No API Key Required)
```env
LLM_PROVIDER=mock
```

---

## 🚀 7. Quickstart & Installation

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Configure Environment
Copy `.env.example` to `.env` and provide your API key:
```bash
cp .env.example .env
```

### Step 3: Generate Synthetic Database (Reproducible)
```bash
python data_generation/generate_dummy_data.py --seed 42
```
*Note: Using `--seed 42` guarantees identical data generation across multiple machines.*

### Step 4: Run the CLI Agent Pipeline
```bash
python main.py "Analyze all technical events conducted last semester and tell me which clubs performed the best."
```

### Step 5: (Optional) Launch the Interactive Streamlit Dashboard
```bash
streamlit run app.py
```

---

## 🧪 8. Automated Verification Suite

Run the full automated test suite covering all functional and security requirements:

```bash
python -m pytest tests/test_pipeline.py -v
```

### Test Coverage Summary:
- `test_seed_reproducibility` — Asserts bitwise identical database generation on repeated runs.
- `test_sqlite_foreign_key_enforcement` — Verifies database engine rejects orphaned foreign keys.
- `test_intentional_missing_data_generated` — Confirms `EVT_003`/`EVT_008` (attendance) and `EVT_005` (feedback) are absent.
- `test_deterministic_metrics_and_exclusions` — Asserts missing data is excluded from averages and flagged as partial data.
- `test_ranking_weights_and_normalization` — Verifies 0–100 min-max normalization and composite score calculation.
- `test_number_grounding_anti_hallucination_validator` — Tests detection of fabricated numerical figures.
- `test_privacy_enforcement_no_student_ids` — Guarantees zero student PII leaks in reports or prompts.
- `test_fr1_clarifying_question_on_missing_date` — Confirms agent asks for clarification if date is missing.
- `test_provider_swap_mock` — Proves zero code changes needed when swapping LLM providers.

---

## 📁 9. Repository Structure

```
smart-event-analytics-agent/
├── data_generation/
│   └── generate_dummy_data.py     # SQLite synthetic generator with deliberate gaps & seeds
├── data/
│   └── sea_agent.db               # SQLite database (generated at runtime, gitignored)
├── agent/
│   ├── llm_client.py              # Provider-agnostic adapter (Groq, Gemini, OpenRouter, Mock)
│   ├── tools.py                   # Parameterized SQL data collection tools & OpenAPI schemas
│   ├── metrics.py                 # Pure Python/pandas deterministic metrics & missing data logic
│   ├── ranking.py                 # Min-max normalization & weights_config.json loader
│   ├── explain.py                 # Grounded LLM reasoning & regex number validator
│   └── orchestrator.py            # Native tool-calling loop with clarification safeguard
├── report/
│   ├── templates/
│   │   └── report_template.md.j2  # Jinja2 template for Markdown report
│   └── generate_report.py         # Markdown and Word (.docx) report generators
├── tests/
│   └── test_pipeline.py           # 9 automated verification tests
├── weights_config.json            # Transparent scoring weights configuration
├── .env.example                   # Sanitized environment template
├── .gitignore                     # Gitignore protecting keys, SQLite DB, and reports
├── requirements.txt               # Dependencies
├── main.py                        # Terminal CLI entry point
├── app.py                         # Interactive Streamlit demo dashboard
└── README.md                      # Viva defense documentation & instructions
```
