"""
Script to generate the comprehensive Word Document (.docx)
'SEA_Agent_Complete_Code_Architecture_Guide.docx'
covering all files, frameworks, libraries, pipelines, and mathematical logic in simple words.
"""

import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_hex):
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=120, bottom=120, left=150, right=150):
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def add_heading_styled(doc, text, level):
    h = doc.add_heading(text, level=level)
    h.paragraph_format.space_before = Pt(14)
    h.paragraph_format.space_after = Pt(6)
    for r in h.runs:
        r.font.name = 'Calibri'
        if level == 1:
            r.font.size = Pt(20)
            r.font.bold = True
            r.font.color.rgb = RGBColor(15, 76, 129) # Classic Blue
        elif level == 2:
            r.font.size = Pt(15)
            r.font.bold = True
            r.font.color.rgb = RGBColor(2, 132, 199) # Sky Blue
        elif level == 3:
            r.font.size = Pt(12)
            r.font.bold = True
            r.font.color.rgb = RGBColor(30, 41, 59) # Slate Dark
    return h

def create_guide_docx(output_path="SEA_Agent_Complete_Code_Architecture_Guide.docx"):
    doc = Document()

    # Set page margins
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    # ── Document Title ──
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(4)
    r_title = title_p.add_run("Smart Event Analytics Agent (SEA Agent)")
    r_title.font.name = 'Calibri'
    r_title.font.size = Pt(26)
    r_title.font.bold = True
    r_title.font.color.rgb = RGBColor(15, 76, 129)

    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_after = Pt(14)
    r_sub = sub_p.add_run("Complete Codebase Reference, File Directory, Frameworks & Simple Architectural Guide")
    r_sub.font.name = 'Calibri'
    r_sub.font.size = Pt(14)
    r_sub.font.italic = True
    r_sub.font.color.rgb = RGBColor(71, 85, 105)

    # Callout Box: Executive Overview
    callout_tbl = doc.add_table(rows=1, cols=1)
    callout_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = callout_tbl.cell(0, 0)
    set_cell_background(c, "F0F9FF")
    set_cell_margins(c, 160, 160, 200, 200)
    p_box = c.paragraphs[0]
    p_box.paragraph_format.space_after = Pt(0)
    r_b1 = p_box.add_run("📌 What is this Document?\n")
    r_b1.bold = True
    r_b1.font.color.rgb = RGBColor(2, 132, 199)
    r_b2 = p_box.add_run(
        "This guide provides a comprehensive, beginner-friendly yet technically thorough breakdown of every single file, "
        "library, framework, and mathematical algorithm across the SEA Agent repository (both v1 baseline and v2 modular pipeline). "
        "It explains the purpose of each component in simple, intuitive words for presentations, documentation, and technical jury defense."
    )
    r_b2.font.size = Pt(10.5)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # ══════════════════════════════════════════════════════════════════════════════
    # SECTION 1: MASTER LIST OF FRAMEWORKS & LIBRARIES
    # ══════════════════════════════════════════════════════════════════════════════
    add_heading_styled(doc, "1. Master List of Frameworks, Libraries & Technologies", level=1)
    p = doc.add_paragraph(
        "The project is built on Python 3.11 with a zero-black-box philosophy. "
        "Every external library was deliberately chosen for speed, auditability, and mathematical precision."
    )
    p.paragraph_format.space_after = Pt(8)

    frameworks = [
        ("FastAPI (>=0.111.0)", "Web / REST API Framework", "Powers the v2 REST API server. Exposes fast HTTP endpoints (/analyze-events, /explain-club, /health) with automatic Swagger/OpenAPI interactive documentation."),
        ("Uvicorn (>=0.29.0)", "ASGI Web Server", "The high-performance asynchronous web server that runs the FastAPI backend on localhost port 8001."),
        ("Pydantic v2 (>=2.0.0)", "Data Validation & Schema Modeling", "Guarantees strict type safety for every record ingested from the database. Rejects corrupted rows and converts missing values (NaNs) cleanly before math calculations."),
        ("Streamlit (>=1.62.0)", "Interactive Web UI", "Provides the front-end dashboard with light/dark pastel themes, natural language query inputs, interactive leaderboards, and audit verification expanders on port 8501."),
        ("Pandas (>=2.0.0)", "Deterministic Data Engine", "Performs all mathematical aggregations, turnout calculations, standard deviations, and min-max normalization in pure Python arithmetic—completely zero LLM math hallucinations."),
        ("NumPy (>=1.24.0)", "Numerical Computing", "Provides fast statistical calculations (standard deviations, min/max bounds, array handling) used in consistency and turnout variance formulas."),
        ("SQLite3 (Built-in)", "Relational Embedded Database", "Lightweight, zero-config relational database engine enforcing relational integrity with foreign keys (PRAGMA foreign_keys = ON). Operates via isolated database files."),
        ("Groq SDK (>=0.9.0)", "Ultra-Fast LLM Inference", "Cloud client for executing ultra-fast open-source LLM models (e.g. OpenAI GPT-OSS 120B / Llama 3.3 70B) with native function/tool calling support."),
        ("Anthropic SDK (>=0.30.0)", "Claude LLM Adapter", "Official Python client for Claude 3.5 Sonnet, providing advanced qualitative reasoning and natural language synthesis in v2."),
        ("Plotly (>=5.22.0)", "Interactive Data Visualizations", "Generates publication-quality horizontal bar charts with data-status color badges and multi-dimensional radar/spider charts comparing club profiles."),
        ("PyYAML (>=6.0)", "YAML Configuration Parser", "Loads human-readable scoring weights, tie-breaking rules, and runtime settings from rubric.yaml and v2_config.yaml without touching Python code."),
        ("Python-Docx (>=0.8.11)", "Word Document Exporter", "Programmatically generates formatted Microsoft Word (.docx) performance and audit reports directly to disk."),
        ("Faker (>=24.0.0)", "Synthetic Data Generator", "Generates realistic student names, club descriptions, event categories, and feedback comments for reproducible database seeding."),
        ("Pytest (>=8.0.0)", "Automated Testing Framework", "Executes the 70-test verification suite covering unit math, schema contracts, integration pipelines, explainability grounding, and API smoke tests.")
    ]

    tbl_f = doc.add_table(rows=1, cols=3)
    tbl_f.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = tbl_f.rows[0].cells
    hdr[0].text = "Library / Framework"
    hdr[1].text = "Category / Role"
    hdr[2].text = "Simple Explanation & Why We Use It"
    for cell in hdr:
        set_cell_background(cell, "0F4C81")
        set_cell_margins(cell, 100, 100, 120, 120)
        for cp in cell.paragraphs:
            for run in cp.runs:
                run.font.color.rgb = RGBColor(255, 255, 255)
                run.font.bold = True
                run.font.size = Pt(10)

    for name, cat, desc in frameworks:
        row = tbl_f.add_row().cells
        row[0].text = name
        row[1].text = cat
        row[2].text = desc
        for i, cell in enumerate(row):
            set_cell_background(cell, "F8FAFC" if len(tbl_f.rows) % 2 == 0 else "FFFFFF")
            set_cell_margins(cell, 80, 80, 100, 100)
            for cp in cell.paragraphs:
                for run in cp.runs:
                    run.font.size = Pt(9.5)
                    if i == 0:
                        run.font.bold = True

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # ══════════════════════════════════════════════════════════════════════════════
    # SECTION 2: COMPLETE FILE-BY-FILE BREAKDOWN
    # ══════════════════════════════════════════════════════════════════════════════
    add_heading_styled(doc, "2. Complete File-by-File Directory & Explanation", level=1)
    p = doc.add_paragraph(
        "Below is every single file across the entire repository. "
        "The project is partitioned into two distinct systems: the original v1 baseline and the upgraded v2 modular pipeline, "
        "alongside the comparison test harness."
    )
    p.paragraph_format.space_after = Pt(8)

    # Sub-section: Root Files
    add_heading_styled(doc, "A. Root Level Files (v1 Entry Points & Utilities)", level=2)
    root_files = [
        ("app.py", "Streamlit Dashboard Frontend", "The main web user interface. Implements the pastel light/dark theme toggle, real-time KPI metrics cards, interactive leaderboard table, natural language query input box, preset test buttons, and live SQLite database inspector."),
        ("main.py", "CLI Terminal Entry Point", "Command-line interface for running event analytics directly from the terminal without launching a web browser. Supports arguments like --query, --provider, and --impute-missing."),
        ("weights_config.json", "v1 Scoring Weights Configuration", "JSON configuration storing the v1 scoring formula weights (Engagement 35%, Attendance 25%, Consistency 20%, Reach 15%, Volume 5%) and the mathematical rationale."),
        ("generate_jury_ppt.py", "PowerPoint Deck Generator", "Automated python-pptx script that builds the 10-slide dark tech-themed PowerPoint presentation (SEA_Agent_v2_Jury_Presentation.pptx) complete with speaker notes for jury defense."),
        (".env / .env.example", "Environment Variables & API Keys", "Stores sensitive API keys (GROQ_API_KEY, ANTHROPIC_API_KEY, database paths). .env is git-ignored for security; .env.example provides the documented template."),
        (".gitignore", "Version Control Ignore Rules", "Prevents committing virtual environments (.venv), API keys (.env), temporary cache files, generated databases, and test reports into Git.")
    ]
    for fn, role, expl in root_files:
        p = doc.add_paragraph()
        r1 = p.add_run(f"📄 {fn} — ")
        r1.bold = True
        r1.font.color.rgb = RGBColor(2, 132, 199)
        r2 = p.add_run(f"[{role}]\n")
        r2.bold = True
        r2.font.color.rgb = RGBColor(71, 85, 105)
        r3 = p.add_run(expl)
        r3.font.size = Pt(10)
        p.paragraph_format.space_after = Pt(4)

    # Sub-section: v1 Agent Core Files
    add_heading_styled(doc, "B. v1 Core Agent Directory (`agent/`)", level=2)
    v1_agent_files = [
        ("agent/orchestrator.py", "v1 Agent Loop Orchestrator", "Contains the EventAnalyticsAgent class. Runs a 5-iteration while-loop calling the LLM with native function tools, coordinates query parsing, metric calculations, and audit generation."),
        ("agent/tools.py", "v1 SQLite Database Tools", "Defines the 5 deterministic query functions (get_events, get_registrations, get_attendance, get_feedback, get_club_plans) that query sea_agent.db via parameterized SQL."),
        ("agent/metrics.py", "v1 Deterministic Metrics Engine", "Pure pandas statistical aggregation calculating unique student Reach, Turnout %, Feedback Ratings, and Turnout Stability Standard Deviation."),
        ("agent/ranking.py", "v1 Normalization & Composite Scoring", "Applies min-max normalization to scale raw metrics to a 0–100 range and computes the weighted composite score based on weights_config.json."),
        ("agent/explain.py", "v1 Grounded Report & Regex Auditor", "Prompts the LLM to write qualitative performance summaries using ONLY pre-computed JSON metrics, then runs a regex AST scanner to verify all numbers."),
        ("agent/llm_client.py", "v1 Multi-Provider LLM Client", "Provider-agnostic adapter class supporting Groq, Gemini, OpenRouter, and offline Mock LLM execution with unified function-calling schemas.")
    ]
    for fn, role, expl in v1_agent_files:
        p = doc.add_paragraph()
        r1 = p.add_run(f"📄 {fn} — ")
        r1.bold = True
        r1.font.color.rgb = RGBColor(2, 132, 199)
        r2 = p.add_run(f"[{role}]\n")
        r2.bold = True
        r2.font.color.rgb = RGBColor(71, 85, 105)
        r3 = p.add_run(expl)
        r3.font.size = Pt(10)
        p.paragraph_format.space_after = Pt(4)

    # Sub-section: v2 Upgraded Directory
    add_heading_styled(doc, "C. v2 Modular Pipeline Directory (`event-analytics-v2/`)", level=2)
    v2_files = [
        ("config/rubric.yaml", "v2 Scoring Rubric & Tie-Break Policy", "YAML file defining the 5 scoring weights and the explicit 3-level tie-break hierarchy (Engagement Quality -> Attendance Rate -> Completeness Score). Editable without changing Python code."),
        ("config/v2_config.yaml", "v2 Runtime Settings", "Configures runtime parameters including database path (sea_agent_v2.db), default LLM provider (Claude/Groq/Mock), API host/port, and chart dimensions."),
        ("models/schemas.py", "Pydantic v2 Ingestion Schemas", "Defines strict data models for ClubPlanRecord, EventRecord, RegistrationRecord, AttendanceRecord, FeedbackRecord, and ParsedQueryParams. Rejects bad data and converts NaNs safely."),
        ("engine/metrics.py", "v2 Deterministic Metrics Engine", "Computes Reach, Turnout %, Feedback Quality, Consistency, and newly adds completeness_score and confidence_score to measure data quality mathematically."),
        ("engine/ranking.py", "v2 Deterministic Ranking Engine", "Applies min-max normalization (with division-by-zero protection for single-club edge cases) and executes the strict 3-tier tie-breaking protocol."),
        ("engine/sensitivity.py", "Rubric Sensitivity Analysis Tool", "Standalone experiment script that tests how the leaderboard shifts under 4 different policy configurations (Baseline, Feedback-Heavy, Turnout-Heavy, Scale-Heavy)."),
        ("llm/adapter.py", "v2 Swappable LLM Adapter & Telemetry", "Provides BaseLLMAdapter with implementations for Claude 3.5 Sonnet, Groq Llama-3.3, and offline Mock. Features built-in UsageTracker capturing token usage, latency, and estimated cost per request."),
        ("pipeline/state.py", "Pipeline State TypedDict", "Defines the immutable AgentState TypedDict passed between graph nodes, holding query params, dataframes, validation errors, and audit logs."),
        ("pipeline/query_parser.py", "Query Understanding Node (Stage 1)", "Translates conversational natural language into structured parameters using LLM function calling. Halts for clarification if temporal bounds are missing."),
        ("pipeline/validator.py", "Data Ingestion & Validation Node (Stage 2)", "Queries the isolated SQLite DB (sea_agent_v2.db) and validates all rows against Pydantic models with automated NaN sanitization."),
        ("pipeline/explain.py", "Grounded Explainability Node", "Dedicated endpoint logic answering 'Why did Club X rank at its position?' by feeding only that club's JSON data to the LLM and auditing numeric citations."),
        ("pipeline/graph.py", "6-Stage Pipeline State Machine", "The central coordinator wiring Query Understanding -> Ingestion -> Data Quality -> Metrics -> Ranking -> Report Generation into a clean, deterministic directed graph."),
        ("reporting/report_generator.py", "Grounded Narrative Generator (Stage 6)", "Prompts the LLM to write qualitative summaries strictly from pre-computed metrics and runs the anti-hallucination regex audit."),
        ("reporting/charts.py", "Plotly Visualization Engine", "Generates publication-quality horizontal composite score bar charts with data-status color badges and multi-axis radar/spider performance charts."),
        ("api/server.py", "FastAPI Production REST Server", "Exposes POST /analyze-events, GET /explain-club/{name}, and GET /health with auto-generated Swagger documentation at http://127.0.0.1:8001/docs.")
    ]
    for fn, role, expl in v2_files:
        p = doc.add_paragraph()
        r1 = p.add_run(f"📄 event-analytics-v2/{fn} — ")
        r1.bold = True
        r1.font.color.rgb = RGBColor(124, 58, 237) # Purple
        r2 = p.add_run(f"[{role}]\n")
        r2.bold = True
        r2.font.color.rgb = RGBColor(71, 85, 105)
        r3 = p.add_run(expl)
        r3.font.size = Pt(10)
        p.paragraph_format.space_after = Pt(4)

    # Sub-section: Comparison Directory
    add_heading_styled(doc, "D. A/B Comparison Harness (`comparison/`)", level=2)
    comp_files = [
        ("comparison/run_comparison.py", "A/B Comparison Runner", "Runs v1 and v2 side-by-side on identical queries across 3 data scenarios (Clean, Missing Attendance, Missing Feedback). Measures agreement, latency, token usage, and generates diff reports."),
        ("comparison/reports/comparison_summary.md", "Generated Comparison Report", "Markdown report documenting live benchmark results, ranking diffs, cost breakdowns, and deep metric explanations for any #1 disagreements.")
    ]
    for fn, role, expl in comp_files:
        p = doc.add_paragraph()
        r1 = p.add_run(f"📄 {fn} — ")
        r1.bold = True
        r1.font.color.rgb = RGBColor(0, 168, 150) # Teal
        r2 = p.add_run(f"[{role}]\n")
        r2.bold = True
        r2.font.color.rgb = RGBColor(71, 85, 105)
        r3 = p.add_run(expl)
        r3.font.size = Pt(10)
        p.paragraph_format.space_after = Pt(4)

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # ══════════════════════════════════════════════════════════════════════════════
    # SECTION 3: MATHEMATICAL FORMULAS EXPLAINED SIMPLY
    # ══════════════════════════════════════════════════════════════════════════════
    add_heading_styled(doc, "3. Core Mathematical Formulas Explained in Plain English", level=1)

    formulas = [
        ("1. Attendance Turnout Rate (%)",
         "Attendance Rate = (Total Students Attended / Total Registered Students) * 100",
         "Measures student commitment. If 80 out of 100 registered students attend, the turnout is 80.0%. Missing events are excluded from the average rather than falsely penalizing the club with 0%."),

        ("2. Consistency Metric (0.0 to 1.0)",
         "Consistency = 0.5 * min(1.0, Conducted / Planned) + 0.5 * max(0.0, 1.0 - 2 * Turnout_StdDev)",
         "Balances delivery against stability. The first half rewards clubs for delivering all events promised in their baseline plan. The second half rewards clubs whose attendance is steady from event to event, penalizing erratic turnout swings."),

        ("3. Data Completeness Score (0.0 to 1.0)",
         "Completeness = 0.5 * (Events_with_Attendance / Total_Events) + 0.5 * (Events_with_Feedback / Total_Events)",
         "Measures data integrity. If a club organized 4 events but only submitted attendance for 3 and feedback for 2, its completeness is 0.5 * (3/4) + 0.5 * (2/4) = 62.5%. This replaces silent missing data with mathematical transparency."),

        ("4. Min-Max Score Normalization (0 to 100)",
         "Normalized_Value = (Raw_Value - Min_Value) / (Max_Value - Min_Value) * 100",
         "Levels the playing field across different metric units (converting 1–5 ratings, raw student reach counts, and percentages into a unified 0–100 scale). Edge cases where all clubs tie default safely to 50.0 rather than producing NaN/division-by-zero errors."),

        ("5. Composite Ranking Score (0 to 100)",
         "Score = 0.35 * Quality_Norm + 0.25 * Attendance_Norm + 0.20 * Consistency_Norm + 0.15 * Reach_Norm + 0.05 * Volume_Norm",
         "The weighted master ranking score. Heavily prioritizes student satisfaction (35%) and verified turnout (25%) over raw volume spam (5%).")
    ]

    for title, formula_text, plain_desc in formulas:
        add_heading_styled(doc, title, level=3)
        p_f = doc.add_paragraph()
        r_f = p_f.add_run(f"Formula:  {formula_text}\n")
        r_f.bold = True
        r_f.font.color.rgb = RGBColor(15, 76, 129)
        r_d = p_f.add_run(f"Plain English Meaning: {plain_desc}")
        r_d.font.size = Pt(10)
        p_f.paragraph_format.space_after = Pt(6)

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # ══════════════════════════════════════════════════════════════════════════════
    # SECTION 4: HOW TO RUN EVERYTHING
    # ══════════════════════════════════════════════════════════════════════════════
    add_heading_styled(doc, "4. Quick Execution Guide", level=1)

    cmds = [
        ("Launch Streamlit Web UI", ".venv\\Scripts\\streamlit run app.py", "Opens the interactive web dashboard on http://localhost:8501."),
        ("Launch FastAPI REST Server", ".venv\\Scripts\\uvicorn api.server:app --app-dir event-analytics-v2 --port 8001", "Runs the production REST API backend with Swagger UI on http://127.0.0.1:8001/docs."),
        ("Run All 70 Automated Tests", ".venv\\Scripts\\pytest tests/ event-analytics-v2/tests/ -v", "Runs the complete 70-test verification suite (unit math, integration, schemas, explainability)."),
        ("Run Live A/B Comparison", ".venv\\Scripts\\python comparison/run_comparison.py --provider-v1 groq --provider-v2 groq", "Executes v1 vs v2 side-by-side on 3 data scenarios and generates comparison_summary.md."),
        ("Run Rubric Sensitivity Test", ".venv\\Scripts\\python event-analytics-v2/engine/sensitivity.py", "Evaluates leaderboard stability across 4 distinct weight policy configurations."),
        ("Generate Jury PowerPoint", ".venv\\Scripts\\python generate_jury_ppt.py", "Rebuilds the 10-slide jury presentation (SEA_Agent_v2_Jury_Presentation.pptx).")
    ]

    tbl_c = doc.add_table(rows=1, cols=3)
    tbl_c.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr_c = tbl_c.rows[0].cells
    hdr_c[0].text = "Task / Goal"
    hdr_c[1].text = "Terminal Command"
    hdr_c[2].text = "Description"
    for cell in hdr_c:
        set_cell_background(cell, "0F4C81")
        set_cell_margins(cell, 100, 100, 120, 120)
        for cp in cell.paragraphs:
            for run in cp.runs:
                run.font.color.rgb = RGBColor(255, 255, 255)
                run.font.bold = True
                run.font.size = Pt(10)

    for goal, cmd, desc in cmds:
        row = tbl_c.add_row().cells
        row[0].text = goal
        row[1].text = cmd
        row[2].text = desc
        for i, cell in enumerate(row):
            set_cell_background(cell, "F8FAFC" if len(tbl_c.rows) % 2 == 0 else "FFFFFF")
            set_cell_margins(cell, 80, 80, 100, 100)
            for cp in cell.paragraphs:
                for run in cp.runs:
                    run.font.size = Pt(9.5)
                    if i == 1:
                        run.font.name = 'Consolas'
                        run.font.color.rgb = RGBColor(194, 65, 12) # Dark Orange

    # Save Document
    doc.save(output_path)
    print(f"[OK] Word Document successfully generated: {os.path.abspath(output_path)}")

if __name__ == "__main__":
    create_guide_docx()
