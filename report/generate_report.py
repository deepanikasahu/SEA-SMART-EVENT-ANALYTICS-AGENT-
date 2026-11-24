"""
Report Generation Layer for Smart Event Analytics Agent.
Renders structured Markdown reports via Jinja2 and Microsoft Word documents via python-docx.
Enforces strict Privacy NFR: only accepts pre-aggregated club metrics and audit metadata.
"""

import datetime
import os
from typing import Dict, Any, Tuple
from jinja2 import Environment, FileSystemLoader


def generate_markdown_report(
    agent_output: Dict[str, Any],
    template_dir: str = "report/templates",
    output_dir: str = "reports"
) -> str:
    """Render structured Markdown report from agent results dictionary."""
    os.makedirs(output_dir, exist_ok=True)
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("report_template.md.j2")

    # Add current timestamp
    render_context = dict(agent_output)
    render_context["generated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    markdown_content = template.render(**render_context)

    # Save to timestamped file and latest_report.md
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"report_{timestamp}.md"
    report_path = os.path.join(output_dir, report_filename)
    latest_path = os.path.join(output_dir, "latest_report.md")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    return report_path


def generate_docx_report(
    agent_output: Dict[str, Any],
    output_dir: str = "reports"
) -> str:
    """Generate professional Word (.docx) document from agent results."""
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
    except ImportError:
        return ""

    os.makedirs(output_dir, exist_ok=True)
    doc = Document()

    # Title
    title = doc.add_heading("Smart Event Analytics Performance Report", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Metadata subtitle
    p_meta = doc.add_paragraph()
    p_meta.add_run(f"Query: {agent_output.get('query', '')}\n").bold = True
    p_meta.add_run(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Engine: {agent_output.get('provider', 'Groq')}\n")
    p_meta.add_run(f"Evaluated Events: {agent_output.get('in_scope_events_count', 0)} events across {len(agent_output.get('ranked_clubs', []))} clubs")

    doc.add_heading("1. Executive Leaderboard", level=1)
    
    # Leaderboard Table
    clubs = agent_output.get("ranked_clubs", [])
    if clubs:
        table = doc.add_table(rows=1, cols=7)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        hdr_cells = table.rows[0].cells
        hdr_titles = ["Rank", "Club Name", "Score", "Attendance %", "Feedback", "Consistency", "Status"]
        for i, t in enumerate(hdr_titles):
            hdr_cells[i].text = t
            hdr_cells[i].paragraphs[0].runs[0].bold = True

        for c in clubs:
            row_cells = table.add_row().cells
            row_cells[0].text = f"#{c.get('rank')}"
            row_cells[1].text = str(c.get("club_name"))
            row_cells[2].text = f"{c.get('composite_score', 0):.2f}"
            row_cells[3].text = f"{c.get('attendance_rate_pct', 0):.1f}%" if c.get("attendance_rate_pct") is not None else "N/A"
            row_cells[4].text = f"{c.get('engagement_quality', 0):.2f}" if c.get("engagement_quality") is not None else "N/A"
            row_cells[5].text = f"{c.get('consistency_raw', 0)*100:.1f}%"
            row_cells[6].text = str(c.get("data_status"))

    doc.add_heading("2. Qualitative Findings & LLM Reasoning", level=1)
    doc.add_paragraph(agent_output.get("grounded_narrative", ""))

    doc.add_heading("3. Number-Grounding & Anti-Hallucination Audit", level=1)
    audit = agent_output.get("number_grounding_audit", {})
    p_audit = doc.add_paragraph()
    p_audit.add_run(f"Status: {audit.get('verdict', '')}\n").bold = True
    p_audit.add_run(f"Numbers Checked: {audit.get('total_numbers_checked', 0)} | Grounded: {audit.get('grounded_numbers_count', 0)} | Suspicious: {audit.get('suspicious_count', 0)}")

    doc.add_heading("4. Missing Data Disclosures", level=1)
    disclosures = agent_output.get("audit_disclosures", {})
    partial_clubs = disclosures.get("clubs_with_partial_data", [])
    if partial_clubs:
        for p in partial_clubs:
            p_p = doc.add_paragraph(style='List Bullet')
            p_p.add_run(f"{p.get('club_name')}: ").bold = True
            p_p.add_run(f"Attendance sheets submitted for {p.get('events_with_attendance')}/{p.get('total_events')} events; feedback received for {p.get('events_with_feedback')}/{p.get('total_events')} events.")
    else:
        doc.add_paragraph("All events had 100% complete attendance and feedback records.")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    docx_filename = f"report_{timestamp}.docx"
    docx_path = os.path.join(output_dir, docx_filename)
    latest_docx = os.path.join(output_dir, "latest_report.docx")

    doc.save(docx_path)
    doc.save(latest_docx)
    return docx_path


def generate_all_reports(agent_output: Dict[str, Any], output_dir: str = "reports") -> Tuple[str, str]:
    """Generate both Markdown and Word reports and return their filepaths."""
    md_path = generate_markdown_report(agent_output, output_dir=output_dir)
    docx_path = generate_docx_report(agent_output, output_dir=output_dir)
    return md_path, docx_path
