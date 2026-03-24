"""
db_preview.py — Preview tables and data in data.db.

Usage:
    python db_preview.py                        # list all tables with row counts
    python db_preview.py --table <name>         # show first 20 rows of a table
    python db_preview.py --table <name> -n 50   # show first 50 rows
    python db_preview.py --table <name> --all   # show all rows
    python db_preview.py --sql "SELECT ..."     # run custom SQL query
    python db_preview.py --schema               # show schema for all tables
    python db_preview.py --stats                # show column stats for a table
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

from app_config import cfg

DB_PATH = cfg.db_file


def list_tables(conn: sqlite3.Connection) -> None:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = cur.fetchall()
    if not tables:
        print("No tables in database.")
        return

    print(f"\n{'Table':<60s} {'Rows':>8s}  {'Columns':>8s}")
    print("-" * 80)
    for (name,) in tables:
        row_cnt = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        col_cnt = len(conn.execute(f'PRAGMA table_info("{name}")').fetchall())
        print(f"{name:<60s} {row_cnt:>8d}  {col_cnt:>8d}")
    print(f"\nTotal: {len(tables)} tables\n")


def show_schema(conn: sqlite3.Connection, table: str | None = None) -> None:
    if table:
        tables = [(table,)]
    else:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

    for (name,) in tables:
        cols = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
        print(f"\n── {name} ({len(cols)} columns) ──")
        for _, col_name, col_type, *_ in cols:
            print(f"  {col_name:<50s} {col_type}")


def show_table(conn: sqlite3.Connection, table: str, n: int | None) -> None:
    query = f'SELECT * FROM "{table}"'
    if n is not None:
        query += f" LIMIT {n}"

    df = pd.read_sql_query(query, conn)
    total = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    showing = len(df)

    print(f"\n── {table}  ({showing}/{total} rows, {len(df.columns)} columns) ──\n")

    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 30)
    print(df.to_string(index=False))
    print()


def show_stats(conn: sqlite3.Connection, table: str) -> None:
    df = pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
    print(f"\n── {table}  Stats ({len(df)} rows, {len(df.columns)} columns) ──\n")

    # Convert numeric columns
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="ignore")

    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        print("Numeric columns:")
        pd.set_option("display.max_columns", 10)
        pd.set_option("display.width", 200)
        print(numeric.describe().round(4).to_string())
    else:
        print("No numeric columns found.")

    non_numeric = df.select_dtypes(exclude="number")
    if not non_numeric.empty:
        print("\nText columns:")
        print(non_numeric.describe().to_string())
    print()


def run_sql(conn: sqlite3.Connection, query: str) -> None:
    try:
        df = pd.read_sql_query(query, conn)
        pd.set_option("display.max_columns", 20)
        pd.set_option("display.width", 200)
        pd.set_option("display.max_colwidth", 30)
        print(f"\n({len(df)} rows)\n")
        print(df.to_string(index=False))
        print()
    except Exception as e:
        print(f"SQL Error: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview data.db tables and data")
    parser.add_argument(
        "--db", type=str, default=str(DB_PATH), help="SQLite database path"
    )
    parser.add_argument(
        "--table", "-t", type=str, default=None, help="Table name to preview"
    )
    parser.add_argument(
        "-n", type=int, default=20, help="Number of rows to show (default: 20)"
    )
    parser.add_argument("--all", action="store_true", help="Show all rows")
    parser.add_argument("--schema", action="store_true", help="Show table schema")
    parser.add_argument("--stats", action="store_true", help="Show column statistics")
    parser.add_argument("--sql", type=str, default=None, help="Run custom SQL query")
    args = parser.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"Error: database not found: {db}")
        return

    conn = sqlite3.connect(str(db))

    if args.sql:
        run_sql(conn, args.sql)
    elif args.schema:
        show_schema(conn, args.table)
    elif args.stats and args.table:
        show_stats(conn, args.table)
    elif args.table:
        show_table(conn, args.table, None if args.all else args.n)
    else:
        list_tables(conn)

    conn.close()


if __name__ == "__main__":
    main()
