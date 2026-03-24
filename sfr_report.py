"""
sfr_report.py — Generate SFR report from data.db, separated by part type.

SlotID mapping:
    1 = DTC_R    2 = DTC_L    3 = STC

Reports per part:
    1. Summary: total records, pass/fail yield
    2. Daily yield trend
    3. SFR Min trend by distance
    4. SFR distribution box plots  (JS — date-filterable)
    5. Per-ROI box plots           (JS — date-filterable)
    6. SFR statistics table
    7. Top fail items

Usage:
    python sfr_report.py                     # generate report for latest day (default)
    python sfr_report.py --all               # generate full HTML report (all dates)
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
import plotly.graph_objects as go
from app_config import cfg
from plotly.subplots import make_subplots

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
# Data embedding for client-side charts
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
# Report components — server-rendered (Plotly Python)
# ---------------------------------------------------------------------------


def summary_html(df: pd.DataFrame, part: str | None = None) -> str:
    total = len(df)
    passed = (df["TestResult"] == "PASS").sum()
    failed = (df["TestResult"] == "FAIL").sum()
    yield_pct = (passed / total * 100) if total > 0 else 0
    date_min = df["Date"].min()
    date_max = df["Date"].max()
    unique_sn = df["SerialNumber"].nunique()
    color = PART_COLORS.get(part, "#3498db")

    title_extra = f" — {part}" if part else ""
    return f"""
    <div class="summary-grid">
        <div class="card" style="border-top:4px solid {color}">
            <div class="card-title">Total{title_extra}</div>
            <div class="card-value">{total:,}</div>
        </div>
        <div class="card">
            <div class="card-title">Unique S/N</div>
            <div class="card-value">{unique_sn:,}</div>
        </div>
        <div class="card">
            <div class="card-title">Pass</div>
            <div class="card-value" style="color:#2ecc71">{passed:,}</div>
        </div>
        <div class="card">
            <div class="card-title">Fail</div>
            <div class="card-value" style="color:#e74c3c">{failed:,}</div>
        </div>
        <div class="card">
            <div class="card-title">Yield</div>
            <div class="card-value" style="color:{'#2ecc71' if yield_pct>=95 else '#e67e22' if yield_pct>=90 else '#e74c3c'}">{yield_pct:.1f}%</div>
        </div>
        <div class="card">
            <div class="card-title">Date Range</div>
            <div class="card-value" style="font-size:1.1em">{date_min} → {date_max}</div>
        </div>
    </div>"""


def fig_daily_yield(df: pd.DataFrame, part: str | None = None) -> str:
    daily = (
        df.groupby("Date")
        .agg(
            total=("TestResult", "count"),
            passed=("TestResult", lambda x: (x == "PASS").sum()),
        )
        .reset_index()
    )
    daily["yield_pct"] = daily["passed"] / daily["total"] * 100
    color = PART_COLORS.get(part, "#3498db")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=daily["Date"],
            y=daily["total"],
            name="Total",
            marker_color=color,
            opacity=0.5,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(
            x=daily["Date"],
            y=daily["total"] - daily["passed"],
            name="Fail",
            marker_color="#e74c3c",
            opacity=0.8,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=daily["Date"],
            y=daily["yield_pct"],
            name="Yield %",
            mode="lines+markers",
            line=dict(color="#2ecc71", width=3),
            marker=dict(size=8),
        ),
        secondary_y=True,
    )
    fig.add_hline(
        y=95,
        line_dash="dash",
        line_color="orange",
        annotation_text="95% target",
        secondary_y=True,
    )

    title = f"Daily Yield — {part}" if part else "Daily Yield — All Parts"
    fig.update_layout(
        title=title, barmode="overlay", height=350, margin=dict(l=50, r=50, t=60, b=50)
    )
    fig.update_yaxes(title_text="Count", secondary_y=False)
    fig.update_yaxes(title_text="Yield %", range=[0, 105], secondary_y=True)
    return fig.to_html(full_html=False, include_plotlyjs=False)


def fig_daily_yield_overlay(df: pd.DataFrame) -> str:
    """All 3 parts yield on one chart for comparison."""
    fig = go.Figure()
    for part in ["DTC_R", "DTC_L", "STC"]:
        pdf = df[df["Part"] == part]
        if pdf.empty:
            continue
        daily = (
            pdf.groupby("Date")
            .agg(
                total=("TestResult", "count"),
                passed=("TestResult", lambda x: (x == "PASS").sum()),
            )
            .reset_index()
        )
        daily["yield_pct"] = daily["passed"] / daily["total"] * 100
        fig.add_trace(
            go.Scatter(
                x=daily["Date"],
                y=daily["yield_pct"],
                name=part,
                mode="lines+markers",
                line=dict(color=PART_COLORS[part], width=2.5),
                marker=dict(size=7),
            )
        )

    fig.add_hline(
        y=95, line_dash="dash", line_color="orange", annotation_text="95% target"
    )
    fig.update_layout(
        title="Daily Yield Comparison — DTC_R vs DTC_L vs STC",
        xaxis_title="Date",
        yaxis_title="Yield %",
        yaxis=dict(range=[0, 105]),
        height=400,
        margin=dict(l=50, r=50, t=60, b=50),
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def fig_sfr_trend(df: pd.DataFrame, part: str | None = None) -> str:
    figs_html = []
    suffix = f" — {part}" if part else ""
    for group_name, cols in SFR_GROUPS.items():
        available = {k: v for k, v in cols.items() if v in df.columns}
        if not available:
            continue
        daily_means = df.groupby("Date")[list(available.values())].mean().reset_index()
        fig = go.Figure()
        for label, col in available.items():
            if col in daily_means.columns:
                fig.add_trace(
                    go.Scatter(
                        x=daily_means["Date"],
                        y=daily_means[col],
                        mode="lines+markers",
                        name=label,
                        marker=dict(size=6),
                    )
                )
        fig.update_layout(
            title=f"SFR Min Trend — {group_name}{suffix}",
            xaxis_title="Date",
            yaxis_title="SFR (Ny/4)",
            height=320,
            margin=dict(l=50, r=50, t=60, b=50),
            yaxis=dict(range=[0, 1]),
        )
        figs_html.append(fig.to_html(full_html=False, include_plotlyjs=False))
    return "\n".join(figs_html)


# ---------------------------------------------------------------------------
# Report components — client-rendered (placeholder divs, JS fills them)
# ---------------------------------------------------------------------------


def fig_sfr_comparison(df: pd.DataFrame, source: str = "online") -> str:
    """Placeholder for JS-rendered SFR comparison box plot."""
    cols = SFR_GROUPS.get("VIS_25cm", {})
    available = {k: v for k, v in cols.items() if v in df.columns}
    if not available:
        return ""
    return f'<div id="chart-sfr-comparison-{source}"></div>'


def fig_sfr_box(
    df: pd.DataFrame, part: str | None = None, source: str = "online"
) -> str:
    """Placeholder divs for JS-rendered SFR distribution box plots."""
    divs = []
    for group_name, cols in SFR_GROUPS.items():
        available = {k: v for k, v in cols.items() if v in df.columns}
        if not available:
            continue
        div_id = f"chart-sfr-box-{source}-{part}-{group_name}"
        divs.append(f'<div id="{div_id}"></div>')
    return "\n".join(divs)


def fig_roi_box(
    df: pd.DataFrame, part: str | None = None, source: str = "online"
) -> str:
    """Placeholder divs for JS-rendered per-ROI SFR box plots."""
    divs = []
    for group_name, roi_cols in ROI_GROUPS.items():
        available = {k: v for k, v in roi_cols.items() if v in df.columns}
        if not available:
            continue
        div_id = f"chart-roi-box-{source}-{part}-{group_name}"
        divs.append(f'<div id="{div_id}"></div>')
    return "\n".join(divs)


def fig_sfr_dev_roi(
    df: pd.DataFrame, part: str | None = None, source: str = "online"
) -> str:
    """Placeholder divs for JS-rendered SFR deviation ROI box plots."""
    divs = []
    for group_name, roi_cols in ROI_DEV_GROUPS.items():
        available = {k: v for k, v in roi_cols.items() if v in df.columns}
        if not available:
            continue
        div_id = f"chart-dev-roi-{source}-{part}-{group_name}"
        divs.append(f'<div id="{div_id}"></div>')
    return "\n".join(divs)


# ---------------------------------------------------------------------------
# Server-rendered components (continued)
# ---------------------------------------------------------------------------


def fig_sfr_dev_trend(df: pd.DataFrame, part: str | None = None) -> str:
    """Daily trend of min SFR deviation by field.

    Uses DB _Min_Dev columns when available; falls back to computing
    min across per-ROI _Dev columns for fields without a _Min_Dev column.
    """
    figs_html = []
    suffix = f" — {part}" if part else ""
    for group_name, dev_cols in SFR_DEV_GROUPS.items():
        roi_dev_cols = ROI_DEV_GROUPS.get(group_name, {})

        tmp = pd.DataFrame({"Date": df["Date"].values})
        has_any = False
        for field, min_dev_col in dev_cols.items():
            if min_dev_col in df.columns:
                tmp[field] = df[min_dev_col].values
                has_any = True
            else:
                roi_cols = [
                    c
                    for lbl, c in roi_dev_cols.items()
                    if lbl.startswith(field + "_ROI") and c in df.columns
                ]
                if roi_cols:
                    tmp[field] = df[roi_cols].min(axis=1).values
                    has_any = True

        if not has_any:
            continue

        field_cols = [c for c in tmp.columns if c != "Date"]
        daily_min = tmp.groupby("Date")[field_cols].min().reset_index()

        fig = go.Figure()
        for field in field_cols:
            fig.add_trace(
                go.Scatter(
                    x=daily_min["Date"],
                    y=daily_min[field],
                    mode="lines+markers",
                    name=field,
                    marker=dict(size=6),
                )
            )
        fig.add_hline(y=0, line_dash="dash", line_color="grey", opacity=0.6)
        fig.update_layout(
            title=f"Min SFR Dev Trend by Field — {group_name}{suffix}",
            xaxis_title="Date",
            yaxis_title="Min SFR Dev",
            height=400,
            margin=dict(l=50, r=50, t=60, b=50),
        )
        figs_html.append(fig.to_html(full_html=False, include_plotlyjs=False))
    return "\n".join(figs_html)


def stats_table_html(
    df: pd.DataFrame, part: str | None = None, source: str = "online"
) -> str:
    """Placeholder div for JS-rendered SFR statistics table."""
    div_id = f"stats-table-{source}-{part}"
    return f'<div id="{div_id}"><p>Loading…</p></div>'


def fail_analysis_html(
    df: pd.DataFrame, part: str | None = None, source: str = "online"
) -> str:
    """Placeholder div for JS-rendered top fail items table."""
    div_id = f"fail-table-{source}-{part}"
    return f'<div id="{div_id}"><p>Loading…</p></div>'


def build_part_section(
    df: pd.DataFrame, part: str, full_df: pd.DataFrame | None = None
) -> str:
    trend_df = full_df if full_df is not None else df
    color = PART_COLORS.get(part, "#3498db")
    return f"""
    <div class="part-section" id="{part}">
        <h2 style="border-left:5px solid {color}; padding-left:12px;">{part}</h2>
        {summary_html(df, part)}
        <div class="chart-container">{fig_daily_yield(trend_df, part)}</div>
        <div class="chart-container">{fig_sfr_trend(trend_df, part)}</div>
        <div class="chart-container">{fig_sfr_box(df, part, source="online")}</div>
        <div class="chart-container">{fig_roi_box(df, part, source="online")}</div>
        <div class="chart-container">{fig_sfr_dev_roi(df, part, source="online")}</div>
        <div class="chart-container">{fig_sfr_dev_trend(trend_df, part)}</div>
        <h3>SFR Statistics — {part}</h3>
        {stats_table_html(df, part, source="online")}
        <h3>Top Fail Items — {part}</h3>
        {fail_analysis_html(df, part, source="online")}
    </div>"""


def build_audit_part_section(
    df: pd.DataFrame, part: str, full_df: pd.DataFrame | None = None
) -> str:
    """Build a per-part section for audit data (yield + SFR trends only)."""
    trend_df = full_df if full_df is not None else df
    color = PART_COLORS.get(part, "#3498db")
    return f"""
    <div class="part-subsection">
        <h3 style="border-left:4px solid {color}; padding-left:10px;">{part} — Audit</h3>
        {summary_html(df, part)}
        <div class="chart-container">{fig_daily_yield(trend_df, part)}</div>
        <div class="chart-container">{fig_sfr_trend(trend_df, part)}</div>
        <div class="chart-container">{fig_sfr_box(df, part, source="audit")}</div>
    </div>"""


def build_audit_section(
    audit_df: pd.DataFrame, full_audit_df: pd.DataFrame | None = None
) -> str:
    """Build the full Audit SFR section."""
    if audit_df.empty:
        return ""

    trend_audit = full_audit_df if full_audit_df is not None else audit_df

    parts_html = ""
    for part_name in SLOT_MAP.values():
        part_df = audit_df[audit_df["Part"] == part_name]
        if part_df.empty:
            continue
        full_part_df = (
            trend_audit[trend_audit["Part"] == part_name]
            if not trend_audit.empty
            else None
        )
        parts_html += build_audit_part_section(part_df, part_name, full_df=full_part_df)

    if not parts_html:
        return ""

    overlay = fig_daily_yield_overlay(trend_audit)

    return f"""
    <div class="part-section" id="audit">
        <h2 style="border-left:5px solid #e74c3c; padding-left:12px;">🔍 Audit SFR Trend</h2>
        <div class="chart-container">{overlay}</div>
        {parts_html}
    </div>"""


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------


def build_report(
    df: pd.DataFrame,
    audit_df: pd.DataFrame | None = None,
    full_df: pd.DataFrame | None = None,
    full_audit_df: pd.DataFrame | None = None,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    trend_df = full_df if full_df is not None else df
    trend_audit = full_audit_df if full_audit_df is not None else audit_df

    # Per-part sections
    part_sections = ""
    for slot_id, part_name in SLOT_MAP.items():
        part_df = df[df["Part"] == part_name]
        if part_df.empty:
            continue
        full_part_df = (
            trend_df[trend_df["Part"] == part_name] if not trend_df.empty else None
        )
        part_sections += build_part_section(part_df, part_name, full_df=full_part_df)

    # Audit section
    audit_section = ""
    if audit_df is not None and not audit_df.empty:
        audit_section = build_audit_section(audit_df, full_audit_df=trend_audit)

    # Navigation links
    nav_links = " ".join(
        f'<a href="#{p}" class="nav-link" style="border-color:{PART_COLORS[p]}">{p}</a>'
        for p in SLOT_MAP.values()
    )
    audit_nav = ""
    if audit_section:
        audit_nav = (
            '<a href="#audit" class="nav-link" style="border-color:#e74c3c">Audit</a>'
        )

    # Date range for picker
    all_dates: list[str] = []
    if not df.empty:
        all_dates += [str(df["Date"].min()), str(df["Date"].max())]
    if audit_df is not None and not audit_df.empty:
        all_dates += [str(audit_df["Date"].min()), str(audit_df["Date"].max())]
    date_min = min(all_dates) if all_dates else ""
    date_max = max(all_dates) if all_dates else ""

    # Embed data & config for JS charts
    online_json = _embed_chart_data(df)
    audit_json = _embed_chart_data(audit_df if audit_df is not None else pd.DataFrame())
    sfr_groups_json = json.dumps(SFR_GROUPS)
    roi_groups_json = json.dumps(ROI_GROUPS)
    roi_dev_groups_json = json.dumps(ROI_DEV_GROUPS)
    part_colors_json = json.dumps(PART_COLORS)
    parts_json = json.dumps(list(SLOT_MAP.values()))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SFR Report — Loma CW_1_01</title>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
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

<h1>📊 SFR Report — Loma CW_1_01 ONLINE</h1>
<div class="nav">
    <span style="color:#7f8c8d;font-size:0.9em;">Jump to:</span>
    <a href="#overview" class="nav-link" style="border-color:#2c3e50">Comparison</a>
    {nav_links}
    {audit_nav}
</div>

<div class="date-filter">
    <label>📅 Date Range:</label>
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
    <div class="chart-container">{fig_daily_yield_overlay(trend_df)}</div>

    <h2>SFR Comparison by Part — VIS 25cm</h2>
    <div class="chart-container">{fig_sfr_comparison(df, source="online")}</div>
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
const ROI_DEV_GROUPS = {roi_dev_groups_json};
const PART_COLORS = {part_colors_json};
const PARTS = {parts_json};

function filterByDate(data, start, end) {{
    return data.filter(function(r) {{
        return (!start || r.Date >= start) && (!end || r.Date <= end);
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
    if (source === 'online') {{
        var el = document.getElementById('chart-sfr-comparison-online');
        if (el) renderSfrComparison(data, 'chart-sfr-comparison-online');
    }}
    PARTS.forEach(function(part) {{
        var pd = data.filter(function(r) {{ return r.Part === part; }});
        if (!pd.length) return;
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
        help="Show all data (default: latest day only)",
    )
    args = parser.parse_args()

    print(f"Loading data from {args.db} …")
    full_df = load_data(Path(args.db), args.days)
    print(f"Loaded {len(full_df)} records (ONLINE)")

    full_audit_df = load_data(Path(args.db), args.days, table=AUDIT_TABLE)
    print(f"Loaded {len(full_audit_df)} records (Audit)")

    # Default: filter to latest day in DB (unless --days or --all given)
    # Trend plots always use the full (unfiltered) data.
    df = full_df
    audit_df = full_audit_df
    if args.days is None and not args.show_all:
        latest = None
        if not full_df.empty:
            latest = full_df["Date"].max()
        if not full_audit_df.empty:
            audit_latest = full_audit_df["Date"].max()
            latest = max(latest, audit_latest) if latest else audit_latest
        if latest is not None:
            df = full_df[full_df["Date"] == latest]
            audit_df = (
                full_audit_df[full_audit_df["Date"] == latest]
                if not full_audit_df.empty
                else full_audit_df
            )
            print(f"Filtered to latest day: {latest}  (use --all for full history)")

    for part in SLOT_MAP.values():
        cnt = (df["Part"] == part).sum()
        print(f"  {part}: {cnt} rows")

    for part in SLOT_MAP.values():
        cnt = (audit_df["Part"] == part).sum() if not audit_df.empty else 0
        print(f"  {part} (audit): {cnt} rows")

    print("Building report …")
    html = build_report(df, audit_df, full_df=full_df, full_audit_df=full_audit_df)

    output = Path(args.output)
    output.write_text(html)
    print(f"Report saved: {output.resolve()}")


if __name__ == "__main__":
    main()
