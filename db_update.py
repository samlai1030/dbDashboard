"""
db_update.py — Sync files from datasets/ into a single sfr_data table in data.db.

• All files merge into ONE table (sfr_data) — no per-file tables.
• Deduplicates by TSRID — each test record is stored only once.
• Tracks imported files in _import_log to skip already-processed files.

Usage:
    python db_update.py              # import new files only
    python db_update.py --dry-run    # preview what would be imported
    python db_update.py --rebuild    # drop everything & re-import from scratch
    python db_update.py --status     # show import log & row counts
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app_config import cfg

DATASETS_FOLDER = cfg.datasets
DB_PATH = cfg.db_file

TABLE_NAME = "sfr_data"
LOG_TABLE = "_import_log"
DATA_EXTENSIONS = cfg.data_extensions
SKIP_PREFIXES = ("Lower Limit", "Upper Limit", "Unit")
UNIQUE_KEY = "TSRID"


def _read_file(filepath: Path) -> pd.DataFrame:
    """Read a CSV/XLS/XLSX, dropping metadata rows."""
    ext = filepath.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(filepath, dtype=str)
    else:
        df = pd.read_excel(filepath, dtype=str)

    first_col = df.columns[0]
    mask = df[first_col].apply(
        lambda v: isinstance(v, str) and v.startswith(SKIP_PREFIXES)
    )
    df = df[~mask].reset_index(drop=True)
    return df


def _init_log_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS "{LOG_TABLE}" (
            filename    TEXT PRIMARY KEY,
            rows_added  INTEGER,
            rows_skipped INTEGER,
            imported_at TEXT
        )
    """
    )
    conn.commit()


def _imported_files(conn: sqlite3.Connection) -> set[str]:
    _init_log_table(conn)
    cur = conn.execute(f'SELECT filename FROM "{LOG_TABLE}"')
    return {r[0] for r in cur.fetchall()}


def _existing_tsrids(conn: sqlite3.Connection) -> set[str]:
    try:
        cur = conn.execute(f'SELECT "{UNIQUE_KEY}" FROM "{TABLE_NAME}"')
        return {r[0] for r in cur.fetchall()}
    except sqlite3.OperationalError:
        return set()


def _existing_columns(conn: sqlite3.Connection) -> set[str]:
    """Return set of column names in sfr_data, or empty set if table doesn't exist."""
    try:
        cur = conn.execute(f'PRAGMA table_info("{TABLE_NAME}")')
        return {row[1] for row in cur.fetchall()}
    except sqlite3.OperationalError:
        return set()


def _add_missing_columns(conn: sqlite3.Connection, df_columns: list[str]) -> None:
    """ALTER TABLE to add any columns in the DataFrame that don't exist in the table yet."""
    existing = _existing_columns(conn)
    if not existing:
        return  # table doesn't exist yet, to_sql will create it

    added = []
    for col in df_columns:
        if col not in existing:
            conn.execute(f'ALTER TABLE "{TABLE_NAME}" ADD COLUMN "{col}" TEXT')
            added.append(col)
    if added:
        conn.commit()
        print(f"    [schema] Added {len(added)} new columns: {', '.join(added[:5])}{'...' if len(added) > 5 else ''}")


