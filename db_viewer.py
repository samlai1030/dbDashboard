"""
db_viewer.py — Generate an interactive HTML viewer for data.db.

Features:
    • Table list sidebar with row/column counts
    • Click a table to view its data in a searchable, sortable grid
    • Column filter & search
    • SQL query box for custom queries
    • Schema viewer
    • Image links via Google Drive (image_id_map.json or live GDrive listing)
    • Pagination with 100 rows per page by default
    • Date range selector for filtering by Time column

Usage:
    SlotID 1 = "DTC_R"                      # generate viewer
    python db_viewer.py -o my_viewer.html    # custom output name
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

from app_config import cfg

DB_PATH = cfg.db_file


def _get_tables(conn: sqlite3.Connection) -> list[dict]:
    tables = []
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    for (name,) in cur.fetchall():
        rows = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        cols_info = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
        tables.append(
            {
                "name": name,
                "rows": rows,
                "columns": [{"name": c[1], "type": c[2]} for c in cols_info],
            }
        )
    return tables


def _get_table_data(
    conn: sqlite3.Connection, table: str, limit: int = 5000
) -> list[dict]:
    df = pd.read_sql_query(f'SELECT * FROM "{table}" LIMIT {limit}', conn)
    df = df.fillna("")
    return df.to_dict(orient="records")


def _load_image_id_map(output_folder: Path) -> dict:
    """Load the image filename → Google Drive file ID mapping."""
    map_file = output_folder / "image_id_map.json"
    if map_file.exists():
        with open(map_file) as f:
            return json.load(f)
    return {}


def _build_image_id_map_from_gdrive(output_folder: Path) -> dict:
    """Build image_id_map.json by listing images from GDrive images folder.

    Uses the images_folder_id from the config JSON (if present).
    """
    config_path = Path(__file__).parent / "config" / f"{cfg.config_name}.json"
    if not config_path.exists():
        return {}

    config_data = json.loads(config_path.read_text())
    images_folder_id = config_data.get("gdrive", {}).get("images_folder_id")
    if not images_folder_id:
        return {}

    print(f"  Building image_id_map from GDrive folder {images_folder_id} …")

    all_files: list[dict] = []
    page_token = None

    for _ in range(50):  # max 50 pages × 1000 = 50k files
        params: dict = {
            "q": f'"{images_folder_id}" in parents and trashed = false',
            "fields": "files(id,name),nextPageToken",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token

        result = subprocess.run(
            ["gws", "drive", "files", "list", "--params", json.dumps(params)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  ⚠ GDrive listing failed: {result.stderr.strip()}")
            break

        data = json.loads(result.stdout)
        all_files.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    if not all_files:
        return {}

    id_map = {f["name"]: f["id"] for f in all_files}

    # Save for future use
    map_file = output_folder / "image_id_map.json"
    map_file.write_text(json.dumps(id_map))
    print(f"  ✓ image_id_map.json saved ({len(id_map)} images)")

    return id_map


def build_html(db_path: Path) -> str:
    conn = sqlite3.connect(str(db_path))
    tables = _get_tables(conn)

    # Pre-load ALL data for all tables (increased from 500 to 5000)
    all_data = {}
    for t in tables:
        all_data[t["name"]] = _get_table_data(conn, t["name"], limit=5000)
    conn.close()

    # Load Google Drive image ID mapping — try local file first, then GDrive
    output_folder = db_path.parent
    image_id_map = _load_image_id_map(output_folder)
    if not image_id_map:
        image_id_map = _build_image_id_map_from_gdrive(output_folder)
    image_id_map_json = json.dumps(image_id_map)

    tables_json = json.dumps(tables)
    data_json = json.dumps(all_data)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    db_name = db_path.name

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>DB Viewer — {db_name}</title>
<style>
:root {{
    --bg: #f0f2f5; --sidebar-bg: #1e2a3a; --sidebar-text: #cbd5e1;
    --card-bg: #ffffff; --accent: #3b82f6; --accent-hover: #2563eb;
    --text: #1e293b; --text-muted: #64748b; --border: #e2e8f0;
    --success: #22c55e; --warning: #f59e0b;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       display: flex; height: 100vh; background: var(--bg); color: var(--text); }}

/* Sidebar */
.sidebar {{ width: 280px; min-width: 280px; background: var(--sidebar-bg); color: var(--sidebar-text);
            display: flex; flex-direction: column; overflow: hidden; }}
.sidebar-header {{ padding: 20px; border-bottom: 1px solid rgba(255,255,255,0.1); }}
.sidebar-header h2 {{ color: white; font-size: 1.1em; }}
.sidebar-header .db-name {{ font-size: 0.8em; color: var(--sidebar-text); margin-top: 4px; }}
.table-list {{ flex: 1; overflow-y: auto; padding: 8px; }}
.table-item {{ padding: 10px 12px; border-radius: 8px; cursor: pointer; margin-bottom: 4px;
               transition: background 0.15s; }}
.table-item:hover {{ background: rgba(255,255,255,0.08); }}
.table-item.active {{ background: var(--accent); color: white; }}
.table-item .tname {{ font-weight: 600; font-size: 0.9em; word-break: break-all; }}
.table-item .tmeta {{ font-size: 0.75em; margin-top: 3px; opacity: 0.7; }}

/* Main */
.main {{ flex: 1; display: flex; flex-direction: column; overflow: hidden; }}

/* Toolbar */
.toolbar {{ padding: 12px 20px; background: var(--card-bg); border-bottom: 1px solid var(--border);
            display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
.toolbar input[type=text], .toolbar input[type=date] {{
    padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px;
    font-size: 0.9em; outline: none; }}
.toolbar input[type=text]:focus, .toolbar input[type=date]:focus {{
    border-color: var(--accent); box-shadow: 0 0 0 2px rgba(59,130,246,0.2); }}
#searchBox {{ width: 250px; }}
#sqlBox {{ flex: 1; min-width: 300px; font-family: 'SF Mono', 'Menlo', monospace; font-size: 0.85em; }}
.btn {{ padding: 8px 16px; border: none; border-radius: 6px; font-size: 0.85em;
        cursor: pointer; font-weight: 600; transition: background 0.15s; }}
.btn-primary {{ background: var(--accent); color: white; }}
.btn-primary:hover {{ background: var(--accent-hover); }}
.btn-outline {{ background: transparent; border: 1px solid var(--border); color: var(--text); }}
.btn-outline:hover {{ background: var(--bg); }}
.btn-sm {{ padding: 5px 10px; font-size: 0.8em; }}
.tab-group {{ display: flex; gap: 4px; }}
.tab {{ padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border); background: transparent;
        cursor: pointer; font-size: 0.85em; color: var(--text-muted); }}
.tab.active {{ background: var(--accent); color: white; border-color: var(--accent); }}

/* Range selector */
.range-selector {{ display: flex; align-items: center; gap: 6px; font-size: 0.85em; color: var(--text-muted); }}
.range-selector label {{ white-space: nowrap; font-weight: 500; }}

/* Info bar */
.info-bar {{ padding: 8px 20px; background: var(--bg); font-size: 0.8em; color: var(--text-muted);
             border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; }}

/* Table view */
.table-wrap {{ flex: 1; overflow: auto; padding: 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.82em; }}
thead {{ position: sticky; top: 0; z-index: 10; }}
th {{ background: #f8fafc; padding: 8px 10px; text-align: left; border-bottom: 2px solid var(--border);
      font-weight: 600; color: var(--text-muted); font-size: 0.85em; white-space: nowrap; cursor: pointer;
      user-select: none; }}
th:hover {{ background: #eef2f7; }}
th .sort-arrow {{ margin-left: 4px; font-size: 0.7em; }}
td {{ padding: 6px 10px; border-bottom: 1px solid var(--border); white-space: nowrap;
      max-width: 250px; overflow: hidden; text-overflow: ellipsis; }}
tr:hover {{ background: #f8fafc; }}
tr.highlight td {{ background: #fef3c7; }}

/* Pagination */
.pagination {{ padding: 10px 20px; background: var(--card-bg); border-top: 1px solid var(--border);
               display: flex; align-items: center; justify-content: center; gap: 8px; flex-wrap: wrap; }}
.pagination button {{ padding: 5px 12px; border: 1px solid var(--border); border-radius: 4px;
                      background: white; cursor: pointer; font-size: 0.82em; }}
.pagination button:hover {{ background: var(--bg); }}
.pagination button.active {{ background: var(--accent); color: white; border-color: var(--accent); }}
.pagination button:disabled {{ opacity: 0.4; cursor: default; }}
.pagination .page-info {{ font-size: 0.82em; color: var(--text-muted); }}
.page-size-select {{ padding: 4px 8px; border: 1px solid var(--border); border-radius: 4px;
                     font-size: 0.82em; outline: none; }}

/* Schema view */
.schema-wrap {{ flex: 1; overflow: auto; padding: 20px; }}
.schema-table {{ width: 100%; max-width: 700px; }}
.schema-table th {{ background: var(--sidebar-bg); color: white; }}
.schema-table td {{ font-family: 'SF Mono', 'Menlo', monospace; font-size: 0.85em; }}

/* SQL results */
#sqlResults {{ padding: 10px 20px; font-size: 0.8em; color: var(--text-muted); }}

.generated {{ padding: 10px 20px; font-size: 0.75em; color: var(--text-muted); text-align: right;
              border-top: 1px solid var(--border); }}

.img-link {{ color: var(--accent); text-decoration: none; font-size: 1.1em; }}
.img-link:hover {{ color: var(--accent-hover); }}
</style>
</head>
<body>

<div class="sidebar">
    <div class="sidebar-header">
        <h2>DB Viewer</h2>
        <div class="db-name">{db_name}</div>
    </div>
    <div class="table-list" id="tableList"></div>
</div>

<div class="main">
    <div class="toolbar">
        <div class="tab-group">
            <button class="tab active" onclick="setView('data')">Data</button>
            <button class="tab" onclick="setView('schema')">Schema</button>
            <button class="tab" onclick="setView('sql')">SQL</button>
        </div>
        <input type="text" id="searchBox" placeholder="Search rows…" oninput="applyFilters()">
        <div class="range-selector" id="rangeSelector">
            <label>From:</label>
            <input type="date" id="dateFrom" onchange="applyFilters()">
            <label>To:</label>
            <input type="date" id="dateTo" onchange="applyFilters()">
            <button class="btn btn-sm btn-outline" onclick="clearDateRange()">Clear</button>
        </div>
        <input type="text" id="sqlBox" placeholder="SELECT * FROM sfr_data WHERE TestResult='FAIL' LIMIT 50" style="display:none">
        <button class="btn btn-primary" id="sqlRunBtn" onclick="runSQL()" style="display:none">Run</button>
    </div>
    <div class="info-bar" id="infoBar">Select a table from the sidebar</div>

    <div class="table-wrap" id="dataView"></div>
    <div class="schema-wrap" id="schemaView" style="display:none"></div>
    <div id="sqlResults" style="display:none"></div>

    <div class="pagination" id="pagination" style="display:none"></div>

    <div class="generated">Generated: {now}</div>
</div>

<script>
const TABLES = {tables_json};
const DATA = {data_json};
const IMG_ID_MAP = {image_id_map_json};

let currentTable = null;
let currentView = 'data';
let sortCol = null;
let sortAsc = true;
let currentPage = 1;
let pageSize = 100;
let filteredRows = [];

// Sidebar
function renderSidebar() {{
    const list = document.getElementById('tableList');
    list.innerHTML = TABLES.map(t => `
        <div class="table-item ${{currentTable === t.name ? 'active' : ''}}"
             onclick="selectTable('${{t.name.replace(/'/g, "\\\\'")}}')">
            <div class="tname">${{t.name}}</div>
            <div class="tmeta">${{t.rows.toLocaleString()}} rows · ${{t.columns.length}} cols</div>
        </div>
    `).join('');
}}

function selectTable(name) {{
    currentTable = name;
    sortCol = null;
    sortAsc = true;
    currentPage = 1;
    document.getElementById('searchBox').value = '';
    document.getElementById('dateFrom').value = '';
    document.getElementById('dateTo').value = '';
    renderSidebar();
    updateDateRangeVisibility();
    renderView();
}}

// Check if current table has a Time column
function hasTimeColumn() {{
    if (!currentTable) return false;
    const table = TABLES.find(t => t.name === currentTable);
    return table && table.columns.some(c => c.name === 'Time');
}}

function updateDateRangeVisibility() {{
    const rs = document.getElementById('rangeSelector');
    rs.style.display = hasTimeColumn() ? 'flex' : 'none';
}}

// Views
function setView(view) {{
    currentView = view;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab')[['data','schema','sql'].indexOf(view)].classList.add('active');

    document.getElementById('dataView').style.display = view === 'data' ? '' : 'none';
    document.getElementById('schemaView').style.display = view === 'schema' ? '' : 'none';
    document.getElementById('sqlResults').style.display = view === 'sql' ? '' : 'none';
    document.getElementById('searchBox').style.display = view === 'data' ? '' : 'none';
    document.getElementById('rangeSelector').style.display = (view === 'data' && hasTimeColumn()) ? 'flex' : 'none';
    document.getElementById('sqlBox').style.display = view === 'sql' ? '' : 'none';
    document.getElementById('sqlRunBtn').style.display = view === 'sql' ? '' : 'none';
    document.getElementById('pagination').style.display = view === 'data' ? '' : 'none';

    renderView();
}}

function renderView() {{
    if (currentView === 'data') renderData();
    else if (currentView === 'schema') renderSchema();
}}

// Parse time string to Date for comparison
function parseTime(val) {{
    if (!val || typeof val !== 'string') return null;
    // Format: "2026-03-09 22:44:26+08:00"
    try {{
        return new Date(val);
    }} catch(e) {{
        return null;
    }}
}}

// Apply filters (search + date range)
function applyFilters() {{
    currentPage = 1;
    renderData();
}}

function clearDateRange() {{
    document.getElementById('dateFrom').value = '';
    document.getElementById('dateTo').value = '';
    applyFilters();
}}

// Data view with pagination
function renderData() {{
    if (!currentTable) {{
        document.getElementById('dataView').innerHTML = '<p style="padding:40px;color:#94a3b8;">Select a table from the sidebar.</p>';
        document.getElementById('infoBar').textContent = 'Select a table from the sidebar';
        document.getElementById('pagination').style.display = 'none';
        return;
    }}

    const table = TABLES.find(t => t.name === currentTable);
    let rows = DATA[currentTable] || [];
    const search = document.getElementById('searchBox').value.toLowerCase();
    const dateFrom = document.getElementById('dateFrom').value;
    const dateTo = document.getElementById('dateTo').value;

    // Apply search filter
    if (search) {{
        rows = rows.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(search)));
    }}

    // Apply date range filter
    if ((dateFrom || dateTo) && hasTimeColumn()) {{
        const fromDate = dateFrom ? new Date(dateFrom + 'T00:00:00') : null;
        const toDate = dateTo ? new Date(dateTo + 'T23:59:59') : null;
        rows = rows.filter(r => {{
            const t = parseTime(r['Time']);
            if (!t) return false;
            if (fromDate && t < fromDate) return false;
            if (toDate && t > toDate) return false;
            return true;
        }});
    }}

    // Apply sort
    if (sortCol !== null) {{
        rows = [...rows].sort((a, b) => {{
            let va = a[sortCol] ?? '', vb = b[sortCol] ?? '';
            const na = parseFloat(va), nb = parseFloat(vb);
            if (!isNaN(na) && !isNaN(nb)) {{ va = na; vb = nb; }}
            if (va < vb) return sortAsc ? -1 : 1;
            if (va > vb) return sortAsc ? 1 : -1;
            return 0;
        }});
    }}

    filteredRows = rows;
    const totalFiltered = rows.length;
    const totalPages = Math.max(1, Math.ceil(totalFiltered / pageSize));
    if (currentPage > totalPages) currentPage = totalPages;

    const startIdx = (currentPage - 1) * pageSize;
    const endIdx = Math.min(startIdx + pageSize, totalFiltered);
    const pageRows = rows.slice(startIdx, endIdx);

    const cols = table.columns.map(c => c.name);
    const totalRows = table.rows;

    let filterDesc = '';
    if (search) filterDesc += ` · search "${{search}}"`;
    if (dateFrom || dateTo) filterDesc += ` · date ${{dateFrom || '…'}} to ${{dateTo || '…'}}`;

    document.getElementById('infoBar').textContent =
        `${{currentTable}} — showing ${{startIdx + 1}}–${{endIdx}} of ${{totalFiltered}} filtered / ${{totalRows}} total rows${{filterDesc}}`;

    let html = '<table><thead><tr>';
    html += cols.map(c => {{
        let arrow = '';
        if (sortCol === c) arrow = sortAsc ? ' ▲' : ' ▼';
        return `<th onclick="sortBy('${{c.replace(/'/g, "\\\\'")}}')">${{c}}<span class="sort-arrow">${{arrow}}</span></th>`;
    }}).join('');
    html += '</tr></thead><tbody>';

    pageRows.forEach(r => {{
        const isFail = r['TestResult'] === 'FAIL';
        html += `<tr${{isFail ? ' class="highlight"' : ''}}>`;
        cols.forEach(c => {{
            let val = r[c] ?? '';
            if (typeof val === 'number') val = parseFloat(val.toFixed(6));
            if (c.startsWith('img_') && typeof val === 'string' && val.endsWith('.jpg')) {{
                const fname = val.replace('images/', '');
                const fileId = IMG_ID_MAP[fname];
                if (fileId) {{
                    const imgUrl = `https://drive.google.com/file/d/${{fileId}}/view`;
                    html += `<td><a class="img-link" href="${{imgUrl}}" target="_blank" title="${{fname}}">&#128247;</a></td>`;
                }} else {{
                    html += `<td title="${{fname}}" style="color:#94a3b8;">&#128247;</td>`;
                }}
            }} else {{
                html += `<td title="${{String(val).replace(/"/g, '&quot;')}}">${{val}}</td>`;
            }}
        }});
        html += '</tr>';
    }});

    html += '</tbody></table>';
    document.getElementById('dataView').innerHTML = html;

    // Render pagination
    renderPagination(totalFiltered, totalPages);
}}

function renderPagination(totalFiltered, totalPages) {{
    const pag = document.getElementById('pagination');
    if (totalFiltered <= 0) {{
        pag.style.display = 'none';
        return;
    }}
    pag.style.display = 'flex';

    let html = '';

    // Page size selector
    html += `<span class="page-info">Rows/page:</span>
             <select class="page-size-select" onchange="changePageSize(this.value)">
                 <option value="50" ${{pageSize===50?'selected':''}}>50</option>
                 <option value="100" ${{pageSize===100?'selected':''}}>100</option>
                 <option value="200" ${{pageSize===200?'selected':''}}>200</option>
                 <option value="500" ${{pageSize===500?'selected':''}}>500</option>
                 <option value="${{totalFiltered}}" ${{pageSize>=totalFiltered?'selected':''}}>All</option>
             </select>`;

    // Navigation buttons
    html += `<button ${{currentPage <= 1 ? 'disabled' : ''}} onclick="goToPage(1)">&#171; First</button>`;
    html += `<button ${{currentPage <= 1 ? 'disabled' : ''}} onclick="goToPage(${{currentPage-1}})">&#8249; Prev</button>`;

    // Page numbers (show max 7 around current)
    const maxButtons = 7;
    let startPage = Math.max(1, currentPage - Math.floor(maxButtons / 2));
    let endPage = Math.min(totalPages, startPage + maxButtons - 1);
    if (endPage - startPage < maxButtons - 1) startPage = Math.max(1, endPage - maxButtons + 1);

    if (startPage > 1) html += `<span class="page-info">…</span>`;
    for (let p = startPage; p <= endPage; p++) {{
        html += `<button class="${{p === currentPage ? 'active' : ''}}" onclick="goToPage(${{p}})">${{p}}</button>`;
    }}
    if (endPage < totalPages) html += `<span class="page-info">…</span>`;

    html += `<button ${{currentPage >= totalPages ? 'disabled' : ''}} onclick="goToPage(${{currentPage+1}})">Next &#8250;</button>`;
    html += `<button ${{currentPage >= totalPages ? 'disabled' : ''}} onclick="goToPage(${{totalPages}})">Last &#187;</button>`;

    html += `<span class="page-info">Page ${{currentPage}} of ${{totalPages}} (${{totalFiltered}} rows)</span>`;

    pag.innerHTML = html;
}}

function goToPage(page) {{
    currentPage = page;
    renderData();
    document.getElementById('dataView').scrollTop = 0;
}}

function changePageSize(val) {{
    pageSize = parseInt(val);
    currentPage = 1;
    renderData();
}}

function sortBy(col) {{
    if (sortCol === col) sortAsc = !sortAsc;
    else {{ sortCol = col; sortAsc = true; }}
    currentPage = 1;
    renderData();
}}

function filterRows() {{ applyFilters(); }}

// Schema view
function renderSchema() {{
    if (!currentTable) {{
        document.getElementById('schemaView').innerHTML = '<p style="color:#94a3b8;">Select a table.</p>';
        return;
    }}
    const table = TABLES.find(t => t.name === currentTable);
    let html = `<h3 style="margin-bottom:12px;">${{currentTable}} — ${{table.columns.length}} columns</h3>`;
    html += '<table class="schema-table"><thead><tr><th>#</th><th>Column Name</th><th>Type</th></tr></thead><tbody>';
    table.columns.forEach((c, i) => {{
        html += `<tr><td>${{i+1}}</td><td>${{c.name}}</td><td>${{c.type || 'TEXT'}}</td></tr>`;
    }});
    html += '</tbody></table>';
    document.getElementById('schemaView').innerHTML = html;
    document.getElementById('infoBar').textContent = `${{currentTable}} — Schema (${{table.columns.length}} columns)`;
}}

// SQL (client-side note)
function runSQL() {{
    const sql = document.getElementById('sqlBox').value.trim();
    if (!sql) return;
    document.getElementById('sqlResults').innerHTML =
        '<p style="padding:20px;color:#94a3b8;">SQL execution requires a server. ' +
        'Use <code>python db_preview.py --sql "' + sql.replace(/"/g, '&quot;') + '"</code> in terminal.</p>';
}}


// Init
renderSidebar();
if (TABLES.length > 0) selectTable(TABLES[TABLES.length - 1].name);
</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate interactive HTML viewer for data.db"
    )
    parser.add_argument(
        "--db", type=str, default=str(DB_PATH), help="SQLite database path"
    )
    parser.add_argument(
        "-o", "--output", type=str, default=str(cfg.viewer_file), help="Output HTML file"
    )
    args = parser.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"Error: database not found: {db}")
        return

    print(f"Reading {db} …")
    html = build_html(db)

    out = Path(args.output)
    out.write_text(html)
    print(f"Viewer saved: {out.resolve()}")
    print(f"Open with: open {out}")


if __name__ == "__main__":
    main()
