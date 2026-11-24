"""
Smart Event Analytics Agent — SEA Agent
Professional analytics dashboard with:
- Theme Switcher: ☀️ Minimalist Light Mode & 🌙 Sleek Dark Mode
- Highlighted Pastel Color Palette (Mint, Sky Blue, Lavender, Peach, Rose)
- Unlocked Sidebar Toggle: prominently styled expand/collapse buttons
- Clean, User-Friendly UI/UX with high contrast and readable typography
"""

import os
import sqlite3
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent.orchestrator import EventAnalyticsAgent
from agent.ranking import load_weights_config
from data_generation.generate_dummy_data import generate_data
from report.generate_report import generate_all_reports

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SEA Agent — Smart Event Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "Smart Event Analytics Agent — College Jury Demo"
    }
)

# ── Session state initialization ──────────────────────────────────────────────
if "theme" not in st.session_state:
    st.session_state["theme"] = "light"  # Default to fresh minimalist light mode

for key, default in {
    "pending_clarification": False,
    "clarification_question": "",
    "original_query": "",
    "latest_results": None,
    "main_query_box": "Analyze all technical events conducted last semester and tell me which clubs performed the best.",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── Dynamic Theme CSS (Pastel Minimalist: Light & Dark) ────────────────────────
def get_theme_css(theme: str) -> str:
    is_light = (theme == "light")

    if is_light:
        # Minimalist Light with Pastel Highlights
        vars_css = """
        --bg-app: #F8FAFC;
        --bg-card: #FFFFFF;
        --bg-card-alt: #F1F5F9;
        --bg-sidebar: #FFFFFF;
        --border-subtle: #E2E8F0;
        --border-accent: #CBD5E1;
        --text-primary: #0F172A;
        --text-secondary: #334155;
        --text-muted: #64748B;
        --shadow-card: 0 4px 16px rgba(15, 23, 42, 0.05);
        --shadow-elevated: 0 10px 25px -5px rgba(15, 23, 42, 0.08);

        --btn-primary: #0284C7;
        --btn-primary-hover: #0369A1;
        --btn-primary-active: #075985;
        --btn-primary-text: #FFFFFF;

        --btn-sec-bg: #F8FAFC;
        --btn-sec-border: #E2E8F0;
        --btn-sec-text: #334155;
        --btn-sec-hover-bg: #F0F9FF;
        --btn-sec-hover-border: #38BDF8;

        /* Pastel Highlights */
        --pastel-mint-bg: #ECFDF5;
        --pastel-mint-border: #10B981;
        --pastel-mint-text: #047857;

        --pastel-sky-bg: #F0F9FF;
        --pastel-sky-border: #0284C7;
        --pastel-sky-text: #0284C7;

        --pastel-lav-bg: #F5F3FF;
        --pastel-lav-border: #7C3AED;
        --pastel-lav-text: #6D28D9;

        --pastel-peach-bg: #FFFBEB;
        --pastel-peach-border: #F59E0B;
        --pastel-peach-text: #B45309;

        --pastel-rose-bg: #FFF1F2;
        --pastel-rose-border: #F43F5E;
        --pastel-rose-text: #BE123C;

        --table-th-bg: #F1F5F9;
        --table-row-odd: #FFFFFF;
        --table-row-even: #F8FAFC;
        --table-hover: #F0F9FF;
        """
    else:
        # Minimalist Dark with Pastel Glows
        vars_css = """
        --bg-app: #0B0F19;
        --bg-card: #151D2E;
        --bg-card-alt: #1A2438;
        --bg-sidebar: #0F172A;
        --border-subtle: #1E293B;
        --border-accent: #334155;
        --text-primary: #F8FAFC;
        --text-secondary: #CBD5E1;
        --text-muted: #94A3B8;
        --shadow-card: 0 4px 20px rgba(0, 0, 0, 0.4);
        --shadow-elevated: 0 10px 30px rgba(0, 0, 0, 0.6);

        --btn-primary: #0284C7;
        --btn-primary-hover: #0369A1;
        --btn-primary-active: #075985;
        --btn-primary-text: #FFFFFF;

        --btn-sec-bg: #151D2E;
        --btn-sec-border: #2A3F5F;
        --btn-sec-text: #CBD5E1;
        --btn-sec-hover-bg: rgba(56, 189, 248, 0.12);
        --btn-sec-hover-border: #38BDF8;

        /* Pastel Highlights */
        --pastel-mint-bg: rgba(16, 185, 129, 0.12);
        --pastel-mint-border: #10B981;
        --pastel-mint-text: #34D399;

        --pastel-sky-bg: rgba(56, 189, 248, 0.12);
        --pastel-sky-border: #38BDF8;
        --pastel-sky-text: #7DD3FC;

        --pastel-lav-bg: rgba(168, 85, 247, 0.12);
        --pastel-lav-border: #A855F7;
        --pastel-lav-text: #D8B4FE;

        --pastel-peach-bg: rgba(245, 158, 11, 0.12);
        --pastel-peach-border: #F59E0B;
        --pastel-peach-text: #FDE68A;

        --pastel-rose-bg: rgba(244, 63, 94, 0.12);
        --pastel-rose-border: #F43F5E;
        --pastel-rose-text: #FECDD3;

        --table-th-bg: #0F172A;
        --table-row-odd: #141C2D;
        --table-row-even: #182236;
        --table-hover: rgba(56, 189, 248, 0.12);
        """

    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap');

    :root {{
        {vars_css}
    }}

    /* ── Base App Body ── */
    html, body, [class*="css"] {{
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
        color: var(--text-primary);
    }}
    .stApp {{
        background-color: var(--bg-app) !important;
        transition: background-color 0.25s ease;
    }}
    .block-container {{
        padding: 28px 36px !important;
        max-width: 100% !important;
    }}

    p, span, label, li {{
        color: var(--text-secondary);
    }}

    /* ── CRITICAL FIX: Sidebar Collapse/Expand Button Unlocked ── */
    /* DO NOT hide stToolbar! It houses the expand button in Streamlit 1.62+ */
    header[data-testid="stHeader"] {{
        background: transparent !important;
        height: 52px !important;
        z-index: 99999 !important;
    }}
    [data-testid="stToolbar"] {{
        visibility: visible !important;
        display: flex !important;
        opacity: 1 !important;
    }}
    /* Hide only deploy and three-dots hamburger menu */
    [data-testid="stMainMenu"],
    .stDeployButton,
    [data-testid="stToolbarActions"],
    [data-testid="stDecoration"] {{
        display: none !important;
        visibility: hidden !important;
    }}

    /* Prominent Sidebar Expand Button */
    [data-testid="stExpandSidebarButton"] {{
        visibility: visible !important;
        display: flex !important;
        align-items: center !important;
        z-index: 999999 !important;
    }}
    [data-testid="stExpandSidebarButton"] button {{
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        background: var(--bg-card) !important;
        border: 1.5px solid var(--pastel-sky-border) !important;
        border-radius: 10px !important;
        width: 42px !important;
        height: 42px !important;
        margin-top: 4px !important;
        margin-left: 8px !important;
        box-shadow: var(--shadow-card) !important;
        cursor: pointer !important;
        transition: all 0.2s ease !important;
    }}
    [data-testid="stExpandSidebarButton"] button:hover {{
        background: var(--pastel-sky-bg) !important;
        transform: scale(1.08) !important;
        box-shadow: 0 4px 14px rgba(2, 132, 199, 0.25) !important;
    }}
    [data-testid="stExpandSidebarButton"] svg {{
        fill: var(--pastel-sky-text) !important;
        color: var(--pastel-sky-text) !important;
        width: 22px !important;
        height: 22px !important;
    }}

    /* Sidebar Collapse Button inside sidebar header */
    [data-testid="stSidebarCollapseButton"] button {{
        background: var(--bg-card) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 8px !important;
        color: var(--text-secondary) !important;
        transition: all 0.2s ease !important;
    }}
    [data-testid="stSidebarCollapseButton"] button:hover {{
        border-color: var(--pastel-sky-border) !important;
        color: var(--pastel-sky-text) !important;
    }}

    /* ── Sidebar Styling ── */
    section[data-testid="stSidebar"] {{
        background: var(--bg-sidebar) !important;
        border-right: 1px solid var(--border-subtle) !important;
        box-shadow: 2px 0 16px rgba(0, 0, 0, 0.03) !important;
    }}
    section[data-testid="stSidebar"] .block-container {{
        padding: 0 !important;
    }}
    .sb-brand {{
        background: var(--bg-card);
        border-bottom: 1px solid var(--border-subtle);
        padding: 22px 18px 18px 18px;
    }}
    .sb-brand-name {{
        font-size: 16px;
        font-weight: 800;
        color: var(--text-primary);
        margin-bottom: 2px;
    }}
    .sb-brand-desc {{
        font-size: 12px;
        color: var(--text-muted);
        margin-bottom: 10px;
    }}
    .sb-section-wrap {{
        padding: 16px 18px;
    }}
    .sb-divider {{
        height: 1px;
        background: var(--border-subtle);
        margin: 14px 0;
    }}
    .sec-label {{
        font-size: 13px !important;
        font-weight: 700 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
        color: var(--pastel-sky-text) !important;
        margin-bottom: 10px !important;
        display: flex;
        align-items: center;
        gap: 6px;
    }}

    /* ── Page Header Area ── */
    .page-header {{
        background: var(--bg-card);
        border: 1px solid var(--border-subtle);
        border-radius: 14px;
        padding: 26px 30px;
        margin-bottom: 24px;
        box-shadow: var(--shadow-card);
        position: relative;
    }}
    .header-top-row {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 20px;
        margin-bottom: 12px;
    }}
    .page-header-title {{
        font-size: 30px;
        font-weight: 800;
        color: var(--text-primary);
        letter-spacing: -0.5px;
        line-height: 1.2;
        margin-bottom: 6px;
    }}
    .page-header-sub {{
        font-size: 14px;
        color: var(--text-muted);
        line-height: 1.6;
        max-width: 820px;
    }}

    /* ── Feature Badges with Highlighted Pastel Accents ── */
    .pipeline-steps {{
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 14px;
    }}
    .step-chip {{
        display: inline-flex;
        align-items: center;
        gap: 7px;
        font-size: 12.5px;
        font-weight: 600;
        border-radius: 8px;
        padding: 7px 14px;
        white-space: nowrap;
        transition: all 0.2s ease;
    }}
    .chip-metrics {{
        background: var(--pastel-mint-bg);
        border: 1.5px solid var(--pastel-mint-border);
        color: var(--pastel-mint-text);
    }}
    .chip-tools {{
        background: var(--pastel-sky-bg);
        border: 1.5px solid var(--pastel-sky-border);
        color: var(--pastel-sky-text);
    }}
    .chip-llm {{
        background: var(--pastel-lav-bg);
        border: 1.5px solid var(--pastel-lav-border);
        color: var(--pastel-lav-text);
    }}
    .chip-audit {{
        background: var(--pastel-peach-bg);
        border: 1.5px solid var(--pastel-peach-border);
        color: var(--pastel-peach-text);
    }}
    .step-chip:hover {{
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
    }}
    .step-arrow {{
        color: var(--border-accent);
        font-size: 14px;
        font-weight: 700;
    }}

    /* ── Central Idle State Card ── */
    .idle-card {{
        background: var(--bg-card);
        border: 1.5px dashed var(--border-subtle);
        border-radius: 14px;
        padding: 56px 36px;
        text-align: center;
        box-shadow: var(--shadow-card);
        margin-bottom: 20px;
    }}
    .idle-icon {{
        font-size: 64px;
        line-height: 1;
        margin-bottom: 14px;
        display: inline-block;
        filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.08));
    }}
    .idle-title {{
        font-size: 22px;
        font-weight: 700;
        color: var(--text-primary);
        margin-bottom: 8px;
    }}
    .idle-desc {{
        font-size: 14px;
        color: var(--text-muted);
        max-width: 480px;
        margin: 0 auto 20px auto;
        line-height: 1.6;
    }}

    /* ── KPI Stats Cards ── */
    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        margin-bottom: 24px;
    }}
    @media (max-width: 1024px) {{
        .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}
    @media (max-width: 640px) {{
        .kpi-grid {{ grid-template-columns: 1fr; }}
    }}
    .kpi-card {{
        background: var(--bg-card);
        border: 1px solid var(--border-subtle);
        border-radius: 12px;
        padding: 20px;
        box-shadow: var(--shadow-card);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        min-height: 140px;
        transition: all 0.2s ease;
        position: relative;
        overflow: hidden;
    }}
    .kpi-card:hover {{
        transform: translateY(-2px);
        box-shadow: var(--shadow-elevated);
    }}
    .kpi-card-peach {{ border-top: 3px solid var(--pastel-peach-border); }}
    .kpi-card-sky   {{ border-top: 3px solid var(--pastel-sky-border); }}
    .kpi-card-mint  {{ border-top: 3px solid var(--pastel-mint-border); }}
    .kpi-card-lav   {{ border-top: 3px solid var(--pastel-lav-border); }}

    .kpi-label {{
        font-size: 11.5px;
        font-weight: 700;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 8px;
    }}
    .kpi-number {{
        font-size: 48px;
        font-weight: 800;
        color: var(--text-primary);
        line-height: 1;
        letter-spacing: -1.5px;
        margin: 4px 0 8px 0;
    }}
    .kpi-club-title {{
        font-size: 18px;
        font-weight: 800;
        color: var(--text-primary);
        line-height: 1.3;
        margin: 4px 0 8px 0;
    }}
    .kpi-footer {{
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 12.5px;
        font-weight: 600;
    }}
    .kpi-dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
    }}
    .dot-mint  {{ background: var(--pastel-mint-border); box-shadow: 0 0 8px var(--pastel-mint-border); }}
    .dot-sky   {{ background: var(--pastel-sky-border); box-shadow: 0 0 8px var(--pastel-sky-border); }}
    .dot-peach {{ background: var(--pastel-peach-border); box-shadow: 0 0 8px var(--pastel-peach-border); }}
    .dot-lav   {{ background: var(--pastel-lav-border); box-shadow: 0 0 8px var(--pastel-lav-border); }}

    /* ── Leaderboard Table (Pastel Minimalist) ── */
    .lb-table-wrapper {{
        background: var(--bg-card);
        border: 1px solid var(--border-subtle);
        border-radius: 12px;
        overflow: hidden;
        margin-top: 10px;
        margin-bottom: 24px;
        box-shadow: var(--shadow-card);
    }}
    .lb-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 13.5px;
        text-align: left;
    }}
    .lb-table thead tr {{
        background: var(--table-th-bg);
        border-bottom: 1.5px solid var(--border-subtle);
    }}
    .lb-table th {{
        padding: 14px 16px;
        font-size: 11.5px;
        font-weight: 700;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        white-space: nowrap;
    }}
    .lb-table tbody tr {{
        border-bottom: 1px solid var(--border-subtle);
        transition: background 0.15s ease;
    }}
    .lb-table tbody tr:nth-child(odd) {{
        background: var(--table-row-odd);
    }}
    .lb-table tbody tr:nth-child(even) {{
        background: var(--table-row-even);
    }}
    .lb-table tbody tr:hover {{
        background: var(--table-hover) !important;
    }}
    .lb-table td {{
        padding: 13px 16px;
        color: var(--text-primary);
        vertical-align: middle;
    }}
    .rank-badge {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 12px;
        border-radius: 6px;
        width: 36px;
        height: 26px;
    }}
    .rank-1 {{ background: var(--pastel-peach-bg); border: 1px solid var(--pastel-peach-border); color: var(--pastel-peach-text); }}
    .rank-2 {{ background: var(--bg-card-alt); border: 1px solid var(--border-accent); color: var(--text-secondary); }}
    .rank-3 {{ background: var(--pastel-rose-bg); border: 1px solid var(--pastel-rose-border); color: var(--pastel-rose-text); }}
    .rank-other {{ background: transparent; color: var(--text-muted); border: 1px solid var(--border-subtle); }}

    .club-primary-name {{
        font-size: 14px;
        font-weight: 700;
        color: var(--text-primary);
    }}
    .club-faculty {{
        font-size: 12px;
        color: var(--text-muted);
    }}
    .score-pill {{
        display: inline-block;
        font-family: 'JetBrains Mono', monospace;
        font-size: 13.5px;
        font-weight: 700;
        color: var(--pastel-sky-text);
        background: var(--pastel-sky-bg);
        border: 1px solid var(--pastel-sky-border);
        border-radius: 6px;
        padding: 2px 8px;
    }}
    .status-pill {{
        display: inline-flex;
        align-items: center;
        gap: 4px;
        font-size: 11px;
        font-weight: 600;
        border-radius: 6px;
        padding: 3px 8px;
        white-space: nowrap;
    }}
    .status-success {{
        background: var(--pastel-mint-bg);
        border: 1px solid var(--pastel-mint-border);
        color: var(--pastel-mint-text);
    }}
    .status-warning {{
        background: var(--pastel-peach-bg);
        border: 1px solid var(--pastel-peach-border);
        color: var(--pastel-peach-text);
    }}
    .status-danger {{
        background: var(--pastel-rose-bg);
        border: 1px solid var(--pastel-rose-border);
        color: var(--pastel-rose-text);
    }}

    /* ── Right Panel: Presets & Inputs ── */
    .query-card {{
        background: var(--bg-card);
        border: 1px solid var(--border-subtle);
        border-radius: 12px;
        padding: 20px;
        box-shadow: var(--shadow-card);
        margin-bottom: 20px;
    }}
    div[data-testid="stVerticalBlock"] button[kind="secondary"] {{
        background: var(--btn-sec-bg) !important;
        border: 1px solid var(--btn-sec-border) !important;
        color: var(--btn-sec-text) !important;
        border-radius: 8px !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        text-align: left !important;
        padding: 10px 14px !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04) !important;
    }}
    div[data-testid="stVerticalBlock"] button[kind="secondary"]:hover {{
        background: var(--btn-sec-hover-bg) !important;
        border-color: var(--btn-sec-hover-border) !important;
        color: var(--pastel-sky-text) !important;
        transform: translateX(3px) !important;
    }}

    /* Primary Run Button */
    button[kind="primary"] {{
        background: var(--btn-primary) !important;
        border: none !important;
        color: var(--btn-primary-text) !important;
        border-radius: 8px !important;
        font-size: 14px !important;
        font-weight: 700 !important;
        padding: 12px 24px !important;
        box-shadow: 0 4px 14px rgba(2, 132, 199, 0.3) !important;
        transition: all 0.2s ease !important;
    }}
    button[kind="primary"]:hover {{
        background: var(--btn-primary-hover) !important;
        box-shadow: 0 6px 18px rgba(2, 132, 199, 0.45) !important;
        transform: translateY(-1px) !important;
    }}
    button[kind="primary"]:active {{
        background: var(--btn-primary-active) !important;
        transform: translateY(1px) !important;
    }}

    /* Input & Textarea */
    [data-testid="stTextArea"] textarea {{
        background: var(--bg-card-alt) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 8px !important;
        font-size: 13.5px !important;
        color: var(--text-primary) !important;
        line-height: 1.55 !important;
        padding: 12px 14px !important;
        transition: all 0.2s ease !important;
    }}
    [data-testid="stTextArea"] textarea:focus {{
        border-color: var(--pastel-sky-border) !important;
        box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.15) !important;
        outline: none !important;
    }}
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input {{
        background: var(--bg-card-alt) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 8px !important;
        font-size: 13.5px !important;
        color: var(--text-primary) !important;
    }}
    [data-testid="stSelectbox"] > div > div {{
        background: var(--bg-card-alt) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 8px !important;
        font-size: 13.5px !important;
        color: var(--text-primary) !important;
    }}

    /* Expanders & Dividers */
    details[data-testid="stExpander"] {{
        background: var(--bg-card) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 8px !important;
        margin-bottom: 8px !important;
        box-shadow: var(--shadow-card) !important;
    }}
    details[data-testid="stExpander"] summary {{
        font-size: 13px !important;
        font-weight: 600 !important;
        color: var(--text-secondary) !important;
        padding: 10px 14px !important;
    }}
    hr {{
        border-color: var(--border-subtle) !important;
        margin: 20px 0 !important;
    }}

    /* Clarification Banner */
    .clarif-box {{
        background: var(--pastel-peach-bg);
        border: 1.5px solid var(--pastel-peach-border);
        border-radius: 10px;
        padding: 16px 18px;
        margin-bottom: 16px;
    }}
    .clarif-box h4 {{
        color: var(--pastel-peach-text);
        margin: 0 0 4px 0;
        font-size: 14px;
        font-weight: 700;
    }}
    .clarif-box p {{
        color: var(--text-primary);
        margin: 0;
        font-size: 13px;
    }}
    </style>
    """


# Inject CSS for active theme
st.markdown(get_theme_css(st.session_state["theme"]), unsafe_allow_html=True)


def get_db_path():
    return os.getenv("DATABASE_PATH", "data/sea_agent.db")


# ── Render KPI Cards HTML ─────────────────────────────────────────────────────
def render_kpi_display(results: dict, ranked_clubs: list, audit: dict) -> str:
    top = ranked_clubs[0] if ranked_clubs else {}
    top_name = top.get("club_name", "—")
    top_score = top.get("composite_score", 0.0)

    events_analyzed = results.get("in_scope_events_count", 0)
    clubs_count = len(ranked_clubs)

    grd = audit.get("grounded_numbers_count", 0)
    tot = audit.get("total_numbers_checked", 0)
    is_valid = audit.get("is_valid", True) and audit.get("suspicious_count", 0) == 0

    duration = results.get("total_duration_seconds", 0.0)
    provider = results.get("provider", "LLM").upper()

    html = (
        '<div class="kpi-grid">'
        '<div class="kpi-card kpi-card-peach">'
        '<div><div class="kpi-label">🏆 Top Club</div>'
        f'<div class="kpi-club-title" title="{top_name}">{top_name}</div></div>'
        '<div class="kpi-footer"><span class="kpi-dot dot-peach"></span>'
        f'<span style="color: var(--pastel-peach-text);">Score: <strong>{top_score:.2f}</strong> / 100</span></div>'
        '</div>'
        '<div class="kpi-card kpi-card-sky">'
        '<div><div class="kpi-label">📅 In-Scope Events</div>'
        f'<div class="kpi-number">{events_analyzed}</div></div>'
        '<div class="kpi-footer"><span class="kpi-dot dot-sky"></span>'
        f'<span style="color: var(--pastel-sky-text);">Across <strong>{clubs_count}</strong> clubs</span></div>'
        '</div>'
        '<div class="kpi-card kpi-card-mint">'
        '<div><div class="kpi-label">🛡️ Numbers Grounded</div>'
        f'<div class="kpi-number">{grd}<span style="font-size: 26px; color: var(--text-muted); font-weight: 500;">/{tot}</span></div></div>'
        '<div class="kpi-footer"><span class="kpi-dot dot-mint"></span>'
        f'<span style="color: var(--pastel-mint-text);"><strong>{"✓ 100% Grounded" if is_valid else "⚠ Check Audit"}</strong></span></div>'
        '</div>'
        '<div class="kpi-card kpi-card-lav">'
        '<div><div class="kpi-label">⚡ Execution Time</div>'
        f'<div class="kpi-number">{duration:.2f}<span style="font-size: 26px; color: var(--text-muted); font-weight: 500;">s</span></div></div>'
        '<div class="kpi-footer"><span class="kpi-dot dot-lav"></span>'
        f'<span style="color: var(--pastel-lav-text);">Engine: <strong>{provider}</strong></span></div>'
        '</div>'
        '</div>'
    )
    return html


# ── Render Leaderboard Table HTML ─────────────────────────────────────────────
def render_leaderboard_table(ranked_clubs: list) -> str:
    rows = []
    for c in ranked_clubs:
        rank = c.get("rank", 1)
        rank_class = f"rank-{rank}" if rank <= 3 else "rank-other"

        att_val = c.get("attendance_rate_pct")
        att_str = f"{att_val:.1f}%" if att_val is not None else '<span style="color:var(--pastel-peach-text);">N/A*</span>'

        fb_val = c.get("engagement_quality")
        fb_str = f"{fb_val:.2f} <span style=\'font-size:11px;color:var(--text-muted);\'>/5.0</span>" if fb_val is not None else '<span style="color:var(--pastel-peach-text);">N/A*</span>'

        cons_val = c.get("consistency_raw")
        cons_str = f"{cons_val*100:.1f}%" if cons_val is not None else 'N/A'

        reach_val = c.get("reach", 0)
        events_ratio = f"{c.get('activity_volume', 0)} / {c.get('planned_events', 0)}"
        score_val = f"{c.get('composite_score', 0):.2f}"

        data_status = c.get("data_status", "Complete Data")
        if "Significant Gaps" in data_status:
            status_html = f'<span class="status-pill status-danger">⚠ {data_status}</span>'
        elif "Partial Data" in data_status:
            status_html = f'<span class="status-pill status-warning">⚠ {data_status}</span>'
        else:
            status_html = f'<span class="status-pill status-success">✓ Complete Data</span>'

        lead = c.get("faculty_lead", "")
        lead_sub = f'<div class="club-faculty">Lead: {lead}</div>' if lead else ''

        row_html = (
            f'<tr>'
            f'<td style="width: 60px;"><span class="rank-badge {rank_class}">#{rank}</span></td>'
            f'<td><div class="club-primary-name">{c.get("club_name")}</div>{lead_sub}</td>'
            f'<td style="text-align: right;"><span class="score-pill">{score_val}</span></td>'
            f'<td style="text-align: right; font-weight: 600;">{att_str}</td>'
            f'<td style="text-align: right; font-weight: 600;">{fb_str}</td>'
            f'<td style="text-align: right; font-weight: 600;">{cons_str}</td>'
            f'<td style="text-align: right; font-weight: 600; color: var(--pastel-sky-text);">{reach_val:,}</td>'
            f'<td style="text-align: center; font-weight: 600;">{events_ratio}</td>'
            f'<td>{status_html}</td>'
            f'</tr>'
        )
        rows.append(row_html)

    tbody = "".join(rows)
    table_html = (
        '<div class="lb-table-wrapper">'
        '<table class="lb-table">'
        '<thead><tr>'
        '<th style="width: 60px;">Rank</th>'
        '<th>Club Name</th>'
        '<th style="text-align: right;">Score</th>'
        '<th style="text-align: right;">Turnout %</th>'
        '<th style="text-align: right;">Feedback</th>'
        '<th style="text-align: right;">Consistency</th>'
        '<th style="text-align: right;">Reach</th>'
        '<th style="text-align: center;">Events</th>'
        '<th>Integrity Status</th>'
        '</tr></thead>'
        f'<tbody>{tbody}</tbody>'
        '</table>'
        '</div>'
    )
    return table_html


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR CONTROLS
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        '<div class="sb-brand">'
        '<div style="font-size: 32px; line-height: 1; margin-bottom: 6px;">📊</div>'
        '<div class="sb-brand-name">SEA Agent</div>'
        '<div class="sb-brand-desc">Smart Event Analytics Agent</div>'
        '</div>',
        unsafe_allow_html=True
    )

    # Section 1: Agent Controls
    st.markdown('<div class="sb-section-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="sec-label">⚙️ Agent Controls</div>', unsafe_allow_html=True)
    current_provider = os.getenv("LLM_PROVIDER", "groq")
    provider_options = ["groq", "mock", "openrouter", "gemini"]
    selected_provider = st.selectbox(
        "LLM Provider",
        provider_options,
        index=provider_options.index(current_provider) if current_provider in provider_options else 0,
        label_visibility="visible"
    )
    impute_missing = st.checkbox(
        "Enable Imputation (FR7 Opt-in)",
        value=False,
        help="Substitutes missing event metrics with category-wide averages instead of excluding them."
    )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)

    # Section 2: Database Management
    st.markdown('<div class="sb-section-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="sec-label">🗄️ Synthetic Database</div>', unsafe_allow_html=True)
    seed_input = st.number_input("Random Seed", min_value=1, max_value=9999, value=42, label_visibility="visible")
    if st.button("Regenerate Database", use_container_width=True):
        with st.spinner("Generating database…"):
            summary = generate_data(db_path=get_db_path(), seed=seed_input)
            st.success(f"{summary['events_count']} events created.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)

    # Section 3: Scoring Weights
    st.markdown('<div class="sb-section-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="sec-label">⚖️ Scoring Weights</div>', unsafe_allow_html=True)
    weights_cfg = load_weights_config("weights_config.json")
    st.json(weights_cfg.get("weights", {}), expanded=False)
    st.caption(weights_cfg.get("rationale", ""))
    st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE HELPER
# ══════════════════════════════════════════════════════════════════════════════
def run_pipeline(query: str):
    if not os.path.exists(get_db_path()):
        with st.spinner("Initializing database…"):
            generate_data(db_path=get_db_path(), seed=42)

    agent = EventAnalyticsAgent(
        db_path=get_db_path(),
        weights_path="weights_config.json",
        provider=selected_provider,
        impute_missing=impute_missing
    )
    with st.spinner(f"Running analysis via {selected_provider.upper()}…"):
        results = agent.run(user_query=query)

    if results.get("status") in ["needs_clarification", "CLARIFICATION_NEEDED"]:
        st.session_state.pending_clarification = True
        st.session_state.clarification_question = results.get("question") or results.get("message")
        st.session_state.original_query = query
        st.session_state.latest_results = None
    else:
        st.session_state.pending_clarification = False
        st.session_state.latest_results = results


# ══════════════════════════════════════════════════════════════════════════════
# TOP HEADER WITH TITLE, THEME SWITCHER, & FEATURE BADGES
# ══════════════════════════════════════════════════════════════════════════════
header_col1, header_col2 = st.columns([3.8, 1.2])
with header_col1:
    st.markdown(
        '<div class="page-header-title">Smart Event Analytics Agent</div>'
        '<div class="page-header-sub">'
        'Deterministic club-performance ranking powered by grounded LLM reasoning with automated anti-hallucination verification.'
        '</div>',
        unsafe_allow_html=True
    )

with header_col2:
    # Minimalist Theme Switcher Button
    current_theme = st.session_state["theme"]
    toggle_icon = "🌙 Dark Theme" if current_theme == "light" else "☀️ Light Theme"
    if st.button(toggle_icon, key="theme_toggle_btn", use_container_width=True):
        st.session_state["theme"] = "dark" if current_theme == "light" else "light"
        st.rerun()

# Feature Badges Row
st.markdown("""
<div class="pipeline-steps">
  <span class="step-chip chip-metrics">🐍 Deterministic Metrics</span>
  <span class="step-arrow">→</span>
  <span class="step-chip chip-tools">🔧 Tool-Calling Loop</span>
  <span class="step-arrow">→</span>
  <span class="step-chip chip-llm">🧠 LLM Reasoning</span>
  <span class="step-arrow">→</span>
  <span class="step-chip chip-audit">🛡️ Anti-Hallucination Audit</span>