def sync_datasets(
    datasets_dir: Path,
    db_path: Path,
    *,
    dry_run: bool = False,
    rebuild: bool = False,
) -> None:
    files = sorted(
        f
        for f in datasets_dir.iterdir()
        if f.is_file() and f.suffix.lower() in DATA_EXTENSIONS
    )

    if not files:
        print("No data files found in datasets/")
        return

    conn = sqlite3.connect(str(db_path))

    if rebuild:
        if not dry_run:
            conn.execute(f'DROP TABLE IF EXISTS "{TABLE_NAME}"')
            conn.execute(f'DROP TABLE IF EXISTS "{LOG_TABLE}"')
            conn.commit()
            print("Dropped existing tables.\n")
        else:
            print("[DRY] Would drop existing tables.\n")

    _init_log_table(conn)
    already_imported = _imported_files(conn) if not rebuild else set()
    known_tsrids = _existing_tsrids(conn)

    total_added, total_skipped, total_dup, file_processed, file_skipped, errors = (
        0,
        0,
        0,
        0,
        0,
        0,
    )

    for filepath in files:
        fname = filepath.name

        if fname in already_imported:
            file_skipped += 1
            continue

        try:
            df = _read_file(filepath)
        except Exception as e:
            print(f"  ✗ READ ERROR  {fname}  ({e})")
            errors += 1
            continue

        if UNIQUE_KEY not in df.columns:
            print(f"  ⚠ SKIP  {fname}  (no {UNIQUE_KEY} column)")
            file_skipped += 1
            continue

        # Filter out rows whose TSRID already exists in db
        new_mask = ~df[UNIQUE_KEY].isin(known_tsrids)
        new_df = df[new_mask]
        dup_count = len(df) - len(new_df)

        if dry_run:
            print(
                f"  [DRY] {fname}  → {len(new_df)} new, {dup_count} duplicates skipped"
            )
        else:
            if not new_df.empty:
                table_cols = _existing_columns(conn)
                if not table_cols:
                    # Table doesn't exist yet, create it with all columns from this CSV
                    new_df.to_sql(TABLE_NAME, conn, if_exists="append", index=False)
                else:
                    # Add any new columns and insert
                    _add_missing_columns(conn, new_df.columns.tolist())
                    # Re-read table columns after adding missing ones
                    table_cols = _existing_columns(conn)
                    # Only insert columns that exist in both DataFrame and table
                    common_cols = [c for c in new_df.columns if c in table_cols]
                    new_df[common_cols].to_sql(TABLE_NAME, conn, if_exists="append", index=False)
                known_tsrids.update(new_df[UNIQUE_KEY].tolist())

            conn.execute(
                f'INSERT OR REPLACE INTO "{LOG_TABLE}" VALUES (?, ?, ?, ?)',
                (fname, len(new_df), dup_count, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            print(f"  ✓ {fname}  → {len(new_df)} added, {dup_count} duplicates skipped")

        total_added += len(new_df)
        total_dup += dup_count
        file_processed += 1

    conn.close()

    print(f"\nDone: {file_processed} files processed, {file_skipped} skipped")
    print(f"Rows: {total_added} added, {total_dup} duplicates prevented")
    print(f"Database: {db_path}")


def show_status(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))

    try:
        total = conn.execute(f'SELECT COUNT(*) FROM "{TABLE_NAME}"').fetchone()[0]
    except sqlite3.OperationalError:
        total = 0

    print(f"\n  sfr_data: {total} rows")

    try:
        logs = conn.execute(
            f'SELECT filename, rows_added, rows_skipped, imported_at FROM "{LOG_TABLE}" ORDER BY imported_at'
        ).fetchall()
    except sqlite3.OperationalError:
        logs = []

    if logs:
        print(f"\n  {'File':<65s} {'Added':>6s} {'Dups':>6s}  Imported")
        print("  " + "-" * 110)
        for fname, added, skipped, ts in logs:
            print(f"  {fname:<65s} {added:>6d} {skipped:>6d}  {ts}")
    else:
        print("  No import history.")

    print()
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync datasets/ into sfr_data table in data.db"
    )
    parser.add_argument(
        "--src", type=str, default=str(DATASETS_FOLDER), help="Datasets folder"
    )
    parser.add_argument(
        "--db", type=str, default=str(DB_PATH), help="SQLite database path"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing to db"
    )
    parser.add_argument(
        "--rebuild", action="store_true", help="Drop & re-import everything"
    )
    parser.add_argument(
        "--status", action="store_true", help="Show import log & row counts"
    )
    args = parser.parse_args()

    db = Path(args.db)

    if args.status:
        show_status(db)
        return

    src = Path(args.src)
    if not src.exists():
        print(f"Error: datasets folder not found: {src}")
        return

    print(f"Scanning: {src}")
    print(f"Database: {db}")
    if args.dry_run:
        print("[DRY RUN]")
    if args.rebuild:
        print("[REBUILD — dropping all data first]")
    print()

    sync_datasets(src, db, dry_run=args.dry_run, rebuild=args.rebuild)


if __name__ == "__main__":
    main()
