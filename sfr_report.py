"""
sfr_report.py — Generate SFR report from data.db, separated by part type.

SlotID mapping:
    1 = DTC_R    2 = DTC_L    3 = STC

Reports per part:
    1. Summary: total records, pass/fail yield  (JS — date-filterable)
    2. Daily yield trend                        (JS — date-filterable)
    3. SFR Min trend by distance                (JS — date-filterable)
    4. SFR distribution box plots               (JS — date-filterable)
    5. Per-ROI box plots                        (JS — date-filterable)
    6. SFR Deviation by ROI                     (JS — date-filterable)
    7. SFR Dev Trend by Field                   (JS — date-filterable)
    8. SFR statistics table                     (JS — date-filterable)
    9. Top fail items                           (JS — date-filterable)

Usage:
    python sfr_report.py                     # generate report (all dates embedded)
    python sfr_report.py --output report.html
    python sfr_report.py --days 30           # last 30 days only
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
from app_config import cfg

DB_PATH = cfg.db_file
TABLE = "sfr_data"
AUDIT_TABLE = "SFR_audit"

SLOT_MAP = cfg.slot_map
PART_COLORS = {"DTC_R": "#3498db", "DTC_L": "#e67e22", "STC": "#9b59b6"}

SFR_GROUPS = {
    "VIS_25cm": {
        "0.1F": "SFR_VIS_25cm_Ny4_01F_Min",
        "0.3F": "SFR_VIS_25cm_Ny4_03F_Min",
        "0.6F": "SFR_VIS_25cm_Ny4_06F_Min",
        "0.8F": "SFR_VIS_25cm_Ny4_08F_Min",
        "1.0F": "SFR_VIS_25cm_Ny4_010F_Min",
    },
    "IR_25cm": {
        "0.1F": "SFR_IR_25cm_Ny4_01F_Min",
        "0.3F": "SFR_IR_25cm_Ny4_03F_Min",
        "0.6F": "SFR_IR_25cm_Ny4_06F_Min",
        "0.8F": "SFR_IR_25cm_Ny4_08F_Min",
        "1.0F": "SFR_IR_25cm_Ny4_010F_Min",
    },
}

ROI_GROUPS = {
    "VIS_25cm": {
        "0.1F_ROI1": "SFR_VIS_25cm_Ny4_01F_ROI1",
        "0.1F_ROI2": "SFR_VIS_25cm_Ny4_01F_ROI2",
        "0.1F_ROI3": "SFR_VIS_25cm_Ny4_01F_ROI3",
        "0.1F_ROI4": "SFR_VIS_25cm_Ny4_01F_ROI4",
        "0.3F_ROI5": "SFR_VIS_25cm_Ny4_03F_ROI5",
        "0.3F_ROI6": "SFR_VIS_25cm_Ny4_03F_ROI6",
        "0.3F_ROI7": "SFR_VIS_25cm_Ny4_03F_ROI7",
        "0.3F_ROI8": "SFR_VIS_25cm_Ny4_03F_ROI8",
        "0.6F_ROI9": "SFR_VIS_25cm_Ny4_06F_ROI9",
        "0.6F_ROI10": "SFR_VIS_25cm_Ny4_06F_ROI10",
        "0.6F_ROI11": "SFR_VIS_25cm_Ny4_06F_ROI11",
        "0.6F_ROI12": "SFR_VIS_25cm_Ny4_06F_ROI12",
        "0.6F_ROI13": "SFR_VIS_25cm_Ny4_06F_ROI13",
        "0.6F_ROI14": "SFR_VIS_25cm_Ny4_06F_ROI14",
        "0.6F_ROI15": "SFR_VIS_25cm_Ny4_06F_ROI15",
        "0.6F_ROI16": "SFR_VIS_25cm_Ny4_06F_ROI16",
        "0.8F_ROI17": "SFR_VIS_25cm_Ny4_08F_ROI17",
        "0.8F_ROI18": "SFR_VIS_25cm_Ny4_08F_ROI18",
        "0.8F_ROI19": "SFR_VIS_25cm_Ny4_08F_ROI19",
        "0.8F_ROI20": "SFR_VIS_25cm_Ny4_08F_ROI20",
        "0.8F_ROI21": "SFR_VIS_25cm_Ny4_08F_ROI21",
        "0.8F_ROI22": "SFR_VIS_25cm_Ny4_08F_ROI22",
        "0.8F_ROI23": "SFR_VIS_25cm_Ny4_08F_ROI23",
        "0.8F_ROI24": "SFR_VIS_25cm_Ny4_08F_ROI24",
        "0.8F_ROI25": "SFR_VIS_25cm_Ny4_08F_ROI25",
        "0.8F_ROI26": "SFR_VIS_25cm_Ny4_08F_ROI26",
        "0.8F_ROI27": "SFR_VIS_25cm_Ny4_08F_ROI27",
        "0.8F_ROI28": "SFR_VIS_25cm_Ny4_08F_ROI28",
        "1.0F_ROI29": "SFR_VIS_25cm_Ny4_010F_ROI29",
        "1.0F_ROI30": "SFR_VIS_25cm_Ny4_010F_ROI30",
        "1.0F_ROI31": "SFR_VIS_25cm_Ny4_010F_ROI31",
        "1.0F_ROI32": "SFR_VIS_25cm_Ny4_010F_ROI32",
    },
    "IR_25cm": {
        "0.1F_ROI1": "SFR_IR_25cm_Ny4_01F_ROI1",
        "0.1F_ROI2": "SFR_IR_25cm_Ny4_01F_ROI2",
        "0.1F_ROI3": "SFR_IR_25cm_Ny4_01F_ROI3",
        "0.1F_ROI4": "SFR_IR_25cm_Ny4_01F_ROI4",
        "0.3F_ROI5": "SFR_IR_25cm_Ny4_03F_ROI5",
        "0.3F_ROI6": "SFR_IR_25cm_Ny4_03F_ROI6",
        "0.3F_ROI7": "SFR_IR_25cm_Ny4_03F_ROI7",
        "0.3F_ROI8": "SFR_IR_25cm_Ny4_03F_ROI8",
        "0.6F_ROI9": "SFR_IR_25cm_Ny4_06F_ROI9",
        "0.6F_ROI10": "SFR_IR_25cm_Ny4_06F_ROI10",
        "0.6F_ROI11": "SFR_IR_25cm_Ny4_06F_ROI11",
        "0.6F_ROI12": "SFR_IR_25cm_Ny4_06F_ROI12",
        "0.6F_ROI13": "SFR_IR_25cm_Ny4_06F_ROI13",
        "0.6F_ROI14": "SFR_IR_25cm_Ny4_06F_ROI14",
        "0.6F_ROI15": "SFR_IR_25cm_Ny4_06F_ROI15",
        "0.6F_ROI16": "SFR_IR_25cm_Ny4_06F_ROI16",
        "0.8F_ROI17": "SFR_IR_25cm_Ny4_08F_ROI17",
        "0.8F_ROI18": "SFR_IR_25cm_Ny4_08F_ROI18",
        "0.8F_ROI19": "SFR_IR_25cm_Ny4_08F_ROI19",
        "0.8F_ROI20": "SFR_IR_25cm_Ny4_08F_ROI20",
        "0.8F_ROI21": "SFR_IR_25cm_Ny4_08F_ROI21",
        "0.8F_ROI22": "SFR_IR_25cm_Ny4_08F_ROI22",
        "0.8F_ROI23": "SFR_IR_25cm_Ny4_08F_ROI23",
        "0.8F_ROI24": "SFR_IR_25cm_Ny4_08F_ROI24",
        "0.8F_ROI25": "SFR_IR_25cm_Ny4_08F_ROI25",
        "0.8F_ROI26": "SFR_IR_25cm_Ny4_08F_ROI26",
        "0.8F_ROI27": "SFR_IR_25cm_Ny4_08F_ROI27",
        "0.8F_ROI28": "SFR_IR_25cm_Ny4_08F_ROI28",
        "1.0F_ROI29": "SFR_IR_25cm_Ny4_010F_ROI29",
        "1.0F_ROI30": "SFR_IR_25cm_Ny4_010F_ROI30",
        "1.0F_ROI31": "SFR_IR_25cm_Ny4_010F_ROI31",
        "1.0F_ROI32": "SFR_IR_25cm_Ny4_010F_ROI32",
    },
}

SFR_DEV_GROUPS = {
    group: {field: col + "_Dev" for field, col in cols.items()}
    for group, cols in SFR_GROUPS.items()
}

ROI_DEV_GROUPS = {
    group: {roi: col + "_Dev" for roi, col in rois.items()}
    for group, rois in ROI_GROUPS.items()
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_data(
    db_path: Path, days: int | None = None, table: str = TABLE
) -> pd.DataFrame:
    conn = sqlite3.connect(str(db_path))

    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        conn.close()
        return pd.DataFrame()

    all_sfr_cols = set()
    for group in SFR_GROUPS.values():
        all_sfr_cols.update(group.values())
    all_sfr_cols.update(c for roi in ROI_GROUPS.values() for c in roi.values())
    for group in SFR_DEV_GROUPS.values():
        all_sfr_cols.update(group.values())
    all_sfr_cols.update(c for roi in ROI_DEV_GROUPS.values() for c in roi.values())

    cur = conn.execute(f'PRAGMA table_info("{table}")')
    db_columns = {row[1] for row in cur.fetchall()}

    meta_cols = [
        "SerialNumber",
        "CM",
        "TestStation",
        "TestResult",
        "Test_Mode",
        "Time",
        "TSRID",
        "Product_Name",
        "TestFailItem",
        "SlotID",
    ]
    select_cols = [c for c in meta_cols if c in db_columns] + sorted(
        c for c in all_sfr_cols if c in db_columns
    )
    cols_str = ", ".join(f'"{c}"' for c in select_cols)

    df = pd.read_sql_query(f'SELECT {cols_str} FROM "{table}"', conn)
    conn.close()

    if df.empty:
        return df

    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df["Date"] = df["Time"].dt.date
    df["Part"] = df["SlotID"].astype(str).map(SLOT_MAP).fillna("Unknown")

    for col in all_sfr_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if days:
        cutoff = pd.Timestamp.now(tz="Asia/Taipei") - pd.Timedelta(days=days)
        df = df[df["Time"] >= cutoff]

    return df


# ---------------------------------------------------------------------------
# Data embedding for client-side charts (ALL charts now JS-rendered)
# ---------------------------------------------------------------------------


def _embed_chart_data(df: pd.DataFrame) -> str:
    """Serialize relevant columns as JSON for JS chart rendering."""
    if df.empty:
        return "[]"
    all_cols: set[str] = set()
    for group in SFR_GROUPS.values():
        all_cols.update(group.values())
    for group in ROI_GROUPS.values():
        all_cols.update(group.values())
    for group in SFR_DEV_GROUPS.values():
        all_cols.update(group.values())
    for group in ROI_DEV_GROUPS.values():
        all_cols.update(group.values())

    meta = ["TestResult", "TestFailItem"]
    keep = (
        ["Date", "Part"]
        + [m for m in meta if m in df.columns]
        + sorted(c for c in all_cols if c in df.columns)
    )
    subset = df[keep].copy()
    subset["Date"] = subset["Date"].astype(str)
    return subset.to_json(orient="records")


# ---------------------------------------------------------------------------
# HTML placeholder builders (all charts are JS-rendered now)
# ---------------------------------------------------------------------------


def _placeholder(div_id: str) -> str:
    return f'<div id="{div_id}"></div>'


def build_part_section(df: pd.DataFrame, part: str) -> str:
    color = PART_COLORS.get(part, "#3498db")
    sfr_box_divs = ""
    for gn in SFR_GROUPS:
        sfr_box_divs += f'<div class="chart-container">{_placeholder(f"chart-sfr-box-online-{part}-{gn}")}</div>\n'
    roi_box_divs = ""
    for gn in ROI_GROUPS:
        roi_box_divs += f'<div class="chart-container">{_placeholder(f"chart-roi-box-online-{part}-{gn}")}</div>\n'
    dev_roi_divs = ""
    for gn in ROI_DEV_GROUPS:
        dev_roi_divs += f'<div class="chart-container">{_placeholder(f"chart-dev-roi-online-{part}-{gn}")}</div>\n'
    sfr_trend_divs = ""
    for gn in SFR_GROUPS:
        sfr_trend_divs += f'<div class="chart-container">{_placeholder(f"chart-sfr-trend-online-{part}-{gn}")}</div>\n'
    dev_trend_divs = ""
    for gn in SFR_DEV_GROUPS:
        dev_trend_divs += f'<div class="chart-container">{_placeholder(f"chart-dev-trend-online-{part}-{gn}")}</div>\n'

    return f"""
    <div class="part-section" id="{part}">
        <h2 style="border-left:5px solid {color}; padding-left:12px;">{part}</h2>
        <div id="summary-online-{part}"></div>
        <div class="chart-container">{_placeholder(f"chart-daily-yield-online-{part}")}</div>
        {sfr_trend_divs}
        {sfr_box_divs}
        {roi_box_divs}
        {dev_roi_divs}
        {dev_trend_divs}
        <h3>SFR Statistics — {part}</h3>
        <div id="stats-table-online-{part}"><p>Loading…</p></div>
        <h3>Top Fail Items — {part}</h3>
        <div id="fail-table-online-{part}"><p>Loading…</p></div>
    </div>"""


def build_audit_part_section(part: str) -> str:
    color = PART_COLORS.get(part, "#3498db")
    sfr_trend_divs = ""
    for gn in SFR_GROUPS:
        sfr_trend_divs += f'<div class="chart-container">{_placeholder(f"chart-sfr-trend-audit-{part}-{gn}")}</div>\n'
    sfr_box_divs = ""
    for gn in SFR_GROUPS:
        sfr_box_divs += f'<div class="chart-container">{_placeholder(f"chart-sfr-box-audit-{part}-{gn}")}</div>\n'
    return f"""
    <div class="part-subsection">
        <h3 style="border-left:4px solid {color}; padding-left:10px;">{part} — Audit</h3>
        <div id="summary-audit-{part}"></div>
        <div class="chart-container">{_placeholder(f"chart-daily-yield-audit-{part}")}</div>
        {sfr_trend_divs}
        {sfr_box_divs}
    </div>"""


def build_audit_section(has_audit: bool) -> str:
    if not has_audit:
        return ""
    parts_html = ""
    for part_name in SLOT_MAP.values():
        parts_html += build_audit_part_section(part_name)
    return f"""
    <div class="part-section" id="audit">
        <h2 style="border-left:5px solid #e74c3c; padding-left:12px;">Audit SFR Trend</h2>
        <div class="chart-container">{_placeholder("chart-yield-overlay-audit")}</div>
        {parts_html}
    </div>"""


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------


def build_report(
    full_df: pd.DataFrame,
    full_audit_df: pd.DataFrame | None = None,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Determine which parts have data
    available_parts = []
    for part_name in SLOT_MAP.values():
        if not full_df.empty and (full_df["Part"] == part_name).any():
            available_parts.append(part_name)

    # Per-part sections (all placeholder divs)
    part_sections = ""
    for part_name in available_parts:
        part_sections += build_part_section(
            full_df[full_df["Part"] == part_name], part_name
        )

    # Audit section
    has_audit = full_audit_df is not None and not full_audit_df.empty
    audit_section = build_audit_section(has_audit)

    # Navigation links
    nav_links = " ".join(
        f'<a href="#{p}" class="nav-link" style="border-color:{PART_COLORS[p]}">{p}</a>'
        for p in SLOT_MAP.values()
    )
    audit_nav = ""
    if has_audit:
        audit_nav = (
            '<a href="#audit" class="nav-link" style="border-color:#e74c3c">Audit</a>'
        )

    # Date range for picker (from full data)
    all_dates: list[str] = []
    if not full_df.empty:
        all_dates += [str(full_df["Date"].min()), str(full_df["Date"].max())]
    if has_audit:
        all_dates += [str(full_audit_df["Date"].min()), str(full_audit_df["Date"].max())]
    date_min = min(all_dates) if all_dates else ""
    date_max = max(all_dates) if all_dates else ""

    # Embed ALL data for JS charts
    online_json = _embed_chart_data(full_df)
    audit_json = _embed_chart_data(
        full_audit_df if full_audit_df is not None else pd.DataFrame()
    )
    sfr_groups_json = json.dumps(SFR_GROUPS)
    roi_groups_json = json.dumps(ROI_GROUPS)
    sfr_dev_groups_json = json.dumps(SFR_DEV_GROUPS)
    roi_dev_groups_json = json.dumps(ROI_DEV_GROUPS)
    part_colors_json = json.dumps(PART_COLORS)
    parts_json = json.dumps(list(SLOT_MAP.values()))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SFR Report — Loma CW_1_01</title>
<script src="https://cdn.plot.ly/plotly-3.1.1.min.js"></script>
<style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           max-width: 1300px; margin: 0 auto; padding: 20px; background: #f5f6fa; }}
    h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
    h2 {{ color: #34495e; margin-top: 40px; }}
    h3 {{ color: #4a5568; margin-top: 25px; margin-bottom: 10px; }}
    .nav {{ display: flex; gap: 10px; margin: 15px 0 10px 0; flex-wrap: wrap; align-items: center; }}
    .nav-link {{ padding: 8px 20px; border-radius: 8px; border: 3px solid; text-decoration: none;
                 font-weight: 700; color: #2c3e50; font-size: 0.95em; transition: all 0.15s; }}
    .nav-link:hover {{ opacity: 0.8; transform: translateY(-1px); }}
    .date-filter {{ display: flex; gap: 10px; margin: 10px 0 30px 0; align-items: center;
                    background: white; padding: 12px 18px; border-radius: 10px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.08); flex-wrap: wrap; }}
    .date-filter label {{ font-weight: 600; color: #2c3e50; font-size: 0.9em; }}
    .date-filter input[type="date"] {{ padding: 6px 10px; border: 2px solid #dfe6e9; border-radius: 6px;
                                        font-size: 0.9em; color: #2c3e50; }}
    .date-filter button {{ padding: 6px 16px; border: none; border-radius: 6px; font-weight: 600;
                           font-size: 0.85em; cursor: pointer; transition: all 0.15s; }}
    .date-filter .btn-apply {{ background: #3498db; color: white; }}
    .date-filter .btn-apply:hover {{ background: #2980b9; }}
    .date-filter .btn-reset {{ background: #ecf0f1; color: #2c3e50; }}
    .date-filter .btn-reset:hover {{ background: #dfe6e9; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                     gap: 12px; margin: 15px 0; }}
    .card {{ background: white; border-radius: 10px; padding: 16px; text-align: center;
             box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .card-title {{ font-size: 0.8em; color: #7f8c8d; text-transform: uppercase; }}
    .card-value {{ font-size: 1.8em; font-weight: bold; color: #2c3e50; margin-top: 4px; }}
    .chart-container {{ background: white; border-radius: 10px; padding: 12px;
                        margin: 15px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .stats-table {{ border-collapse: collapse; width: 100%; background: white;
                    border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .stats-table th {{ background: #3498db; color: white; padding: 8px 12px; text-align: left; font-size: 0.85em; }}
    .stats-table td {{ padding: 6px 12px; border-bottom: 1px solid #ecf0f1; font-size: 0.85em; }}
    .stats-table tr:hover {{ background: #f8f9fa; }}
    .part-section {{ margin-top: 50px; padding-top: 20px; border-top: 2px solid #e2e8f0; }}
    .generated {{ color: #95a5a6; font-size: 0.85em; text-align: right; margin-top: 30px; }}
</style>
</head>
<body>

<h1>SFR Report — Loma CW_1_01 ONLINE</h1>
<div class="nav">
    <span style="color:#7f8c8d;font-size:0.9em;">Jump to:</span>
    <a href="#overview" class="nav-link" style="border-color:#2c3e50">Comparison</a>
    {nav_links}
    {audit_nav}
</div>

<div class="date-filter">
    <label>Date Range:</label>
    <input type="date" id="date-start" value="{date_min}" min="{date_min}" max="{date_max}">
    <span style="color:#7f8c8d">to</span>
    <input type="date" id="date-end" value="{date_max}" min="{date_min}" max="{date_max}">
    <button class="btn-apply" onclick="onDateChange()">Apply</button>
    <button class="btn-reset" onclick="resetDates()">Reset</button>
    <span id="date-status" style="color:#7f8c8d; font-size:0.85em;"></span>
</div>

<!-- ===== COMPARISON ===== -->
<div id="overview">
    <h2>Yield Comparison — All Parts</h2>
    <div class="chart-container">{_placeholder("chart-yield-overlay-online")}</div>

    <h2>SFR Comparison by Part — VIS 25cm</h2>
    <div class="chart-container">{_placeholder("chart-sfr-comparison-online")}</div>
</div>

<!-- ===== PER-PART SECTIONS ===== -->
{part_sections}

<!-- ===== AUDIT SFR ===== -->
{audit_section}

<p class="generated">Generated: {now}</p>

<!-- ===== EMBEDDED DATA & JS CHART ENGINE ===== -->
<script>
const ONLINE_DATA = {online_json};
const AUDIT_DATA  = {audit_json};
const SFR_GROUPS  = {sfr_groups_json};
const ROI_GROUPS  = {roi_groups_json};
const SFR_DEV_GROUPS = {sfr_dev_groups_json};
const ROI_DEV_GROUPS = {roi_dev_groups_json};
const PART_COLORS = {part_colors_json};
const PARTS = {parts_json};

function filterByDate(data, start, end) {{
    return data.filter(function(r) {{
        return (!start || r.Date >= start) && (!end || r.Date <= end);
    }});
}}

/* ---- Helper: group data by Date ---- */
function groupByDate(data) {{
    var groups = {{}};
    data.forEach(function(r) {{
        if (!groups[r.Date]) groups[r.Date] = [];
        groups[r.Date].push(r);
    }});
    var dates = Object.keys(groups).sort();
    return {{ dates: dates, groups: groups }};
}}

/* ---- Summary cards ---- */
function renderSummary(data, part, source) {{
    var divId = 'summary-' + source + '-' + part;
    var el = document.getElementById(divId);
    if (!el) return;
    var total = data.length;
    var passed = data.filter(function(r) {{ return r.TestResult === 'PASS'; }}).length;
    var failed = total - passed;
    var yieldPct = total > 0 ? (passed / total * 100) : 0;
    var dates = data.map(function(r) {{ return r.Date; }}).sort();
    var dateMin = dates.length ? dates[0] : '-';
    var dateMax = dates.length ? dates[dates.length - 1] : '-';
    var sns = {{}};
    data.forEach(function(r) {{ if (r.SerialNumber) sns[r.SerialNumber] = true; }});
    var uniqueSN = Object.keys(sns).length || total;
    var color = PART_COLORS[part] || '#3498db';
    var yieldColor = yieldPct >= 95 ? '#2ecc71' : yieldPct >= 90 ? '#e67e22' : '#e74c3c';
    el.innerHTML = '<div class="summary-grid">' +
        '<div class="card" style="border-top:4px solid ' + color + '"><div class="card-title">Total — ' + part + '</div><div class="card-value">' + total.toLocaleString() + '</div></div>' +
        '<div class="card"><div class="card-title">Unique S/N</div><div class="card-value">' + uniqueSN.toLocaleString() + '</div></div>' +
        '<div class="card"><div class="card-title">Pass</div><div class="card-value" style="color:#2ecc71">' + passed.toLocaleString() + '</div></div>' +
        '<div class="card"><div class="card-title">Fail</div><div class="card-value" style="color:#e74c3c">' + failed.toLocaleString() + '</div></div>' +
        '<div class="card"><div class="card-title">Yield</div><div class="card-value" style="color:' + yieldColor + '">' + yieldPct.toFixed(1) + '%</div></div>' +
        '<div class="card"><div class="card-title">Date Range</div><div class="card-value" style="font-size:1.1em">' + dateMin + ' &rarr; ' + dateMax + '</div></div>' +
        '</div>';
}}

/* ---- Yield Comparison Overlay (all parts on one chart) ---- */
function renderYieldOverlay(data, divId) {{
    var el = document.getElementById(divId);
    if (!el) return;
    var traces = [];
    PARTS.forEach(function(part) {{
        var pd = data.filter(function(r) {{ return r.Part === part; }});
        if (!pd.length) return;
        var g = groupByDate(pd);
        var yieldVals = g.dates.map(function(d) {{
            var rows = g.groups[d];
            var passed = rows.filter(function(r) {{ return r.TestResult === 'PASS'; }}).length;
            return rows.length > 0 ? (passed / rows.length * 100) : 0;
        }});
        traces.push({{
            type: 'scatter', mode: 'lines+markers',
            x: g.dates, y: yieldVals, name: part,
            line: {{color: PART_COLORS[part], width: 2.5}},
            marker: {{size: 7}}
        }});
    }});
    if (!traces.length) return;
    traces.push({{
        type: 'scatter', mode: 'lines', x: traces[0].x,
        y: traces[0].x.map(function() {{ return 95; }}),
        name: '95% target', line: {{dash: 'dash', color: 'orange', width: 2}},
        showlegend: true
    }});
    Plotly.react(divId, traces, {{
        title: 'Daily Yield Comparison — DTC_R vs DTC_L vs STC',
        xaxis: {{title: 'Date'}}, yaxis: {{title: 'Yield %', range: [0, 105]}},
        height: 400, margin: {{l: 50, r: 50, t: 60, b: 50}}
    }});
}}

/* ---- Daily Yield per part (bar + line, dual y-axis) ---- */
function renderDailyYield(data, part, source) {{
    var divId = 'chart-daily-yield-' + source + '-' + part;
    var el = document.getElementById(divId);
    if (!el) return;
    var g = groupByDate(data);
    var totals = [], fails = [], yields = [];
    g.dates.forEach(function(d) {{
        var rows = g.groups[d];
        var t = rows.length;
        var p = rows.filter(function(r) {{ return r.TestResult === 'PASS'; }}).length;
        totals.push(t);
        fails.push(t - p);
        yields.push(t > 0 ? (p / t * 100) : 0);
    }});
    var color = PART_COLORS[part] || '#3498db';
    var traces = [
        {{ type: 'bar', x: g.dates, y: totals, name: 'Total', marker: {{color: color}}, opacity: 0.5, yaxis: 'y' }},
        {{ type: 'bar', x: g.dates, y: fails, name: 'Fail', marker: {{color: '#e74c3c'}}, opacity: 0.8, yaxis: 'y' }},
        {{ type: 'scatter', mode: 'lines+markers', x: g.dates, y: yields, name: 'Yield %',
          line: {{color: '#2ecc71', width: 3}}, marker: {{size: 8}}, yaxis: 'y2' }},
        {{ type: 'scatter', mode: 'lines', x: g.dates,
          y: g.dates.map(function() {{ return 95; }}),
          name: '95% target', line: {{dash: 'dash', color: 'orange', width: 2}},
          showlegend: true, yaxis: 'y2' }}
    ];
    Plotly.react(divId, traces, {{
        title: 'Daily Yield — ' + part,
        barmode: 'overlay', height: 350,
        margin: {{l: 50, r: 50, t: 60, b: 50}},
        yaxis: {{title: 'Count'}},
        yaxis2: {{title: 'Yield %', range: [0, 105], overlaying: 'y', side: 'right'}}
    }});
}}

/* ---- SFR Min Trend (line chart per group) ---- */
function renderSfrTrend(data, part, source) {{
    Object.entries(SFR_GROUPS).forEach(function(e) {{
        var groupName = e[0], cols = e[1];
        var divId = 'chart-sfr-trend-' + source + '-' + part + '-' + groupName;
        var el = document.getElementById(divId);
        if (!el) return;
        var g = groupByDate(data);
        var traces = [];
        Object.entries(cols).forEach(function(fe) {{
            var label = fe[0], col = fe[1];
            var xVals = [], yVals = [];
            g.dates.forEach(function(d) {{
                var rows = g.groups[d];
                var vals = rows.map(function(r) {{ return r[col]; }}).filter(function(v) {{ return v !== null && v !== undefined && !isNaN(v); }});
                if (vals.length) {{
                    xVals.push(d);
                    yVals.push(vals.reduce(function(a,b) {{ return a+b; }}, 0) / vals.length);
                }}
            }});
            if (xVals.length) {{
                traces.push({{
                    type: 'scatter', mode: 'lines+markers',
                    x: xVals, y: yVals, name: label, marker: {{size: 6}}
                }});
            }}
        }});
        if (!traces.length) return;
        Plotly.react(divId, traces, {{
            title: 'SFR Min Trend — ' + groupName + ' — ' + part,
            xaxis: {{title: 'Date'}}, yaxis: {{title: 'SFR (Ny/4)', range: [0, 1]}},
            height: 320, margin: {{l: 50, r: 50, t: 60, b: 50}}
        }});
    }});
}}

/* ---- SFR Dev Trend by Field (line chart) ---- */
function renderSfrDevTrend(data, part, source) {{
    Object.entries(SFR_DEV_GROUPS).forEach(function(e) {{
        var groupName = e[0], devCols = e[1];
        var divId = 'chart-dev-trend-' + source + '-' + part + '-' + groupName;
        var el = document.getElementById(divId);
        if (!el) return;

        var roiDevCols = ROI_DEV_GROUPS[groupName] || {{}};
        var g = groupByDate(data);
        var traces = [];

        Object.entries(devCols).forEach(function(fe) {{
            var field = fe[0], minDevCol = fe[1];
            var xVals = [], yVals = [];
            g.dates.forEach(function(d) {{
                var rows = g.groups[d];
                /* Try the _Min_Dev column first */
                var vals = rows.map(function(r) {{ return r[minDevCol]; }}).filter(function(v) {{ return v !== null && v !== undefined && !isNaN(v); }});
                if (!vals.length) {{
                    /* Fallback: compute min across per-ROI _Dev columns */
                    var roiCols = Object.entries(roiDevCols).filter(function(re) {{ return re[0].startsWith(field + '_ROI'); }}).map(function(re) {{ return re[1]; }});
                    if (roiCols.length) {{
                        rows.forEach(function(r) {{
                            var rv = roiCols.map(function(c) {{ return r[c]; }}).filter(function(v) {{ return v !== null && v !== undefined && !isNaN(v); }});
                            if (rv.length) vals.push(Math.min.apply(null, rv));
                        }});
                    }}
                }}
                if (vals.length) {{
                    xVals.push(d);
                    yVals.push(Math.min.apply(null, vals));
                }}
            }});
            if (xVals.length) {{
                traces.push({{
                    type: 'scatter', mode: 'lines+markers',
                    x: xVals, y: yVals, name: field, marker: {{size: 6}}
                }});
            }}
        }});
        if (!traces.length) return;
        Plotly.react(divId, traces, {{
            title: 'Min SFR Dev Trend by Field — ' + groupName + ' — ' + part,
            xaxis: {{title: 'Date'}}, yaxis: {{title: 'Min SFR Dev'}},
            height: 400, margin: {{l: 50, r: 50, t: 60, b: 50}},
            shapes: [{{type:'line', yref:'y', y0:0, y1:0, xref:'paper', x0:0, x1:1,
                       line:{{dash:'dash', color:'grey', width:1}}, opacity:0.6}}]
        }});
    }});
}}

/* ---- SFR Comparison by Part (VIS_25cm) ---- */
function renderSfrComparison(data, divId) {{
    var fields = SFR_GROUPS['VIS_25cm'];
    if (!fields) return;
    var traces = [];
    var fieldKeys = Object.keys(fields);
    PARTS.forEach(function(part) {{
        var pd = data.filter(function(r) {{ return r.Part === part; }});
        if (!pd.length) return;
        var first = true;
        fieldKeys.forEach(function(label) {{
            var col = fields[label];
            var vals = pd.map(function(r) {{ return r[col]; }}).filter(function(v) {{ return v !== null && v !== undefined; }});
            if (!vals.length) return;
            traces.push({{
                type: 'box', y: vals, x: vals.map(function() {{ return label; }}),
                name: part, marker: {{color: PART_COLORS[part]}},
                legendgroup: part, showlegend: first
            }});
            first = false;
        }});
    }});
    if (!traces.length) return;
    Plotly.react(divId, traces, {{
        title: 'SFR Comparison by Part — VIS 25cm',
        boxmode: 'group', height: 400,
        margin: {{l: 50, r: 50, t: 60, b: 50}},
        yaxis: {{range: [0, 1]}}
    }});
}}

/* ---- SFR Distribution box plot ---- */
function renderSfrBox(data, part, groupName, cols, divId) {{
    var entries = Object.entries(cols);
    var traces = [];
    entries.forEach(function(e) {{
        var label = e[0], col = e[1];
        var vals = data.map(function(r) {{ return r[col]; }}).filter(function(v) {{ return v !== null && v !== undefined; }});
        if (!vals.length) return;
        traces.push({{type: 'box', y: vals, name: label}});
    }});
    if (!traces.length) return;
    Plotly.react(divId, traces, {{
        title: 'SFR Distribution — ' + groupName + ' — ' + part,
        height: 320, margin: {{l: 50, r: 50, t: 60, b: 50}},
        yaxis: {{range: [0, 1]}}, showlegend: false
    }});
}}

/* ---- Vertical-line helper for ROI field boundaries ---- */
function addFieldVlines(layout, labels) {{
    var prev = null;
    var shapes = layout.shapes ? layout.shapes.slice() : [];
    var anns = layout.annotations ? layout.annotations.slice() : [];
    for (var i = 0; i < labels.length; i++) {{
        var f = labels[i].split('_ROI')[0];
        if (prev !== null && f !== prev) {{
            shapes.push({{
                type: 'line', x0: i - 0.5, x1: i - 0.5,
                yref: 'paper', y0: 0, y1: 1,
                line: {{dash: 'dot', color: '#7f8c8d', width: 1}}, opacity: 0.7
            }});
            anns.push({{
                x: i - 0.5, y: 1.02, yref: 'paper', xref: 'x',
                text: f, showarrow: false,
                font: {{size: 10, color: '#7f8c8d'}}
            }});
        }}
        prev = f;
    }}
    layout.shapes = shapes;
    layout.annotations = anns;
}}

/* ---- Per-ROI SFR box plot ---- */
function renderRoiBox(data, part, groupName, cols, divId) {{
    var entries = Object.entries(cols);
    var labels = entries.map(function(e) {{ return e[0]; }});
    var traces = [];
    entries.forEach(function(e) {{
        var label = e[0], col = e[1];
        var vals = data.map(function(r) {{ return r[col]; }}).filter(function(v) {{ return v !== null && v !== undefined; }});
        if (!vals.length) return;
        traces.push({{type: 'box', y: vals, name: label}});
    }});
    if (!traces.length) return;
    var layout = {{
        title: 'Per-ROI SFR — ' + groupName + ' — ' + part,
        height: 400, margin: {{l: 50, r: 50, t: 60, b: 50}},
        yaxis: {{range: [0, 1]}}, showlegend: false,
        xaxis: {{tickangle: -45}}
    }};
    addFieldVlines(layout, labels);
    Plotly.react(divId, traces, layout);
}}

/* ---- SFR Deviation by ROI ---- */
function renderDevRoi(data, part, groupName, cols, divId) {{
    var entries = Object.entries(cols);
    var labels = entries.map(function(e) {{ return e[0]; }});
    var traces = [];
    entries.forEach(function(e) {{
        var label = e[0], col = e[1];
        var vals = data.map(function(r) {{ return r[col]; }}).filter(function(v) {{ return v !== null && v !== undefined; }});
        if (!vals.length) return;
        traces.push({{type: 'box', y: vals, name: label}});
    }});
    if (!traces.length) return;
    var layout = {{
        title: 'SFR Deviation by ROI — ' + groupName + ' — ' + part,
        height: 400, margin: {{l: 50, r: 50, t: 60, b: 50}},
        showlegend: false, xaxis: {{tickangle: -45}},
        yaxis: {{title: 'SFR Dev'}},
        shapes: [{{
            type: 'line', yref: 'y', y0: 0, y1: 0,
            xref: 'paper', x0: 0, x1: 1,
            line: {{dash: 'dash', color: 'grey', width: 1}}, opacity: 0.6
        }}]
    }};
    addFieldVlines(layout, labels);
    Plotly.react(divId, traces, layout);
}}

/* ---- SFR Statistics table (Cpk) ---- */
function renderStatsTable(data, part, source) {{
    var divId = 'stats-table-' + source + '-' + part;
    var el = document.getElementById(divId);
    if (!el) return;
    var rows = [];
    Object.entries(SFR_GROUPS).forEach(function(ge) {{
        var groupName = ge[0], cols = ge[1];
        Object.entries(cols).forEach(function(fe) {{
            var field = fe[0], col = fe[1];
            var vals = data.map(function(r) {{ return r[col]; }}).filter(function(v) {{ return v !== null && v !== undefined && !isNaN(v); }});
            if (!vals.length) return;
            var n = vals.length;
            var mean = vals.reduce(function(a,b) {{ return a+b; }}, 0) / n;
            var variance = vals.reduce(function(a,b) {{ return a + (b - mean) * (b - mean); }}, 0) / n;
            var std = Math.sqrt(variance);
            var mn = Math.min.apply(null, vals);
            var mx = Math.max.apply(null, vals);
            var cpk = std > 0 ? (Math.min(mean - mn, mx - mean) / (3 * std)).toFixed(2) : '-';
            rows.push({{group: groupName, field: field, count: n,
                        mean: mean.toFixed(4), std: std.toFixed(4),
                        min: mn.toFixed(4), max: mx.toFixed(4), cpk: cpk}});
        }});
    }});
    if (!rows.length) {{ el.innerHTML = '<p>No SFR data available.</p>'; return; }}
    var html = '<table class="stats-table"><thead><tr>' +
        '<th>Group</th><th>Field</th><th>Count</th><th>Mean</th><th>Std</th><th>Min</th><th>Max</th><th>Cpk_est</th>' +
        '</tr></thead><tbody>';
    rows.forEach(function(r) {{
        html += '<tr><td>' + r.group + '</td><td>' + r.field + '</td><td>' + r.count +
                '</td><td>' + r.mean + '</td><td>' + r.std + '</td><td>' + r.min +
                '</td><td>' + r.max + '</td><td>' + r.cpk + '</td></tr>';
    }});
    html += '</tbody></table>';
    el.innerHTML = html;
}}

/* ---- Top Fail Items table ---- */
function renderFailTable(data, part, source) {{
    var divId = 'fail-table-' + source + '-' + part;
    var el = document.getElementById(divId);
    if (!el) return;
    var fails = data.filter(function(r) {{ return r.TestResult === 'FAIL'; }});
    if (!fails.length) {{ el.innerHTML = '<p>No failures recorded.</p>'; return; }}
    var counts = {{}};
    fails.forEach(function(r) {{
        var item = r.TestFailItem || '(empty)';
        counts[item] = (counts[item] || 0) + 1;
    }});
    var sorted = Object.entries(counts).sort(function(a, b) {{ return b[1] - a[1]; }}).slice(0, 10);
    var total = fails.length;
    var html = '<table class="stats-table"><thead><tr>' +
        '<th>Fail Item</th><th>Count</th><th>% of Fails</th>' +
        '</tr></thead><tbody>';
    sorted.forEach(function(e) {{
        var pct = (e[1] / total * 100).toFixed(1);
        html += '<tr><td>' + e[0] + '</td><td>' + e[1] + '</td><td>' + pct + '%</td></tr>';
    }});
    html += '</tbody></table>';
    el.innerHTML = html;
}}

/* ---- Render all JS-driven charts for a data source ---- */
function renderAllCharts(source, data) {{
    /* Yield overlay */
    var overlayId = 'chart-yield-overlay-' + source;
    if (document.getElementById(overlayId)) renderYieldOverlay(data, overlayId);

    /* SFR Comparison */
    if (source === 'online') {{
        var el = document.getElementById('chart-sfr-comparison-online');
        if (el) renderSfrComparison(data, 'chart-sfr-comparison-online');
    }}

    PARTS.forEach(function(part) {{
        var pd = data.filter(function(r) {{ return r.Part === part; }});
        if (!pd.length) return;

        /* Summary cards */
        renderSummary(pd, part, source);

        /* Daily yield */
        renderDailyYield(pd, part, source);

        /* SFR Min Trend */
        renderSfrTrend(pd, part, source);

        /* SFR Dev Trend */
        if (source === 'online') renderSfrDevTrend(pd, part, source);

        /* Box plots */
        Object.entries(SFR_GROUPS).forEach(function(e) {{
            var gn = e[0], cols = e[1];
            var id = 'chart-sfr-box-' + source + '-' + part + '-' + gn;
            if (document.getElementById(id)) renderSfrBox(pd, part, gn, cols, id);
        }});
        Object.entries(ROI_GROUPS).forEach(function(e) {{
            var gn = e[0], cols = e[1];
            var id = 'chart-roi-box-' + source + '-' + part + '-' + gn;
            if (document.getElementById(id)) renderRoiBox(pd, part, gn, cols, id);
        }});
        Object.entries(ROI_DEV_GROUPS).forEach(function(e) {{
            var gn = e[0], cols = e[1];
            var id = 'chart-dev-roi-' + source + '-' + part + '-' + gn;
            if (document.getElementById(id)) renderDevRoi(pd, part, gn, cols, id);
        }});

        /* Tables */
        renderStatsTable(pd, part, source);
        renderFailTable(pd, part, source);
    }});
}}

/* ---- Date filter controls ---- */
function onDateChange() {{
    var start = document.getElementById('date-start').value;
    var end   = document.getElementById('date-end').value;
    var onF = filterByDate(ONLINE_DATA, start, end);
    var auF = filterByDate(AUDIT_DATA, start, end);
    renderAllCharts('online', onF);
    renderAllCharts('audit', auF);
    document.getElementById('date-status').textContent =
        'Showing ' + onF.length + ' online + ' + auF.length + ' audit rows';
}}

function resetDates() {{
    var s = document.getElementById('date-start');
    var e = document.getElementById('date-end');
    s.value = s.min;
    e.value = e.max;
    onDateChange();
}}

/* ---- Initial render on page load ---- */
document.addEventListener('DOMContentLoaded', function() {{
    renderAllCharts('online', ONLINE_DATA);
    renderAllCharts('audit', AUDIT_DATA);
    document.getElementById('date-status').textContent =
        'Showing ' + ONLINE_DATA.length + ' online + ' + AUDIT_DATA.length + ' audit rows';
}});
</script>

</body>
</html>"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SFR report from data.db")
    parser.add_argument(
        "--db", type=str, default=str(DB_PATH), help="SQLite database path"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=str(cfg.report_file),
        help="Output HTML file",
    )
    parser.add_argument("--days", type=int, default=None, help="Limit to last N days")
    parser.add_argument(
        "--all",
        action="store_true",
        dest="show_all",
        help="(Deprecated, all data is now always embedded)",
    )
    args = parser.parse_args()

    print(f"Loading data from {args.db} …")
    full_df = load_data(Path(args.db), args.days)
    print(f"Loaded {len(full_df)} records (ONLINE)")

    full_audit_df = load_data(Path(args.db), args.days, table=AUDIT_TABLE)
    print(f"Loaded {len(full_audit_df)} records (Audit)")

    for part in SLOT_MAP.values():
        cnt = (full_df["Part"] == part).sum()
        print(f"  {part}: {cnt} rows")

    for part in SLOT_MAP.values():
        cnt = (full_audit_df["Part"] == part).sum() if not full_audit_df.empty else 0
        print(f"  {part} (audit): {cnt} rows")

    print("Building report …")
    html = build_report(full_df, full_audit_df)

    output = Path(args.output)
    output.write_text(html)
    print(f"Report saved: {output.resolve()}")


if __name__ == "__main__":
    main()