</div>
<div style="height: 16px;"></div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN WORKSPACE  [Output 2.5x  |  Query + Audit 1x]
# ══════════════════════════════════════════════════════════════════════════════
col_out, col_in = st.columns([2.5, 1], gap="large")


# ─────────────────────────────────────────────────────────────────────────────
# RIGHT PANEL — Presets, Query Input, Audit Trail
# ─────────────────────────────────────────────────────────────────────────────
with col_in:
    st.markdown('<div class="sec-label">⚡ Quick Presets</div>', unsafe_allow_html=True)
    presets = {
        "Technical Events (Standard)": "Analyze all technical events conducted last semester and tell me which clubs performed the best.",
        "Missing Date (FR1 Trigger)": "Tell me which clubs performed best.",
        "Cultural Events Scope": "Analyze only Cultural events from last semester.",
    }
    for label, query_val in presets.items():
        if st.button(label, use_container_width=True, key=f"preset_{label}"):
            st.session_state["main_query_box"] = query_val
            st.session_state.pending_clarification = False
            st.session_state.latest_results = None
            st.rerun()

    st.divider()

    st.markdown('<div class="sec-label">💬 Your Query</div>', unsafe_allow_html=True)
    query_text = st.text_area(
        "query_input",
        key="main_query_box",
        height=110,
        label_visibility="collapsed",
        placeholder="Describe what you want to evaluate…"
    )
    run_clicked = st.button("🚀 Run Analysis", type="primary", use_container_width=True)
    if run_clicked:
        run_pipeline(query_text)

    # Clarification Sub-form
    if st.session_state.pending_clarification:
        st.divider()
        st.markdown(
            '<div class="clarif-box">'
            '<h4>⚠ Time Scope Required</h4>'
            '<p>Please specify a semester or date range to continue.</p>'
            '</div>',
            unsafe_allow_html=True
        )
        st.caption(f"Agent: {st.session_state.clarification_question}")
        clarif_answer = st.text_input(
            "Time period",
            placeholder="e.g. last semester, Spring 2024",
            key="clarif_user_response",
            label_visibility="collapsed"
        )
        if st.button("Submit Clarification", type="primary", use_container_width=True):
            if clarif_answer.strip():
                merged = f"{st.session_state.original_query} (Time Period: {clarif_answer.strip()})"
                st.session_state.pending_clarification = False
                run_pipeline(merged)
                st.rerun()
            else:
                st.warning("Enter a time period to proceed.")

    # Audit & Inspection Panel (When results are ready)
    if st.session_state.latest_results and st.session_state.latest_results.get("status") == "SUCCESS":
        res_r  = st.session_state.latest_results
        aud_r  = res_r.get("number_grounding_audit", {})
        disc_r = res_r.get("audit_disclosures", {})
        tot_r  = aud_r.get('total_numbers_checked', 0)
        grd_r  = aud_r.get('grounded_numbers_count', 0)
        ok_r   = aud_r.get('is_valid', True) and aud_r.get('suspicious_count', 0) == 0
        susp_r = aud_r.get('suspicious_count', 0)

        st.divider()
        st.markdown('<div class="sec-label">🔍 Audit &amp; Verification</div>', unsafe_allow_html=True)

        a1, a2 = st.columns(2)
        with a1:
            st.metric("Grounded", f"{grd_r}/{tot_r}", "✓ Verified" if ok_r else f"{susp_r} Flagged",
                      delta_color="normal" if ok_r else "inverse")
        with a2:
            st.metric("Duration", f"{res_r.get('total_duration_seconds',0):.2f}s",
                      res_r.get('provider', ''))

        with st.expander("🛡️ Anti-Hallucination Audit"):
            verdict_badge = '<span class="status-pill status-success">PASS</span>' if ok_r else '<span class="status-pill status-danger">FAIL</span>'
            verdict_label = "PASS" if ok_r else "FAIL"
            st.markdown(f"**Audit Status:** {verdict_badge} — `{verdict_label}`", unsafe_allow_html=True)
            st.write(f"Total numbers checked: **{tot_r}** | Grounded count: **{grd_r}**")
            flagged = aud_r.get("flagged_items", [])
            if flagged:
                st.error("**Flagged Items:**")
                for item in flagged:
                    st.write(f"- `{item}`")
            else:
                st.info("No flagged items")

        with st.expander("📋 Missing Data — FR7 Disclosure"):
            st.caption("Missing events are excluded from averages rather than penalized as zero.")
            ex_count = disc_r.get("excluded_event_count", 0)
            st.write(f"**Total Events with Missing Attendance/Feedback:** `{ex_count}`")
            imp_fields = disc_r.get("imputed_fields", [])
            if imp_fields:
                st.info(f"**Imputed Field Substitutions ({len(imp_fields)}):**")
                for item in imp_fields:
                    st.write(f"- `{item.get('club_name')}`: {item.get('field')} = `{item.get('substituted_value')}`")
            else:
                st.caption(f"Imputation Applied: `{disc_r.get('imputation_applied', False)}` (0 substitutions)")
            parts = disc_r.get("clubs_with_partial_data", [])
            if parts:
                for p in parts:
                    st.warning(
                        f"**{p.get('club_name')}** — "
                        f"Attendance: {p.get('events_with_attendance')}/{p.get('total_events')} | "
                        f"Feedback: {p.get('events_with_feedback')}/{p.get('total_events')}"
                    )
            else:
                st.success("All clubs had 100% complete records.")

        with st.expander("🔧 Tool Execution Trajectory"):
            st.caption("Autonomous tool invocation steps:")
            for i, log in enumerate(res_r.get("execution_log", [])):
                name = log.get("name") or log.get("step")
                args = log.get("arguments", {})
                recs = log.get("record_count", log.get("records_fetched", 0))
                dur = log.get("duration", log.get("duration_seconds", 0.0))
                st.markdown(f"**{i+1}. Tool Call:** `{name}`")
                st.write(f"- **Arguments:** `{args}`")
                st.write(f"- **Record Count:** `{recs}`")
                st.write(f"- **Duration:** `{dur}s`")

        with st.expander("🗄️ SQLite Database Inspector"):
            conn = sqlite3.connect(get_db_path())
            tbl = st.selectbox("Table", ["events","club_plans","registrations","attendance","feedback"],
                               key="sidebar_table_inspect", label_visibility="collapsed")
            df_tbl = pd.read_sql_query(f"SELECT * FROM {tbl} LIMIT 25;", conn)
            conn.close()
            st.dataframe(df_tbl, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# LEFT/MIDDLE PANE — Results
# ─────────────────────────────────────────────────────────────────────────────
with col_out:

    # ── Idle State ───────────────────────────────────────────────────────────
    if not st.session_state.pending_clarification and not st.session_state.latest_results:
        st.info("Pick a preset query from the right panel and click Run Analysis to begin.")
        # 1-click sample button
        if st.button("⚡ Run Technical Events Analysis Demo", key="idle_demo_run"):
            run_pipeline("Analyze all technical events conducted last semester and tell me which clubs performed the best.")
            st.rerun()

    # ── Clarification State ──────────────────────────────────────────────────
    elif st.session_state.pending_clarification:
        st.markdown(
            '<div class="clarif-box">'
            '<h4>⚠ Analysis Paused — Time Period Required (FR1)</h4>'
            '<p>Please enter the desired semester or date range in the right panel to proceed.</p>'
            '</div>',
            unsafe_allow_html=True
        )
        st.info(f"Agent Prompt: {st.session_state.clarification_question}")

    # ── Results State ────────────────────────────────────────────────────────
    elif st.session_state.latest_results and st.session_state.latest_results.get("status") == "SUCCESS":
        results      = st.session_state.latest_results
        ranked_clubs = results.get("ranked_clubs", [])
        ranked_df    = pd.DataFrame(ranked_clubs)
        audit        = results.get("number_grounding_audit", {})

        # ── 1. KPI Stats Cards Row ───────────────────────────────────────────
        st.markdown(render_kpi_display(results, ranked_clubs, audit), unsafe_allow_html=True)

        # ── 2. Results Leaderboard Table (Above Narrative) ───────────────────
        st.markdown('<div class="sec-label">🏆 Club Performance Leaderboard</div>', unsafe_allow_html=True)
        st.caption(
            f"Evaluated **{results.get('in_scope_events_count', 0)}** events across **{len(ranked_clubs)}** clubs · "
            f"Execution time: **{results.get('total_duration_seconds')}s** via **{results.get('provider')}**"
        )

        table_rows = []
        for c in ranked_clubs:
            table_rows.append({
                "rank": f"#{c.get('rank')}",
                "club": c.get("club_name"),
                "composite_score": f"{c.get('composite_score', 0):.2f}",
                "engagement_quality": f"{c.get('engagement_quality', 0):.2f}" if c.get("engagement_quality") is not None else "N/A",
                "attendance_rate": f"{c.get('attendance_rate_pct', 0):.2f}%" if c.get("attendance_rate_pct") is not None else "N/A",
                "consistency": f"{c.get('consistency_raw', 0)*100:.1f}%" if c.get("consistency_raw") is not None else "N/A",
                "reach": f"{c.get('reach', 0):,}",
                "activity_volume": f"{c.get('activity_volume', 0)}/{c.get('planned_events', 0)}",
                "data_quality_flag": c.get("data_status", "Complete Data")
            })
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

        st.markdown(render_leaderboard_table(ranked_clubs), unsafe_allow_html=True)

        st.divider()

        # ── 3. Qualitative LLM Narrative ─────────────────────────────────────
        st.markdown('<div class="sec-label">🧠 Grounded Qualitative Analysis & Trade-offs</div>', unsafe_allow_html=True)
        st.markdown(results.get("grounded_narrative", "").strip())

        st.divider()

        # ── 4. Export Section ────────────────────────────────────────────────
        st.markdown('<div class="sec-label">📄 Export Audit Reports</div>', unsafe_allow_html=True)
        md_file, docx_file = generate_all_reports(results)
        dl1, dl2 = st.columns(2)
        with dl1:
            with open(md_file, "r", encoding="utf-8") as f:
                st.download_button("📥 Download Markdown Report", f.read(),
                                   file_name="sea_agent_report.md",
                                   mime="text/markdown",
                                   use_container_width=True)
        with dl2:
            if docx_file and os.path.exists(docx_file):
                with open(docx_file, "rb") as f:
                    st.download_button("📥 Download Word Report (.docx)", f.read(),
                                       file_name="sea_agent_report.docx",
                                       mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                       use_container_width=True)
